#!/bin/bash
# Parameter Store 설정 스크립트
# 실행 전 관리자 권한이 있는 AWS 프로필로 전환하세요
# 예: export AWS_PROFILE=admin

set -e

REGION="ap-northeast-2"

echo "==================================================="
echo "AWS Parameter Store 설정"
echo "==================================================="
echo ""

# 1. 수신거부 Function URL
echo "[1/3] 수신거부 Function URL 등록..."
aws ssm put-parameter \
  --name "/etnews/unsubscribe-function-url" \
  --value "https://heswdvaag57hgz3ugvxk6ifqpq0ukhog.lambda-url.ap-northeast-2.on.aws" \
  --type "String" \
  --description "수신거부 Lambda Function URL" \
  --region $REGION \
  --overwrite

echo "✅ 등록 완료: /etnews/unsubscribe-function-url"
echo ""

# 2. 관리자 이메일
echo "[2/3] 관리자 이메일 등록..."
aws ssm put-parameter \
  --name "/etnews/admin-email" \
  --value "turtlesoup0@gmail.com" \
  --type "String" \
  --description "관리자 알림 수신 이메일" \
  --region $REGION \
  --overwrite

echo "✅ 등록 완료: /etnews/admin-email"
echo ""

# 3. 수신거부 Secret (SecureString)
echo "[3/3] 수신거부 Secret 생성 및 등록..."
SECRET=$(openssl rand -base64 32)
aws ssm put-parameter \
  --name "/etnews/unsubscribe-secret" \
  --value "$SECRET" \
  --type "SecureString" \
  --description "수신거부 HMAC Secret Key" \
  --region $REGION \
  --overwrite

echo "✅ 등록 완료: /etnews/unsubscribe-secret"
echo "   생성된 Secret: $SECRET"
echo ""

echo "==================================================="
echo "✅ Parameter Store 설정 완료"
echo "==================================================="
echo ""
echo "등록된 Parameters 확인:"
aws ssm get-parameters \
  --names "/etnews/unsubscribe-function-url" "/etnews/admin-email" "/etnews/unsubscribe-secret" \
  --with-decryption \
  --region $REGION \
  --query "Parameters[*].[Name,Value,Type]" \
  --output table

echo ""
echo "⚠️  다음 단계: Lambda IAM 역할에 SSM 권한 추가 필요"
echo "   스크립트 실행: ./scripts/add_lambda_iam_policy.sh"
