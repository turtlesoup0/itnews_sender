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

# 워크플로우 모듈
from src.workflow import check_idempotency, check_failure_limit
from src.workflow.pdf_workflow import download_and_process_pdf, download_itfind_pdf
from src.utils.notification import send_admin_notification

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


# 관리자 알림 함수는 src/utils/notification.py로 이동
from src.utils.notification import send_admin_notification as _send_admin_notification


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
        # 0. 멱등성 보장
        request_id = context.aws_request_id if context else "local"
        can_proceed, error_response = check_idempotency(mode, request_id, skip_idempotency)

        if not can_proceed:
            duration_ms = (time.time() - start_time) * 1000
            structured_logger.info(
                event="duplicate_execution_prevented",
                message=f"오늘 이미 {mode} 모드로 실행됨",
                execution_mode=mode,
                duration_ms=duration_ms
            )
            return {
                'statusCode': error_response['statusCode'],
                'body': json.dumps(error_response['body'])
            }

        # DeliveryTracker 초기화 (수신인별 발송 이력 추적용)
        tracker = DeliveryTracker()

        # 1. 실패 제한 체크
        can_proceed, error_response = check_failure_limit()

        if not can_proceed:
            duration_ms = (time.time() - start_time) * 1000
            return {
                'statusCode': error_response['statusCode'],
                'body': json.dumps(error_response['body'])
            }

        # 실패 추적기 초기화
        failure_tracker = FailureTracker()

        # 2. 전자신문 PDF 다운로드 및 처리
        try:
            pdf_path, processed_pdf_path, page_info = download_and_process_pdf(failure_tracker)

        except ValueError as ve:
            # 신문 미발행일 처리
            if "신문이 발행되지 않은 날" in str(ve):
                duration_ms = (time.time() - start_time) * 1000
                logger.info("신문이 발행되지 않은 날입니다")

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
                raise

        except Exception as e:
            # PDF 다운로드 실패 (워크플로우에서 이미 알림 처리됨)
            raise

        # 2-1. 수요일이면 ITFIND 주간기술동향 다운로드
        itfind_pdf_path = None
        itfind_trend_info = None

        # 현재 시각 로깅 (디버깅용)
        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst)
        now_utc = datetime.now(timezone.utc)
        logger.info(f"현재 시각 - UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}, KST: {now_kst.strftime('%Y-%m-%d %H:%M:%S %Z')}, weekday: {now_kst.weekday()}")

        if is_wednesday():
            logger.info("📅 오늘은 수요일 - ITFIND 주간기술동향 다운로드 시도")
            try:
                itfind_pdf_path, itfind_trend_info = download_itfind_pdf()
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

        # 4. 이메일 전송 (모드에 따라 수신인 결정)
        logger.info("4단계: 이메일 전송 시작")

        # 4-1. 전자신문 발송
        logger.info("4-1단계: 전자신문 PDF 발송")
        email_success, success_emails = send_pdf_bulk_email(
            processed_pdf_path,
            test_mode=is_test_mode,
            itfind_pdf_path=None,  # 전자신문만
            itfind_info=None
        )

        if not email_success:
            logger.error("전자신문 이메일 전송 실패")
            raise Exception("전자신문 이메일 전송 실패")

        logger.info(f"전자신문 이메일 전송 성공: {len(success_emails)}명")

        # 4-2. ITFIND 주간기술동향 별도 발송 (수요일에만)
        if itfind_pdf_path and itfind_trend_info:
            logger.info("4-2단계: ITFIND 주간기술동향 별도 발송")

            # 이메일 제목: 첫 토픽 + 호수
            email_subject = f"{itfind_trend_info.title} [주간기술동향 {itfind_trend_info.issue_number}호]"

            itfind_email_success, itfind_success_emails = send_pdf_bulk_email(
                itfind_pdf_path,
                subject=email_subject,
                test_mode=is_test_mode,
                itfind_pdf_path=None,  # 단독 발송이므로 None
                itfind_info=itfind_trend_info
            )

            if itfind_email_success:
                logger.info(f"ITFIND 이메일 전송 성공: {len(itfind_success_emails)}명")
            else:
                logger.warning("ITFIND 이메일 전송 실패 (전자신문은 발송됨)")
        else:
            logger.info("4-2단계: ITFIND 발송 건너뛰기 (수요일 아님)")

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
