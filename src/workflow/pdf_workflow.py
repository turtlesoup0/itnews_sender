"""
PDF 다운로드 및 처리 워크플로우
"""
import logging
from typing import Optional, Tuple
from ..scraper import download_pdf_sync
from ..pdf_processor import process_pdf
from ..itfind_scraper import download_itfind_pdf_sync
from ..failure_tracker import FailureTracker
from ..utils.notification import send_admin_notification

logger = logging.getLogger(__name__)


def download_and_process_pdf() -> Tuple[Optional[str], Optional[str]]:
    """
    전자신문 PDF 다운로드 및 처리

    Returns:
        (원본 PDF 경로, 처리된 PDF 경로)
    """
    failure_tracker = FailureTracker()

    # 2. PDF 다운로드
    logger.info("2단계: 전자신문 PDF 다운로드")
    pdf_path = download_pdf_sync()

    if not pdf_path:
        failure_tracker.record_failure()
        logger.error("PDF 다운로드 실패")

        # 관리자 알림
        try:
            send_admin_notification(
                subject="[etnews-pdf-sender] PDF 다운로드 실패",
                message="전자신문 PDF 다운로드에 실패했습니다."
            )
        except Exception as e:
            logger.error(f"관리자 알림 실패: {e}")

        return None, None

    logger.info(f"✅ PDF 다운로드 성공: {pdf_path}")

    # 3. PDF 처리 (광고 제거)
    logger.info("3단계: PDF 광고 제거 처리")
    processed_pdf_path = process_pdf(pdf_path)

    if not processed_pdf_path:
        logger.error("PDF 처리 실패")
        return pdf_path, None

    logger.info(f"✅ PDF 처리 완료: {processed_pdf_path}")
    return pdf_path, processed_pdf_path


def download_itfind_pdf() -> Tuple[Optional[str], Optional[dict]]:
    """
    ITFIND 주간기술동향 PDF 다운로드

    Returns:
        (PDF 경로, 메타데이터)
    """
    logger.info("3-1단계: ITFIND 주간기술동향 다운로드")

    try:
        result = download_itfind_pdf_sync()

        if result and result.get('pdf_path'):
            itfind_pdf_path = result['pdf_path']
            itfind_trend_info = result.get('trend_info')
            logger.info(f"✅ ITFIND PDF 다운로드 성공: {itfind_pdf_path}")
            return itfind_pdf_path, itfind_trend_info
        else:
            logger.warning("ITFIND PDF를 찾지 못했습니다 (주간기술동향 없음)")
            return None, None

    except Exception as e:
        logger.error(f"ITFIND PDF 다운로드 중 오류: {e}")
        return None, None
