"""
환경변수 및 설정 관리 모듈
"""
import os
import logging
from dotenv import load_dotenv
from typing import Optional

logger = logging.getLogger(__name__)

# .env 파일 로드 (로컬 개발 환경용)
load_dotenv()


class ConfigClass:
    """애플리케이션 설정 클래스"""

    def __init__(self):
        # Credentials (Secrets Manager에서 로드 가능)
        self._credentials: Optional[dict] = None
        self._credentials_loaded = False

    # IT뉴스 설정
    ETNEWS_LOGIN_URL = "https://member.etnews.com/member/login.html?return_url=https://pdf.etnews.com/pdf_today.html"
    ETNEWS_PDF_URL = "https://pdf.etnews.com/pdf_today.html"

    # Gmail SMTP 설정
    GMAIL_SMTP_SERVER = "smtp.gmail.com"
    GMAIL_SMTP_PORT = 587

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

    def _load_credentials(self):
        """Credentials 로드 (Secrets Manager 또는 환경변수)"""
        if self._credentials_loaded:
            return

        try:
            # Lambda 환경 감지
            is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None

            if is_lambda:
                logger.info("Lambda 환경: Parameter Store에서 credentials 로드")
                from .parameter_store import get_credentials
                self._credentials = get_credentials()
            else:
                logger.info("로컬 환경: 환경변수에서 credentials 로드")
                self._credentials = {
                    'ETNEWS_USER_ID': os.getenv('ETNEWS_USER_ID', ''),
                    'ETNEWS_PASSWORD': os.getenv('ETNEWS_PASSWORD', ''),
                    'GMAIL_USER': os.getenv('GMAIL_USER', ''),
                    'GMAIL_APP_PASSWORD': os.getenv('GMAIL_APP_PASSWORD', ''),
                    'RECIPIENT_EMAIL': os.getenv('RECIPIENT_EMAIL', ''),
                    'ICLOUD_EMAIL': os.getenv('ICLOUD_EMAIL', ''),
                    'ICLOUD_PASSWORD': os.getenv('ICLOUD_PASSWORD', ''),
                    'ICLOUD_FOLDER_NAME': os.getenv('ICLOUD_FOLDER_NAME', 'IT뉴스'),
                }

            self._credentials_loaded = True
            logger.info("Credentials 로드 완료")

        except Exception as e:
            logger.error(f"Credentials 로드 실패: {e}")
            # 실패 시 환경변수 fallback
            self._credentials = {
                'ETNEWS_USER_ID': os.getenv('ETNEWS_USER_ID', ''),
                'ETNEWS_PASSWORD': os.getenv('ETNEWS_PASSWORD', ''),
                'GMAIL_USER': os.getenv('GMAIL_USER', ''),
                'GMAIL_APP_PASSWORD': os.getenv('GMAIL_APP_PASSWORD', ''),
                'RECIPIENT_EMAIL': os.getenv('RECIPIENT_EMAIL', ''),
                'ICLOUD_EMAIL': os.getenv('ICLOUD_EMAIL', ''),
                'ICLOUD_PASSWORD': os.getenv('ICLOUD_PASSWORD', ''),
                'ICLOUD_FOLDER_NAME': os.getenv('ICLOUD_FOLDER_NAME', 'IT뉴스'),
            }
            self._credentials_loaded = True

    def get_credential(self, key: str, default: str = '') -> str:
        """
        Credential 가져오기

        Args:
            key: credential 키
            default: 기본값

        Returns:
            credential 값
        """
        self._load_credentials()
        value = self._credentials.get(key, default)

        # Gmail 앱 비밀번호는 공백 제거
        if key == 'GMAIL_APP_PASSWORD':
            value = value.replace(" ", "")

        return value

    # Property로 credential 접근 제공
    @property
    def ETNEWS_USER_ID(self):
        return self.get_credential('ETNEWS_USER_ID')

    @property
    def ETNEWS_PASSWORD(self):
        return self.get_credential('ETNEWS_PASSWORD')

    @property
    def GMAIL_USER(self):
        return self.get_credential('GMAIL_USER')

    @property
    def GMAIL_APP_PASSWORD(self):
        return self.get_credential('GMAIL_APP_PASSWORD')

    @property
    def RECIPIENT_EMAIL(self):
        """
        레거시: 단일 수신자 이메일 (더 이상 사용하지 않음)
        다중 수신인은 DynamoDB에서 관리
        """
        return self.get_credential('RECIPIENT_EMAIL', '')

    @property
    def ICLOUD_EMAIL(self):
        return self.get_credential('ICLOUD_EMAIL')

    @property
    def ICLOUD_PASSWORD(self):
        return self.get_credential('ICLOUD_PASSWORD')

    @property
    def ICLOUD_FOLDER_NAME(self):
        return self.get_credential('ICLOUD_FOLDER_NAME', 'IT뉴스')

    @property
    def UNSUBSCRIBE_FUNCTION_URL(self):
        """수신거부 Lambda Function URL"""
        # Lambda 환경에서는 Parameter Store에서 로드
        is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None
        if is_lambda:
            try:
                from .parameter_store import get_parameter
                return get_parameter('/etnews/unsubscribe-function-url')
            except Exception as e:
                logger.warning(f"Parameter Store에서 unsubscribe URL 로드 실패: {e}")

        # 로컬 환경 또는 fallback
        return os.getenv('UNSUBSCRIBE_FUNCTION_URL', '')

    @property
    def ADMIN_EMAIL(self):
        """관리자 알림 수신 이메일"""
        # Lambda 환경에서는 Parameter Store에서 로드
        is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None
        if is_lambda:
            try:
                from .parameter_store import get_parameter
                return get_parameter('/etnews/admin-email')
            except Exception as e:
                logger.warning(f"Parameter Store에서 admin email 로드 실패: {e}")

        # 로컬 환경 또는 fallback
        return os.getenv('ADMIN_EMAIL', 'turtlesoup0@gmail.com')

    @property
    def UNSUBSCRIBE_SECRET(self):
        """수신거부 HMAC Secret Key"""
        # Lambda 환경에서는 Parameter Store에서 로드
        is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None
        if is_lambda:
            try:
                from .parameter_store import get_parameter
                return get_parameter('/etnews/unsubscribe-secret', with_decryption=True)
            except Exception as e:
                logger.warning(f"Parameter Store에서 unsubscribe secret 로드 실패: {e}")

        # 로컬 환경 또는 fallback
        return os.getenv('UNSUBSCRIBE_SECRET', '')

    def validate(self):
        """필수 환경변수 검증"""
        self._load_credentials()

        required_vars = [
            "ETNEWS_USER_ID",
            "ETNEWS_PASSWORD",
            "GMAIL_USER",
            "GMAIL_APP_PASSWORD",
        ]

        missing_vars = []
        for var in required_vars:
            if not self.get_credential(var):
                missing_vars.append(var)

        if missing_vars:
            raise ValueError(
                f"필수 환경변수가 설정되지 않았습니다: {', '.join(missing_vars)}"
            )

        return True


# 싱글톤 인스턴스 생성
Config = ConfigClass()

# 설정 유효성 검증 (모듈 임포트 시)
if __name__ != "__main__":
    try:
        Config.validate()
    except ValueError as e:
        print(f"경고: {e}")
