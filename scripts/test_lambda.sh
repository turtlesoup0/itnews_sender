#!/bin/bash
# Lambda 테스트 실행 스크립트
# Timeout 설정으로 중복 실행 방지

set -e

FUNCTION_NAME="etnews-pdf-sender"
REGION="ap-northeast-2"
OUTPUT_FILE="/tmp/lambda_test_response.json"

# 기본값: TEST 모드
MODE="${1:-test}"

# 두 번째 인자: skip-idempotency 옵션
SKIP_IDEMPOTENCY="${2:-false}"

echo "===== Lambda 테스트 실행 ====="
echo "모드: $MODE"
if [ "$SKIP_IDEMPOTENCY" = "skip-idempotency" ]; then
  echo "멱등성 체크: 비활성화 (재실행 가능)"
else
  echo "멱등성 체크: 활성화"
fi
echo "함수: $FUNCTION_NAME"
echo ""

# Timeout 충분히 설정 (5분)
echo "Lambda 호출 중... (최대 5분 대기)"

# Payload 생성
if [ "$SKIP_IDEMPOTENCY" = "skip-idempotency" ]; then
  PAYLOAD=$(echo -n "{\"mode\": \"$MODE\", \"skip_idempotency\": true}" | base64)
else
  PAYLOAD=$(echo -n "{\"mode\": \"$MODE\"}" | base64)
fi

aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --cli-read-timeout 300 \
  --cli-connect-timeout 60 \
  --payload "$PAYLOAD" \
  "$OUTPUT_FILE"

echo ""
echo "===== 실행 결과 ====="
cat "$OUTPUT_FILE" | jq . 2>/dev/null || cat "$OUTPUT_FILE"

echo ""
echo "===== CloudWatch Logs (최근 1분) ====="
aws logs tail /aws/lambda/"$FUNCTION_NAME" \
  --region "$REGION" \
  --since 1m \
  --format short | grep -E "모드|StatusCode|메일" || echo "(관련 로그 없음)"

echo ""
echo "===== 완료 ====="
echo ""
echo "사용법:"
echo "  일반 테스트 (멱등성 O):     ./scripts/test_lambda.sh test"
echo "  재실행 가능 (멱등성 X):     ./scripts/test_lambda.sh test skip-idempotency"
echo "  OPR 모드:                   ./scripts/test_lambda.sh opr"
echo ""
