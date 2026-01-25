"""
환경변수 및 설정 관리 모듈
"""
import os
from dotenv import load_dotenv

# .env 파일 로드 (로컬 개발 환경용)
load_dotenv()


class Config:
    """애플리케이션 설정 클래스"""

    # 전자신문 계정
    ETNEWS_USER_ID = os.getenv("ETNEWS_USER_ID")
    ETNEWS_PASSWORD = os.getenv("ETNEWS_PASSWORD")
    ETNEWS_LOGIN_URL = "https://member.etnews.com/member/login.html?return_url=https://pdf.etnews.com/pdf_today.html"
    ETNEWS_PDF_URL = "https://pdf.etnews.com/pdf_today.html"

    # Gmail SMTP 설정
    GMAIL_USER = os.getenv("GMAIL_USER")
    # Gmail 앱 비밀번호는 공백 제거 (Google이 공백 포함해서 제공하지만 실제로는 공백 없이 사용)
    _gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "")
    GMAIL_APP_PASSWORD = _gmail_app_password.replace(" ", "")
    GMAIL_SMTP_SERVER = "smtp.gmail.com"
    GMAIL_SMTP_PORT = 587

    # 수신자 이메일
    RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "turtlesoup0@gmail.com")

    # iCloud Drive 설정
    ICLOUD_EMAIL = os.getenv("ICLOUD_EMAIL")
    ICLOUD_PASSWORD = os.getenv("ICLOUD_PASSWORD")
    ICLOUD_FOLDER_NAME = os.getenv("ICLOUD_FOLDER_NAME", "전자신문")

    # 임시 파일 경로
    TEMP_DIR = "/tmp" if os.name != "nt" else os.getenv("TEMP", "temp")

    # 타임아웃 설정 (초)
    BROWSER_TIMEOUT = 60000  # 60초
    DOWNLOAD_TIMEOUT = 120  # 2분

    # 광고 감지 키워드
    AD_KEYWORDS = ["광고", "AD", "Advertisement", "전면광고", "advertorial"]

    # PDF 처리 설정
    AD_TEXT_LENGTH_THRESHOLD = 50  # 광고로 간주할 텍스트 길이 임계값 (글자 수)
    AD_KEYWORD_COUNT_THRESHOLD = 2  # 광고로 간주할 키워드 출현 횟수 임계값

    # SMTP 재시도 설정
    SMTP_MAX_RETRIES = 3  # SMTP 전송 최대 재시도 횟수
    SMTP_RETRY_DELAY = 1  # SMTP 재시도 대기 시간 (초)

    @classmethod
    def validate(cls):
        """필수 환경변수 검증"""
        required_vars = [
            "ETNEWS_USER_ID",
            "ETNEWS_PASSWORD",
            "GMAIL_USER",
            "GMAIL_APP_PASSWORD",
        ]

        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)

        if missing_vars:
            raise ValueError(
                f"필수 환경변수가 설정되지 않았습니다: {', '.join(missing_vars)}"
            )

        return True


# 설정 유효성 검증 (모듈 임포트 시)
if __name__ != "__main__":
    try:
        Config.validate()
    except ValueError as e:
        print(f"경고: {e}")
