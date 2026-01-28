"""
실행 제어 로직 (멱등성, 실패 제한)
"""
import logging
import time
from typing import Optional, Tuple
from ..execution_tracker import ExecutionTracker
from ..failure_tracker import FailureTracker
from ..utils.notification import send_admin_notification

logger = logging.getLogger(__name__)


def check_idempotency(
    mode: str,
    request_id: str,
    skip_idempotency: bool = False
) -> Tuple[bool, Optional[dict]]:
    """
    멱등성 체크 - 오늘 이미 실행되었는지 확인

    Args:
        mode: 실행 모드 (test/opr)
        request_id: Lambda 요청 ID
        skip_idempotency: 멱등성 체크 건너뛰기 (테스트용)

    Returns:
        (실행 가능 여부, 에러 응답)
    """
    if skip_idempotency:
        logger.warning("⚠️  멱등성 체크 비활성화 (skip_idempotency=True)")
        return True, None

    logger.info("0단계: 멱등성 보장 - 실행 이력 선기록")
    exec_tracker = ExecutionTracker()

    if not exec_tracker.mark_execution(mode, request_id):
        logger.warning(f"⚠️  오늘 이미 {mode} 모드로 실행되었습니다")
        return False, {
            'statusCode': 200,
            'body': {
                'message': f'오늘 이미 {mode} 모드로 실행되었습니다 (중복 실행 방지)',
                'skipped': True,
                'reason': 'already_executed_today'
            }
        }

    logger.info(f"✅ 멱등성 보장 완료: 오늘 {mode} 모드 첫 실행")
    return True, None


def check_failure_limit() -> Tuple[bool, Optional[dict]]:
    """
    실패 제한 체크 - 오늘 3회 이상 실패했는지 확인

    Returns:
        (실행 가능 여부, 에러 응답)
    """
    logger.info("1단계: 실패 제한 체크")
    failure_tracker = FailureTracker()

    if failure_tracker.should_skip_today():
        logger.error("오늘 3회 이상 실패하여 발송을 건너뜁니다")

        # 관리자 알림
        try:
            send_admin_notification(
                subject="[etnews-pdf-sender] 발송 실패 알림",
                message="오늘 3회 이상 PDF 다운로드에 실패하여 발송을 건너뜁니다."
            )
        except Exception as e:
            logger.error(f"관리자 알림 실패: {e}")

        return False, {
            'statusCode': 429,
            'body': {
                'message': '오늘 3회 이상 실패하여 발송을 건너뜁니다',
                'skipped': True,
                'reason': 'too_many_failures_today'
            }
        }

    logger.info("✅ 실패 제한 체크 통과")
    return True, None
