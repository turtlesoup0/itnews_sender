"""
PDF 다운로드 실패 추적
DynamoDB를 사용하여 날짜별 실패 횟수를 기록하고 3회 이상 실패 시 건너뛰기
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from .recipients.dynamodb_client import DynamoDBClient

logger = logging.getLogger(__name__)


class FailureTracker:
    """PDF 다운로드 실패 추적 클래스"""

    def __init__(self, table_name: str = "etnews-delivery-failures", region_name: str = "ap-northeast-2"):
        """
        Args:
            table_name: DynamoDB 실패 이력 테이블 이름
            region_name: AWS 리전
        """
        self.table_name = table_name
        self.region_name = region_name
        self.db_client = DynamoDBClient(table_name, region_name)

    def _get_today_date(self) -> str:
        """
        오늘 날짜 반환 (KST 기준)

        Returns:
            YYYY-MM-DD 형식의 날짜 문자열
        """
        kst = timezone(timedelta(hours=9))
        today = datetime.now(kst)
        return today.strftime("%Y-%m-%d")

    def should_skip_today(self) -> bool:
        """
        오늘 3회 이상 실패했는지 확인

        Returns:
            건너뛰어야 하면 True
        """
        today = self._get_today_date()

        try:
            # DynamoDB에서 오늘 날짜 레코드 조회
            table = self.db_client._get_table()
            response = table.get_item(Key={"date": today})

            if "Item" not in response:
                return False

            item = response["Item"]
            failure_count = item.get("failure_count", 0)

            if failure_count >= 3:
                logger.warning(f"오늘({today}) 3회 이상 실패하여 발송을 건너뜁니다 (현재: {failure_count}회)")
                return True

            return False

        except Exception as e:
            logger.error(f"실패 이력 조회 오류: {e}")
            # 조회 실패 시 안전하게 진행
            return False

    def increment_failure(self, error_message: str) -> int:
        """
        실패 카운트 증가 및 현재 카운트 반환

        Args:
            error_message: 오류 메시지

        Returns:
            증가 후 실패 카운트
        """
        today = self._get_today_date()
        now = datetime.now(timezone.utc).isoformat()

        try:
            # TTL: 7일 후 자동 삭제
            ttl = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())

            # DynamoDB UpdateItem으로 원자적 증가
            table = self.db_client._get_table()
            response = table.update_item(
                Key={"date": today},
                UpdateExpression="ADD failure_count :inc SET last_error = :error, updated_at = :updated, #ttl = :ttl",
                ExpressionAttributeNames={
                    "#ttl": "ttl"  # ttl은 예약어이므로 별칭 사용
                },
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":error": error_message[:500],  # 최대 500자로 제한
                    ":updated": now,
                    ":ttl": ttl
                },
                ReturnValues="ALL_NEW"
            )

            new_count = response["Attributes"].get("failure_count", 0)
            logger.info(f"실패 카운트 증가: {today} - {new_count}회")
            return new_count

        except Exception as e:
            logger.error(f"실패 카운트 업데이트 오류: {e}")
            return 1  # 오류 발생 시 기본값 1 반환

    def reset_today(self) -> bool:
        """
        오늘 실패 카운트 리셋 (성공 시 호출)

        Returns:
            성공 여부
        """
        today = self._get_today_date()

        try:
            table = self.db_client._get_table()
            table.delete_item(Key={"date": today})
            logger.info(f"실패 카운트 리셋: {today}")
            return True

        except Exception as e:
            logger.error(f"실패 카운트 리셋 오류: {e}")
            return False

    def get_failure_info(self, date: Optional[str] = None) -> Optional[dict]:
        """
        특정 날짜의 실패 정보 조회

        Args:
            date: 조회할 날짜 (YYYY-MM-DD), None이면 오늘

        Returns:
            실패 정보 딕셔너리 또는 None
        """
        target_date = date or self._get_today_date()

        try:
            table = self.db_client._get_table()
            response = table.get_item(Key={"date": target_date})

            if "Item" not in response:
                return None

            return response["Item"]

        except Exception as e:
            logger.error(f"실패 정보 조회 오류: {e}")
            return None
