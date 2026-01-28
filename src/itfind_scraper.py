#!/usr/bin/env python3
"""
ITFIND 주간기술동향 스크래퍼

정보통신기획평가원(IITP)의 주간기술동향 PDF를 다운로드하고 정보를 추출합니다.
https://www.itfind.or.kr/trend/weekly/weekly.do
"""
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional, List
from playwright.async_api import async_playwright, Page, Browser
import requests

logger = logging.getLogger(__name__)


@dataclass
class WeeklyTrend:
    """주간기술동향 정보"""
    title: str                # 제목 (예: "AI-Ready 산업 생태계...")
    issue_number: str         # 호수 (예: "2203호")
    publish_date: str         # 발행일 (YYYY-MM-DD)
    pdf_url: str              # PDF 다운로드 URL
    topics: List[str]         # 주요 토픽 리스트
    detail_id: str            # 상세 페이지 ID (예: "1388")


class ItfindScraper:
    """ITFIND 주간기술동향 스크래퍼"""

    BASE_URL = "https://www.itfind.or.kr"
    LIST_URL = f"{BASE_URL}/trend/weekly/weekly.do"

    def __init__(self, headless: bool = True):
        """
        Args:
            headless: 브라우저 헤드리스 모드 (기본: True)
        """
        self.headless = headless
        self.browser: Optional[Browser] = None

    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료 - 브라우저 정리"""
        if self.browser:
            await self.browser.close()

    async def get_latest_weekly_trend(self) -> Optional[WeeklyTrend]:
        """
        최신 주간기술동향 정보 조회

        Returns:
            WeeklyTrend: (제목, PDF URL, 토픽 리스트) 또는 None
        """
        try:
            async with async_playwright() as p:
                self.browser = await p.chromium.launch(headless=self.headless)
                page = await self.browser.new_page()

                logger.info(f"ITFIND 목록 페이지 접속: {self.LIST_URL}")
                await page.goto(self.LIST_URL, wait_until="domcontentloaded", timeout=30000)

                # 최신 항목 추출 (첫 번째 tr)
                first_row = await page.query_selector('table.tbl_basic tbody tr:first-child')
                if not first_row:
                    logger.warning("ITFIND 목록에서 항목을 찾을 수 없습니다")
                    return None

                # 제목과 링크 추출
                title_link = await first_row.query_selector('td.tit a')
                if not title_link:
                    logger.warning("제목 링크를 찾을 수 없습니다")
                    return None

                title = await title_link.inner_text()
                detail_url = await title_link.get_attribute('href')

                if not detail_url:
                    logger.warning("상세 페이지 URL을 찾을 수 없습니다")
                    return None

                # detail_id 추출 (예: weeklyDetail.do?id=1388 → 1388)
                detail_id = detail_url.split('id=')[-1] if 'id=' in detail_url else ''

                # 발행일 추출
                date_cell = await first_row.query_selector('td:nth-child(3)')
                publish_date = await date_cell.inner_text() if date_cell else ''
                publish_date = publish_date.strip()

                logger.info(f"최신 주간기술동향 발견: {title} ({publish_date})")

                # 상세 페이지 이동
                detail_full_url = f"{self.BASE_URL}{detail_url}" if detail_url.startswith('/') else detail_url
                logger.info(f"상세 페이지 접속: {detail_full_url}")
                await page.goto(detail_full_url, wait_until="domcontentloaded", timeout=30000)

                # PDF 다운로드 링크 추출
                pdf_link = await page.query_selector('a[href*="getStreamDocsRegi"]')
                if not pdf_link:
                    logger.warning("PDF 다운로드 링크를 찾을 수 없습니다")
                    return None

                pdf_url = await pdf_link.get_attribute('href')
                if pdf_url and pdf_url.startswith('/'):
                    pdf_url = f"{self.BASE_URL}{pdf_url}"

                logger.info(f"PDF URL: {pdf_url}")

                # 주요 토픽 추출 (상세 페이지의 본문에서)
                topics = await self._extract_topics(page)

                # 호수 추출 (제목에서 "NNNN호" 패턴 찾기)
                import re
                issue_match = re.search(r'(\d{4})호', title)
                issue_number = issue_match.group(0) if issue_match else "N/A"

                return WeeklyTrend(
                    title=title.strip(),
                    issue_number=issue_number,
                    publish_date=publish_date,
                    pdf_url=pdf_url,
                    topics=topics,
                    detail_id=detail_id
                )

        except Exception as e:
            logger.error(f"ITFIND 최신 주간기술동향 조회 실패: {e}", exc_info=True)
            return None

    async def _extract_topics(self, page: Page) -> List[str]:
        """
        상세 페이지에서 주요 토픽 추출

        Args:
            page: Playwright 페이지 객체

        Returns:
            List[str]: 토픽 리스트 (최대 5개)
        """
        topics = []
        try:
            # 본문 영역에서 <li> 또는 <p> 태그의 주요 토픽 찾기
            # ITFIND 사이트 구조에 따라 셀렉터 조정 필요
            content_area = await page.query_selector('.view_cont, .view_area, .cont_view')

            if content_area:
                # <li> 태그에서 토픽 추출
                list_items = await content_area.query_selector_all('li')
                for item in list_items[:5]:  # 최대 5개
                    text = await item.inner_text()
                    text = text.strip()
                    if text and len(text) > 10:  # 최소 길이 체크
                        topics.append(text)

                # <li>가 없으면 <p> 태그에서 추출
                if not topics:
                    paragraphs = await content_area.query_selector_all('p')
                    for p in paragraphs[:5]:
                        text = await p.inner_text()
                        text = text.strip()
                        if text and len(text) > 10:
                            topics.append(text)

            logger.info(f"추출된 토픽 수: {len(topics)}")

        except Exception as e:
            logger.warning(f"토픽 추출 실패: {e}")

        return topics[:5]  # 최대 5개만 반환

    async def download_weekly_pdf(
        self,
        pdf_url: str,
        save_path: str
    ) -> str:
        """
        주간기술동향 PDF 다운로드

        Args:
            pdf_url: PDF 다운로드 URL
            save_path: 저장 경로 (/tmp/itfind_weekly_{date}.pdf)

        Returns:
            str: 다운로드된 PDF 파일 경로

        Raises:
            Exception: 다운로드 실패 시
        """
        try:
            logger.info(f"ITFIND PDF 다운로드 시작: {pdf_url}")

            # requests로 다운로드 (Playwright보다 빠름)
            response = requests.get(pdf_url, timeout=60, stream=True)
            response.raise_for_status()

            # 파일 저장
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = os.path.getsize(save_path)
            logger.info(f"ITFIND PDF 다운로드 완료: {save_path} ({file_size:,} bytes)")

            return save_path

        except Exception as e:
            logger.error(f"ITFIND PDF 다운로드 실패: {e}", exc_info=True)
            raise


async def main():
    """테스트용 메인 함수"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async with ItfindScraper(headless=True) as scraper:
        # 최신 주간기술동향 조회
        trend = await scraper.get_latest_weekly_trend()

        if trend:
            print("\n=== 최신 주간기술동향 ===")
            print(f"제목: {trend.title}")
            print(f"호수: {trend.issue_number}")
            print(f"발행일: {trend.publish_date}")
            print(f"PDF URL: {trend.pdf_url}")
            print(f"상세 ID: {trend.detail_id}")
            print(f"\n주요 토픽:")
            for i, topic in enumerate(trend.topics, 1):
                print(f"  {i}. {topic}")

            # PDF 다운로드 테스트
            save_path = f"/tmp/itfind_weekly_test.pdf"
            await scraper.download_weekly_pdf(trend.pdf_url, save_path)
            print(f"\nPDF 다운로드 완료: {save_path}")

        else:
            print("주간기술동향을 찾을 수 없습니다")


if __name__ == '__main__':
    asyncio.run(main())
