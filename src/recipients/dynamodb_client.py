"""
DynamoDB 클라이언트
"""
import logging
import os
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class DynamoDBClient:
    """DynamoDB 테이블 작업 클라이언트"""

    def __init__(self, table_name: str = "etnews-recipients", region_name: str = "ap-northeast-2"):
        """
        Args:
            table_name: DynamoDB 테이블 이름
            region_name: AWS 리전
        """
        self.table_name = table_name
        self.region_name = region_name
        self._dynamodb = None
        self._table = None

    def _get_table(self):
        """DynamoDB 테이블 리소스 가져오기 (lazy loading)"""
        if self._table is None:
            self._dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
            self._table = self._dynamodb.Table(self.table_name)
        return self._table

    def put_item(self, item: Dict) -> bool:
        """
        아이템 추가 또는 업데이트

        Args:
            item: 저장할 아이템

        Returns:
            성공 여부
        """
        try:
            table = self._get_table()
            table.put_item(Item=item)
            logger.info(f"DynamoDB에 아이템 저장 완료: {item.get('email')}")
            return True

        except ClientError as e:
            logger.error(f"DynamoDB put_item 실패: {e}")
            return False

    def get_item(self, email: str) -> Optional[Dict]:
        """
        이메일로 아이템 조회

        Args:
            email: 조회할 이메일

        Returns:
            아이템 딕셔너리 또는 None
        """
        try:
            table = self._get_table()
            response = table.get_item(Key={"email": email})

            if "Item" in response:
                logger.info(f"DynamoDB 아이템 조회 완료: {email}")
                return response["Item"]
            else:
                logger.info(f"DynamoDB 아이템 없음: {email}")
                return None

        except ClientError as e:
            logger.error(f"DynamoDB get_item 실패: {e}")
            return None

    def query_by_status(self, status: str) -> List[Dict]:
        """
        상태별로 아이템 조회 (GSI 사용)

        Args:
            status: 조회할 상태 (active, unsubscribed)

        Returns:
            아이템 리스트
        """
        try:
            table = self._get_table()
            response = table.query(
                IndexName="status-index",
                KeyConditionExpression="#status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": status},
            )

            items = response.get("Items", [])
            logger.info(f"DynamoDB 상태별 조회 완료: {status} ({len(items)}건)")
            return items

        except ClientError as e:
            logger.error(f"DynamoDB query 실패: {e}")
            return []

    def scan_all(self) -> List[Dict]:
        """
        모든 아이템 스캔

        Returns:
            모든 아이템 리스트
        """
        try:
            table = self._get_table()
            response = table.scan()

            items = response.get("Items", [])

            # 페이지네이션 처리
            while "LastEvaluatedKey" in response:
                response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
                items.extend(response.get("Items", []))

            logger.info(f"DynamoDB 전체 스캔 완료: {len(items)}건")
            return items

        except ClientError as e:
            logger.error(f"DynamoDB scan 실패: {e}")
            return []

    def update_item(self, email: str, updates: Dict) -> bool:
        """
        아이템 필드 업데이트

        Args:
            email: 업데이트할 이메일
            updates: 업데이트할 필드 딕셔너리

        Returns:
            성공 여부
        """
        try:
            table = self._get_table()

            # UpdateExpression 생성
            update_expression = "SET " + ", ".join([f"#{k} = :{k}" for k in updates.keys()])
            expression_attribute_names = {f"#{k}": k for k in updates.keys()}
            expression_attribute_values = {f":{k}": v for k, v in updates.items()}

            table.update_item(
                Key={"email": email},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
            )

            logger.info(f"DynamoDB 아이템 업데이트 완료: {email}")
            return True

        except ClientError as e:
            logger.error(f"DynamoDB update_item 실패: {e}")
            return False

    def delete_item(self, email: str) -> bool:
        """
        아이템 삭제

        Args:
            email: 삭제할 이메일

        Returns:
            성공 여부
        """
        try:
            table = self._get_table()
            table.delete_item(Key={"email": email})
            logger.info(f"DynamoDB 아이템 삭제 완료: {email}")
            return True

        except ClientError as e:
            logger.error(f"DynamoDB delete_item 실패: {e}")
            return False
