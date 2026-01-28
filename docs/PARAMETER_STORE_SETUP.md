# Parameter Store 설정 가이드

## 빠른 시작 (스크립트 사용)

관리자 권한이 있는 AWS 프로필로 전환 후 실행:

```bash
# AWS 프로필 전환 (선택사항)
export AWS_PROFILE=admin

# 1. Parameter Store에 값 등록
./scripts/setup_parameter_store.sh

# 2. Lambda IAM 역할에 SSM 권한 추가
./scripts/add_lambda_iam_policy.sh
```

---

## 수동 설정 (상세)

### 1. 필수 Parameter 추가

### 1.1 수신거부 Function URL
```bash
aws ssm put-parameter \
  --name "/etnews/unsubscribe-function-url" \
  --value "https://heswdvaag57hgz3ugvxk6ifqpq0ukhog.lambda-url.ap-northeast-2.on.aws" \
  --type "String" \
  --description "수신거부 Lambda Function URL" \
  --region ap-northeast-2
```

### 1.2 관리자 이메일
```bash
aws ssm put-parameter \
  --name "/etnews/admin-email" \
  --value "turtlesoup0@gmail.com" \
  --type "String" \
  --description "관리자 알림 수신 이메일" \
  --region ap-northeast-2
```

### 1.3 수신거부 Secret (Secrets Manager 권장)
```bash
# Option A: Parameter Store (SecureString)
aws ssm put-parameter \
  --name "/etnews/unsubscribe-secret" \
  --value "$(openssl rand -base64 32)" \
  --type "SecureString" \
  --description "수신거부 HMAC Secret Key" \
  --region ap-northeast-2

# Option B: Secrets Manager (권장)
aws secretsmanager create-secret \
  --name "etnews/unsubscribe-secret" \
  --secret-string "$(openssl rand -base64 32)" \
  --description "수신거부 HMAC Secret Key" \
  --region ap-northeast-2
```

## 2. 기존 `/etnews/credentials` 확인

현재 구조:
```json
{
  "ETNEWS_USER_ID": "...",
  "ETNEWS_PASSWORD": "...",
  "GMAIL_USER": "...",
  "GMAIL_APP_PASSWORD": "...",
  "ICLOUD_EMAIL": "...",
  "ICLOUD_PASSWORD": "...",
  "ICLOUD_FOLDER_NAME": "..."
}
```

## 3. IAM 권한 추가

### Lambda 실행 역할에 추가 필요
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter"
      ],
      "Resource": [
        "arn:aws:ssm:ap-northeast-2:269809345127:parameter/etnews/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:ap-northeast-2:269809345127:secret:etnews/*"
      ]
    }
  ]
}
```

## 4. 로컬 개발 환경

`.env` 파일에 추가:
```bash
UNSUBSCRIBE_FUNCTION_URL=https://heswdvaag57hgz3ugvxk6ifqpq0ukhog.lambda-url.ap-northeast-2.on.aws
ADMIN_EMAIL=turtlesoup0@gmail.com
UNSUBSCRIBE_SECRET=<로컬 개발용 secret>
```
