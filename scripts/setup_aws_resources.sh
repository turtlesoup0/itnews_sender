#!/bin/bash
# AWS 리소스 설정 스크립트
# DynamoDB 테이블 생성 및 EventBridge 스케줄 설정

set -e

REGION="ap-northeast-2"
FAILURE_TABLE="etnews-delivery-failures"
LAMBDA_FUNCTION="etnews-pdf-sender"
EVENTBRIDGE_RULE="etnews-daily-trigger"

echo "===== AWS 리소스 설정 시작 ====="

# 1. DynamoDB 실패 이력 테이블 생성
echo ""
echo "1. DynamoDB 테이블 생성: ${FAILURE_TABLE}"

aws dynamodb create-table \
  --region ${REGION} \
  --table-name ${FAILURE_TABLE} \
  --attribute-definitions AttributeName=date,AttributeType=S \
  --key-schema AttributeName=date,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=etnews-pdf-sender Key=Purpose,Value=failure-tracking

echo "✅ DynamoDB 테이블 생성 완료"

# 2. Lambda 함수 ARN 조회
echo ""
echo "2. Lambda 함수 ARN 조회"

LAMBDA_ARN=$(aws lambda get-function \
  --region ${REGION} \
  --function-name ${LAMBDA_FUNCTION} \
  --query 'Configuration.FunctionArn' \
  --output text)

echo "Lambda ARN: ${LAMBDA_ARN}"

# 3. EventBridge 스케줄 Input 설정 (OPR 모드)
echo ""
echo "3. EventBridge 스케줄 설정 (OPR 모드)"

aws events put-targets \
  --region ${REGION} \
  --rule ${EVENTBRIDGE_RULE} \
  --targets "Id=1,Arn=${LAMBDA_ARN},Input={\"mode\":\"opr\"}"

echo "✅ EventBridge 스케줄 설정 완료"

# 4. Lambda IAM 정책 업데이트 안내
echo ""
echo "4. Lambda IAM 정책 업데이트 필요"
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
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": "arn:aws:dynamodb:ap-northeast-2:*:table/etnews-delivery-failures"
    }
  ]
}
EOF
echo "--------------------------------"
echo ""
echo "AWS Console에서 Lambda > etnews-pdf-sender > 구성 > 권한 > 실행 역할에서 정책을 추가하세요."
echo ""

# 5. 설정 확인
echo "5. 설정 확인"
echo ""

# DynamoDB 테이블 확인
echo "- DynamoDB 테이블:"
aws dynamodb describe-table \
  --region ${REGION} \
  --table-name ${FAILURE_TABLE} \
  --query 'Table.[TableName,TableStatus,BillingModeSummary.BillingMode]' \
  --output text

# EventBridge 타겟 확인
echo ""
echo "- EventBridge 타겟:"
aws events list-targets-by-rule \
  --region ${REGION} \
  --rule ${EVENTBRIDGE_RULE} \
  --query 'Targets[0].[Id,Input]' \
  --output text

echo ""
echo "===== AWS 리소스 설정 완료 ====="
