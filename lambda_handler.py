"""
AWS Lambda 핸들러
EventBridge에서 트리거되어 전자신문 PDF 다운로드 및 전송
"""
import logging
import os
import json
import time

from src.scraper import download_pdf_sync
from src.pdf_processor import process_pdf
from src.email_sender import send_pdf_bulk_email
from src.icloud_uploader import upload_to_icloud
from src.structured_logging import get_structured_logger

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)


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

    logger.info("===== 전자신문 PDF 전송 작업 시작 =====")
    logger.info(f"Event: {json.dumps(event)}")

    structured_logger.info(
        event="lambda_start",
        message="전자신문 PDF 전송 작업 시작",
        function_name=context.function_name if context else "local",
        request_id=context.request_id if context else "local"
    )

    pdf_path = None
    processed_pdf_path = None

    try:
        # 1. PDF 다운로드 및 페이지 정보 수집
        logger.info("1단계: PDF 다운로드 시작")
        try:
            pdf_path, page_info = download_pdf_sync()
            logger.info(f"PDF 다운로드 완료: {pdf_path}")
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
                raise

        # 2. 광고 페이지 제거
        logger.info("2단계: 광고 페이지 제거 시작")
        processed_pdf_path = process_pdf(pdf_path, page_info)
        logger.info(f"PDF 처리 완료: {processed_pdf_path}")

        # 3. 이메일 전송 (다중 수신인 BCC)
        logger.info("3단계: 이메일 전송 시작 (다중 수신인 BCC)")
        email_success = send_pdf_bulk_email(processed_pdf_path)

        if not email_success:
            logger.error("이메일 전송 실패")
            raise Exception("이메일 전송 실패")

        logger.info("이메일 전송 성공")

        # 4. iCloud Drive 업로드 (선택사항)
        logger.info("4단계: iCloud Drive 업로드 시작")
        try:
            icloud_success = upload_to_icloud(processed_pdf_path, use_monthly_folder=True)
            if icloud_success:
                logger.info("iCloud Drive 업로드 성공")
            else:
                logger.warning("iCloud Drive 업로드 실패 (계속 진행)")
        except Exception as icloud_error:
            logger.warning(f"iCloud Drive 업로드 중 오류 (계속 진행): {icloud_error}")

        duration_ms = (time.time() - start_time) * 1000

        logger.info("===== 전자신문 PDF 전송 작업 완료 =====")

        structured_logger.info(
            event="lambda_success",
            message="전자신문 PDF 전송 작업 완료",
            duration_ms=duration_ms,
            pdf_path=pdf_path,
            processed_pdf_path=processed_pdf_path
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': '전자신문 PDF 전송 성공',
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
            message=f"전자신문 PDF 전송 작업 실패: {str(e)}",
            duration_ms=duration_ms,
            error=str(e),
            error_type=type(e).__name__
        )

        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': '전자신문 PDF 전송 실패',
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
