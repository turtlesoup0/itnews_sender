"""
전자신문 웹 스크래핑 모듈
Playwright를 사용하여 로그인, PDF 다운로드 및 페이지 정보 수집
"""
import os
import asyncio
import logging
from datetime import datetime
from typing import Tuple, List, Dict
from playwright.async_api import async_playwright, Page, Browser
from bs4 import BeautifulSoup

from .config import Config

logger = logging.getLogger(__name__)


class EtnewsScraper:
    """전자신문 PDF 다운로드 및 페이지 정보 수집"""

    def __init__(self):
        self.config = Config
        self.playwright = None
        self.browser: Browser = None
        self.page: Page = None

    async def __aenter__(self):
        """컨텍스트 매니저 진입"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        await self.close()

    async def initialize(self):
        """브라우저 초기화"""
        logger.info("브라우저 초기화 중...")
        self.playwright = await async_playwright().start()

        # Lambda 환경을 위한 브라우저 옵션
        launch_options = {
            'headless': True,
            'args': [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--single-process'
            ]
        }

        self.browser = await self.playwright.chromium.launch(**launch_options)
        self.page = await self.browser.new_page()
        logger.info("브라우저 초기화 완료")

    async def close(self):
        """브라우저 종료"""
        if self.browser:
            await self.browser.close()
            logger.info("브라우저 종료 완료")

        if self.playwright:
            await self.playwright.stop()
            logger.info("Playwright 종료 완료")

    async def login(self) -> bool:
        """전자신문 로그인"""
        try:
            logger.info("전자신문 로그인 시도 중...")
            await self.page.goto(
                self.config.ETNEWS_LOGIN_URL,
                timeout=self.config.BROWSER_TIMEOUT
            )

            # 로그인 폼 입력
            await self.page.fill('input[name="login_id"]', self.config.ETNEWS_USER_ID)
            await self.page.fill('input[name="login_pw"]', self.config.ETNEWS_PASSWORD)

            # 로그인 버튼 클릭
            await self.page.click('input[type="submit"]')

            # 페이지 로딩 대기
            await self.page.wait_for_load_state("networkidle", timeout=self.config.BROWSER_TIMEOUT)

            # 로그인 성공 확인 (PDF 페이지로 리다이렉트 확인)
            current_url = self.page.url
            if "pdf_today.html" in current_url or "pdf.etnews.com" in current_url:
                logger.info("로그인 성공")
                return True
            else:
                logger.error(f"로그인 실패: 예상치 못한 URL - {current_url}")
                return False

        except Exception as e:
            logger.error(f"로그인 중 오류 발생: {e}")
            return False

    async def check_subscription(self) -> bool:
        """PDF 서비스 구독 종료일 확인"""
        try:
            # 페이지 컨텐츠에서 구독 종료일 찾기
            content = await self.page.content()

            # "종료일은 YYYY년MM월DD일" 패턴 찾기
            import re
            match = re.search(r'종료일은\s*(\d{4})년(\d{2})월(\d{2})일', content)

            if match:
                year, month, day = match.groups()
                end_date_str = f"{year}-{month}-{day}"

                # 종료일과 현재 날짜 비교
                from datetime import datetime, timedelta
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
                today = datetime.now()
                days_left = (end_date - today).days

                logger.info(f"PDF 서비스 종료일: {end_date_str} (남은 일수: {days_left}일)")

                # 7일 이내 종료 시 경고
                if days_left <= 7:
                    logger.warning(f"⚠️  PDF 서비스 종료까지 {days_left}일 남았습니다. 갱신이 필요합니다!")
                elif days_left <= 0:
                    logger.error("❌ PDF 서비스가 종료되었습니다. 갱신이 필요합니다!")
                    return False

                return True
            else:
                logger.info("구독 종료일 정보를 찾을 수 없습니다.")
                return True

        except Exception as e:
            logger.warning(f"구독 정보 확인 중 오류: {e}")
            return True  # 오류가 있어도 계속 진행

    async def check_newspaper_availability(self) -> bool:
        """
        신문 발행 여부 확인

        Returns:
            bool: 신문이 발행된 경우 True, 미발행인 경우 False
        """
        try:
            # 페이지 HTML 가져오기
            content = await self.page.content()

            # "선택하신 날짜에는 신문이 발행되지 않았거나" 문구 확인
            if "선택하신 날짜에는 신문이 발행되지 않았거나" in content:
                logger.warning("신문이 발행되지 않은 날입니다")
                return False

            if "발행된 신문 원본이 없습니다" in content:
                logger.warning("발행된 신문 원본이 없습니다")
                return False

            logger.info("신문 발행 확인됨")
            return True

        except Exception as e:
            logger.error(f"신문 발행 여부 확인 중 오류: {e}")
            # 오류 시에는 True 반환 (다운로드 시도)
            return True

    async def get_page_info(self) -> List[Dict[str, str]]:
        """PDF 페이지 정보 수집 (광고 페이지 식별용)"""
        try:
            logger.info("PDF 페이지 정보 수집 중...")

            # 페이지 HTML 가져오기
            content = await self.page.content()
            soup = BeautifulSoup(content, "html.parser")

            page_info_list = []

            # 전자신문 PDF 페이지 구조 파싱
            # <dl class="clearfix"> 내의 <dt> 태그에서 페이지 정보 추출
            dl_elements = soup.find_all("dl", class_="clearfix")

            for dl in dl_elements:
                dt = dl.find("dt")
                if not dt:
                    continue

                title = dt.get_text(strip=True)

                # 페이지 번호 추출 ("6면 전면광고" -> "6")
                import re
                page_match = re.match(r'(\d+)면', title)
                if not page_match:
                    continue

                page_num = page_match.group(1)

                # 광고 페이지 여부 확인
                is_ad = "전면광고" in title or "광고" in title

                page_info = {
                    "page_number": page_num,
                    "title": title,
                    "is_ad": is_ad
                }

                page_info_list.append(page_info)
                logger.debug(f"페이지 {page_num}: {title} (광고: {is_ad})")

            logger.info(f"총 {len(page_info_list)}개 페이지 정보 수집 완료")

            # 광고 페이지 개수 로깅
            ad_count = sum(1 for p in page_info_list if p["is_ad"])
            logger.info(f"광고 페이지: {ad_count}개")

            return page_info_list

        except Exception as e:
            logger.warning(f"페이지 정보 수집 중 오류 (광고 자동 감지 불가): {e}")
            return []

    async def download_pdf(self) -> Tuple[str, List[Dict[str, str]]]:
        """
        PDF 다운로드 및 페이지 정보 반환

        Returns:
            (pdf_path, page_info_list): PDF 파일 경로와 페이지 정보 리스트

        Raises:
            ValueError: 신문이 발행되지 않은 날인 경우
        """
        try:
            # 신문 발행 여부 확인
            is_available = await self.check_newspaper_availability()
            if not is_available:
                raise ValueError("신문이 발행되지 않은 날입니다")

            # 페이지 정보 수집
            page_info = await self.get_page_info()

            # PDF 다운로드 설정
            download_dir = self.config.TEMP_DIR
            os.makedirs(download_dir, exist_ok=True)

            # 오늘 날짜 가져오기
            today = datetime.now().strftime("%Y%m%d")

            # 구독 종료일 확인
            await self.check_subscription()

            # 다운로드 페이지로 이동 (합본 PDF)
            download_url = f"https://pdf.etnews.com/download.html?ymd={today}&serial=T"
            logger.info(f"다운로드 페이지 접속: {download_url}")

            # 다운로드 이벤트 대기
            async with self.page.expect_download(timeout=self.config.DOWNLOAD_TIMEOUT * 1000) as download_info:
                # 다운로드 시작 (JavaScript로 페이지 이동)
                await self.page.evaluate(f'window.location.href = "{download_url}"')

            download = await download_info.value

            # 파일명 생성 (날짜 포함)
            filename = f"etnews_{today}.pdf"
            pdf_path = os.path.join(download_dir, filename)

            # 다운로드 완료 대기 및 저장
            await download.save_as(pdf_path)
            logger.info(f"PDF 다운로드 완료: {pdf_path}")

            return pdf_path, page_info

        except Exception as e:
            logger.error(f"PDF 다운로드 중 오류 발생: {e}")
            raise


async def download_etnews_pdf() -> Tuple[str, List[Dict[str, str]]]:
    """
    전자신문 PDF 다운로드 메인 함수

    Returns:
        (pdf_path, page_info_list): PDF 파일 경로와 페이지 정보 리스트
    """
    async with EtnewsScraper() as scraper:
        # 로그인
        login_success = await scraper.login()
        if not login_success:
            raise Exception("로그인 실패")

        # PDF 다운로드
        pdf_path, page_info = await scraper.download_pdf()
        return pdf_path, page_info


# 동기 래퍼 함수 (Azure Functions에서 사용)
def download_pdf_sync() -> Tuple[str, List[Dict[str, str]]]:
    """동기 방식으로 PDF 다운로드"""
    return asyncio.run(download_etnews_pdf())


if __name__ == "__main__":
    # 테스트
    try:
        pdf_path, page_info = download_pdf_sync()
        print(f"다운로드 완료: {pdf_path}")
        print(f"페이지 정보: {page_info}")
    except Exception as e:
        print(f"오류 발생: {e}")
