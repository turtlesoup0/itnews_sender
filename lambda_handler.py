"""
AWS Lambda 핸들러
EventBridge에서 트리거되어 IT뉴스 PDF 다운로드 및 전송
"""
import logging
import os
import json
import time
import re
from datetime import datetime, timezone, timedelta

from src.scraper import download_pdf_sync
from src.pdf_processor import process_pdf
from src.email_sender import send_pdf_bulk_email
from src.icloud_uploader import upload_to_icloud
from src.structured_logging import get_structured_logger
from src.delivery_tracker import DeliveryTracker
from src.failure_tracker import FailureTracker
from src.execution_tracker import ExecutionTracker
from src.itfind_scraper import ItfindScraper

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)


def is_wednesday() -> bool:
    """
    오늘이 수요일인지 확인 (KST 기준)

    Returns:
        bool: 수요일이면 True
    """
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    return now_kst.weekday() == 2  # 0=월요일, 2=수요일


def sanitize_error(error_msg: str) -> str:
    """
    오류 메시지에서 민감정보 필터링

    비밀번호, 토큰, API 키 등 민감정보를 [REDACTED]로 대체

    Args:
        error_msg: 원본 오류 메시지

    Returns:
        str: 민감정보가 제거된 오류 메시지
    """
    patterns = [
        (r'(password|passwd|pwd)=[^&\s]*', 'password=[REDACTED]'),
        (r'(token|secret|key|apikey|api_key)=[^&\s]*', 'token=[REDACTED]'),
        (r'Authorization:\s*[^\s]+', 'Authorization: [REDACTED]'),
        (r'Bearer\s+[^\s]+', 'Bearer [REDACTED]'),
        (r'"(password|passwd|pwd|token|secret|key)":\s*"[^"]*"', r'"\1": "[REDACTED]"'),
    ]

    sanitized = error_msg
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    return sanitized


def _send_admin_notification(subject: str, message: str):
    """관리자에게 알림 이메일 전송"""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from src.config import Config

        config = Config()
        admin_email = "turtlesoup0@gmail.com"

        msg = MIMEMultipart()
        msg["From"] = config.GMAIL_USER
        msg["To"] = admin_email
        msg["Subject"] = subject

        msg.attach(MIMEText(message, "plain"))

        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
            server.send_message(msg)

        logger.info(f"관리자 알림 전송 완료: {subject}")
    except Exception as e:
        logger.error(f"관리자 알림 전송 실패: {e}")


