# 배포 가이드

## GitHub Actions 자동 배포 설정

### 사전 요구사항

1. **AWS IAM 사용자 생성 (GitHub Actions용)**
   - 필요한 권한:
     - `AWSLambda_FullAccess` (Lambda 함수 업데이트)
     - `AmazonEC2ContainerRegistryPowerUser` (ECR 이미지 푸시)
   - Access Key ID와 Secret Access Key 생성

2. **GitHub Secrets 설정**
   - Repository → Settings → Secrets and variables → Actions
   - 다음 secrets 추가:
     - `AWS_ACCESS_KEY_ID`: IAM 사용자의 Access Key ID
     - `AWS_SECRET_ACCESS_KEY`: IAM 사용자의 Secret Access Key

### 배포 워크플로우

`.github/workflows/deploy.yml` 파일이 다음 작업을 자동으로 수행합니다:

#### 1. Main Lambda 함수 배포 (Container 기반)
- `main` 브랜치에 push 시 자동 실행
- Docker 이미지 빌드
- Amazon ECR에 이미지 푸시
- Lambda 함수 코드 업데이트 (`etnews-pdf-sender`)

#### 2. Unsubscribe Lambda 함수 배포 (Zip 기반)
- Python 의존성 패키지 생성
- Zip 파일로 패키징
- Lambda 함수 코드 업데이트 (`etnews-unsubscribe-handler`)

### 수동 배포

워크플로우를 수동으로 실행하려면:
1. GitHub Repository → Actions 탭
2. "Deploy to AWS Lambda" 워크플로우 선택
3. "Run workflow" 버튼 클릭

### 배포 확인

```bash
# Lambda 함수 정보 확인
aws lambda get-function --function-name etnews-pdf-sender --region ap-northeast-2
aws lambda get-function --function-name etnews-unsubscribe-handler --region ap-northeast-2

# 최근 배포 로그 확인
aws lambda get-function-configuration --function-name etnews-pdf-sender --region ap-northeast-2
```

## 로컬 개발 및 테스트

### 환경 설정

```bash
# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

### 수신인 관리 CLI 도구

```bash
# 수신인 추가
python scripts/manage_recipients.py add user@example.com "사용자 이름"

# 활성 수신인 목록 조회
python scripts/manage_recipients.py list-active

# 전체 수신인 목록 조회
python scripts/manage_recipients.py list

# 수신인 삭제
python scripts/manage_recipients.py remove user@example.com
```

### Lambda 함수 로컬 테스트

```bash
# Main Lambda 함수 테스트 (Docker 컨테이너)
docker build -t etnews-sender .
docker run --rm \
  -e AWS_ACCESS_KEY_ID=your_key \
  -e AWS_SECRET_ACCESS_KEY=your_secret \
  -e AWS_DEFAULT_REGION=ap-northeast-2 \
  etnews-sender

# Unsubscribe Lambda 함수 테스트
python -c "
from unsubscribe_lambda import handler
import json

event = {
    'httpMethod': 'GET',
    'queryStringParameters': {
        'token': 'test-token'
    }
}
result = handler(event, None)
print(json.dumps(result, indent=2))
"
```

## 트러블슈팅

### 배포 실패 시

1. **GitHub Actions 로그 확인**
   - Actions 탭에서 실패한 워크플로우 클릭
   - 각 스텝의 로그 확인

2. **AWS 권한 확인**
   ```bash
   aws sts get-caller-identity
   ```

3. **ECR 저장소 확인**
   ```bash
   aws ecr describe-repositories --region ap-northeast-2
   ```

### Lambda 함수 오류 시

```bash
# CloudWatch Logs 확인
aws logs tail /aws/lambda/etnews-pdf-sender --follow
aws logs tail /aws/lambda/etnews-unsubscribe-handler --follow
```

## 환경변수 관리

Lambda 함수는 AWS Systems Manager Parameter Store를 사용합니다:

```bash
# Parameter 확인
aws ssm get-parameter --name /etnews/credentials --region ap-northeast-2 --with-decryption

# Parameter 업데이트
aws ssm put-parameter \
  --name /etnews/credentials \
  --type SecureString \
  --value '{"ETNEWS_USER_ID":"xxx","ETNEWS_PASSWORD":"xxx","GMAIL_USER":"xxx","GMAIL_APP_PASSWORD":"xxx"}' \
  --overwrite \
  --region ap-northeast-2
```

## 모니터링

### CloudWatch 대시보드
- Lambda 함수 실행 횟수, 기간, 오류율 확인
- DynamoDB 읽기/쓰기 용량 모니터링
- ECR 스토리지 사용량 확인

### 알림 설정 (선택사항)
- CloudWatch Alarms 생성
- Lambda 오류 발생 시 SNS 알림
- EventBridge 스케줄 실행 실패 시 알림
