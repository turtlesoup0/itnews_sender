#!/bin/bash
# ITFIND PDF 다운로더 Lambda 배포 스크립트

set -e

# 색상 정의
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}ITFIND PDF Downloader Lambda 배포${NC}"
echo -e "${BLUE}========================================${NC}"

# 설정
AWS_REGION="ap-northeast-2"
FUNCTION_NAME="itfind-pdf-downloader"
ECR_REPOSITORY="${FUNCTION_NAME}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"

echo -e "\n${GREEN}[1/6] ECR 저장소 확인/생성${NC}"
if ! aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${AWS_REGION} 2>/dev/null; then
    echo "ECR 저장소 생성 중..."
    aws ecr create-repository \
        --repository-name ${ECR_REPOSITORY} \
        --region ${AWS_REGION} \
        --image-scanning-configuration scanOnPush=true
    echo -e "${GREEN}✓ ECR 저장소 생성 완료${NC}"
else
    echo -e "${GREEN}✓ ECR 저장소 존재 확인${NC}"
fi

echo -e "\n${GREEN}[2/6] ECR 로그인${NC}"
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
echo -e "${GREEN}✓ ECR 로그인 완료${NC}"

echo -e "\n${GREEN}[3/6] Docker 이미지 빌드${NC}"
docker build -t ${FUNCTION_NAME}:latest -f Dockerfile.itfind .
echo -e "${GREEN}✓ Docker 이미지 빌드 완료${NC}"

echo -e "\n${GREEN}[4/6] Docker 이미지 태그 및 푸시${NC}"
docker tag ${FUNCTION_NAME}:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest
echo -e "${GREEN}✓ ECR 푸시 완료${NC}"

echo -e "\n${GREEN}[5/6] Lambda 함수 확인/생성${NC}"
if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${AWS_REGION} 2>/dev/null; then
    echo "Lambda 함수 업데이트 중..."
    aws lambda update-function-code \
        --function-name ${FUNCTION_NAME} \
        --image-uri ${ECR_URI}:latest \
        --region ${AWS_REGION}

    echo "설정 업데이트 중..."
    aws lambda update-function-configuration \
        --function-name ${FUNCTION_NAME} \
        --timeout 300 \
        --memory-size 2048 \
        --region ${AWS_REGION}

    echo -e "${GREEN}✓ Lambda 함수 업데이트 완료${NC}"
else
    echo "Lambda 함수 생성 중..."

    # IAM 역할 ARN 가져오기
    ROLE_ARN=$(aws iam get-role --role-name lambda-execution-role --query 'Role.Arn' --output text 2>/dev/null || echo "")

    if [ -z "$ROLE_ARN" ]; then
        echo -e "${RED}✗ IAM 역할을 찾을 수 없습니다${NC}"
        echo "다음 명령어로 역할을 생성하세요:"
        echo "  aws iam create-role --role-name lambda-execution-role --assume-role-policy-document file://trust-policy.json"
        exit 1
    fi

    aws lambda create-function \
        --function-name ${FUNCTION_NAME} \
        --package-type Image \
        --code ImageUri=${ECR_URI}:latest \
        --role ${ROLE_ARN} \
        --timeout 300 \
        --memory-size 2048 \
        --environment Variables="{S3_BUCKET=itnews-sender-pdfs}" \
        --region ${AWS_REGION}

    echo -e "${GREEN}✓ Lambda 함수 생성 완료${NC}"
fi

echo -e "\n${GREEN}[6/6] Lambda 함수 배포 대기${NC}"
aws lambda wait function-updated --function-name ${FUNCTION_NAME} --region ${AWS_REGION}
echo -e "${GREEN}✓ Lambda 함수 배포 완료${NC}"

echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}✓ 배포 완료!${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "함수 이름: ${FUNCTION_NAME}"
echo -e "리전: ${AWS_REGION}"
echo -e "메모리: 2048 MB"
echo -e "타임아웃: 300초"
echo -e "\n테스트 명령어:"
echo -e "  aws lambda invoke --function-name ${FUNCTION_NAME} --region ${AWS_REGION} /tmp/response.json"
