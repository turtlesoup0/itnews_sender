"""
이메일 전송 모듈
Gmail SMTP를 사용하여 처리된 PDF 파일 전송
"""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
from typing import Optional

from .config import Config

logger = logging.getLogger(__name__)


class EmailSender:
    """Gmail SMTP 이메일 전송"""

    def __init__(self):
        self.config = Config

    def send_email(
        self,
        pdf_path: str,
        recipient: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> bool:
        """
        PDF 파일을 첨부하여 이메일 전송

        Args:
            pdf_path: 전송할 PDF 파일 경로
            recipient: 수신자 이메일 (None이면 기본 수신자 사용)
            subject: 이메일 제목 (None이면 자동 생성)

        Returns:
            전송 성공 여부
        """
        try:
            # 수신자 설정
            to_email = recipient or self.config.RECIPIENT_EMAIL

            # 제목 설정
            if not subject:
                today = datetime.now().strftime("%Y-%m-%d")
                subject = f"전자신문 [{today}]"

            # 이메일 메시지 생성
            msg = self._create_message(pdf_path, to_email, subject)

            # SMTP 서버 연결 및 전송
            self._send_via_smtp(msg, to_email)

            logger.info(f"이메일 전송 성공: {to_email}")
            return True

        except Exception as e:
            logger.error(f"이메일 전송 실패: {e}")
            return False

    def _create_message(
        self, pdf_path: str, to_email: str, subject: str
    ) -> MIMEMultipart:
        """이메일 메시지 생성"""

        # 메시지 객체 생성
        msg = MIMEMultipart()
        msg["From"] = self.config.GMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject

        # 이메일 본문 생성
        body = self._create_email_body()
        msg.attach(MIMEText(body, "html", "utf-8"))

        # PDF 파일 첨부
        self._attach_pdf(msg, pdf_path)

        return msg

    def _create_email_body(self) -> str:
        """이메일 본문 HTML 생성"""
        today = datetime.now().strftime("%Y년 %m월 %d일")

        body = f"""
        <html>
            <head></head>
            <body>
                <h2>전자신문 PDF 뉴스지면</h2>
                <p>안녕하세요,</p>
                <p>{today} 전자신문 PDF 뉴스지면을 보내드립니다.</p>
                <p>광고 페이지가 제거된 파일입니다.</p>
                <br>
                <p>이 이메일은 자동으로 발송되었습니다.</p>
                <hr>
                <small>문의사항이 있으시면 turtlesoup0@gmail.com으로 연락주세요.</small>
            </body>
        </html>
        """
        return body

    def _attach_pdf(self, msg: MIMEMultipart, pdf_path: str):
        """PDF 파일을 이메일에 첨부"""
        try:
            with open(pdf_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()

            # PDF 첨부 파일 생성
            pdf_attachment = MIMEApplication(pdf_data, _subtype="pdf")

            # 파일명 설정
            filename = os.path.basename(pdf_path)
            pdf_attachment.add_header(
                "Content-Disposition", f"attachment; filename={filename}"
            )

            msg.attach(pdf_attachment)
            logger.info(f"PDF 파일 첨부 완료: {filename} ({len(pdf_data)} bytes)")

        except Exception as e:
            logger.error(f"PDF 파일 첨부 실패: {e}")
            raise

    def _send_via_smtp(self, msg: MIMEMultipart, to_email: str):
        """SMTP 서버를 통해 이메일 전송"""
        max_retries = self.config.SMTP_MAX_RETRIES
        retry_count = 0

        while retry_count < max_retries:
            try:
                # SMTP 서버 연결
                server = smtplib.SMTP(
                    self.config.GMAIL_SMTP_SERVER, self.config.GMAIL_SMTP_PORT
                )
                server.ehlo()

                # TLS 보안 연결
                server.starttls()
                server.ehlo()

                # 로그인
                server.login(self.config.GMAIL_USER, self.config.GMAIL_APP_PASSWORD)

                # 이메일 전송
                server.send_message(msg)

                # 연결 종료
                server.quit()

                logger.info(f"SMTP 전송 성공 (시도 {retry_count + 1}/{max_retries})")
                return

            except smtplib.SMTPException as e:
                retry_count += 1
                logger.warning(
                    f"SMTP 전송 실패 (시도 {retry_count}/{max_retries}): {e}"
                )

                if retry_count >= max_retries:
                    raise Exception(f"SMTP 전송 최대 재시도 초과: {e}")

                # 재시도 대기
                import time
                time.sleep(self.config.SMTP_RETRY_DELAY)

            except Exception as e:
                logger.error(f"SMTP 연결 중 예상치 못한 오류: {e}")
                raise


def send_pdf_email(
    pdf_path: str, recipient: Optional[str] = None, subject: Optional[str] = None
) -> bool:
    """
    PDF 이메일 전송 메인 함수

    Args:
        pdf_path: 전송할 PDF 파일 경로
        recipient: 수신자 이메일
        subject: 이메일 제목

    Returns:
        전송 성공 여부
    """
    sender = EmailSender()
    return sender.send_email(pdf_path, recipient, subject)


if __name__ == "__main__":
    # 테스트
    import sys

    if len(sys.argv) > 1:
        test_pdf_path = sys.argv[1]
        success = send_pdf_email(test_pdf_path)
        if success:
            print("이메일 전송 성공")
        else:
            print("이메일 전송 실패")
    else:
        print("사용법: python email_sender.py <pdf_path>")
