"""
이메일 발송 이력 추적
DynamoDB를 사용하여 일별 발송 여부를 기록하고 중복 발송을 방지
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class DeliveryTracker:
    """이메일 발송 이력 추적 클래스"""

    def __init__(self, table_name: str = "etnews-delivery-history", region_name: str = "ap-northeast-2"):
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

    def _get_today_key(self) -> str:
        """
        오늘 날짜의 키 생성 (KST 기준)

        Returns:
            YYYY-MM-DD 형식의 날짜 문자열
        """
        kst = timezone(timedelta(hours=9))
        today = datetime.now(kst)
        return today.strftime("%Y-%m-%d")

    def is_delivered_today(self) -> bool:
        """
        오늘 이미 발송되었는지 확인

        Returns:
            발송 여부 (True: 이미 발송됨, False: 미발송)
        """
        date_key = self._get_today_key()

        try:
            table = self._get_table()
            response = table.get_item(Key={"delivery_date": date_key})

            if "Item" in response:
                item = response["Item"]
                logger.info(f"발송 이력 확인: {date_key} - 발송 완료 (수신인: {item.get('recipient_count', 0)}명)")
                return True
            else:
                logger.info(f"발송 이력 확인: {date_key} - 미발송")
                return False

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')

            # 테이블이 없는 경우 False 반환 (첫 실행)
            if error_code == 'ResourceNotFoundException':
                logger.warning(f"발송 이력 테이블이 없습니다: {self.table_name}")
                return False

            logger.error(f"발송 이력 조회 실패: {e}")
            return False

    def mark_as_delivered(self, recipient_count: int, pdf_title: Optional[str] = None) -> bool:
        """
        오늘 발송 완료로 기록

        Args:
            recipient_count: 수신인 수
            pdf_title: PDF 제목 (선택)

        Returns:
            성공 여부
        """
        date_key = self._get_today_key()
        kst = timezone(timedelta(hours=9))
        timestamp = datetime.now(kst).isoformat()

        item = {
            "delivery_date": date_key,
            "timestamp": timestamp,
            "recipient_count": recipient_count,
            "status": "delivered"
        }

        if pdf_title:
            item["pdf_title"] = pdf_title

        try:
            table = self._get_table()
            table.put_item(Item=item)
            logger.info(f"발송 이력 기록 완료: {date_key} - 수신인 {recipient_count}명")
            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')

            # 테이블이 없는 경우 경고만 출력하고 계속 진행
            if error_code == 'ResourceNotFoundException':
                logger.warning(f"발송 이력 테이블이 없습니다: {self.table_name} (이력 기록 스킵)")
                return True  # 이력 기록 실패해도 메일 발송은 성공으로 처리

            logger.error(f"발송 이력 기록 실패: {e}")
            return False

    def get_delivery_info(self, date_key: Optional[str] = None) -> Optional[dict]:
        """
        특정 날짜의 발송 정보 조회

        Args:
            date_key: 조회할 날짜 (YYYY-MM-DD), None이면 오늘

        Returns:
            발송 정보 딕셔너리 또는 None
        """
        if date_key is None:
            date_key = self._get_today_key()

        try:
            table = self._get_table()
            response = table.get_item(Key={"delivery_date": date_key})

            if "Item" in response:
                return response["Item"]
            else:
                return None

        except ClientError as e:
            logger.error(f"발송 정보 조회 실패: {e}")
            return None
