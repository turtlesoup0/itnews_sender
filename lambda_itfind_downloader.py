#!/usr/bin/env python3
"""
ITFIND 주간기술동향 PDF 다운로드 Lambda 함수

매주 수요일 메인 Lambda에서 호출:
1. 최신 주간기술동향 조회 (RSS)
2. PDF 다운로드 (브라우저 없이!)
3. base64로 인코딩하여 반환
"""
import logging
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import base64

# 로컬 개발 환경에서 src 디렉토리를 PYTHONPATH에 추가
if os.path.exists('/var/task/src'):
    sys.path.insert(0, '/var/task/src')
elif os.path.exists('./src'):
    sys.path.insert(0, './src')

from src.itfind_scraper import ItfindScraper
import requests
import xml.etree.ElementTree as ET
import re

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_latest_weekly_trend_from_rss():
    """
    RSS 피드에서 최신 주간기술동향 정보 조회 (브라우저 불필요)

    Returns:
        dict: {'title': str, 'issue_number': str, 'publish_date': str, 'pdf_url': str, 'detail_id': str}
    """
    try:
        rss_url = "https://www.itfind.or.kr/ccenter/rss.do?codeAlias=all&rssType=02"
        logger.info(f"RSS 피드 조회: {rss_url}")

        response = requests.get(rss_url, timeout=30)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        items = root.findall('.//item')

        logger.info(f"RSS 피드 항목 수: {len(items)}")

        # 첫 번째 주간기술동향의 호수 찾기
        target_issue_number = None
        topics = []
        first_detail_id = None
        first_pdf_url = None

        for item in items:
            title_elem = item.find('title')
            link_elem = item.find('link')

            if title_elem is None or link_elem is None:
                continue

            title = title_elem.text
            link = link_elem.text

            # 주간기술동향 필터링
            if not title or '[주간기술동향' not in title:
                continue

            # 호수 추출
            issue_match = re.search(r'\[주간기술동향\s+(\d+)호\]', title)
            if not issue_match:
                continue

            issue_number = issue_match.group(1)

            # 첫 번째 주간기술동향의 호수 저장
            if target_issue_number is None:
                target_issue_number = issue_number
                logger.info(f"✅ 주간기술동향 발견: {title} ({issue_number}호)")

                # detail_id 추출 (첫 번째 것만 사용)
                detail_id_match = re.search(r'identifier=([\w-]+)', link)
                first_detail_id = detail_id_match.group(1).replace('TVOL_', '') if detail_id_match else None

                if first_detail_id:
                    first_pdf_url = f"https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_{first_detail_id}"
                else:
                    first_pdf_url = link.replace('http://', 'https://')

            # 같은 호수의 모든 토픽 수집
            if issue_number == target_issue_number:
                # 제목에서 토픽 추출 (호수 부분 제거)
                topic = re.sub(r'\s*\[주간기술동향\s+\d+호\]', '', title).strip()
                if topic:
                    topics.append(topic)
                    logger.info(f"   토픽 추가: {topic}")

        if target_issue_number and first_detail_id:
            # 발행일 (현재 날짜로 근사)
            kst = timezone(timedelta(hours=9))
            publish_date = datetime.now(kst).strftime("%Y-%m-%d")

            # 첫 번째 토픽을 대표 제목으로 사용
            main_title = topics[0] if topics else f"주간기술동향 {target_issue_number}호"

            return {
                'title': main_title,  # 첫 번째 토픽 (호수 제외)
                'issue_number': target_issue_number,
                'publish_date': publish_date,
                'pdf_url': first_pdf_url,
                'detail_id': first_detail_id,
                'topics': topics  # 모든 토픽 리스트
            }

        logger.warning("RSS 피드에서 주간기술동향을 찾을 수 없습니다")
        return None

    except Exception as e:
        logger.error(f"RSS 피드 조회 실패: {e}")
        return None


