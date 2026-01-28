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
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO

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
    # 전체 콘텐츠 RSS 피드 (주간기술동향 포함)
    RSS_URL = "https://www.itfind.or.kr/ccenter/rss.do?codeAlias=all&rssType=02"  # RSS 2.0

    def __init__(self, headless: bool = True):
        """
        Args:
            headless: 브라우저 헤드리스 모드 (기본: True)
        """
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.playwright = None

    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입 - Playwright 및 브라우저 시작"""
        from playwright.async_api import async_playwright
        logger.info("Playwright 시작 중...")
        self.playwright = await async_playwright().start()
        logger.info("Chromium 브라우저 실행 중...")
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        logger.info(f"브라우저 실행 완료 (connected: {self.browser.is_connected()})")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료 - 브라우저 및 Playwright 정리"""
        if exc_type:
            logger.warning(f"컨텍스트 매니저 종료 (에러 발생): {exc_type.__name__}: {exc_val}")

        if self.browser:
            try:
                logger.info("브라우저 종료 중...")
                await self.browser.close()
                logger.info("브라우저 종료 완료")
            except Exception as e:
                logger.warning(f"브라우저 종료 실패: {e}")

        if self.playwright:
            try:
                logger.info("Playwright 정리 중...")
                await self.playwright.stop()
                logger.info("Playwright 정리 완료")
            except Exception as e:
                logger.warning(f"Playwright 정리 실패: {e}")

    def get_latest_weekly_trend_from_rss(self) -> Optional[WeeklyTrend]:
        """
        RSS 피드에서 최신 주간기술동향 정보 조회 (빠르고 안정적)

        Returns:
            WeeklyTrend: (제목, PDF URL, 토픽 리스트) 또는 None
        """
        try:
            logger.info(f"ITFIND RSS 피드 조회: {self.RSS_URL}")

            # RSS 피드 가져오기
            response = requests.get(self.RSS_URL, timeout=30)
            response.raise_for_status()

            # XML 파싱 (BytesIO 사용)
            tree = ET.parse(BytesIO(response.content))
            root = tree.getroot()

            # RSS 2.0 포맷: channel/item
            channel = root.find('channel')
            if not channel:
                logger.warning("RSS 피드에서 channel을 찾을 수 없습니다")
                return None

            items = channel.findall('item')
            logger.info(f"RSS 피드 항목 수: {len(items)}")

            #  디버깅: 첫 항목 확인
            if items:
                first = items[0]
                logger.info(f"첫 항목 - title elem: {first.find('title')}, link elem: {first.find('link')}")

            # 주간기술동향 항목 찾기
            for idx, item in enumerate(items):
                title_elem = item.find('title')
                link_elem = item.find('link')
                pub_date_elem = item.find('pubDate')
                description_elem = item.find('description')

                if title_elem is None or link_elem is None:
                    if idx < 3:
                        logger.info(f"항목 {idx+1} 스킵 - title_elem={title_elem}, link_elem={link_elem}")
                    continue

                title = title_elem.text
                link = link_elem.text

                # 디버깅: 처음 몇 개 항목의 값 확인
                if idx < 3:
                    logger.info(f"항목 {idx+1} - title type: {type(title)}, link type: {type(link)}")
                    logger.info(f"항목 {idx+1} - title value: {repr(title)}, link value: {repr(link)}")

                # None 체크 후 strip
                if not title or not link:
                    if idx >= len(items) - 5:
                        logger.info(f"항목 {idx+1}/{len(items)} 스킵 - title={title is not None}, link={link is not None}")
                    continue

                title = title.strip()
                link = link.strip()

                pub_date = pub_date_elem.text if pub_date_elem is not None else ''
                description = description_elem.text if description_elem is not None else ''

                # 디버깅: 마지막 5개 항목 로깅
                if idx >= len(items) - 5:
                    logger.info(f"RSS 항목 {idx+1}/{len(items)}: {title[:50]}...")

                # 주간기술동향인지 확인
                if '주간기술동향' not in title:
                    continue

                logger.info(f"주간기술동향 발견: {title}")

                # detail_id 추출 (링크에서)
                # RSS link 예: https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_1388
                # detail_id는 TVOL_ 다음의 숫자
                detail_id = ''
                if 'identifier=TVOL_' in link:
                    detail_id = link.split('identifier=TVOL_')[-1].split('&')[0]
                elif 'id=' in link:
                    detail_id = link.split('id=')[-1].split('&')[0]

                # 호수 추출
                import re
                issue_match = re.search(r'(\d{4})호', title)
                issue_number = issue_match.group(0) if issue_match else "N/A"

                # 발행일 파싱 (RFC 822 형식)
                # 예: "Tue, 28 Jan 2026 00:00:00 GMT"
                publish_date = ''
                if pub_date:
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(pub_date)
                        publish_date = dt.strftime('%Y-%m-%d')
                    except Exception as e:
                        logger.warning(f"발행일 파싱 실패: {e}")
                        publish_date = pub_date

                # PDF URL은 RSS link를 그대로 사용 (이미 PDF 다운로드 URL)
                pdf_url = link

                # 토픽은 RSS에 없으므로 빈 리스트 (필요시 상세 페이지 방문)
                topics = []

                return WeeklyTrend(
                    title=title,
                    issue_number=issue_number,
                    publish_date=publish_date,
                    pdf_url=pdf_url,
                    topics=topics,
                    detail_id=detail_id
                )

            logger.warning("RSS 피드에서 주간기술동향을 찾을 수 없습니다")
            return None

        except Exception as e:
            logger.error(f"RSS 피드 조회 실패: {e}", exc_info=True)
            return None

    async def get_latest_weekly_trend(self) -> Optional[WeeklyTrend]:
        """
        최신 주간기술동향 정보 조회
        1차: RSS 피드 조회 (빠르고 안정적)
        2차: 웹 스크래핑 (RSS 실패 시)

        Returns:
            WeeklyTrend: (제목, PDF URL, 토픽 리스트) 또는 None
        """
        # 1차: RSS 피드로 먼저 시도
        logger.info("1차 시도: RSS 피드로 주간기술동향 조회")
        trend = self.get_latest_weekly_trend_from_rss()

        if trend:
            logger.info("✅ RSS 피드로 주간기술동향 조회 성공")
            return trend

        # 2차: RSS 실패 시 웹 스크래핑
        logger.warning("RSS 조회 실패, 웹 스크래핑으로 재시도")

        if not self.browser:
            logger.error("브라우저가 없어 웹 스크래핑 불가")
            return None

        try:
            page = await self.browser.new_page()

            logger.info(f"ITFIND 목록 페이지 접속: {self.LIST_URL}")
            await page.goto(self.LIST_URL, wait_until="domcontentloaded", timeout=30000)

            # 페이지 로드 대기 (JavaScript 렌더링 대기)
            await page.wait_for_timeout(2000)

            # tbody의 모든 tr 조회
            all_rows = await page.query_selector_all('tbody tr')
            logger.info(f"전체 tbody tr 수: {len(all_rows)}")

            # 링크가 있는 첫 번째 tr 찾기 (헤더 스킵)
            first_row = None
            for row in all_rows:
                link = await row.query_selector('a')
                if link:
                    first_row = row
                    logger.info("링크가 있는 첫 번째 항목 발견")
                    break

            if not first_row:
                logger.warning(f"ITFIND 목록에서 링크가 있는 항목을 찾을 수 없습니다")
                return None

            # 제목과 링크 추출 (여러 셀렉터 시도)
            title_link = None
            link_selectors = ['td.tit a', 'td a', 'a']

            for selector in link_selectors:
                title_link = await first_row.query_selector(selector)
                if title_link:
                    break

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

            weekly_trend = WeeklyTrend(
                title=title.strip(),
                issue_number=issue_number,
                publish_date=publish_date,
                pdf_url=pdf_url,
                topics=topics,
                detail_id=detail_id
            )

            # 페이지 정리
            await page.close()
            return weekly_trend

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

    def download_weekly_pdf_simple(
        self,
        pdf_url: str,
        save_path: str
    ) -> str:
        """
        주간기술동향 PDF 간단 다운로드 (브라우저 불필요)

        Args:
            pdf_url: PDF 다운로드 URL (RSS에서 얻은 URL)
            save_path: 저장 경로

        Returns:
            str: 다운로드된 PDF 파일 경로

        Raises:
            Exception: 다운로드 실패 시
        """
        try:
            logger.info(f"ITFIND PDF 간단 다운로드 시작: {pdf_url}")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
                'Referer': 'https://www.itfind.or.kr/'
            }

            response = requests.get(pdf_url, headers=headers, timeout=60, stream=True)
            response.raise_for_status()

            content = response.content
            content_type = response.headers.get('content-type', '').lower()

            # PDF 검증
            if content[:5] != b'%PDF-':
                logger.warning(f"응답이 PDF가 아닙니다: content-type={content_type}, size={len(content)}")
                raise ValueError("Downloaded file is not a PDF")

            # 파일 저장
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'wb') as f:
                f.write(content)

            file_size = os.path.getsize(save_path)
            logger.info(f"✅ ITFIND PDF 간단 다운로드 성공: {file_size:,} bytes")

            return save_path

        except Exception as e:
            logger.error(f"ITFIND PDF 간단 다운로드 실패: {e}")
            raise

    async def download_weekly_pdf(
        self,
        pdf_url: str,
        save_path: str,
        detail_url: Optional[str] = None
    ) -> str:
        """
        주간기술동향 PDF 다운로드

        Args:
            pdf_url: PDF 다운로드 URL
            save_path: 저장 경로 (/tmp/itfind_weekly_{date}.pdf)
            detail_url: 상세 페이지 URL (쿠키/세션 설정용, Optional)

        Returns:
            str: 다운로드된 PDF 파일 경로

        Raises:
            Exception: 다운로드 실패 시
        """
        if not self.browser:
            raise RuntimeError("ItfindScraper must be used as async context manager (async with)")

        # 브라우저 연결 상태 확인
        try:
            if not self.browser.is_connected():
                logger.error("브라우저 연결이 끊어졌습니다")
                raise RuntimeError("Browser connection lost")
        except Exception as check_error:
            logger.warning(f"브라우저 상태 확인 실패: {check_error}")

        try:
            logger.info(f"ITFIND PDF 다운로드 시작: {pdf_url}")

            # 방법 0: PDF URL 직접 다운로드 시도 (가장 간단한 방법)
            # getStreamDocsRegi.htm URL을 getFile.htm으로 변환
            if 'getStreamDocsRegi.htm?identifier=TVOL_' in pdf_url:
                # TVOL_1388 → 파일 다운로드용 identifier로 변환
                identifier = pdf_url.split('identifier=TVOL_')[-1].split('&')[0]

                # 방법 0-1: 상세 페이지에서 직접 다운로드 링크 찾기
                if detail_url:
                    logger.info(f"상세 페이지에서 직접 다운로드 링크 찾기: {detail_url}")
                    page = await self.browser.new_page()
                    await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(1000)

                    # 상세 페이지에서 PDF 다운로드 링크 찾기 (여러 셀렉터 시도)
                    direct_pdf_selectors = [
                        'a[href*="getFile.htm"]',
                        'a[href*="getStreamDocsRegi"]',
                        'a.btn_download',
                        'a:has-text("다운로드")',
                        'a:has-text("원문보기")'
                    ]

                    direct_pdf_link = None
                    for selector in direct_pdf_selectors:
                        direct_pdf_link = await page.query_selector(selector)
                        if direct_pdf_link:
                            direct_pdf_url = await direct_pdf_link.get_attribute('href')
                            if direct_pdf_url:
                                if direct_pdf_url.startswith('/'):
                                    direct_pdf_url = f"{self.BASE_URL}{direct_pdf_url}"
                                logger.info(f"직접 다운로드 URL 발견: {direct_pdf_url}")

                                # 직접 URL로 다운로드 시도
                                try:
                                    context = page.context
                                    cookies = await context.cookies()

                                    session = requests.Session()
                                    for cookie in cookies:
                                        session.cookies.set(cookie['name'], cookie['value'])

                                    headers = {
                                        'User-Agent': 'Mozilla/5.0',
                                        'Referer': detail_url,
                                        'Accept': 'application/pdf,*/*'
                                    }

                                    logger.info(f"직접 URL로 다운로드 시도: {direct_pdf_url}")
                                    response = session.get(direct_pdf_url, headers=headers, timeout=60, stream=True)
                                    response.raise_for_status()

                                    # PDF 응답인지 확인
                                    content_type = response.headers.get('content-type', '').lower()
                                    if 'application/pdf' in content_type or response.content[:5] == b'%PDF-':
                                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                                        with open(save_path, 'wb') as f:
                                            f.write(response.content)

                                        file_size = os.path.getsize(save_path)
                                        logger.info(f"✅ 직접 다운로드 성공: {file_size:,} bytes")

                                        await page.close()
                                        return save_path
                                    else:
                                        logger.warning(f"응답이 PDF가 아님: {content_type}")

                                except Exception as direct_error:
                                    logger.warning(f"직접 다운로드 실패: {direct_error}")
                                    break

                    await page.close()

            # 새 페이지에서 StreamDocs 뷰어를 통해 PDF 다운로드
            page = await self.browser.new_page()

            # 상세 페이지 먼저 방문 (세션 유지)
            if detail_url:
                logger.info(f"상세 페이지 먼저 방문: {detail_url}")
                await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1000)

            # StreamDocs 뷰어 페이지로 이동하면서 모든 네트워크 요청 캡처
            logger.info("StreamDocs 뷰어 페이지로 이동")

            # 네트워크 요청 중 PDF 찾기 (페이지 로드 전에 리스너 등록)
            pdf_bytes = None
            all_pdf_requests = []  # 모든 PDF 관련 요청 저장

            async def capture_all_responses(response):
                """모든 응답을 캡처하여 PDF 찾기"""
                try:
                    url = response.url
                    content_type = response.headers.get('content-type', '').lower()

                    # PDF 응답 또는 PDF 관련 요청 로깅
                    if 'pdf' in content_type or 'pdf' in url.lower() or 'stream' in url.lower():
                        logger.info(f"PDF 관련 응답: {url}, content-type: {content_type}")
                        all_pdf_requests.append({'url': url, 'content_type': content_type, 'response': response})

                    if 'application/pdf' in content_type:
                        nonlocal pdf_bytes
                        try:
                            pdf_bytes = await response.body()
                            logger.info(f"✅ PDF 응답 자동 캡처: {url}, 크기: {len(pdf_bytes)} bytes")
                        except Exception as body_error:
                            logger.warning(f"PDF 바디 읽기 실패: {body_error}")

                except Exception as e:
                    # 응답 처리 중 에러는 무시 (계속 진행)
                    pass

            page.on('response', capture_all_responses)

            await page.goto(pdf_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(5000)  # PDF 로딩 대기 시간 증가

            # 캡처된 PDF가 있는지 확인
            if pdf_bytes:
                logger.info(f"페이지 로드 중 PDF 자동 캡처 완료: {len(pdf_bytes)} bytes")
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'wb') as f:
                    f.write(pdf_bytes)

                # PDF 헤더 검증
                with open(save_path, 'rb') as f:
                    if f.read(5) == b'%PDF-':
                        logger.info("PDF 파일 검증 성공")
                        await page.close()
                        return save_path

            # StreamDocs 문서 ID 추출 (URL에서)
            streamdocs_id = None
            for req in all_pdf_requests:
                if 'streamdocs/view/sd;streamdocsId=' in req['url']:
                    streamdocs_id = req['url'].split('streamdocsId=')[-1].split('&')[0].split('#')[0]
                    logger.info(f"StreamDocs 문서 ID 추출: {streamdocs_id}")
                    break
                elif '/streamdocs/v4/documents/' in req['url']:
                    # v4 API URL에서 직접 추출
                    parts = req['url'].split('/streamdocs/v4/documents/')[-1].split('/')[0]
                    if parts and not streamdocs_id:
                        streamdocs_id = parts
                        logger.info(f"StreamDocs 문서 ID 추출 (v4 API): {streamdocs_id}")

            # StreamDocs API로 PDF 다운로드 시도
            if streamdocs_id:
                context = page.context
                cookies = await context.cookies()
                session = requests.Session()
                for cookie in cookies:
                    session.cookies.set(cookie['name'], cookie['value'])

                # 여러 PDF 다운로드 URL 패턴 시도
                pdf_download_urls = [
                    # 직접 documents/{id} 접근
                    f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}",
                    # 다운로드 엔드포인트
                    f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}/download",
                    f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}/pdf",
                    f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}/original",
                    # 파라미터 방식
                    f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}?format=pdf",
                    f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}?download=true",
                ]

                for download_url in pdf_download_urls:
                    try:
                        logger.info(f"StreamDocs PDF 다운로드 시도: {download_url}")
                        headers = {
                            'User-Agent': 'Mozilla/5.0',
                            'Referer': pdf_url,
                            'Accept': 'application/pdf,application/octet-stream,*/*'
                        }
                        response = session.get(download_url, headers=headers, timeout=30, stream=True)

                        # PDF인지 확인 (헤더 또는 content-type)
                        if response.status_code == 200:
                            content_type = response.headers.get('content-type', '').lower()
                            content_length = response.headers.get('content-length', '0')

                            # 응답 바디 읽기
                            content = response.content
                            is_pdf = 'application/pdf' in content_type or content[:5] == b'%PDF-'

                            logger.info(f"  응답: status={response.status_code}, content-type={content_type}, size={len(content)} bytes")

                            if is_pdf:
                                pdf_bytes = content
                                logger.info(f"✅ StreamDocs API로 PDF 다운로드 성공: {len(pdf_bytes)} bytes")
                                break
                            elif len(content) > 1000000:  # 1MB 이상이면 PDF일 가능성
                                logger.info(f"큰 파일 발견 ({len(content)} bytes), PDF 헤더 체크")
                                if content[:5] == b'%PDF-':
                                    pdf_bytes = content
                                    logger.info(f"✅ PDF 헤더 확인으로 다운로드 성공: {len(pdf_bytes)} bytes")
                                    break

                    except Exception as api_error:
                        logger.warning(f"StreamDocs API 다운로드 실패: {api_error}")

            # PDF 다운로드 성공 시 저장
            if pdf_bytes:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'wb') as f:
                    f.write(pdf_bytes)

                await page.close()
                return save_path

            # 방법 1: 좌측 상단 메뉴 > 하위 메뉴 > PDF 다운로드 버튼 클릭
            try:
                logger.info("메뉴 버튼 찾기")

                # PDF 응답 캡처를 위한 리스너 등록 (클릭 전에!)
                pdf_response_url = None
                pdf_response_body = None
                download_captured = None

                async def capture_pdf_response(response):
                    nonlocal pdf_response_url, pdf_response_body
                    content_type = response.headers.get('content-type', '').lower()
                    if 'application/pdf' in content_type:
                        pdf_response_url = response.url
                        logger.info(f"PDF 응답 캡처: {pdf_response_url}")
                        try:
                            pdf_response_body = await response.body()
                            logger.info(f"PDF 바디 캡처 완료: {len(pdf_response_body)} bytes")
                        except Exception as e:
                            logger.warning(f"PDF 바디 캡처 실패: {e}")

                page.on('response', capture_pdf_response)

                # StreamDocs 툴바의 메뉴 버튼
                menu_selectors = [
                    'sd-toolbar pu-menu',
                    'pu-menu',
                    'button[title*="메뉴"]',
                    'sd-toolbar button'
                ]

                menu_button = None
                for selector in menu_selectors:
                    menu_button = await page.query_selector(selector)
                    if menu_button:
                        logger.info(f"메뉴 발견: {selector}")
                        break

                if menu_button:
                    # 메뉴 클릭하여 하위 메뉴 열기
                    logger.info("pu-menu 클릭하여 하위 메뉴 열기")
                    await menu_button.click(force=True)
                    await page.wait_for_timeout(1500)

                    # pu-menu 내부의 "PDF 다운로드" 메뉴 아이템 찾기
                    # HTML: <div class="menu-item"><span class="menu-item__text">PDF 다운로드</span></div>
                    logger.info("pu-menu 내부에서 'PDF 다운로드' 메뉴 아이템 찾기")

                    # pu-menu 내부 HTML 확인
                    menu_html = await menu_button.inner_html()
                    logger.info(f"pu-menu HTML (처음 200자): {menu_html[:200]}")

                    # .menu-item 중에서 "PDF 다운로드" 텍스트가 있는 것 찾기
                    menu_items = await menu_button.query_selector_all('.menu-item')
                    logger.info(f"menu-item 수: {len(menu_items)}")

                    pdf_download_item = None
                    for item in menu_items:
                        # inner_text() 대신 text_content() 사용
                        text = await item.text_content()
                        logger.info(f"menu-item 텍스트 (text_content): '{text}'")

                        # 또는 내부 span 직접 확인
                        span = await item.query_selector('.menu-item__text')
                        if span:
                            span_text = await span.text_content()
                            logger.info(f"  span.menu-item__text 텍스트: '{span_text}'")
                            # "PDF 다운로드" 또는 "PDF Download"
                            if span_text and 'PDF' in span_text and ('다운로드' in span_text or 'Download' in span_text):
                                pdf_download_item = item
                                logger.info(f"✓ PDF 다운로드 메뉴 아이템 발견: '{span_text}'")
                                break

                    if pdf_download_item:
                        logger.info("PDF 다운로드 메뉴 아이템 클릭")

                        # 다운로드 이벤트와 PDF 응답 동시 대기
                        try:
                            async with page.expect_download(timeout=8000) as download_info:
                                await pdf_download_item.click(force=True)
                                download_captured = await download_info.value

                            # 다운로드 이벤트로 PDF 저장
                            logger.info(f"✅ 다운로드 이벤트 캡처 성공: {download_captured.suggested_filename}")
                            os.makedirs(os.path.dirname(save_path), exist_ok=True)
                            await download_captured.save_as(save_path)

                            file_size = os.path.getsize(save_path)
                            logger.info(f"PDF 파일 저장 완료: {file_size:,} bytes")

                            # PDF 헤더 검증
                            with open(save_path, 'rb') as f:
                                if f.read(5) == b'%PDF-':
                                    logger.info("PDF 파일 검증 성공")
                                    await page.close()
                                    return save_path
                                else:
                                    logger.error("저장된 파일이 PDF가 아닙니다")

                        except Exception as download_error:
                            logger.warning(f"다운로드 이벤트 실패: {download_error}, PDF 응답 캡처 확인")

                            # 다운로드 이벤트 실패 시 PDF 응답 확인
                            await page.wait_for_timeout(5000)  # PDF 응답 대기

                            if pdf_response_body:
                                logger.info(f"✅ PDF 응답 캡처 성공: {len(pdf_response_body)} bytes")
                                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                                with open(save_path, 'wb') as f:
                                    f.write(pdf_response_body)

                                with open(save_path, 'rb') as f:
                                    if f.read(5) == b'%PDF-':
                                        logger.info("PDF 파일 검증 성공")
                                        await page.close()
                                        return save_path
                                    else:
                                        logger.error("저장된 파일이 PDF가 아닙니다")
                            else:
                                logger.warning("PDF 응답을 캡처하지 못했습니다")
                    else:
                        logger.warning("'PDF 다운로드' 메뉴 아이템을 찾을 수 없습니다")

            except Exception as menu_error:
                logger.warning(f"메뉴 방식 실패: {menu_error}")

            # 방법 2: 네트워크 요청 캡처
            if not pdf_bytes:
                logger.info("네트워크 요청에서 PDF 찾기")

                # 페이지 새로고침하면서 PDF 요청 캡처
                pdf_request_url = None

                async def capture_pdf_request(response):
                    nonlocal pdf_request_url
                    content_type = response.headers.get('content-type', '').lower()
                    if 'application/pdf' in content_type:
                        pdf_request_url = response.url
                        logger.info(f"PDF 요청 발견: {pdf_request_url}")

                page.on('response', capture_pdf_request)
                await page.reload(wait_until="networkidle")
                await page.wait_for_timeout(3000)

                if pdf_request_url:
                    # 발견한 PDF URL로 다시 다운로드
                    logger.info(f"발견한 PDF URL로 다운로드: {pdf_request_url}")
                    context = page.context
                    cookies = await context.cookies()

                    session = requests.Session()
                    for cookie in cookies:
                        session.cookies.set(cookie['name'], cookie['value'])

                    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': self.BASE_URL}
                    response = session.get(pdf_request_url, headers=headers, timeout=60, stream=True)
                    response.raise_for_status()
                    pdf_bytes = response.content
                else:
                    raise ValueError("PDF 다운로드 URL을 찾을 수 없습니다")

            await page.close()

            # 파일 저장 (방법 2에서 pdf_bytes가 있는 경우)
            if pdf_bytes:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'wb') as f:
                    f.write(pdf_bytes)

                file_size = os.path.getsize(save_path)
                logger.info(f"ITFIND PDF 다운로드 완료: {save_path} ({file_size:,} bytes)")

                # PDF 파일 유효성 간단 체크
                if file_size < 10000:
                    logger.warning(f"PDF 파일 크기가 너무 작습니다: {file_size} bytes")

                # PDF 헤더 확인
                with open(save_path, 'rb') as f:
                    header = f.read(5)
                    if header != b'%PDF-':
                        raise ValueError("다운로드된 파일이 PDF가 아닙니다")

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
