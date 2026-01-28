#!/usr/bin/env python3
"""
ITFIND 스크래퍼 테스트 스크립트
로컬 환경에서 ITFIND 주간기술동향 조회 및 PDF 다운로드 테스트
"""
import sys
import os
import asyncio
import logging

# 상위 디렉토리 추가 (src 모듈 임포트용)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.itfind_scraper import ItfindScraper

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_itfind_scraper():
    """ITFIND 스크래퍼 전체 테스트"""
    print("=" * 60)
    print("ITFIND 주간기술동향 스크래퍼 테스트")
    print("=" * 60)
    print()

    async with ItfindScraper(headless=True) as scraper:
        # 1. 최신 주간기술동향 조회
        print("1단계: 최신 주간기술동향 조회")
        print("-" * 60)

        trend = await scraper.get_latest_weekly_trend()

        if not trend:
            print("❌ 주간기술동향을 찾을 수 없습니다")
            return False

        print("✅ 주간기술동향 조회 성공")
        print()
        print(f"제목: {trend.title}")
        print(f"호수: {trend.issue_number}")
        print(f"발행일: {trend.publish_date}")
        print(f"상세 ID: {trend.detail_id}")
        print(f"PDF URL: {trend.pdf_url}")
        print()
        print("주요 토픽:")
        for i, topic in enumerate(trend.topics, 1):
            print(f"  {i}. {topic[:80]}{'...' if len(topic) > 80 else ''}")
        print()

        # 2. PDF 다운로드 테스트
        print("2단계: PDF 다운로드 테스트")
        print("-" * 60)

        save_path = "/tmp/itfind_weekly_test.pdf"

        try:
            # detail_url 생성
            detail_url = f"https://www.itfind.or.kr/trend/weekly/weeklyDetail.do?id={trend.detail_id.split('&')[0]}"
            downloaded_path = await scraper.download_weekly_pdf(trend.pdf_url, save_path, detail_url=detail_url)
            file_size = os.path.getsize(downloaded_path)

            print(f"✅ PDF 다운로드 성공")
            print(f"경로: {downloaded_path}")
            print(f"크기: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
            print()

            # 3. 파일 유효성 간단 체크
            print("3단계: PDF 파일 유효성 체크")
            print("-" * 60)

            with open(downloaded_path, 'rb') as f:
                header = f.read(4)

            if header == b'%PDF':
                print("✅ PDF 파일 헤더 검증 성공")
            else:
                print("❌ PDF 파일 헤더 검증 실패")
                return False

        except Exception as e:
            print(f"❌ PDF 다운로드 실패: {e}")
            return False

    print()
    print("=" * 60)
    print("✅ 모든 테스트 통과")
    print("=" * 60)
    return True


if __name__ == '__main__':
    success = asyncio.run(test_itfind_scraper())
    sys.exit(0 if success else 1)
