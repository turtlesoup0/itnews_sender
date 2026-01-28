#!/usr/bin/env python3
"""
수요일 체크 로직 테스트
"""
from datetime import datetime, timezone, timedelta

def is_wednesday() -> bool:
    """
    오늘이 수요일인지 확인 (KST 기준)

    Returns:
        bool: 수요일이면 True
    """
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    return now_kst.weekday() == 2  # 0=월요일, 2=수요일


if __name__ == '__main__':
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    now_utc = datetime.now(timezone.utc)

    print("=" * 60)
    print("수요일 체크 로직 테스트")
    print("=" * 60)
    print()
    print(f"현재 시각 (UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"현재 시각 (KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()
    print(f"요일 (weekday): {now_kst.weekday()}")
    print(f"  0=월요일, 1=화요일, 2=수요일, 3=목요일, 4=금요일, 5=토요일, 6=일요일")
    print()
    print(f"오늘은 수요일인가? {is_wednesday()}")
    print()

    if is_wednesday():
        print("✅ 오늘은 수요일입니다 - ITFIND 다운로드 시도")
    else:
        print("❌ 오늘은 수요일이 아닙니다 - ITFIND 다운로드 건너뛰기")
