"""
관리자 알림 유틸리티
"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from ..config import Config

logger = logging.getLogger(__name__)


def send_admin_notification(subject: str, message: str, include_signature: bool = True) -> bool:
    """
    관리자에게 알림 이메일 전송

    Args:
        subject: 이메일 제목
        message: 이메일 본문
        include_signature: 시그니처 포함 여부 (기본: True)

    Returns:
        전송 성공 여부
    """
    try:
        config = Config
        admin_email = config.ADMIN_EMAIL

        msg = MIMEMultipart()
        msg["From"] = config.GMAIL_USER
        msg["To"] = admin_email
        msg["Subject"] = subject

        # 본문 구성
        body = message
        if include_signature:
            body += """

---
IT뉴스 PDF 자동 배송 시스템
"""

        msg.attach(MIMEText(body, "plain", "utf-8"))

        # SMTP 전송
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.GMAIL_USER, config.GMAIL_APP_PASSWORD)
            server.send_message(msg)

        logger.info(f"관리자 알림 전송 완료: {subject}")
        return True

    except Exception as e:
        logger.error(f"관리자 알림 전송 실패: {e}")
        return False
