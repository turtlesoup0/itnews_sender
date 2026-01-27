"""
이메일 발송 이력 추적
수신인별 마지막 발송 날짜를 DynamoDB에 기록하여 중복 발송 방지
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List

from .recipients import get_active_recipients
from .recipients.dynamodb_client import DynamoDBClient

logger = logging.getLogger(__name__)


class DeliveryTracker:
    """이메일 발송 이력 추적 클래스"""

    def __init__(self, table_name: str = "etnews-recipients", region_name: str = "ap-northeast-2"):
        """
        Args:
            table_name: DynamoDB 수신인 테이블 이름
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

    def is_delivered_today(self) -> bool:
        """
        오늘 이미 발송되었는지 확인 (모든 활성 수신인 체크)

        Returns:
            발송 여부 (True: 모든 수신인에게 이미 발송됨, False: 미발송)
        """
        today = self._get_today_date()
        recipients = get_active_recipients()

        if not recipients:
            logger.warning("활성 수신인이 없습니다")
            return True  # 발송 완료로 간주하여 조기 종료

        # 모든 수신인이 오늘 발송 받았는지 확인
        all_delivered = True
        delivered_count = 0

        for recipient in recipients:
            if recipient.last_delivery_date == today:
                delivered_count += 1
            else:
                all_delivered = False

        if all_delivered and delivered_count > 0:
            logger.info(f"발송 이력 확인: {today} - 모든 수신인({delivered_count}명)에게 이미 발송됨")
            return True
        elif delivered_count > 0:
            logger.info(f"발송 이력 확인: {today} - 일부 수신인({delivered_count}/{len(recipients)}명)에게 발송됨, 재발송 진행")
            return False
        else:
            logger.info(f"발송 이력 확인: {today} - 미발송")
            return False

    def mark_as_delivered(self, recipient_emails: List[str]) -> bool:
        """
        수신인별로 오늘 날짜를 마지막 발송일로 업데이트

        Args:
            recipient_emails: 발송 성공한 수신인 이메일 리스트

        Returns:
            성공 여부
        """
        today = self._get_today_date()
        success_count = 0
        fail_count = 0

        for email in recipient_emails:
            try:
                # last_delivery_date 필드만 업데이트
                result = self.db_client.update_item(
                    email=email,
                    updates={"last_delivery_date": today}
                )

                if result:
                    success_count += 1
                else:
                    fail_count += 1
                    logger.warning(f"발송 이력 업데이트 실패: {email}")

            except Exception as e:
                fail_count += 1
                logger.error(f"발송 이력 업데이트 오류: {email} - {e}")

        logger.info(f"발송 이력 업데이트 완료: 성공 {success_count}명, 실패 {fail_count}명 (날짜: {today})")
        return success_count > 0
