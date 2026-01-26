"""
수신거부 토큰 생성 및 검증 모듈

HMAC 기반의 안전한 토큰 생성/검증을 제공합니다.
토큰 형식: Base64(email:timestamp:signature)
- email: 수신인 이메일 주소
- timestamp: YYYY-MM 형식의 년월 (월별 로테이션)
- signature: HMAC-SHA256 서명
"""
import base64
import hmac
import hashlib
import logging
from datetime import datetime
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class UnsubscribeTokenError(Exception):
    """토큰 관련 에러"""
    pass


def generate_token(email: str, secret: str) -> str:
    """
    수신거부 토큰 생성

    Args:
        email: 수신인 이메일 주소
        secret: HMAC 시크릿 키

    Returns:
        Base64 인코딩된 토큰

    Example:
        >>> token = generate_token("user@example.com", "secret-key")
        >>> print(token)  # "dXNlckBleGFtcGxlLmNvbToyMDI2LTAxOmFiYzEyMy4uLg=="
    """
    try:
        # 현재 년월
        current_month = datetime.now().strftime('%Y-%m')

        # 서명할 메시지: email:YYYY-MM
        message = f"{email}:{current_month}"

        # HMAC-SHA256 서명 생성
        signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()

        # Base64 인코딩
        signature_b64 = base64.urlsafe_b64encode(signature).decode()

        # 최종 토큰: email:YYYY-MM:signature
        token_data = f"{email}:{current_month}:{signature_b64}"
        token = base64.urlsafe_b64encode(token_data.encode()).decode()

        logger.debug(f"토큰 생성 완료: {email}")
        return token

    except Exception as e:
        logger.error(f"토큰 생성 실패: {e}")
        raise UnsubscribeTokenError(f"토큰 생성 실패: {e}")


def verify_token(token: str, secret: str) -> Tuple[bool, Optional[str]]:
    """
    수신거부 토큰 검증

    Args:
        token: Base64 인코딩된 토큰
        secret: HMAC 시크릿 키

    Returns:
        (유효 여부, 이메일 주소) 튜플
        유효하지 않으면 (False, None) 반환

    Example:
        >>> is_valid, email = verify_token(token, "secret-key")
        >>> if is_valid:
        ...     print(f"Valid email: {email}")
    """
    try:
        # Base64 디코딩
        decoded = base64.urlsafe_b64decode(token).decode()
        parts = decoded.split(":")

        # 형식 검증: email:YYYY-MM:signature
        if len(parts) != 3:
            logger.warning("토큰 형식 오류: 올바른 구조가 아님")
            return False, None

        email, timestamp, signature_b64 = parts

        # 현재 월과 비교하여 검증
        if _verify_signature(email, timestamp, signature_b64, secret):
            logger.info(f"토큰 검증 성공: {email} (timestamp: {timestamp})")
            return True, email

        # 이전 월 토큰도 검증 (월 경계 유효성)
        prev_month = _get_previous_month()
        if _verify_signature(email, prev_month, signature_b64, secret):
            logger.info(f"토큰 검증 성공 (이전 달): {email} (timestamp: {prev_month})")
            return True, email

        logger.warning(f"토큰 서명 불일치: {email}")
        return False, None

    except Exception as e:
        logger.error(f"토큰 검증 실패: {e}")
        return False, None


def _verify_signature(email: str, timestamp: str, signature_b64: str, secret: str) -> bool:
    """
    특정 타임스탬프에 대한 서명 검증

    Args:
        email: 이메일 주소
        timestamp: YYYY-MM 형식 타임스탬프
        signature_b64: Base64 인코딩된 서명
        secret: HMAC 시크릿 키

    Returns:
        서명이 유효하면 True
    """
    try:
        # 메시지 재생성
        message = f"{email}:{timestamp}"

        # 예상 서명 계산
        expected_signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()

        expected_signature_b64 = base64.urlsafe_b64encode(expected_signature).decode()

        # 상수 시간 비교 (타이밍 공격 방지)
        return hmac.compare_digest(signature_b64, expected_signature_b64)

    except Exception as e:
        logger.error(f"서명 검증 중 오류: {e}")
        return False


def _get_previous_month() -> str:
    """
    이전 달의 YYYY-MM 문자열 반환

    Returns:
        이전 달 문자열 (예: "2026-01")
    """
    now = datetime.now()

    if now.month == 1:
        # 1월이면 전년도 12월
        prev_year = now.year - 1
        prev_month = 12
    else:
        prev_year = now.year
        prev_month = now.month - 1

    return f"{prev_year:04d}-{prev_month:02d}"


# 편의 함수: 기본 시크릿으로 토큰 생성
def generate_token_with_default_secret(email: str) -> str:
    """
    기본 시크릿 키를 사용한 토큰 생성

    Note: 프로덕션에서는 환경변수에서 시크릿을 가져와야 합니다.

    Args:
        email: 수신인 이메일 주소

    Returns:
        생성된 토큰
    """
    import os
    secret = os.getenv("UNSUBSCRIBE_SECRET", "etnews-unsubscribe-secret-2026")
    return generate_token(email, secret)
