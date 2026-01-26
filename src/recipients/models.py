"""
수신인 데이터 모델
"""
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class RecipientStatus(Enum):
    """수신인 상태"""
    ACTIVE = "active"
    UNSUBSCRIBED = "unsubscribed"


@dataclass
class Recipient:
    """수신인 데이터 모델"""

    email: str
    name: str
    status: RecipientStatus
    created_at: str
    unsubscribed_at: Optional[str] = None
    last_delivery_date: Optional[str] = None  # YYYY-MM-DD 형식

    @staticmethod
    def validate_email(email: str) -> bool:
        """
        이메일 주소 유효성 검증

        Args:
            email: 검증할 이메일 주소

        Returns:
            유효한 이메일이면 True
        """
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    @classmethod
    def from_dynamodb(cls, item: dict) -> "Recipient":
        """
        DynamoDB 아이템을 Recipient 객체로 변환

        Args:
            item: DynamoDB 아이템

        Returns:
            Recipient 객체
        """
        return cls(
            email=item["email"],
            name=item["name"],
            status=RecipientStatus(item["status"]),
            created_at=item["created_at"],
            unsubscribed_at=item.get("unsubscribed_at"),
            last_delivery_date=item.get("last_delivery_date"),
        )

    def to_dynamodb(self) -> dict:
        """
        Recipient 객체를 DynamoDB 아이템으로 변환

        Returns:
            DynamoDB 아이템
        """
        item = {
            "email": self.email,
            "name": self.name,
            "status": self.status.value,
            "created_at": self.created_at,
        }

        if self.unsubscribed_at:
            item["unsubscribed_at"] = self.unsubscribed_at

        if self.last_delivery_date:
            item["last_delivery_date"] = self.last_delivery_date

        return item

    @classmethod
    def create_new(cls, email: str, name: str) -> "Recipient":
        """
        새 수신인 생성

        Args:
            email: 이메일 주소
            name: 이름

        Returns:
            새 Recipient 객체

        Raises:
            ValueError: 이메일 형식이 올바르지 않은 경우
        """
        if not cls.validate_email(email):
            raise ValueError(f"올바르지 않은 이메일 형식: {email}")

        return cls(
            email=email,
            name=name,
            status=RecipientStatus.ACTIVE,
            created_at=datetime.now().isoformat(),
        )

    def unsubscribe(self) -> None:
        """수신거부 처리"""
        self.status = RecipientStatus.UNSUBSCRIBED
        self.unsubscribed_at = datetime.now().isoformat()

    def is_active(self) -> bool:
        """활성 수신인인지 확인"""
        return self.status == RecipientStatus.ACTIVE
