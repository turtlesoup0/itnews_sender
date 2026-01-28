#!/bin/bash
# Lambda 실행 역할에 Parameter Store 접근 권한 추가
# 실행 전 관리자 권한이 있는 AWS 프로필로 전환하세요
# 예: export AWS_PROFILE=admin

set -e

ROLE_NAME="itnews-sender-lambda-role"
POLICY_NAME="SSMParameterStoreAccess"
POLICY_FILE="scripts/ssm-policy.json"

echo "==================================================="
echo "Lambda IAM 역할에 SSM 권한 추가"
echo "==================================================="
echo ""
echo "대상 역할: $ROLE_NAME"
echo "정책 이름: $POLICY_NAME"
echo ""

# 역할 존재 여부 확인
echo "역할 확인 중..."
if ! aws iam get-role --role-name $ROLE_NAME &> /dev/null; then
    echo "❌ 역할을 찾을 수 없습니다: $ROLE_NAME"
    echo ""
    echo "사용 가능한 역할 목록:"
    aws iam list-roles --query "Roles[?contains(RoleName, 'itnews')].RoleName" --output table
    exit 1
fi

echo "✅ 역할 확인 완료: $ROLE_NAME"
echo ""

# 정책 추가
echo "정책 추가 중..."
aws iam put-role-policy \
  --role-name $ROLE_NAME \
  --policy-name $POLICY_NAME \
  --policy-document file://$POLICY_FILE

echo "✅ 정책 추가 완료: $POLICY_NAME"
echo ""

# 추가된 정책 확인
echo "==================================================="
echo "추가된 정책 내용:"
echo "==================================================="
aws iam get-role-policy \
  --role-name $ROLE_NAME \
  --policy-name $POLICY_NAME \
  --query "PolicyDocument" \
  --output json

echo ""
echo "==================================================="
echo "✅ Lambda IAM 역할 설정 완료"
echo "==================================================="
echo ""
echo "⚠️  다음 단계:"
echo "   1. 로컬 .env 파일에 Parameter Store URL 추가"
echo "   2. Lambda 함수 재배포 (Docker 이미지 빌드 & 푸시)"
echo "   3. 테스트 실행으로 Parameter Store 접근 확인"