def extract_streamdocs_id_from_detail_page(detail_id: str) -> Optional[str]:
    """
    getStreamDocsRegi.htm에서 StreamDocs 뷰어 URL을 따라가 StreamDocs ID 추출

    Args:
        detail_id: TVOL을 제외한 ID (예: "1388")

    Returns:
        StreamDocs ID 또는 None
    """
    try:
        # 1단계: getStreamDocsRegi.htm 페이지 접근
        streamdocs_regi_url = f"https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_{detail_id}"
        logger.info(f"StreamDocs Regi 페이지 접근: {streamdocs_regi_url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "*/*",
            "Referer": "https://www.itfind.or.kr/",
        }

        session = requests.Session()
        response = session.get(streamdocs_regi_url, headers=headers, timeout=30, allow_redirects=True)

        # JavaScript 리다이렉트 URL 추출
        # 패턴: top.location.href="https://www.itfind.or.kr/publication/.../view.do?..."
        js_redirect_match = re.search(r'location\.href\s*=\s*["\']([^"\']+)["\']', response.text)

        if js_redirect_match:
            redirect_url = js_redirect_match.group(1)
            logger.info(f"JavaScript 리다이렉트 URL 발견: {redirect_url}")

            # 2단계: 리다이렉트된 페이지 접근 (자동으로 StreamDocs 뷰어로 redirect됨)
            if not redirect_url.startswith('http'):
                redirect_url = f"https://www.itfind.or.kr{redirect_url}"

            response2 = session.get(redirect_url, headers=headers, timeout=30, allow_redirects=True)

            logger.info(f"최종 URL: {response2.url}")

            # 3단계: 최종 URL에서 StreamDocs ID 추출
            # 패턴: https://www.itfind.or.kr/streamdocs/view/sd;streamdocsId=RtkNUpG5UfML1iXVCbU0-QqbinAUTQxwz58xRm02GRs
            if 'streamdocsId=' in response2.url:
                match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response2.url)
                if match:
                    streamdocs_id = match.group(1)
                    logger.info(f"✅ StreamDocs ID 추출 성공 (최종 URL): {streamdocs_id}")
                    return streamdocs_id

            # 4단계: HTML에서도 검색
            match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response2.text)
            if match:
                streamdocs_id = match.group(1)
                logger.info(f"✅ StreamDocs ID 추출 성공 (HTML): {streamdocs_id}")
                return streamdocs_id

        logger.warning("StreamDocs ID를 찾을 수 없습니다")
        return None

    except Exception as e:
        logger.error(f"StreamDocs ID 추출 실패: {e}", exc_info=True)
        return None


def download_pdf_direct(streamdocs_id: str, save_path: str) -> bool:
    """
    StreamDocs API를 직접 호출하여 PDF 다운로드 (브라우저 불필요)

    Args:
        streamdocs_id: StreamDocs 문서 ID
        save_path: 저장할 파일 경로

    Returns:
        성공 여부
    """
    try:
        # StreamDocs v4 API 직접 호출
        api_url = f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}"
        logger.info(f"StreamDocs API 직접 호출: {api_url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/pdf,*/*',
            'Referer': 'https://www.itfind.or.kr/'
        }

        response = requests.get(api_url, headers=headers, timeout=60, stream=True)
        response.raise_for_status()

        # PDF인지 확인 (Content-Type은 application/octet-stream일 수 있음)
        content_type = response.headers.get('content-type', '').lower()
        logger.info(f"Content-Type: {content_type}")

        # PDF 시그니처로 확인 (가장 확실함)
        first_chunk = next(response.iter_content(5), b'')
        if first_chunk[:5] != b'%PDF-':
            logger.error(f"응답이 PDF가 아닙니다: content-type={content_type}, 시그니처={first_chunk[:5]}")
            return False

        logger.info(f"✅ PDF 시그니처 확인됨: {first_chunk[:5]}")

        # 파일 저장
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)

        with open(save_path, 'wb') as f:
            # 이미 읽은 첫 청크가 있다면 먼저 쓰기
            if 'first_chunk' in locals():
                f.write(first_chunk)

            # 나머지 다운로드
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        file_size = os.path.getsize(save_path)
        logger.info(f"✅ PDF 다운로드 완료: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
        return True

    except Exception as e:
        logger.error(f"PDF 다운로드 실패: {e}")
        return False


async def download_itfind_pdf() -> Optional[Dict[str, Any]]:
    """
    ITFIND 주간기술동향 PDF 다운로드 (브라우저 없이!)

    Returns:
        Dict: {
            'title': str,
            'issue_number': str,
            'publish_date': str,
            'filename': str,
            'file_size': int,
            'streamdocs_id': str,
            'pdf_base64': str  # base64 인코딩된 PDF 데이터
        } or None
    """
    try:
        logger.info("=" * 60)
        logger.info("ITFIND 주간기술동향 PDF 다운로드 시작 (브라우저 없이)")
        logger.info("=" * 60)

        # 1. RSS에서 최신 주간기술동향 정보 조회
        logger.info("1단계: RSS 피드에서 최신 주간기술동향 조회")
        trend = get_latest_weekly_trend_from_rss()

        if not trend:
            logger.warning("주간기술동향을 찾을 수 없습니다")
            return None

        logger.info(f"✅ 주간기술동향 발견: {trend['title']} ({trend['issue_number']}호)")
        logger.info(f"   발행일: {trend['publish_date']}")
        logger.info(f"   Detail ID: {trend['detail_id']}")

        # 2. 상세 페이지에서 StreamDocs ID 추출
        logger.info("2단계: 상세 페이지에서 StreamDocs ID 추출")
        streamdocs_id = extract_streamdocs_id_from_detail_page(trend['detail_id'])

        if not streamdocs_id:
            logger.error("StreamDocs ID를 추출할 수 없습니다")
            return None

        # 3. StreamDocs API로 PDF 직접 다운로드
        logger.info("3단계: StreamDocs API로 PDF 다운로드")
        kst = timezone(timedelta(hours=9))
        today_str = datetime.now(kst).strftime("%Y%m%d")
        local_path = f"/tmp/itfind_weekly_{today_str}.pdf"

        if not download_pdf_direct(streamdocs_id, local_path):
            logger.error("PDF 다운로드 실패")
            return None

        file_size = os.path.getsize(local_path)

        # 4. PDF를 base64로 인코딩하여 반환 (S3 불필요!)
        logger.info("4단계: PDF base64 인코딩")
        with open(local_path, 'rb') as f:
            pdf_data = f.read()
            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')

        logger.info("=" * 60)
        logger.info("✅ ITFIND PDF 다운로드 성공")
        logger.info("=" * 60)

        return {
            'title': trend['title'],
            'issue_number': trend['issue_number'],
            'publish_date': trend['publish_date'],
            'filename': f"ITFIND_주간기술동향_{trend['issue_number']}호_{today_str}.pdf",
            'file_size': file_size,
            'streamdocs_id': streamdocs_id,
            'pdf_base64': pdf_base64  # base64 인코딩된 PDF
        }

    except Exception as e:
        logger.error(f"ITFIND PDF 다운로드 실패: {e}", exc_info=True)
        logger.warning("=" * 60)
        logger.warning("⚠️ ITFIND PDF 다운로드 실패")
        logger.warning("=" * 60)
        return None


def handler(event, context):
    """
    Lambda 핸들러

    Args:
        event: EventBridge 이벤트 또는 테스트 이벤트
        context: Lambda 컨텍스트

    Returns:
        dict: 성공 여부 및 메타데이터
    """
    try:
        logger.info(f"Lambda 시작: {context.aws_request_id}")
        logger.info(f"이벤트: {event}")

        # 비동기 함수 실행
        result = asyncio.run(download_itfind_pdf())

        if result:
            return {
                'statusCode': 200,
                'body': {
                    'success': True,
                    'message': 'ITFIND PDF downloaded successfully',
                    'data': result
                }
            }
        else:
            return {
                'statusCode': 404,
                'body': {
                    'success': False,
                    'message': 'Failed to download ITFIND PDF',
                    'data': None
                }
            }

    except Exception as e:
        logger.error(f"Lambda 실행 실패: {e}", exc_info=True)

        return {
            'statusCode': 500,
            'body': {
                'success': False,
                'message': f'Lambda execution failed: {str(e)}',
                'data': None
            }
        }


if __name__ == '__main__':
    # 로컬 테스트
    class MockContext:
        request_id = 'local-test-123'
        invoked_function_arn = 'arn:aws:lambda:local'

    result = handler({}, MockContext())
    print(f"\n결과: {result}")
