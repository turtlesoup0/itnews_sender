"""
Azure Functions 메인 애플리케이션
Timer Trigger로 매일 06시에 실행
"""
import logging
import os
import azure.functions as func

from src.scraper import download_pdf_sync
from src.pdf_processor import process_pdf
from src.email_sender import send_pdf_email
from src.icloud_uploader import upload_to_icloud

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Azure Functions 앱 생성
app = func.FunctionApp()


def run_etnews_workflow() -> bool:
    """
    IT뉴스 워크플로우 실행

    Returns:
        성공 여부
    """
    pdf_path = None
    processed_pdf_path = None

    try:
        # 1. PDF 다운로드 및 페이지 정보 수집
        logger.info("1단계: PDF 다운로드 시작")
        pdf_path, page_info = download_pdf_sync()
        logger.info(f"PDF 다운로드 완료: {pdf_path}")

        # 2. 광고 페이지 제거
        logger.info("2단계: 광고 페이지 제거 시작")
        processed_pdf_path = process_pdf(pdf_path, page_info)
        logger.info(f"PDF 처리 완료: {processed_pdf_path}")

        # 3. 이메일 전송
        logger.info("3단계: 이메일 전송 시작")
        email_success = send_pdf_email(processed_pdf_path)

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

        logger.info("===== IT뉴스 PDF 전송 작업 완료 =====")
        return True

    except Exception as e:
        logger.error(f"작업 실행 중 오류 발생: {e}", exc_info=True)
        raise

    finally:
        cleanup_temp_files(pdf_path, processed_pdf_path)


@app.timer_trigger(
    schedule="0 0 21 * * *",  # 매일 21:00 UTC (한국시간 06:00)
    arg_name="myTimer",
    run_on_startup=False,  # 시작 시 즉시 실행하지 않음
    use_monitor=True
)
def etnews_pdf_sender(myTimer: func.TimerRequest) -> None:
    """
    IT뉴스 PDF 자동 다운로드 및 전송 함수
    매일 한국시간 06:00에 실행
    """
    logger.info("===== IT뉴스 PDF 전송 작업 시작 =====")

    if myTimer.past_due:
        logger.warning("Timer is past due!")

    try:
        run_etnews_workflow()
    except Exception:
        pass  # 로깅은 이미 run_etnews_workflow에서 처리됨


@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """헬스 체크 엔드포인트"""
    logger.info("Health check requested")
    return func.HttpResponse("OK", status_code=200)


@app.route(route="trigger", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def manual_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """
    수동 실행 트리거 (테스트용)
    POST /api/trigger
    """
    logger.info("수동 트리거 실행 시작")

    try:
        run_etnews_workflow()
        return func.HttpResponse("IT뉴스 PDF 전송 성공", status_code=200)

    except Exception as e:
        logger.error(f"수동 실행 중 오류: {e}", exc_info=True)
        return func.HttpResponse(f"오류 발생: {str(e)}", status_code=500)


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


