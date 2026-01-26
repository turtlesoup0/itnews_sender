#!/usr/bin/env python3
"""
Lambda 함수 수동 트리거 스크립트
로컬에서 Lambda 핸들러를 직접 호출합니다.
"""
import json
import sys
from lambda_handler import handler


def main():
    print("=" * 80)
    print("IT뉴스 PDF 자동 배송 시스템 - 수동 실행")
    print("=" * 80)
    print()

    # 가짜 Lambda 이벤트와 컨텍스트
    event = {
        "source": "manual-trigger",
        "time": "2026-01-26T00:00:00Z"
    }

    class FakeContext:
        def __init__(self):
            self.function_name = "etnews-pdf-sender"
            self.request_id = "local-manual-trigger"

    context = FakeContext()

    try:
        print("Lambda 함수 실행 중...")
        print()
        result = handler(event, context)

        print()
        print("=" * 80)
        print("실행 결과:")
        print("=" * 80)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print()

        if result.get('statusCode') == 200:
            print("✅ 성공!")
            return 0
        else:
            print("⚠️  경고 또는 오류 발생")
            return 1

    except Exception as e:
        print()
        print("=" * 80)
        print("❌ 오류 발생:")
        print("=" * 80)
        print(f"{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
