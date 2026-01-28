"""
이메일 발송 워크플로우
"""
import logging
from typing import Optional, List
from datetime import datetime
from ..email_sender import send_pdf_bulk_email

logger = logging.getLogger(__name__)


def send_emails(
    processed_pdf_path: str,
    test_mode: bool,
    itfind_pdf_path: Optional[str] = None,
    itfind_info: Optional[dict] = None
) -> tuple[bool, List[str], bool, List[str]]:
    """
    이메일 발송 (전자신문 + ITFIND 별도 발송)

    Args:
        processed_pdf_path: 처리된 전자신문 PDF 경로
        test_mode: 테스트 모드 여부
        itfind_pdf_path: ITFIND PDF 경로 (선택)
        itfind_info: ITFIND 메타데이터 (선택)

    Returns:
        (전자신문 성공 여부, 전자신문 성공 이메일 목록,
         ITFIND 성공 여부, ITFIND 성공 이메일 목록)
    """
    # 4-1. 전자신문 발송
    logger.info("4-1단계: 전자신문 PDF 이메일 발송")
    email_success, success_emails = send_pdf_bulk_email(
        processed_pdf_path,
        test_mode=test_mode,
        itfind_pdf_path=None,  # 전자신문만 첨부
        itfind_info=None
    )

    if email_success:
        logger.info(f"✅ 전자신문 이메일 발송 성공 (수신인: {len(success_emails)}명)")
    else:
        logger.warning(f"⚠️  전자신문 일부 이메일 발송 실패 (성공: {len(success_emails)}명)")

    # 4-2. ITFIND 주간기술동향 별도 발송 (있는 경우)
    itfind_email_success = False
    itfind_success_emails = []

    if itfind_pdf_path and itfind_info:
        logger.info("4-2단계: ITFIND 주간기술동향 별도 발송")

        # 이메일 제목 생성
        email_subject = f"{itfind_info.title} [주간기술동향 {itfind_info.issue_number}호]"

        itfind_email_success, itfind_success_emails = send_pdf_bulk_email(
            itfind_pdf_path,
            subject=email_subject,
            test_mode=test_mode,
            itfind_pdf_path=None,  # ITFIND를 메인 첨부로
            itfind_info=itfind_info
        )

        if itfind_email_success:
            logger.info(f"✅ ITFIND 이메일 발송 성공 (수신인: {len(itfind_success_emails)}명)")
        else:
            logger.warning(f"⚠️  ITFIND 일부 이메일 발송 실패 (성공: {len(itfind_success_emails)}명)")

    return email_success, success_emails, itfind_email_success, itfind_success_emails
