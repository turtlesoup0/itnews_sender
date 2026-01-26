"""
구조화 로깅 유틸리티
CloudWatch Logs에서 검색/필터링이 용이한 JSON 형식 로깅 지원
"""
import json
import logging
from typing import Any, Dict
from datetime import datetime


class StructuredLogger:
    """구조화된 JSON 로깅을 위한 래퍼 클래스"""

    def __init__(self, logger: logging.Logger):
        """
        Args:
            logger: 기존 logger 인스턴스
        """
        self.logger = logger

    def log_event(
        self,
        level: str,
        event: str,
        message: str,
        extra: Dict[str, Any] = None,
        **kwargs
    ):
        """
        구조화된 로그 이벤트 기록

        Args:
            level: 로그 레벨 (INFO, WARNING, ERROR 등)
            event: 이벤트 타입 (email_sent, pdf_downloaded 등)
            message: 사람이 읽기 쉬운 메시지
            extra: 추가 메타데이터 딕셔너리
            **kwargs: 추가 키워드 인자
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level.upper(),
            "event": event,
            "message": message,
        }

        # extra 딕셔너리 병합
        if extra:
            log_data.update(extra)

        # kwargs 병합
        if kwargs:
            log_data.update(kwargs)

        # JSON 문자열로 변환
        log_message = json.dumps(log_data, ensure_ascii=False)

        # 해당 레벨로 로깅
        log_level = getattr(logging, level.upper(), logging.INFO)
        self.logger.log(log_level, log_message)

    def info(self, event: str, message: str, **kwargs):
        """INFO 레벨 로그"""
        self.log_event("INFO", event, message, **kwargs)

    def warning(self, event: str, message: str, **kwargs):
        """WARNING 레벨 로그"""
        self.log_event("WARNING", event, message, **kwargs)

    def error(self, event: str, message: str, **kwargs):
        """ERROR 레벨 로그"""
        self.log_event("ERROR", event, message, **kwargs)

    def debug(self, event: str, message: str, **kwargs):
        """DEBUG 레벨 로그"""
        self.log_event("DEBUG", event, message, **kwargs)


# 편의 함수
def get_structured_logger(name: str) -> StructuredLogger:
    """
    구조화 로거 생성

    Args:
        name: 로거 이름 (일반적으로 __name__ 사용)

    Returns:
        StructuredLogger 인스턴스

    Example:
        >>> logger = get_structured_logger(__name__)
        >>> logger.info(
        ...     event="email_sent",
        ...     message="이메일 전송 완료",
        ...     recipient="user@example.com",
        ...     success=True
        ... )
    """
    return StructuredLogger(logging.getLogger(name))


# 특정 이벤트 타입별 로깅 헬퍼
def log_email_sent(logger: StructuredLogger, recipient: str, success: bool, error: str = None):
    """이메일 전송 로그"""
    if success:
        logger.info(
            event="email_sent",
            message=f"이메일 전송 성공: {recipient}",
            recipient=recipient,
            success=True
        )
    else:
        logger.error(
            event="email_failed",
            message=f"이메일 전송 실패: {recipient}",
            recipient=recipient,
            success=False,
            error=error
        )


def log_pdf_processed(logger: StructuredLogger, file_path: str, pages_removed: int, success: bool):
    """PDF 처리 로그"""
    logger.info(
        event="pdf_processed",
        message=f"PDF 처리 완료: {file_path}",
        file_path=file_path,
        pages_removed=pages_removed,
        success=success
    )


def log_lambda_execution(logger: StructuredLogger, function_name: str, duration_ms: float, success: bool, error: str = None):
    """Lambda 실행 로그"""
    if success:
        logger.info(
            event="lambda_execution",
            message=f"Lambda 실행 완료: {function_name}",
            function_name=function_name,
            duration_ms=duration_ms,
            success=True
        )
    else:
        logger.error(
            event="lambda_execution_failed",
            message=f"Lambda 실행 실패: {function_name}",
            function_name=function_name,
            duration_ms=duration_ms,
            success=False,
            error=error
        )
