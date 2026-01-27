"""
AWS Lambda 핸들러
EventBridge에서 트리거되어 IT뉴스 PDF 다운로드 및 전송
"""
import logging
import os
import json
import time
from datetime import datetime

from src.scraper import download_pdf_sync
from src.pdf_processor import process_pdf
from src.email_sender import send_pdf_bulk_email
from src.icloud_uploader import upload_to_icloud
from src.structured_logging import get_structured_logger
from src.delivery_tracker import DeliveryTracker
from src.failure_tracker import FailureTracker
from src.execution_tracker import ExecutionTracker

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)


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
    logger.info(f"Event: {json.dumps(event)}")

    # 실행 모드 결정 (기본값: test)
    mode = event.get("mode", "test")
    is_test_mode = (mode != "opr")

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
        # 0-1. 멱등성 체크 (중복 실행 방지)
        logger.info("0-1단계: 멱등성 체크 (중복 실행 방지)")
        exec_tracker = ExecutionTracker()

        if exec_tracker.should_skip_execution(mode):
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

        logger.info(f"✅ 멱등성 체크 완료: 오늘 {mode} 모드 미실행 확인")

        # 0-2. 중복 발송 체크 (OPR 모드에만 적용)
        if not is_test_mode:
            logger.info("0-2단계: 중복 발송 체크 (OPR 모드)")
            tracker = DeliveryTracker()

            if tracker.is_delivered_today():
                duration_ms = (time.time() - start_time) * 1000
                logger.info("⚠️  오늘 이미 메일이 발송되었습니다. 중복 발송을 방지합니다.")

                structured_logger.info(
                    event="duplicate_delivery_prevented",
                    message="오늘 이미 발송되어 중복 발송 방지",
                    duration_ms=duration_ms
                )

                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': '오늘 이미 메일이 발송되었습니다 (중복 발송 방지)',
                        'skipped': True,
                        'reason': 'already_delivered_today'
                    })
                }

            logger.info("✅ 중복 발송 체크 완료: 오늘 미발송 확인")
        else:
            logger.info("0-2단계: 중복 발송 체크 건너뛰기 (TEST 모드)")
            tracker = DeliveryTracker()  # 발송 이력 기록용

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
        logger.info("2단계: PDF 다운로드 시작")
        try:
            pdf_path, page_info = download_pdf_sync()
            logger.info(f"PDF 다운로드 완료: {pdf_path}")

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
                        _send_admin_notification(
                            subject="[etnews-pdf-sender] PDF 다운로드 실패 알림",
                            message=f"PDF 다운로드가 3회 연속 실패했습니다.\n\n오류: {ve}"
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
                    _send_admin_notification(
                        subject="[etnews-pdf-sender] PDF 다운로드 실패 알림",
                        message=f"PDF 다운로드가 3회 연속 실패했습니다.\n\n오류: {e}"
                    )
                except Exception as notify_error:
                    logger.error(f"관리자 알림 실패: {notify_error}")

            raise

        # 3. 광고 페이지 제거
        logger.info("3단계: 광고 페이지 제거 시작")
        processed_pdf_path = process_pdf(pdf_path, page_info)
        logger.info(f"PDF 처리 완료: {processed_pdf_path}")

        # 4. 이메일 전송 (모드에 따라 수신인 결정)
        logger.info("4단계: 이메일 전송 시작")
        email_success, success_emails = send_pdf_bulk_email(processed_pdf_path, test_mode=is_test_mode)

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

        # 5-1. 실행 이력 기록 (멱등성 보장)
        logger.info("5-1단계: 실행 이력 기록 (멱등성 보장)")
        request_id = context.aws_request_id if context else "local"
        exec_tracker.mark_execution(mode, request_id)
        logger.info(f"실행 이력 기록 완료: {mode} 모드, RequestId: {request_id}")

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
        cleanup_temp_files(pdf_path, processed_pdf_path)


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
