"""
수신인 관리 비즈니스 로직
"""
import logging
from typing import List, Optional

from .dynamodb_client import DynamoDBClient
from .models import Recipient, RecipientStatus

logger = logging.getLogger(__name__)


class RecipientManager:
    """수신인 관리자"""

    def __init__(self, table_name: str = "etnews-recipients", region_name: str = "ap-northeast-2"):
        """
        Args:
            table_name: DynamoDB 테이블 이름
            region_name: AWS 리전
        """
        self.db_client = DynamoDBClient(table_name, region_name)

    def add_recipient(self, email: str, name: str) -> bool:
        """
        수신인 추가

        Args:
            email: 이메일 주소
            name: 이름

        Returns:
            성공 여부
        """
        try:
            # 기존 수신인 확인
            existing = self.get_recipient(email)
            if existing:
                logger.warning(f"이미 존재하는 수신인: {email}")
                return False

            # 새 수신인 생성
            recipient = Recipient.create_new(email, name)

            # DynamoDB에 저장
            success = self.db_client.put_item(recipient.to_dynamodb())

            if success:
                logger.info(f"수신인 추가 완료: {email} ({name})")
            return success

        except ValueError as e:
            logger.error(f"수신인 추가 실패 (유효성 검증): {e}")
            return False
        except Exception as e:
            logger.error(f"수신인 추가 실패: {e}")
            return False

    def get_recipient(self, email: str) -> Optional[Recipient]:
        """
        수신인 조회

        Args:
            email: 이메일 주소

        Returns:
            Recipient 객체 또는 None
        """
        item = self.db_client.get_item(email)
        if item:
            return Recipient.from_dynamodb(item)
        return None

    def get_active_recipients(self) -> List[Recipient]:
        """
        활성 수신인 목록 조회

        Returns:
            활성 수신인 리스트
        """
        items = self.db_client.query_by_status(RecipientStatus.ACTIVE.value)
        recipients = [Recipient.from_dynamodb(item) for item in items]
        logger.info(f"활성 수신인 조회 완료: {len(recipients)}명")
        return recipients

    def get_all_recipients(self) -> List[Recipient]:
        """
        모든 수신인 조회

        Returns:
            모든 수신인 리스트
        """
        items = self.db_client.scan_all()
        recipients = [Recipient.from_dynamodb(item) for item in items]
        logger.info(f"전체 수신인 조회 완료: {len(recipients)}명")
        return recipients

    def unsubscribe(self, email: str) -> bool:
        """
        수신거부 처리

        Args:
            email: 이메일 주소

        Returns:
            성공 여부
        """
        try:
            # 수신인 조회
            recipient = self.get_recipient(email)
            if not recipient:
                logger.warning(f"수신인을 찾을 수 없음: {email}")
                return False

            # 이미 수신거부 상태인지 확인
            if not recipient.is_active():
                logger.info(f"이미 수신거부 상태: {email}")
                return True

            # 수신거부 처리
            recipient.unsubscribe()

            # DynamoDB 업데이트
            updates = {
                "status": recipient.status.value,
                "unsubscribed_at": recipient.unsubscribed_at,
            }
            success = self.db_client.update_item(email, updates)

            if success:
                logger.info(f"수신거부 처리 완료: {email}")
            return success

        except Exception as e:
            logger.error(f"수신거부 처리 실패: {e}")
            return False

    def resubscribe(self, email: str) -> bool:
        """
        수신 재개 처리

        Args:
            email: 이메일 주소

        Returns:
            성공 여부
        """
        try:
            # 수신인 조회
            recipient = self.get_recipient(email)
            if not recipient:
                logger.warning(f"수신인을 찾을 수 없음: {email}")
                return False

            # 이미 활성 상태인지 확인
            if recipient.is_active():
                logger.info(f"이미 활성 상태: {email}")
                return True

            # 수신 재개 처리
            updates = {
                "status": RecipientStatus.ACTIVE.value,
                "unsubscribed_at": None,
            }
            success = self.db_client.update_item(email, updates)

            if success:
                logger.info(f"수신 재개 처리 완료: {email}")
            return success

        except Exception as e:
            logger.error(f"수신 재개 처리 실패: {e}")
            return False

    def delete_recipient(self, email: str) -> bool:
        """
        수신인 삭제 (완전 제거)

        Args:
            email: 이메일 주소

        Returns:
            성공 여부
        """
        try:
            success = self.db_client.delete_item(email)
            if success:
                logger.info(f"수신인 삭제 완료: {email}")
            return success

        except Exception as e:
            logger.error(f"수신인 삭제 실패: {e}")
            return False

    def bulk_add_recipients(self, recipients: List[tuple]) -> dict:
        """
        수신인 일괄 추가

        Args:
            recipients: (email, name) 튜플 리스트

        Returns:
            결과 딕셔너리 (success_count, failed_count, failed_emails)
        """
        success_count = 0
        failed_count = 0
        failed_emails = []

        for email, name in recipients:
            if self.add_recipient(email, name):
                success_count += 1
            else:
                failed_count += 1
                failed_emails.append(email)

        logger.info(f"일괄 추가 완료: 성공 {success_count}명, 실패 {failed_count}명")

        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "failed_emails": failed_emails,
        }


# 싱글톤 인스턴스
_recipient_manager = RecipientManager()


def get_active_recipients() -> List[Recipient]:
    """
    활성 수신인 목록 조회 (편의 함수)

    Returns:
        활성 수신인 리스트
    """
    return _recipient_manager.get_active_recipients()


def unsubscribe_recipient(email: str) -> bool:
    """
    수신거부 처리 (편의 함수)

    Args:
        email: 이메일 주소

    Returns:
        성공 여부
    """
    return _recipient_manager.unsubscribe(email)
