# IT 뉴스 PDF 자동 배송 시스템

특정 IT 뉴스 사이트에서 매일 PDF 뉴스지면을 자동으로 다운로드하고, 광고 페이지를 제거한 후 다중 수신인에게 이메일로 전송하는 AWS Lambda 기반 자동화 시스템입니다.

## 주요 기능

- **자동 다운로드**: 매일 한국시간 06:00에 IT뉴스 PDF 자동 다운로드
- **광고 제거**: 웹 페이지 메타 정보와 PDF 텍스트 분석을 통한 전면광고 자동 감지 및 제거
- **다중 수신인 관리**: DynamoDB 기반 수신인 목록 관리 (최대 100명)
- **개별 이메일 전송**: 각 수신인에게 개인화된 수신거부 링크 포함
- **수신거부 기능**: Lambda Function URL을 통한 원클릭 수신거부
- **신문 미발행일 감지**: 발행되지 않은 날에는 자동으로 메일 미전송
- **구독 만료 알림**: PDF 서비스 구독 종료일 7일 전 관리자에게 이메일 알림
- **보안**: AWS Systems Manager Parameter Store를 통한 민감정보 암호화 저장
- **iCloud 업로드**: (선택사항) iCloud Drive에 연/월별 폴더 구조로 자동 업로드
- **CI/CD**: GitHub Actions를 통한 자동 배포

## 시스템 아키텍처

```
EventBridge Scheduler (매일 06:00 KST)
    ↓
Main Lambda (Docker 컨테이너)
    → Playwright: 웹사이트 로그인 + PDF 다운로드
    → PDF Processor: 광고 페이지 제거 (최대 50MB)
    → Recipient Manager: DynamoDB에서 활성 수신인 조회
    → Email Sender: 개별 이메일 전송 (HMAC 기반 수신거부 링크)
    → iCloud Uploader (선택)

사용자 수신거부 클릭
    ↓
Lambda Function URL
    → HMAC 토큰 검증 (월별 로테이션)
    → DynamoDB에서 수신인 완전 삭제
    → HTML 확인 페이지 반환
```

## 프로젝트 구조

```
itnews_sender/
├── .github/
│   └── workflows/
│       └── deploy.yml              # GitHub Actions 워크플로우
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   └── unsubscribe_handler.py  # 수신거부 Lambda 핸들러
│   ├── recipients/
│   │   ├── __init__.py
│   │   ├── models.py               # 수신인 데이터 모델
│   │   ├── dynamodb_client.py      # DynamoDB 클라이언트
│   │   └── recipient_manager.py    # 수신인 관리 로직
│   ├── config.py                   # 설정 관리
│   ├── parameter_store.py          # Parameter Store 클라이언트
│   ├── scraper.py                  # PDF 다운로드
│   ├── pdf_processor.py            # PDF 광고 제거 (최대 50MB)
│   ├── email_sender.py             # 이메일 전송
│   ├── unsubscribe_token.py        # HMAC 토큰 생성/검증
│   ├── structured_logging.py       # JSON 구조화 로깅
│   └── icloud_uploader.py          # iCloud 업로드
├── scripts/
│   └── manage_recipients.py        # 수신인 관리 CLI 도구
├── lambda_handler.py               # Main Lambda 진입점
├── unsubscribe_lambda.py           # Unsubscribe Lambda 진입점
├── Dockerfile                      # 컨테이너 이미지 정의
├── requirements.txt                # Python 의존성
├── DEPLOYMENT.md                   # 배포 가이드
├── SECURITY_SETUP.md               # 보안 설정 가이드
├── REFACTORING_PLAN.md             # 리팩토링 계획
└── REVIEW.md                       # 코드 검토 결과
```

## 시스템 요구사항

- Python 3.11+
- Docker (컨테이너 이미지 빌드용)
- AWS CLI (배포용)
- AWS 계정 (Lambda, DynamoDB, ECR, EventBridge, Parameter Store)

## 설치 및 설정

### 1. AWS 리소스 생성

자세한 설정 방법은 [DEPLOYMENT.md](DEPLOYMENT.md)를 참고하세요.

#### Parameter Store 설정
```bash
aws ssm put-parameter \
  --name /itnews/credentials \
  --type SecureString \
  --value '{
    "SITE_USER_ID": "your_site_id",
    "SITE_PASSWORD": "your_site_password",
    "GMAIL_USER": "your_gmail@gmail.com",
    "GMAIL_APP_PASSWORD": "your_gmail_app_password"
  }' \
  --region ap-northeast-2
```

#### DynamoDB 테이블 생성
```bash
aws dynamodb create-table \
  --table-name newsletter-recipients \
  --attribute-definitions \
    AttributeName=email,AttributeType=S \
    AttributeName=status,AttributeType=S \
  --key-schema AttributeName=email,KeyType=HASH \
  --global-secondary-indexes \
    "IndexName=status-index,KeySchema=[{AttributeName=status,KeyType=HASH}],Projection={ProjectionType=ALL}" \
  --billing-mode PAY_PER_REQUEST \
  --region ap-northeast-2
```

### 2. 수신인 관리

```bash
# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 수신인 추가
python scripts/manage_recipients.py add user@example.com "사용자 이름"

# 활성 수신인 목록 조회
python scripts/manage_recipients.py list-active

# 수신인 삭제
python scripts/manage_recipients.py remove user@example.com
```

### 3. GitHub Actions CI/CD 설정

#### GitHub Secrets 설정
Repository → Settings → Secrets and variables → Actions → Repository secrets:
- `AWS_ACCESS_KEY_ID`: AWS IAM 사용자의 Access Key ID
- `AWS_SECRET_ACCESS_KEY`: AWS IAM 사용자의 Secret Access Key

