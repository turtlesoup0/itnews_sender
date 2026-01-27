#!/bin/bash
# Lambda 실행 이력 테이블 생성 및 IAM 권한 추가

set -e

REGION="ap-northeast-2"
TABLE_NAME="etnews-execution-log"
LAMBDA_FUNCTION="etnews-pdf-sender"

echo "===== Lambda 실행 이력 테이블 설정 시작 ====="

# 1. DynamoDB 테이블 생성
echo ""
echo "1. DynamoDB 테이블 생성: ${TABLE_NAME}"

aws dynamodb create-table \
  --region ${REGION} \
  --table-name ${TABLE_NAME} \
  --attribute-definitions AttributeName=execution_key,AttributeType=S \
  --key-schema AttributeName=execution_key,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=etnews-pdf-sender Key=Purpose,Value=idempotency \
  --time-to-live-specification "Enabled=true,AttributeName=ttl"

echo "✅ DynamoDB 테이블 생성 완료"

# 2. 테이블 확인
echo ""
echo "2. 테이블 상태 확인"
aws dynamodb describe-table \
  --region ${REGION} \
  --table-name ${TABLE_NAME} \
  --query 'Table.[TableName,TableStatus,BillingModeSummary.BillingMode]' \
  --output text

# 3. Lambda IAM 정책 안내
echo ""
echo "3. Lambda IAM 정책 업데이트 필요"
echo ""
echo "Lambda 함수의 실행 역할에 다음 권한을 추가해야 합니다:"
echo ""
echo "-------- IAM 정책 (JSON) --------"
cat <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem"
      ],
      "Resource": "arn:aws:dynamodb:ap-northeast-2:*:table/etnews-execution-log"
    }
  ]
}
EOF
echo "--------------------------------"
echo ""
echo "AWS Console에서 Lambda > ${LAMBDA_FUNCTION} > 구성 > 권한 > 실행 역할에서 정책을 추가하세요."
echo "또는 기존 etnews-delivery-failures 정책에 Resource를 추가하세요:"
echo ""
echo "  \"Resource\": ["
echo "    \"arn:aws:dynamodb:ap-northeast-2:*:table/etnews-delivery-failures\","
echo "    \"arn:aws:dynamodb:ap-northeast-2:*:table/etnews-execution-log\""
echo "  ]"
echo ""

echo "===== Lambda 실행 이력 테이블 설정 완료 ====="
