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
from typing import Optional, List

from .config import Config
from .recipients import get_active_recipients
from .unsubscribe_token import generate_token

logger = logging.getLogger(__name__)


class EmailSender:
    """Gmail SMTP 이메일 전송"""

    def __init__(self):
        self.config = Config
        # 수신거부 토큰 생성을 위한 시크릿 키
        self.unsubscribe_secret = os.getenv("UNSUBSCRIBE_SECRET", "etnews-unsubscribe-secret-2026")
        # Lambda Function URL for unsubscribe
        self.unsubscribe_url_base = os.getenv(
            "UNSUBSCRIBE_FUNCTION_URL",
            "https://heswdvaag57hgz3ugvxk6ifqpq0ukhog.lambda-url.ap-northeast-2.on.aws"
        )

    def send_email(
        self,
        pdf_path: str,
        recipient: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> bool:
        """
        PDF 파일을 첨부하여 이메일 전송 (단일 수신자)

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
                subject = f"IT뉴스 [{today}]"

            # 이메일 메시지 생성
            msg = self._create_message(pdf_path, [to_email], subject)

            # SMTP 서버 연결 및 전송
            self._send_via_smtp(msg, [to_email])

            logger.info(f"이메일 전송 성공: {to_email}")
            return True

        except Exception as e:
            logger.error(f"이메일 전송 실패: {e}")
            return False

    def send_bulk_email(
        self,
        pdf_path: str,
        subject: Optional[str] = None,
        test_mode: bool = False,
    ) -> tuple[bool, List[str]]:
        """
        PDF 파일을 다중 수신자에게 개별 전송 (개인화된 수신거부 링크 포함)

        Args:
            pdf_path: 전송할 PDF 파일 경로
            subject: 이메일 제목 (None이면 자동 생성)
            test_mode: True면 turtlesoup0@gmail.com에게만 발송 (테스트용)

        Returns:
            (전송 성공 여부, 성공한 수신인 이메일 리스트)
        """
        try:
            # 테스트 모드: 관리자 이메일로 고정
            if test_mode:
                from .recipients.models import Recipient, RecipientStatus
                test_recipient = Recipient(
                    email="turtlesoup0@gmail.com",
                    name="관리자 (테스트)",
                    status=RecipientStatus.ACTIVE,
                    created_at=datetime.now().isoformat()
                )
                recipients = [test_recipient]
                logger.info("🧪 TEST 모드: turtlesoup0@gmail.com에게만 발송")
            else:
                # OPR 모드: DynamoDB 활성 수신인
                recipients = get_active_recipients()
                logger.info(f"🚀 OPR 모드: {len(recipients)}명 활성 수신인에게 발송")

            if not recipients:
                logger.warning("활성 수신인이 없습니다")
                return False, []

            logger.info(f"이메일 전송 대상: {len(recipients)}명")

            # 제목 설정
            if not subject:
                today = datetime.now().strftime("%Y-%m-%d")
                subject = f"IT뉴스 [{today}]"

            # 각 수신자에게 개별 전송
            success_emails = []
            fail_count = 0

            for recipient in recipients:
                try:
                    # 개인화된 이메일 메시지 생성
                    msg = self._create_message(
                        pdf_path,
                        [recipient.email],
                        subject,
                        use_bcc=False,
                        recipient_email=recipient.email
                    )

                    # SMTP 서버 연결 및 전송
                    self._send_via_smtp(msg, [recipient.email])

                    success_emails.append(recipient.email)
                    logger.info(f"이메일 전송 완료: {recipient.email} ({len(success_emails)}/{len(recipients)})")

                except Exception as e:
                    fail_count += 1
                    logger.error(f"이메일 전송 실패: {recipient.email} - {e}")

            logger.info(f"이메일 전송 완료: 성공 {len(success_emails)}명, 실패 {fail_count}명")
            return len(success_emails) > 0, success_emails

        except Exception as e:
            logger.error(f"이메일 전송 실패: {e}")
            return False, []

    def _create_message(
        self, pdf_path: str, to_emails: List[str], subject: str, use_bcc: bool = False, recipient_email: Optional[str] = None
    ) -> MIMEMultipart:
        """이메일 메시지 생성"""

        # 메시지 객체 생성
        msg = MIMEMultipart()
        msg["From"] = self.config.GMAIL_USER
        msg["Subject"] = subject

        if use_bcc:
            # BCC로 전송 (수신자 숨김)
            msg["To"] = self.config.GMAIL_USER  # 발신자 자신에게
            msg["Bcc"] = ", ".join(to_emails)
        else:
            # 일반 전송
            msg["To"] = ", ".join(to_emails)

        # 이메일 본문 생성 (개인화된 수신거부 링크)
        body = self._create_email_body(recipient_email)
        msg.attach(MIMEText(body, "html", "utf-8"))

        # PDF 파일 첨부
        self._attach_pdf(msg, pdf_path)

        return msg

    def _generate_unsubscribe_token(self, email: str) -> str:
        """
        수신거부 토큰 생성 (HMAC 기반)

        Args:
            email: 이메일 주소

        Returns:
            Base64 인코딩된 토큰
        """
        return generate_token(email, self.unsubscribe_secret)

    def _create_email_body(self, recipient_email: Optional[str] = None) -> str:
        """이메일 본문 HTML 생성"""
        today = datetime.now().strftime("%Y년 %m월 %d일")

        # 수신거부 URL 생성
        unsubscribe_url = "#"
        if recipient_email:
            token = self._generate_unsubscribe_token(recipient_email)
            unsubscribe_url = f"{self.unsubscribe_url_base}/?token={token}"

        body = f"""
        <html>
            <head></head>
            <body>
                <h2>IT뉴스 PDF 뉴스지면</h2>
                <p>안녕하세요,</p>
                <p>{today} IT뉴스 PDF 뉴스지면을 보내드립니다.</p>
                <p>광고 페이지가 제거된 파일입니다.</p>
                <br>
                <p>이 이메일은 자동으로 발송되었습니다.</p>
                <p style="color: #666; font-size: 0.9em;">
                    이 서비스는 오픈소스 프로젝트로 운영됩니다:
                    <a href="https://github.com/turtlesoup0/itnews_sender" style="color: #0066cc;">GitHub 프로젝트 보기</a>
                </p>
                <hr>
                <small>
                    문의사항이 있으시면 turtlesoup0@gmail.com으로 연락주세요.<br>
                    이 뉴스레터를 더 이상 받고 싶지 않으시면 <a href="{unsubscribe_url}" style="color: #666;">여기</a>를 클릭하세요.
                </small>
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

    def _send_via_smtp(self, msg: MIMEMultipart, to_emails: List[str]):
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
    PDF 이메일 전송 메인 함수 (단일 수신자)

    Args:
        pdf_path: 전송할 PDF 파일 경로
        recipient: 수신자 이메일
        subject: 이메일 제목

    Returns:
        전송 성공 여부
    """
    sender = EmailSender()
    return sender.send_email(pdf_path, recipient, subject)


def send_pdf_bulk_email(pdf_path: str, subject: Optional[str] = None, test_mode: bool = False) -> tuple[bool, List[str]]:
    """
    PDF 이메일 전송 메인 함수 (다중 수신자 개별 전송)

    Args:
        pdf_path: 전송할 PDF 파일 경로
        subject: 이메일 제목
        test_mode: True면 테스트 모드 (turtlesoup0@gmail.com에게만 발송)

    Returns:
        (전송 성공 여부, 성공한 수신인 이메일 리스트)
    """
    sender = EmailSender()
    return sender.send_bulk_email(pdf_path, subject, test_mode)


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