#### 자동 배포
`main` 브랜치에 push 시 자동으로 Lambda 함수 배포:
- Main Lambda: Docker 이미지 빌드 → ECR 푸시 → Lambda 업데이트
- Unsubscribe Lambda: Zip 패키지 생성 → Lambda 업데이트

### 4. AWS 리소스 설정

DynamoDB 실패 추적 테이블 및 EventBridge 스케줄 설정:

```bash
# AWS 리소스 자동 설정
bash scripts/setup_aws_resources.sh

# 또는 수동 설정
# 1. DynamoDB 테이블 생성
aws dynamodb create-table \
  --table-name etnews-delivery-failures \
  --attribute-definitions AttributeName=date,AttributeType=S \
  --key-schema AttributeName=date,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-northeast-2

# 2. EventBridge 스케줄에 OPR 모드 설정
aws events put-targets \
  --rule etnews-daily-trigger \
  --targets 'Id=1,Arn=<Lambda ARN>,Input={"mode":"opr"}' \
  --region ap-northeast-2
```

**Lambda IAM 권한 추가** (AWS Console에서 수동 설정):
- Lambda > etnews-pdf-sender > 구성 > 권한 > 실행 역할 > 정책 추가
- `etnews-delivery-failures` 테이블에 대한 `dynamodb:PutItem`, `GetItem`, `UpdateItem`, `DeleteItem` 권한

## 테스트 모드

### 실행 모드

| 모드 | event 파라미터 | 수신인 | 발송 이력 기록 | 용도 |
|------|---------------|--------|--------------|------|
| **TEST** | `mode: "test"` 또는 미지정 | `turtlesoup0@gmail.com` 고정 | ❌ 기록 안 함 | 안전한 테스트 |
| **OPR** | `mode: "opr"` | DynamoDB 활성 수신인 전체 | ✅ 기록 | 실제 운영 발송 |

### 수동 트리거

**TEST 모드 (기본 - 안전)**:
```bash
# 파라미터 없음 = TEST 모드
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --payload '{}' \
  response.json

# 또는 명시적으로 test 지정
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --payload '{"mode": "test"}' \
  response.json
```

**OPR 모드 (운영 발송 - 신중히)**:
```bash
# ⚠️ 주의: 실제 수신인에게 메일 발송됨
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --payload '{"mode": "opr"}' \
  response.json
```

### 로그 모니터링

```bash
# 실시간 로그 확인
aws logs tail /aws/lambda/etnews-pdf-sender --follow --region ap-northeast-2

# 최근 10분 로그
aws logs tail /aws/lambda/etnews-pdf-sender --since 10m --region ap-northeast-2
```

## 주요 기술 스택

- **언어**: Python 3.11
- **웹 스크래핑**: Playwright (헤드리스 Chromium)
- **PDF 처리**: pypdf (광고 페이지 제거)
- **이메일**: Gmail SMTP (smtplib)
- **데이터베이스**: DynamoDB (수신인 관리)
- **보안**: Parameter Store (민감정보 암호화), HMAC-SHA256 (토큰 서명)
- **컨테이너**: Docker (Lambda 배포)
- **CI/CD**: GitHub Actions
- **모니터링**: CloudWatch Logs (JSON 구조화 로깅)

## 보안 기능

1. **민감정보 암호화**: Parameter Store SecureString 사용
2. **HMAC 토큰**: 수신거부 링크에 SHA256 서명 적용
3. **월별 로테이션**: 토큰이 자동으로 월별 갱신
4. **상수 시간 비교**: 타이밍 공격 방지 (hmac.compare_digest)
5. **IAM 권한 최소화**: Lambda 실행 역할에 필요한 권한만 부여
6. **중복 발송 방지**: 수신인별 발송 이력 추적 (last_delivery_date)
7. **실패 추적**: PDF 다운로드 3회 이상 실패 시 건너뛰기 및 관리자 알림
8. **테스트 모드**: 기본값이 TEST 모드로 실수 발송 방지

## 비용 최적화

- **DynamoDB**: On-demand 모드, 프리티어 25GB
- **Lambda**: 프리티어 월 100만 건 요청
- **Parameter Store**: Standard tier 무료
- **ECR**: 프리티어 월 500MB
- **예상 월 비용**: $0 ~ $5 (프리티어 내)

## 모니터링

### CloudWatch Logs 쿼리 예제

```
# 이메일 전송 실패 검색
fields @timestamp, message, recipient, error
| filter event = "email_failed"
| sort @timestamp desc

# Lambda 실행 시간 분석
fields @timestamp, duration_ms
| filter event = "lambda_success"
| stats avg(duration_ms), max(duration_ms), min(duration_ms)
```

## 문제 해결

### Gmail SMTP 인증 실패
1. Google 계정 → 보안 → 2단계 인증 활성화
2. 보안 → 앱 비밀번호 생성
3. 생성된 16자리 비밀번호를 Parameter Store에 저장

### Lambda 타임아웃
- 현재 설정: 15분 (900초)
- PDF 다운로드가 느린 경우 발생 가능
- CloudWatch Logs에서 실행 시간 확인 후 조정

### 수신거부 링크 오류
1. Lambda Function URL 확인
2. CORS 설정 확인 (모든 메소드 허용)
3. 리소스 기반 정책 확인

## 라이선스

MIT License

## 기여

- 이슈 및 개선 제안: [GitHub Issues](https://github.com/turtlesoup0/itnews_sender/issues)
- 개발자: turtlesoup0@gmail.com

## 면책 조항

이 프로젝트는 개인적인 자동화 목적으로 제작되었습니다. 사용자는 해당 뉴스 서비스의 이용 약관을 준수할 책임이 있습니다.
