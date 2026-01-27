#!/bin/bash

# Lambda 메모리 사용량 분석 스크립트
# CloudWatch Logs Insights 쿼리를 실행하여 실제 메모리 사용량 확인

FUNCTION_NAME="etnews-pdf-sender"
REGION="ap-northeast-2"
LOG_GROUP="/aws/lambda/$FUNCTION_NAME"

echo "===== Lambda 메모리 사용량 분석 ====="
echo "함수: $FUNCTION_NAME"
echo "리전: $REGION"
echo ""

# 참고: AWS CLI가 설치되어 있어야 합니다
# 사용자가 직접 AWS Console의 CloudWatch Logs Insights에서 실행하거나
# 아래 쿼리를 복사하여 사용할 수 있습니다

cat <<'EOF'
CloudWatch Logs Insights 쿼리:

fields @timestamp, @memorySize, @maxMemoryUsed, @duration
| filter @type = "REPORT"
| stats
    avg(@maxMemoryUsed) as avgMemoryMB,
    max(@maxMemoryUsed) as maxMemoryMB,
    avg(@duration) as avgDurationMs,
    max(@duration) as maxDurationMs,
    count(*) as invocations
| limit 1

---

결과 해석:
- avgMemoryMB: 평균 메모리 사용량 (MB)
- maxMemoryMB: 최대 메모리 사용량 (MB)
- avgDurationMs: 평균 실행 시간 (밀리초)
- maxDurationMs: 최대 실행 시간 (밀리초)

권장 메모리 설정:
- maxMemoryMB × 1.2 (20% 여유)
- 예: maxMemoryMB가 1500MB이면 → 1792MB 설정

---

AWS Console에서 실행:
1. CloudWatch → Logs → Insights
2. 로그 그룹 선택: /aws/lambda/etnews-pdf-sender
3. 시간 범위: 최근 7일
4. 위 쿼리 복사 & 실행

EOF

echo ""
echo "메모리 최적화 권장 단계:"
echo "1. 위 쿼리를 CloudWatch Logs Insights에서 실행"
echo "2. maxMemoryMB 확인"
echo "3. Lambda 함수 메모리 설정 = maxMemoryMB × 1.2"
echo "4. AWS Console 또는 AWS CLI로 메모리 업데이트:"
echo ""
echo "   aws lambda update-function-configuration \\"
echo "     --function-name $FUNCTION_NAME \\"
echo "     --region $REGION \\"
echo "     --memory-size <계산된_메모리_MB>"
