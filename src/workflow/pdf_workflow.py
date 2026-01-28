"""
PDF 다운로드 및 처리 워크플로우
"""
import logging
import json
import base64
import boto3
from collections import namedtuple
from typing import Optional, Tuple
from ..scraper import download_pdf_sync
from ..pdf_processor import process_pdf
from ..failure_tracker import FailureTracker
from ..utils.notification import send_admin_notification

logger = logging.getLogger(__name__)


def sanitize_error(error_msg: str) -> str:
    """오류 메시지에서 민감정보 필터링"""
    import re
    patterns = [
        (r'(password|passwd|pwd)=[^&\s]*', 'password=[REDACTED]'),
        (r'(token|secret|key|apikey|api_key)=[^&\s]*', 'token=[REDACTED]'),
        (r'Authorization:\s*[^\s]+', 'Authorization: [REDACTED]'),
        (r'Bearer\s+[^\s]+', 'Bearer [REDACTED]'),
        (r'"(password|passwd|pwd|token|secret|key)":\s*"[^"]*"', r'"\1": "[REDACTED]"'),
    ]
    sanitized = error_msg
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def download_and_process_pdf(failure_tracker: 'FailureTracker') -> Tuple[Optional[str], Optional[str], Optional[dict]]:
    """
    전자신문 PDF 다운로드 및 처리

    Args:
        failure_tracker: 실패 추적 인스턴스

    Returns:
        (원본 PDF 경로, 처리된 PDF 경로, 페이지 정보)
    """
    logger.info("2단계: 전자신문 PDF 다운로드 시작")

    try:
        pdf_path, page_info = download_pdf_sync()
        logger.info(f"전자신문 PDF 다운로드 완료: {pdf_path}")

        # 성공 시 실패 카운트 리셋
        failure_tracker.reset_today()

    except ValueError as ve:
        # 신문 미발행일 처리
        if "신문이 발행되지 않은 날" in str(ve):
            logger.info("신문이 발행되지 않은 날입니다")
            raise  # 상위에서 처리
        else:
            # PDF 다운로드 실패
            count = failure_tracker.increment_failure(str(ve))
            logger.error(f"PDF 다운로드 실패 ({count}회): {ve}")

            # 3회째 실패면 관리자 알림
            if count >= 3:
                try:
                    sanitized_error = sanitize_error(str(ve))
                    send_admin_notification(
                        subject="[etnews-pdf-sender] PDF 다운로드 실패 알림",
                        message=f"PDF 다운로드가 3회 연속 실패했습니다.\n\n오류: {sanitized_error}"
                    )
                except Exception as notify_error:
                    logger.error(f"관리자 알림 실패: {notify_error}")
            raise

    except Exception as e:
        # 기타 다운로드 실패
        count = failure_tracker.increment_failure(str(e))
        logger.error(f"PDF 다운로드 실패 ({count}회): {e}")

        # 3회째 실패면 관리자 알림
        if count >= 3:
            try:
                sanitized_error = sanitize_error(str(e))
                send_admin_notification(
                    subject="[etnews-pdf-sender] PDF 다운로드 실패 알림",
                    message=f"PDF 다운로드가 3회 연속 실패했습니다.\n\n오류: {sanitized_error}"
                )
            except Exception as notify_error:
                logger.error(f"관리자 알림 실패: {notify_error}")
        raise

    # PDF 처리 (광고 제거)
    logger.info("3단계: PDF 광고 제거 처리")
    processed_pdf_path = process_pdf(pdf_path)

    if not processed_pdf_path:
        logger.error("PDF 처리 실패")
        return pdf_path, None, page_info

    logger.info(f"✅ PDF 처리 완료: {processed_pdf_path}")
    return pdf_path, processed_pdf_path, page_info


def download_itfind_pdf() -> Tuple[Optional[str], Optional[object]]:
    """
    ITFIND 주간기술동향 PDF 다운로드 (Lambda 함수 호출)

    Returns:
        (PDF 경로, WeeklyTrend 객체)
    """
    logger.info("2-1단계: ITFIND 주간기술동향 다운로드 시도")

    try:
        lambda_client = boto3.client('lambda')

        logger.info("ITFIND Lambda 함수 호출 중...")
        response = lambda_client.invoke(
            FunctionName='itfind-pdf-downloader',
            InvocationType='RequestResponse',
            Payload=json.dumps({})
        )

        result_payload = json.loads(response['Payload'].read())
        logger.info(f"ITFIND Lambda 응답: statusCode={result_payload.get('statusCode')}")

        if result_payload.get('statusCode') == 200 and result_payload['body']['success']:
            data = result_payload['body']['data']

            # Base64 디코딩하여 /tmp에 저장
            pdf_base64 = data['pdf_base64']
            pdf_data = base64.b64decode(pdf_base64)

            itfind_pdf_path = f"/tmp/{data['filename']}"
            with open(itfind_pdf_path, 'wb') as f:
                f.write(pdf_data)

            logger.info(f"✅ ITFIND PDF 다운로드 성공: {itfind_pdf_path}")
            logger.info(f"   제목: {data['title']}")
            logger.info(f"   호수: {data['issue_number']}호")
            logger.info(f"   크기: {data['file_size']:,} bytes")

            # WeeklyTrend 객체 생성
            WeeklyTrend = namedtuple('WeeklyTrend', ['title', 'issue_number', 'publish_date', 'pdf_url', 'topics', 'detail_id'])
            itfind_trend_info = WeeklyTrend(
                title=data['title'],
                issue_number=data['issue_number'],
                publish_date=data['publish_date'],
                pdf_url='',
                topics=data.get('topics', []),
                detail_id=''
            )

            return itfind_pdf_path, itfind_trend_info
        else:
            logger.warning("ITFIND PDF를 찾지 못했습니다 (주간기술동향 없음)")
            return None, None

    except Exception as e:
        logger.error(f"ITFIND PDF 다운로드 중 오류: {e}")
        return None, None
