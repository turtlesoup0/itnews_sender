# 리팩토링 계획서

## 목표
1. 다중 수신인 관리 시스템 구축
2. 수신거부 기능 구현
3. Git Actions 자동 배포 설정

## 1. 다중 수신인 관리 시스템

### 1.1 DynamoDB 테이블 설계

**테이블 이름**: `etnews-recipients`

| 속성명 | 타입 | 설명 | 키 |
|--------|------|------|-----|
| email | String | 수신자 이메일 | Partition Key |
| name | String | 수신자 이름 | - |
| status | String | 상태 (active/unsubscribed) | - |
| created_at | String | 생성 시간 (ISO 8601) | - |
| unsubscribed_at | String | 수신거부 시간 (ISO 8601) | - |

**GSI (Global Secondary Index)**:
- Index name: `status-index`
- Partition key: `status`
- 목적: active 수신인만 빠르게 조회

### 1.2 새로운 모듈 구조

```
src/
├── recipients/
│   ├── __init__.py
│   ├── dynamodb_client.py      # DynamoDB 클라이언트
│   ├── recipient_manager.py    # 수신인 CRUD 로직
│   └── models.py               # 수신인 데이터 모델
├── api/
│   ├── __init__.py
│   └── unsubscribe_handler.py  # 수신거부 Lambda 핸들러
└── email_sender.py (수정)       # 다중 수신인 지원
```

### 1.3 변경사항

#### `src/recipients/dynamodb_client.py` (신규)
- DynamoDB 테이블 연결
- 기본 CRUD 작업 래퍼

#### `src/recipients/recipient_manager.py` (신규)
- `get_active_recipients()`: 활성 수신인 목록 조회
- `add_recipient(email, name)`: 수신인 추가
- `unsubscribe(email)`: 수신거부 처리
- `get_recipient(email)`: 단일 수신인 조회

#### `src/recipients/models.py` (신규)
- `Recipient` 데이터클래스
- 유효성 검증 로직

#### `src/email_sender.py` (수정)
- `send_bulk_emails()`: 다중 수신인 전송 함수 추가
- 이메일 본문에 수신거부 링크 추가
- 개인화된 수신거부 토큰 생성

#### `src/api/unsubscribe_handler.py` (신규)
- API Gateway + Lambda로 수신거부 처리
- 토큰 검증 후 DynamoDB 업데이트
- 수신거부 확인 페이지 반환

## 2. 수신거부 기능 구현

### 2.1 수신거부 토큰 생성

```python
import hmac
import hashlib
import base64

def generate_unsubscribe_token(email: str, secret_key: str) -> str:
    """HMAC 기반 수신거부 토큰 생성"""
    message = f"{email}:{datetime.now().strftime('%Y-%m')}"
    signature = hmac.new(
        secret_key.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    token = base64.urlsafe_b64encode(signature).decode()
    return f"{email}:{token}"
```

### 2.2 수신거부 URL 구조

```
https://[api-gateway-url]/prod/unsubscribe?token=[base64_token]
```

### 2.3 이메일 본문 수정

```html
<hr>
<p style="font-size: 12px; color: #666;">
    이 뉴스레터를 더 이상 받고 싶지 않으시면
    <a href="{unsubscribe_url}" style="color: #666;">여기</a>를 클릭하세요.
</p>
```

## 3. AWS 인프라 구성

### 3.1 DynamoDB 테이블 생성

```bash
aws dynamodb create-table \
  --table-name etnews-recipients \
  --attribute-definitions \
    AttributeName=email,AttributeType=S \
    AttributeName=status,AttributeType=S \
  --key-schema \
    AttributeName=email,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes \
    IndexName=status-index,KeySchema=[{AttributeName=status,KeyType=HASH}],Projection={ProjectionType=ALL} \
  --region ap-northeast-2
```

### 3.2 Lambda 함수 생성 (수신거부 핸들러)

- 함수 이름: `etnews-unsubscribe-handler`
- 런타임: Python 3.12
- 메모리: 128MB (최소)
- 타임아웃: 10초

### 3.3 API Gateway 설정

- REST API 생성
- `/unsubscribe` GET 엔드포인트
- Lambda 프록시 통합
- CORS 활성화

### 3.4 IAM 권한 추가

