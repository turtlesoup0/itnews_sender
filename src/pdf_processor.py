"""
PDF 처리 모듈
광고 페이지 제거 및 PDF 최적화
"""
import os
import logging
from typing import List, Dict
from datetime import datetime
from pypdf import PdfReader, PdfWriter

from .config import Config

logger = logging.getLogger(__name__)


class PDFProcessor:
    """PDF 광고 제거 및 처리"""

    # PDF 파일 최대 크기 (바이트): 50MB
    MAX_PDF_SIZE = 50 * 1024 * 1024

    def __init__(self):
        self.config = Config

    def remove_ads(self, pdf_path: str, page_info: List[Dict[str, str]] = None) -> str:
        """
        PDF에서 광고 페이지 제거

        Args:
            pdf_path: 원본 PDF 파일 경로
            page_info: 페이지 정보 리스트 (광고 페이지 식별용)

        Returns:
            처리된 PDF 파일 경로

        Raises:
            ValueError: PDF 파일 크기가 제한을 초과한 경우
        """
        try:
            logger.info(f"PDF 처리 시작: {pdf_path}")

            # PDF 파일 크기 검증
            file_size = os.path.getsize(pdf_path)
            file_size_mb = file_size / (1024 * 1024)
            logger.info(f"PDF 파일 크기: {file_size_mb:.2f} MB")

            if file_size > self.MAX_PDF_SIZE:
                error_msg = f"PDF 파일 크기가 너무 큽니다: {file_size_mb:.2f} MB (최대 {self.MAX_PDF_SIZE / (1024 * 1024)} MB)"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # PDF 읽기
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)
            logger.info(f"총 페이지 수: {total_pages}")

            # 광고 페이지 식별
            ad_pages = self._identify_ad_pages(reader, page_info)

            if not ad_pages:
                logger.info("광고 페이지가 감지되지 않았습니다. 원본 PDF 반환")
                return pdf_path

            logger.info(f"광고 페이지 감지: {ad_pages}")

            # 새 PDF 작성 (광고 페이지 제외)
            writer = PdfWriter()

            for page_num in range(total_pages):
                if page_num not in ad_pages:
                    writer.add_page(reader.pages[page_num])

            # 처리된 PDF 저장
            output_path = self._generate_output_path(pdf_path)
            with open(output_path, "wb") as output_file:
                writer.write(output_file)

            removed_count = len(ad_pages)
            final_pages = total_pages - removed_count

            logger.info(f"PDF 처리 완료: {output_path}")
            logger.info(f"제거된 페이지: {removed_count}개, 최종 페이지: {final_pages}개")

            return output_path

        except Exception as e:
            logger.error(f"PDF 처리 중 오류 발생: {e}")
            logger.info("오류로 인해 원본 PDF 반환")
            return pdf_path

    def _identify_ad_pages(
        self, reader: PdfReader, page_info: List[Dict[str, str]] = None
    ) -> List[int]:
        """
        광고 페이지 식별

        Args:
            reader: PDF 리더 객체
            page_info: 웹 스크래핑에서 수집한 페이지 정보

        Returns:
            광고 페이지 번호 리스트 (0-based index)
        """
        ad_pages = []
        total_pages = len(reader.pages)

        # 방법 1: 웹에서 수집한 페이지 정보 활용
        if page_info:
            for info in page_info:
                if info.get("is_ad", False):
                    try:
                        # 페이지 번호를 0-based index로 변환
                        page_idx = int(info["page_number"]) - 1
                        if 0 <= page_idx < total_pages:
                            ad_pages.append(page_idx)
                    except (ValueError, KeyError):
                        continue

        # 방법 2: PDF 메타데이터 및 텍스트 분석
        for page_num in range(total_pages):
            if page_num in ad_pages:
                continue  # 이미 광고로 식별된 경우 스킵

            page = reader.pages[page_num]

            # 페이지 텍스트 추출
            try:
                text = page.extract_text()
                text_length = len(text.strip())

                # 방법 1: 텍스트가 매우 짧은 페이지는 광고 (거의 빈 페이지)
                if text_length < self.config.AD_TEXT_LENGTH_THRESHOLD:
                    logger.debug(f"페이지 {page_num + 1}: 텍스트 길이 {text_length}자 - 광고로 판단")
                    ad_pages.append(page_num)
                    continue

                # 방법 2: 광고 키워드 검색
                if self._contains_ad_keywords(text):
                    ad_pages.append(page_num)
                    continue

            except Exception as e:
                logger.warning(f"페이지 {page_num + 1} 분석 중 오류: {e}")
                continue

        return sorted(set(ad_pages))  # 중복 제거 및 정렬

    def _contains_ad_keywords(self, text: str) -> bool:
        """텍스트에 광고 키워드가 포함되어 있는지 확인"""
        if not text:
            return False

        text_lower = text.lower()

        # 광고 키워드 검색
        for keyword in self.config.AD_KEYWORDS:
            if keyword.lower() in text_lower:
                # 오탐 방지: "광고" 키워드가 본문에 자연스럽게 나오는 경우 제외
                # 예: "광고 산업", "광고 시장" 등
                # 하지만 "전면광고", "Advertisement" 등은 광고 페이지일 가능성 높음
                if keyword in ["전면광고", "Advertisement", "advertorial"]:
                    return True

                # "광고" 단독으로 나오거나 페이지 전체에서 비중이 높은 경우
                if keyword == "광고" or keyword == "AD":
                    keyword_count = text_lower.count(keyword.lower())
                    if keyword_count > self.config.AD_KEYWORD_COUNT_THRESHOLD:
                        return True

        return False

    def _generate_output_path(self, original_path: str) -> str:
        """처리된 PDF 파일 경로 생성"""
        dir_name = os.path.dirname(original_path)
        base_name = os.path.basename(original_path)
        name, ext = os.path.splitext(base_name)

        # "파일명_processed.pdf" 형식
        output_name = f"{name}_processed{ext}"
        return os.path.join(dir_name, output_name)


def process_pdf(pdf_path: str, page_info: List[Dict[str, str]] = None) -> str:
    """
    PDF 처리 메인 함수

    Args:
        pdf_path: 원본 PDF 파일 경로
        page_info: 페이지 정보 리스트

    Returns:
        처리된 PDF 파일 경로
    """
    processor = PDFProcessor()
    return processor.remove_ads(pdf_path, page_info)


if __name__ == "__main__":
    # 테스트
    import sys

    if len(sys.argv) > 1:
        test_pdf_path = sys.argv[1]
        result = process_pdf(test_pdf_path)
        print(f"처리 완료: {result}")
    else:
        print("사용법: python pdf_processor.py <pdf_path>")
