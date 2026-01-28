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

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# S3 클라이언트
s3_client = boto3.client('s3')
S3_BUCKET = os.environ.get('S3_BUCKET', 'itnews-sender-pdfs')


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
        logger.info("ITFIND 주간기술동향 PDF 다운로드 시작")
        logger.info("=" * 60)

        async with ItfindScraper(headless=True) as scraper:
            # 1. 최신 주간기술동향 조회 (RSS)
            logger.info("1단계: RSS 피드에서 최신 주간기술동향 조회")
            trend = await scraper.get_latest_weekly_trend()

            if not trend:
                logger.warning("주간기술동향을 찾을 수 없습니다")
                return None

            logger.info(f"✅ 주간기술동향 발견: {trend.title} ({trend.issue_number})")
            logger.info(f"   발행일: {trend.publish_date}")
            logger.info(f"   PDF URL: {trend.pdf_url}")

            # 2. PDF 다운로드
            logger.info("2단계: PDF 다운로드")
            kst = timezone(timedelta(hours=9))
            today_str = datetime.now(kst).strftime("%Y%m%d")
            local_path = f"/tmp/itfind_weekly_{today_str}.pdf"

            detail_url = f"https://www.itfind.or.kr/trend/weekly/weeklyDetail.do?id={trend.detail_id}"
            await scraper.download_weekly_pdf(trend.pdf_url, local_path, detail_url=detail_url)

            file_size = os.path.getsize(local_path)
            logger.info(f"✅ PDF 다운로드 완료: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")

            # 3. S3에 업로드
            logger.info("3단계: S3에 업로드")
            s3_key = f"itfind/{today_str}/weekly_{trend.issue_number}.pdf"

            with open(local_path, 'rb') as f:
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=s3_key,
                    Body=f,
                    ContentType='application/pdf',
                    Metadata={
                        'title': trend.title,
                        'issue_number': trend.issue_number,
                        'publish_date': trend.publish_date,
                        'download_date': today_str
                    }
                )

            logger.info(f"✅ S3 업로드 완료: s3://{S3_BUCKET}/{s3_key}")

            return {
                'title': trend.title,
                'issue_number': trend.issue_number,
                'publish_date': trend.publish_date,
                'local_path': local_path,
                's3_bucket': S3_BUCKET,
                's3_key': s3_key,
                'file_size': file_size
            }

    except Exception as e:
        logger.error(f"ITFIND PDF 다운로드 실패: {e}", exc_info=True)
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