**etnews-lambda-role에 추가**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:Scan",
        "dynamodb:Query",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:ap-northeast-2:269809345127:table/etnews-recipients",
        "arn:aws:dynamodb:ap-northeast-2:269809345127:table/etnews-recipients/index/*"
      ]
    }
  ]
}
```

## 4. Git 및 CI/CD 설정

### 4.1 Git 리포지토리 초기화

```bash
git init
git add .
git commit -m "Initial commit: AWS Lambda 전자신문 자동화"
```

### 4.2 GitHub Actions 워크플로우

**파일**: `.github/workflows/deploy.yml`

```yaml
name: Deploy to AWS Lambda

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ap-northeast-2

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push Docker image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          ECR_REPOSITORY: etnews-pdf-sender
          IMAGE_TAG: ${{ github.sha }}
        run: |
          docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
          docker tag $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG $ECR_REGISTRY/$ECR_REPOSITORY:latest
          docker push $ECR_REGISTRY/$ECR_REPOSITORY:latest

      - name: Update Lambda function
        run: |
          aws lambda update-function-code \
            --function-name etnews-pdf-sender \
            --image-uri 269809345127.dkr.ecr.ap-northeast-2.amazonaws.com/etnews-pdf-sender:latest
```

### 4.3 GitHub Secrets 설정

Repository Settings → Secrets and variables → Actions에 추가:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

## 5. 수신인 관리 CLI 도구

**파일**: `scripts/manage_recipients.py`

```python
"""
수신인 관리 CLI 도구

사용법:
  python scripts/manage_recipients.py add user@example.com "홍길동"
  python scripts/manage_recipients.py list
  python scripts/manage_recipients.py remove user@example.com
"""
```

## 6. 마이그레이션 단계

### Phase 1: 기본 구조 구축 (Day 1)
1. DynamoDB 테이블 생성
2. `src/recipients/` 모듈 구현
3. 기존 수신인 마이그레이션 (RECIPIENT_EMAIL → DynamoDB)
4. 로컬 테스트

### Phase 2: 다중 수신인 지원 (Day 2)
1. `email_sender.py` 수정 (다중 전송)
2. `lambda_handler.py` 수정
3. 통합 테스트

### Phase 3: 수신거부 기능 (Day 3)
1. 수신거부 Lambda 함수 배포
2. API Gateway 설정
3. 이메일 본문에 수신거부 링크 추가
4. 수신거부 플로우 테스트

### Phase 4: CI/CD 설정 (Day 4)
1. GitHub 리포지토리 생성
2. GitHub Actions 워크플로우 작성
3. 첫 자동 배포 테스트

## 7. 테스트 계획

### 7.1 단위 테스트
- `test_recipient_manager.py`: 수신인 CRUD 테스트
- `test_email_sender.py`: 다중 전송 테스트
- `test_unsubscribe.py`: 수신거부 토큰 검증 테스트

### 7.2 통합 테스트
- 전체 워크플로우 실행 (PDF 다운로드 → 다중 전송)
- 수신거부 → 다음 전송에서 제외 확인

## 8. 비용 예상

| 서비스 | 사용량 | 비용 |
|--------|--------|------|
| DynamoDB | 100명, 월 30회 read | **무료** (Free Tier) |
| Lambda (수신거부) | 월 ~10회 실행 | **무료** |
| API Gateway | 월 ~10 요청 | **무료** (첫 100만 요청) |
| **총계** | - | **$0.00** |

## 9. 보안 고려사항

1. **수신거부 토큰**: HMAC 기반 서명으로 위조 방지
2. **DynamoDB 접근**: IAM 역할로 최소 권한 원칙
3. **이메일 주소 검증**: 정규식으로 유효성 검사
4. **Rate Limiting**: API Gateway에서 제한 설정

## 10. 롤백 계획

문제 발생 시:
1. 이전 Git 커밋으로 롤백
2. Lambda 함수 이전 버전으로 복구
3. DynamoDB 백업에서 복원 (Point-in-Time Recovery 활성화)

## 다음 단계

1. ✅ 계획서 검토 및 승인
2. ⏳ DynamoDB 테이블 생성
3. ⏳ 수신인 관리 모듈 구현
4. ⏳ 이메일 전송 로직 수정
5. ⏳ 수신거부 API 구현
6. ⏳ CI/CD 파이프라인 구성
