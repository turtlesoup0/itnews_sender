#!/bin/bash
# Lambda 테스트 실행 스크립트
# Timeout 설정으로 중복 실행 방지

set -e

FUNCTION_NAME="etnews-pdf-sender"
REGION="ap-northeast-2"
OUTPUT_FILE="/tmp/lambda_test_response.json"

# 기본값: TEST 모드
MODE="${1:-test}"

echo "===== Lambda 테스트 실행 ====="
echo "모드: $MODE"
echo "함수: $FUNCTION_NAME"
echo ""

# Timeout 충분히 설정 (5분)
echo "Lambda 호출 중... (최대 5분 대기)"
aws lambda invoke \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --cli-read-timeout 300 \
  --cli-connect-timeout 60 \
  --payload "{\"mode\": \"$MODE\"}" \
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
