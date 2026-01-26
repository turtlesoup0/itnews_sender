#!/usr/bin/env python3
"""
DynamoDB 발송 이력 테이블 생성 스크립트
"""
import boto3
from botocore.exceptions import ClientError


def create_delivery_history_table(
    table_name: str = "etnews-delivery-history",
    region_name: str = "ap-northeast-2"
):
    """
    발송 이력 테이블 생성

    Args:
        table_name: 테이블 이름
        region_name: AWS 리전
    """
    dynamodb = boto3.client("dynamodb", region_name=region_name)

    try:
        # 테이블 생성
        response = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {
                    "AttributeName": "delivery_date",
                    "KeyType": "HASH"  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    "AttributeName": "delivery_date",
                    "AttributeType": "S"  # String (YYYY-MM-DD)
                }
            ],
            BillingMode="PAY_PER_REQUEST",  # On-demand 요금제
            Tags=[
                {
                    "Key": "Project",
                    "Value": "etnews-sender"
                },
                {
                    "Key": "Purpose",
                    "Value": "delivery-tracking"
                }
            ]
        )

        print(f"✅ 테이블 생성 시작: {table_name}")
        print(f"   리전: {region_name}")
        print(f"   상태: {response['TableDescription']['TableStatus']}")

        # 테이블이 ACTIVE 상태가 될 때까지 대기
        waiter = dynamodb.get_waiter("table_exists")
        print("\n⏳ 테이블 생성 완료 대기 중...")
        waiter.wait(TableName=table_name)

        print(f"\n✅ 테이블 생성 완료: {table_name}")
        print(f"   ARN: {response['TableDescription']['TableArn']}")

        return True

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")

        if error_code == "ResourceInUseException":
            print(f"⚠️  테이블이 이미 존재합니다: {table_name}")
            return True
        else:
            print(f"❌ 테이블 생성 실패: {e}")
            return False


def describe_table(table_name: str = "etnews-delivery-history", region_name: str = "ap-northeast-2"):
    """테이블 정보 조회"""
    dynamodb = boto3.client("dynamodb", region_name=region_name)

    try:
        response = dynamodb.describe_table(TableName=table_name)
        table = response["Table"]

        print(f"\n📊 테이블 정보: {table_name}")
        print(f"   상태: {table['TableStatus']}")
        print(f"   파티션 키: {table['KeySchema'][0]['AttributeName']}")
        print(f"   항목 수: {table.get('ItemCount', 0)}")
        print(f"   테이블 크기: {table.get('TableSizeBytes', 0)} bytes")
        print(f"   생성 시간: {table['CreationDateTime']}")

    except ClientError as e:
        print(f"❌ 테이블 조회 실패: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "describe":
        describe_table()
    else:
        success = create_delivery_history_table()
        if success:
            print("\n" + "="*60)
            describe_table()
            print("="*60)
            sys.exit(0)
        else:
            sys.exit(1)
