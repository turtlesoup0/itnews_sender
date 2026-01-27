#!/usr/bin/env python3
"""
실행 이력 초기화 스크립트
DynamoDB etnews-execution-log 테이블의 특정 날짜/모드 키 삭제
"""
import sys
import boto3
from datetime import datetime, timezone, timedelta

def reset_execution_log(date=None, mode=None):
    """
    실행 이력 초기화

    Args:
        date: 날짜 (YYYY-MM-DD), None이면 오늘
        mode: 모드 ("test" 또는 "opr"), None이면 모두
    """
    # KST 기준 오늘 날짜
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")

    target_date = date or today

    dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
    table = dynamodb.Table('etnews-execution-log')

    if mode:
        # 특정 모드만 삭제
        keys_to_delete = [f"{target_date}#{mode}"]
    else:
        # 모든 모드 삭제
        keys_to_delete = [f"{target_date}#test", f"{target_date}#opr"]

    for execution_key in keys_to_delete:
        try:
            response = table.delete_item(Key={'execution_key': execution_key})
            print(f"✅ 삭제 완료: {execution_key}")
        except Exception as e:
            print(f"⚠️  삭제 실패 ({execution_key}): {e}")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode not in ['test', 'opr']:
            print(f"사용법: {sys.argv[0]} [test|opr]")
            sys.exit(1)
        reset_execution_log(mode=mode)
    else:
        # 모든 모드 삭제
        reset_execution_log()