def handler(event, context):
    """
    Lambda 함수 핸들러

    Args:
        event: Lambda 이벤트 (EventBridge 스케줄)
        context: Lambda 컨텍스트

    Returns:
        dict: 실행 결과
    """
    start_time = time.time()

    logger.info("===== IT뉴스 PDF 전송 작업 시작 =====")

    # 안전한 이벤트 로깅 (민감정보 제외)
    safe_event = {k: v for k, v in event.items() if k in ['mode', 'request_id']}
    logger.info(f"Event (safe): {json.dumps(safe_event)}")

    # 실행 모드 결정 (기본값: test)
    mode = event.get("mode", "test")
    is_test_mode = (mode != "opr")

    # 멱등성 체크 비활성화 옵션 (테스트용)
    skip_idempotency = event.get("skip_idempotency", False)

    if is_test_mode:
        logger.info("🧪 TEST 모드로 실행 (수신인: turtlesoup0@gmail.com)")
    else:
        logger.info("🚀 OPR 모드로 실행 (수신인: DynamoDB 활성 수신인 전체)")

    structured_logger.info(
        event="lambda_start",
        message=f"IT뉴스 PDF 전송 작업 시작 (모드: {mode})",
        function_name=context.function_name if context else "local",
        request_id=context.aws_request_id if context else "local",
        execution_mode=mode
    )

    pdf_path = None
    processed_pdf_path = None

    try:
        # 0. 멱등성 보장: 실행 시작 전 기록 (Conditional Put으로 경쟁 조건 방지)
        if skip_idempotency:
            logger.warning("⚠️  멱등성 체크 비활성화 (skip_idempotency=True) - 테스트 목적으로만 사용")
        else:
            logger.info("0단계: 멱등성 보장 - 실행 이력 선기록")
            exec_tracker = ExecutionTracker()
            request_id = context.aws_request_id if context else "local"

            # 실행 기록 시도 (이미 있으면 ConditionalCheckFailedException 발생)
            if not exec_tracker.mark_execution(mode, request_id):
                # 실패 = 이미 오늘 실행됨
                duration_ms = (time.time() - start_time) * 1000
                logger.warning(f"⚠️  오늘 이미 {mode} 모드로 실행되었습니다. 중복 실행을 방지합니다.")

                structured_logger.info(
                    event="duplicate_execution_prevented",
                    message=f"오늘 이미 {mode} 모드로 실행됨",
                    execution_mode=mode,
                    duration_ms=duration_ms
                )

                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': f'오늘 이미 {mode} 모드로 실행되었습니다 (중복 실행 방지)',
                        'skipped': True,
                        'reason': 'already_executed_today'
                    })
                }

            logger.info(f"✅ 멱등성 보장 완료: 오늘 {mode} 모드 첫 실행 기록됨")

        # DeliveryTracker 초기화 (수신인별 발송 이력 추적용)
        tracker = DeliveryTracker()

        # 1. 실패 제한 체크
        logger.info("1단계: 실패 제한 체크")
        failure_tracker = FailureTracker()

        if failure_tracker.should_skip_today():
            duration_ms = (time.time() - start_time) * 1000
            logger.error("오늘 3회 이상 실패하여 발송을 건너뜁니다")

            # 관리자 알림
            try:
                _send_admin_notification(
                    subject="[etnews-pdf-sender] 발송 실패 알림",
                    message="오늘 3회 이상 PDF 다운로드에 실패하여 발송을 건너뜁니다."
                )
            except Exception as notify_error:
                logger.error(f"관리자 알림 실패: {notify_error}")

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': '오늘 3회 이상 실패하여 발송 건너뜀',
                    'skipped': True,
                    'reason': 'too_many_failures'
                })
            }

        logger.info("✅ 실패 제한 체크 완료: 발송 진행 가능")

        # 2. PDF 다운로드 및 페이지 정보 수집
        logger.info("2단계: 전자신문 PDF 다운로드 시작")
        try:
            pdf_path, page_info = download_pdf_sync()
            logger.info(f"전자신문 PDF 다운로드 완료: {pdf_path}")

            # 성공 시 실패 카운트 리셋
            failure_tracker.reset_today()

        except ValueError as ve:
            # 신문 미발행일 처리
            if "신문이 발행되지 않은 날" in str(ve):
                duration_ms = (time.time() - start_time) * 1000
                logger.info("신문이 발행되지 않은 날입니다. 메일을 전송하지 않습니다.")

                structured_logger.info(
                    event="newspaper_not_published",
                    message="신문 미발행일로 인해 메일 미전송",
                    duration_ms=duration_ms
                )

                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': '신문이 발행되지 않은 날입니다',
                        'skipped': True
                    })
                }
            else:
                # PDF 다운로드 실패 카운트 증가
                count = failure_tracker.increment_failure(str(ve))
                logger.error(f"PDF 다운로드 실패 ({count}회): {ve}")

                # 3회째 실패면 관리자 알림
                if count >= 3:
                    try:
                        sanitized_error = sanitize_error(str(ve))
                        _send_admin_notification(
                            subject="[etnews-pdf-sender] PDF 다운로드 실패 알림",
                            message=f"PDF 다운로드가 3회 연속 실패했습니다.\n\n오류: {sanitized_error}"
                        )
                    except Exception as notify_error:
                        logger.error(f"관리자 알림 실패: {notify_error}")

                raise
        except Exception as e:
            # 기타 다운로드 실패 처리
            count = failure_tracker.increment_failure(str(e))
            logger.error(f"PDF 다운로드 실패 ({count}회): {e}")

            # 3회째 실패면 관리자 알림
            if count >= 3:
                try:
                    sanitized_error = sanitize_error(str(e))
                    _send_admin_notification(
                        subject="[etnews-pdf-sender] PDF 다운로드 실패 알림",
                        message=f"PDF 다운로드가 3회 연속 실패했습니다.\n\n오류: {sanitized_error}"
                    )
                except Exception as notify_error:
                    logger.error(f"관리자 알림 실패: {notify_error}")

            raise

        # 2-1. 수요일이면 ITFIND 주간기술동향도 다운로드
        itfind_pdf_path = None
        itfind_trend_info = None

        # 디버깅: 현재 시각 로깅
        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst)
        now_utc = datetime.now(timezone.utc)
        logger.info(f"현재 시각 - UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}, KST: {now_kst.strftime('%Y-%m-%d %H:%M:%S %Z')}, weekday: {now_kst.weekday()}")

        if is_wednesday():
            logger.info("📅 오늘은 수요일 - ITFIND 주간기술동향 다운로드 시도")
            try:
                # ITFIND Lambda 함수 호출 (별도 Lambda에서 브라우저 없이 다운로드)
                import boto3
                import base64

                lambda_client = boto3.client('lambda')

                logger.info("ITFIND Lambda 함수 호출 중...")
                response = lambda_client.invoke(
                    FunctionName='itfind-pdf-downloader',
                    InvocationType='RequestResponse',  # 동기 호출
                    Payload=json.dumps({})
                )

                result_payload = json.loads(response['Payload'].read())
                logger.info(f"ITFIND Lambda 응답: statusCode={result_payload.get('statusCode')}")

                if result_payload.get('statusCode') == 200 and result_payload['body']['success']:
                    data = result_payload['body']['data']

                    # base64 디코딩하여 /tmp에 저장
                    pdf_base64 = data['pdf_base64']
                    pdf_data = base64.b64decode(pdf_base64)

                    itfind_pdf_path = f"/tmp/{data['filename']}"
                    with open(itfind_pdf_path, 'wb') as f:
                        f.write(pdf_data)

                    logger.info(f"✅ ITFIND PDF 다운로드 성공: {itfind_pdf_path}")
                    logger.info(f"   제목: {data['title']}")
                    logger.info(f"   호수: {data['issue_number']}호")
                    logger.info(f"   크기: {data['file_size']:,} bytes")

                    # itfind_trend_info 객체 생성 (이메일 발송용)
                    from collections import namedtuple
                    WeeklyTrend = namedtuple('WeeklyTrend', ['title', 'issue_number', 'publish_date', 'pdf_url', 'topics', 'detail_id'])
                    itfind_trend_info = WeeklyTrend(
                        title=data['title'],
                        issue_number=data['issue_number'],
                        publish_date=data['publish_date'],
                        pdf_url='',
                        topics=[],
                        detail_id=''
                    )
                else:
                    logger.warning(f"ITFIND Lambda 실패: {result_payload}")
                    itfind_trend_info, itfind_pdf_path = None, None

            except Exception as itfind_error:
                # ITFIND 실패해도 전자신문 발송은 계속
                logger.error(f"ITFIND 다운로드 실패 (무시하고 계속): {itfind_error}")
                structured_logger.warning(
                    event="itfind_download_failed",
                    message="ITFIND 주간기술동향 다운로드 실패",
                    error=str(itfind_error)
                )
                itfind_pdf_path = None
                itfind_trend_info = None
        else:
            logger.info("📅 오늘은 수요일이 아님 - ITFIND 다운로드 건너뛰기")

        # 3. 광고 페이지 제거 (전자신문만)
        logger.info("3단계: 전자신문 광고 페이지 제거 시작")
        processed_pdf_path = process_pdf(pdf_path, page_info)
        logger.info(f"전자신문 PDF 처리 완료: {processed_pdf_path}")

        # 4. 이메일 전송 (모드에 따라 수신인 결정)
        logger.info("4단계: 이메일 전송 시작")
        email_success, success_emails = send_pdf_bulk_email(
            processed_pdf_path,
            test_mode=is_test_mode,
            itfind_pdf_path=itfind_pdf_path,
            itfind_info=itfind_trend_info
        )

        if not email_success:
            logger.error("이메일 전송 실패")
            raise Exception("이메일 전송 실패")

        logger.info(f"이메일 전송 성공: {len(success_emails)}명")

        # 5. 발송 이력 기록 (OPR 모드에만 기록)
        if not is_test_mode:
            logger.info("5단계: 발송 이력 기록 (OPR 모드)")
            tracker.mark_as_delivered(success_emails)
            logger.info("발송 이력 기록 완료")
        else:
            logger.info("5단계: 발송 이력 기록 건너뛰기 (TEST 모드)")

        # 6. iCloud Drive 업로드 (선택사항)
        logger.info("6단계: iCloud Drive 업로드 시작")
        try:
            icloud_success = upload_to_icloud(processed_pdf_path, use_monthly_folder=True)
            if icloud_success:
                logger.info("iCloud Drive 업로드 성공")
            else:
                logger.warning("iCloud Drive 업로드 실패 (계속 진행)")
        except Exception as icloud_error:
            logger.warning(f"iCloud Drive 업로드 중 오류 (계속 진행): {icloud_error}")

        duration_ms = (time.time() - start_time) * 1000

        logger.info("===== IT뉴스 PDF 전송 작업 완료 =====")

        structured_logger.info(
            event="lambda_success",
            message="IT뉴스 PDF 전송 작업 완료",
            duration_ms=duration_ms,
            pdf_path=pdf_path,
            processed_pdf_path=processed_pdf_path
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'IT뉴스 PDF 전송 성공',
                'pdf_path': pdf_path,
                'processed_pdf_path': processed_pdf_path,
                'duration_ms': duration_ms
            })
        }

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000

        logger.error(f"작업 실행 중 오류 발생: {e}", exc_info=True)

        structured_logger.error(
            event="lambda_error",
            message=f"IT뉴스 PDF 전송 작업 실패: {str(e)}",
            duration_ms=duration_ms,
            error=str(e),
            error_type=type(e).__name__
        )

        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'IT뉴스 PDF 전송 실패',
                'error': str(e),
                'error_type': type(e).__name__
            })
        }

    finally:
        # 임시 파일 정리
        cleanup_temp_files(pdf_path, processed_pdf_path, itfind_pdf_path if 'itfind_pdf_path' in locals() else None)


def cleanup_temp_files(*file_paths):
    """임시 파일 정리"""
    logger.info("임시 파일 정리 시작")

    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"파일 삭제: {file_path}")
            except Exception as e:
                logger.warning(f"파일 삭제 실패 ({file_path}): {e}")

    logger.info("임시 파일 정리 완료")
