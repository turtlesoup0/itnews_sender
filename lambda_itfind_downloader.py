#!/usr/bin/env python3
"""
ITFIND 주간기술동향 PDF 다운로드 Lambda 함수

매주 수요일 EventBridge로 트리거되어:
1. 최신 주간기술동향 조회 (RSS)
2. PDF 다운로드 (Playwright)
3. S3에 저장
4. 메타데이터 반환
"""
import logging
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import boto3

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

# S3 클라이언트
s3_client = boto3.client('s3')
S3_BUCKET = os.environ.get('S3_BUCKET', 'itnews-sender-pdfs')


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

            logger.info(f"주간기술동향 발견: {title}")

            # 호수 추출
            issue_match = re.search(r'\[주간기술동향\s+(\d+)호\]', title)
            issue_number = issue_match.group(1) if issue_match else "unknown"

            # detail_id 추출 (link에서 identifier 파라미터)
            detail_id_match = re.search(r'identifier=([\w-]+)', link)
            detail_id = detail_id_match.group(1).replace('TVOL_', '') if detail_id_match else None

            # PDF URL 변환: getFile.htm → StreamDocs viewer URL
            # link: http://www.itfind.or.kr/admin/getFile.htm?identifier=02-001-260122-000003
            # 상세 페이지를 통해 StreamDocs ID를 얻어야 하므로 일단 getStreamDocsRegi URL로 변환
            if detail_id:
                pdf_url = f"https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_{detail_id}"
            else:
                pdf_url = link.replace('http://', 'https://')

            # 발행일 (현재 날짜로 근사)
            kst = timezone(timedelta(hours=9))
            publish_date = datetime.now(kst).strftime("%Y-%m-%d")

            return {
                'title': title,
                'issue_number': issue_number,
                'publish_date': publish_date,
                'pdf_url': pdf_url,
                'detail_id': detail_id
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
    ITFIND 주간기술동향 PDF 다운로드

    Returns:
        Dict: {
            'title': str,
            'issue_number': str,
            'publish_date': str,
            'local_path': str,
            's3_key': str,
            'file_size': int
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

        # 4. S3에 업로드
        logger.info("4단계: S3에 업로드")
        s3_key = f"itfind/{today_str}/weekly_{trend['issue_number']}.pdf"

        with open(local_path, 'rb') as f:
            # S3 Metadata는 ASCII만 허용하므로 한글 제목 제외
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=f,
                ContentType='application/pdf',
                Metadata={
                    'issue_number': trend['issue_number'],
                    'publish_date': trend['publish_date'],
                    'download_date': today_str,
                    'streamdocs_id': streamdocs_id
                }
            )

        logger.info(f"✅ S3 업로드 완료: s3://{S3_BUCKET}/{s3_key}")

        logger.info("=" * 60)
        logger.info("✅ ITFIND PDF 다운로드 및 업로드 성공")
        logger.info("=" * 60)

        return {
            'title': trend['title'],
            'issue_number': trend['issue_number'],
            'publish_date': trend['publish_date'],
            'local_path': local_path,
            's3_bucket': S3_BUCKET,
            's3_key': s3_key,
            'file_size': file_size,
            'streamdocs_id': streamdocs_id
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
            logger.info("=" * 60)
            logger.info("✅ ITFIND PDF 다운로드 및 S3 업로드 성공")
            logger.info("=" * 60)

            return {
                'statusCode': 200,
                'body': {
                    'success': True,
                    'message': 'ITFIND PDF downloaded and uploaded to S3',
                    'data': result
                }
            }
        else:
            logger.warning("=" * 60)
            logger.warning("⚠️ ITFIND PDF 다운로드 실패")
            logger.warning("=" * 60)

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
