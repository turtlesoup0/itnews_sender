"""
iCloud Drive 업로드 모듈
pyicloud API를 사용하여 PDF 파일을 iCloud Drive에 업로드
"""
import os
import logging
from datetime import datetime
from pyicloud import PyiCloudService

from .config import Config

logger = logging.getLogger(__name__)


class ICloudUploader:
    """iCloud Drive PDF 업로드"""

    def __init__(self):
        self.config = Config
        self.api = None

    def authenticate(self) -> bool:
        """iCloud 인증 (세션 토큰 재사용)"""
        try:
            icloud_email = self.config.ICLOUD_EMAIL
            icloud_password = self.config.ICLOUD_PASSWORD

            if not icloud_email or not icloud_password:
                logger.warning("iCloud 계정 정보가 설정되지 않았습니다. iCloud 업로드를 건너뜁니다.")
                return False

            logger.info(f"iCloud 인증 시도: {icloud_email}")

            # cookie_directory를 지정하여 세션 유지
            cookie_dir = os.path.expanduser("~/.pyicloud")
            self.api = PyiCloudService(
                icloud_email,
                icloud_password,
                cookie_directory=cookie_dir
            )

            # 2단계 인증 필요 여부 확인
            if self.api.requires_2fa:
                logger.error("iCloud 2단계 인증이 필요합니다.")
                logger.error("로컬에서 먼저 인증을 완료하고 세션 쿠키를 생성해야 합니다.")
                logger.error("다음 명령어를 실행하여 인증하세요:")
                logger.error(f"  python3 -c \"from pyicloud import PyiCloudService; api = PyiCloudService('{icloud_email}'); print('인증 완료')\"")
                return False

            logger.info("iCloud 인증 성공")
            return True

        except Exception as e:
            logger.error(f"iCloud 인증 실패: {e}")
            logger.error(f"에러 타입: {type(e).__name__}")
            return False

    def upload_to_monthly_folder(self, pdf_path: str) -> bool:
        """
        PDF를 iCloud Drive의 연/월별 폴더에 업로드
        경로 형식: 전자신문/26/2601/파일.pdf

        Args:
            pdf_path: 업로드할 PDF 파일 경로

        Returns:
            업로드 성공 여부
        """
        try:
            if not self.api:
                if not self.authenticate():
                    return False

            # 파일 존재 확인
            if not os.path.exists(pdf_path):
                logger.error(f"파일을 찾을 수 없습니다: {pdf_path}")
                return False

            # 날짜별 폴더 구조 생성
            now = datetime.now()
            year_short = now.strftime("%y")  # 26
            year_month = now.strftime("%y%m")  # 2601

            # 루트 폴더 (전자신문)
            root_folder_name = self.config.ICLOUD_FOLDER_NAME

            # 1. 루트 폴더 생성/접근 (전자신문)
            if root_folder_name not in self.api.drive:
                logger.info(f"폴더 생성: {root_folder_name}")
                self.api.drive.mkdir(root_folder_name)

            root_folder = self.api.drive[root_folder_name]

            # 2. 연도 폴더 생성/접근 (26)
            if year_short not in root_folder:
                logger.info(f"폴더 생성: {root_folder_name}/{year_short}")
                root_folder.mkdir(year_short)

            year_folder = root_folder[year_short]

            # 3. 월 폴더 생성/접근 (2601)
            if year_month not in year_folder:
                logger.info(f"폴더 생성: {root_folder_name}/{year_short}/{year_month}")
                year_folder.mkdir(year_month)

            month_folder = year_folder[year_month]

            # 4. 파일 업로드
            filename = os.path.basename(pdf_path)
            logger.info(f"iCloud Drive 업로드: {root_folder_name}/{year_short}/{year_month}/{filename}")

            with open(pdf_path, 'rb') as file_in:
                month_folder.upload(file_in)

            logger.info(f"iCloud Drive 업로드 완료: {filename}")
            return True

        except Exception as e:
            logger.error(f"iCloud Drive 업로드 실패: {e}")
            import traceback
            logger.error(f"스택 트레이스:\n{traceback.format_exc()}")
            return False


def upload_to_icloud(pdf_path: str, use_monthly_folder: bool = True) -> bool:
    """
    PDF 파일을 iCloud Drive에 업로드하는 메인 함수

    Args:
        pdf_path: 업로드할 PDF 파일 경로
        use_monthly_folder: 연/월별 폴더 사용 (항상 True)

    Returns:
        업로드 성공 여부
    """
    uploader = ICloudUploader()
    return uploader.upload_to_monthly_folder(pdf_path)


if __name__ == "__main__":
    # 테스트
    import sys

    if len(sys.argv) > 1:
        test_pdf_path = sys.argv[1]
        success = upload_to_icloud(test_pdf_path)
        if success:
            print("iCloud 업로드 성공")
        else:
            print("iCloud 업로드 실패")
    else:
        print("사용법: python icloud_uploader.py <pdf_path>")
