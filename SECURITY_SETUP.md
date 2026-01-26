# 보안 설정 가이드

이 문서는 AWS Secrets Manager를 사용하여 민감정보를 안전하게 관리하는 방법을 설명합니다.

## 현재 보안 구조

### Lambda 환경
- ✅ AWS Secrets Manager를 사용하여 credentials 저장
- ✅ Lambda 함수는 Secrets Manager에서 실시간으로 credentials 로드
- ✅ 환경변수에 평문 저장하지 않음

### 로컬 환경
- ✅ `.env` 파일 사용 (git에서 제외됨)
- ✅ `.env` 파일은 절대 커밋하지 않음

## AWS Secrets Manager 설정 방법

### 1. IAM 권한 추가

Lambda 실행 역할(`etnews-lambda-role`)에 다음 정책 추가:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": "arn:aws:secretsmanager:ap-northeast-2:269809345127:secret:etnews-credentials-*"
        }
    ]
}
```

**AWS Console에서 추가하는 방법:**
1. IAM 콘솔 → Roles → `etnews-lambda-role` 선택
2. "Add permissions" → "Create inline policy" 클릭
3. JSON 탭에서 위 정책 붙여넣기
4. 정책 이름: `SecretsManagerReadAccess`
5. "Create policy" 클릭

### 2. AWS Secrets Manager에 시크릿 생성

#### 방법 1: AWS Console 사용 (권장)

1. AWS Console → Secrets Manager 접속
2. "Store a new secret" 클릭
3. Secret type: "Other type of secret" 선택
4. Key/value pairs에 다음 정보 입력:
   ```
   ETNEWS_USER_ID: turtlesoup0
   ETNEWS_PASSWORD: $ER3w%Tm
   GMAIL_USER: turtlesoup0@gmail.com
   GMAIL_APP_PASSWORD: huucdfabpilreybh
   RECIPIENT_EMAIL: turtlesoup0@gmail.com
   ICLOUD_EMAIL: turtlesoup0.kr@gmail.com
   ICLOUD_PASSWORD: ckol-sbse-kzkh-wdmw
   ICLOUD_FOLDER_NAME: IT뉴스
   ```
5. Secret name: `etnews-credentials`
6. Description: "IT뉴스 PDF 자동 전송 시스템 Credentials"
7. "Next" → "Next" → "Store" 클릭

#### 방법 2: AWS CLI 사용

먼저 IAM 사용자에게 Secrets Manager 권한 추가 필요:

```bash
# IAM 정책 추가 (AWS Console에서 수동으로 추가 권장)
# - AWSSecretsManagerFullAccess 또는
# - 커스텀 정책으로 secretsmanager:CreateSecret 권한 추가

# 시크릿 생성
aws secretsmanager create-secret \
  --name etnews-credentials \
  --description "IT뉴스 PDF 자동 전송 시스템 Credentials" \
  --secret-string '{
    "ETNEWS_USER_ID": "turtlesoup0",
    "ETNEWS_PASSWORD": "$ER3w%Tm",
    "GMAIL_USER": "turtlesoup0@gmail.com",
    "GMAIL_APP_PASSWORD": "huucdfabpilreybh",
    "RECIPIENT_EMAIL": "turtlesoup0@gmail.com",
    "ICLOUD_EMAIL": "turtlesoup0.kr@gmail.com",
    "ICLOUD_PASSWORD": "ckol-sbse-kzkh-wdmw",
    "ICLOUD_FOLDER_NAME": "IT뉴스"
  }' \
  --region ap-northeast-2
```

### 3. Lambda 환경변수 제거

시크릿이 생성되면 Lambda 환경변수에서 민감정보 제거:

```bash
aws lambda update-function-configuration \
  --function-name etnews-pdf-sender \
  --environment 'Variables={TZ=Asia/Seoul}' \
  --region ap-northeast-2
```

이렇게 하면 Lambda는 Secrets Manager에서 credentials를 로드하고,
환경변수에는 타임존 정보만 남습니다.

### 4. 동작 확인

Lambda 함수를 테스트하여 정상 동작 확인:

```bash
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  /tmp/lambda-response.json
```

CloudWatch Logs에서 다음 로그 확인:
```
Lambda 환경: Secrets Manager에서 credentials 로드
Credentials 로드 완료
```

## 비용

AWS Secrets Manager 비용:
- 시크릿 저장: $0.40/월
- API 호출: 10,000건당 $0.05

Lambda 콜드 스타트 시 Secrets Manager 호출이 발생하지만,
실행 중에는 캐싱되므로 추가 API 호출은 없습니다.

일일 실행 기준 월 비용: **약 $0.45**

## 보안 장점

### 기존 방식 (환경변수)
- ❌ AWS Console/CLI에서 평문으로 노출
- ❌ CloudFormation/Terraform에 평문 저장
- ❌ IAM 권한만 있으면 누구나 조회 가능
- ❌ 변경 이력 추적 불가능

### 개선 방식 (Secrets Manager)
- ✅ 암호화되어 저장 (KMS)
- ✅ 접근 시 감사 로그 자동 기록 (CloudTrail)
- ✅ 버전 관리 및 rotation 지원
- ✅ 세분화된 접근 제어 가능
- ✅ 변경 이력 추적 가능

## 주의사항

1. **`.env` 파일 관리**
   - 절대 git에 커밋하지 마세요
   - `.gitignore`에 이미 포함되어 있습니다
   - 로컬 개발용으로만 사용하세요

2. **시크릿 업데이트**
   - 비밀번호 변경 시 Secrets Manager에서 업데이트
   - Lambda 재시작 필요 없음 (다음 콜드 스타트에 자동 반영)

3. **IAM 권한**
   - Lambda 역할에만 Secrets Manager 읽기 권한 부여
   - 개발자 IAM 사용자에는 필요시에만 권한 부여

## 문제 해결

### Secrets Manager 접근 실패

```
ClientError: An error occurred (AccessDeniedException)
```

**해결 방법:**
1. Lambda 실행 역할 확인
2. Secrets Manager 읽기 권한 확인
3. Secret 이름이 정확한지 확인 (`etnews-credentials`)

### 로컬에서 테스트 시 오류

로컬 환경에서는 `.env` 파일을 사용합니다:

```bash
# .env 파일이 있는지 확인
ls -la .env

# 환경변수가 로드되는지 확인
python3 -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('ETNEWS_USER_ID'))"
```

## 참고 자료

- [AWS Secrets Manager 문서](https://docs.aws.amazon.com/secretsmanager/)
- [Lambda에서 Secrets Manager 사용하기](https://docs.aws.amazon.com/lambda/latest/dg/configuration-secrets.html)
- [Secrets Manager 가격](https://aws.amazon.com/secrets-manager/pricing/)
