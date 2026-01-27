"""
Lambda 실행 이력 추적
날짜 + 모드별로 중복 실행 방지 (멱등성 보장)
"""
import logging
from datetime import datetime, timezone, timedelta
from botocore.exceptions import ClientError

from .recipients.dynamodb_client import DynamoDBClient

logger = logging.getLogger(__name__)


class ExecutionTracker:
    """Lambda 실행 이력 추적 클래스"""

    def __init__(self, table_name: str = "etnews-execution-log", region_name: str = "ap-northeast-2"):
        """
        Args:
            table_name: DynamoDB 실행 이력 테이블 이름
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

    def _get_execution_key(self, mode: str) -> str:
        """
        실행 키 생성 (날짜#모드)

        Args:
            mode: 실행 모드 ("test" 또는 "opr")

        Returns:
            실행 키 (예: "2026-01-27#test")
        """
        today = self._get_today_date()
        return f"{today}#{mode}"

    def should_skip_execution(self, mode: str) -> bool:
        """
        오늘 이미 실행되었는지 확인

        Args:
            mode: 실행 모드 ("test" 또는 "opr")

        Returns:
            건너뛰어야 하면 True
        """
        execution_key = self._get_execution_key(mode)

        try:
            table = self.db_client._get_table()
            response = table.get_item(Key={"execution_key": execution_key})

            if "Item" in response:
                item = response["Item"]
                request_id = item.get("request_id", "unknown")
                execution_time = item.get("execution_time", "unknown")

                logger.warning(
                    f"오늘 이미 {mode} 모드로 실행되었습니다 "
                    f"(키: {execution_key}, RequestId: {request_id}, 시각: {execution_time})"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"실행 이력 조회 오류: {e}")
            # 조회 실패 시 안전하게 진행 (false positive 방지)
            return False

    def mark_execution(self, mode: str, request_id: str) -> bool:
        """
        오늘 실행 기록

        Args:
            mode: 실행 모드 ("test" 또는 "opr")
            request_id: Lambda RequestId (context.request_id)

        Returns:
            성공 여부
        """
        execution_key = self._get_execution_key(mode)
        today = self._get_today_date()
        now = datetime.now(timezone.utc).isoformat()

        try:
            table = self.db_client._get_table()

            # TTL: 7일 후 자동 삭제
            ttl = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())

            # 경쟁 조건 방지: 이미 존재하는 키면 실패
            table.put_item(
                Item={
                    "execution_key": execution_key,
                    "date": today,
                    "mode": mode,
                    "request_id": request_id,
                    "execution_time": now,
                    "ttl": ttl
                },
                ConditionExpression="attribute_not_exists(execution_key)"
            )

            logger.info(f"실행 이력 기록: {execution_key} (RequestId: {request_id})")
            return True

        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"이미 기록된 실행: {execution_key} (중복 방지)")
                return False
            logger.error(f"실행 이력 기록 오류: {e}")
            return False
        except Exception as e:
            logger.error(f"실행 이력 기록 오류: {e}")
            # 기록 실패해도 Lambda는 정상 진행 (중요하지 않은 메타데이터)
            return False

    def get_execution_info(self, mode: str, date: str = None) -> dict:
        """
        특정 날짜의 실행 정보 조회

        Args:
            mode: 실행 모드 ("test" 또는 "opr")
            date: 조회할 날짜 (YYYY-MM-DD), None이면 오늘

        Returns:
            실행 정보 딕셔너리 또는 None
        """
        if date is None:
            date = self._get_today_date()

        execution_key = f"{date}#{mode}"

        try:
            table = self.db_client._get_table()
            response = table.get_item(Key={"execution_key": execution_key})

            if "Item" not in response:
                return None

            return response["Item"]

        except Exception as e:
            logger.error(f"실행 정보 조회 오류: {e}")
            return None
