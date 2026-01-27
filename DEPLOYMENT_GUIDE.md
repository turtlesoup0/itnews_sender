# 테스트 모드 및 보안 개선 배포 가이드

**작성일**: 2026-01-27
**대상 버전**: 1aca207

---

## 배포 순서

### 1단계: 코드 배포

GitHub에 푸시하여 자동 배포 트리거:

```bash
git push origin main
```

GitHub Actions가 자동으로 다음 작업을 수행합니다:
- Docker 이미지 빌드 (arm64 아키텍처)
- ECR 푸시
- Lambda 함수 업데이트

배포 진행 상황:
- GitHub → Actions 탭에서 실시간 확인
- 예상 시간: 약 5-10분

---

### 2단계: AWS 리소스 설정

#### Option A: 자동 설정 스크립트 (권장)

```bash
bash scripts/setup_aws_resources.sh
```

#### Option B: 수동 설정

**DynamoDB 테이블 생성**:
```bash
aws dynamodb create-table \
  --region ap-northeast-2 \
  --table-name etnews-delivery-failures \
  --attribute-definitions AttributeName=date,AttributeType=S \
  --key-schema AttributeName=date,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=etnews-pdf-sender Key=Purpose,Value=failure-tracking
```

**EventBridge 스케줄 설정**:
```bash
# Lambda ARN 조회
LAMBDA_ARN=$(aws lambda get-function \
  --region ap-northeast-2 \
  --function-name etnews-pdf-sender \
  --query 'Configuration.FunctionArn' \
  --output text)

# OPR 모드로 정기 실행 설정
aws events put-targets \
  --region ap-northeast-2 \
  --rule etnews-daily-trigger \
  --targets "Id=1,Arn=${LAMBDA_ARN},Input={\"mode\":\"opr\"}"
```

---

### 3단계: Lambda IAM 권한 추가

**AWS Console 방법**:
1. Lambda → `etnews-pdf-sender` → 구성 → 권한
2. 실행 역할 클릭 (IAM 콘솔로 이동)
3. "권한 추가" → "인라인 정책 생성"
4. JSON 탭 선택 후 다음 정책 붙여넣기:

```json
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
```

5. 정책 이름: `etnews-delivery-failures-access`
6. "정책 생성" 클릭

**AWS CLI 방법**:
```bash
# Lambda 실행 역할 이름 조회
ROLE_NAME=$(aws lambda get-function \
  --region ap-northeast-2 \
  --function-name etnews-pdf-sender \
  --query 'Configuration.Role' \
  --output text | awk -F'/' '{print $NF}')

# 인라인 정책 추가
aws iam put-role-policy \
  --role-name ${ROLE_NAME} \
  --policy-name etnews-delivery-failures-access \
  --policy-document '{
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
  }'
```

---

### 4단계: 배포 검증

#### 4-1. TEST 모드 검증 (안전)

```bash
# TEST 모드로 실행
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --payload '{}' \
  response.json

# 로그 확인
aws logs tail /aws/lambda/etnews-pdf-sender --follow --region ap-northeast-2
```

**검증 항목**:
- ✅ "🧪 TEST 모드로 실행" 로그 확인
- ✅ turtlesoup0@gmail.com에게만 메일 수신
- ✅ DynamoDB `etnews-recipients`의 `last_delivery_date` 업데이트 안 됨

#### 4-2. TEST 모드 중복 실행 (안전성 확인)

```bash
# TEST 모드를 3번 연속 실행
for i in {1..3}; do
  echo "실행 $i"
  aws lambda invoke \
    --function-name etnews-pdf-sender \
    --region ap-northeast-2 \
    --payload '{}' \
    response_$i.json
  sleep 10
done
```

**검증**:
- ✅ turtlesoup0@gmail.com에 3통 메일 수신 (중복 방지 안 됨 = 정상)
- ✅ 발송 이력 미기록으로 매번 발송됨

#### 4-3. OPR 모드 안전 검증 (신중히)

**사전 준비**:
```bash
# 모든 수신인을 오늘 발송 받은 것으로 설정
python scripts/manage_recipients.py set-all-delivered-today
```

**OPR 모드 실행**:
```bash
# ⚠️ 주의: 중복 방지 로직이 동작하면 메일 발송 안 됨
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --payload '{"mode": "opr"}' \
  response_opr.json

# 로그 확인
aws logs tail /aws/lambda/etnews-pdf-sender --region ap-northeast-2
```

**검증**:
- ✅ "🚀 OPR 모드로 실행" 로그 확인
- ✅ "오늘 이미 메일이 발송되었습니다" 로그 확인
- ✅ 실제 이메일 발송 안 됨 (중복 방지 동작)

---

### 5단계: 실패 추적 기능 검증 (선택)

#### 5-1. 의도적 실패 시나리오

**전자신문 로그인 정보 임시 변경**:
```bash
# 현재 환경변수 백업
aws lambda get-function-configuration \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --query 'Environment.Variables' > env_backup.json

# 잘못된 자격증명으로 변경 (실패 유도)
aws lambda update-function-configuration \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --environment "Variables={ETNEWS_USER_ID=wrong_user,ETNEWS_PASSWORD=wrong_pass,...}"

# ⚠️ 나머지 환경변수도 함께 지정해야 함 (덮어씌워지므로)
```

**3번 실패 테스트**:
```bash
for i in {1..3}; do
  echo "실패 테스트 $i"
  aws lambda invoke \
    --function-name etnews-pdf-sender \
    --region ap-northeast-2 \
    --payload '{}' \
    response_fail_$i.json
  sleep 10
done
```

**DynamoDB 확인**:
```bash
# 실패 카운트 확인
aws dynamodb get-item \
  --table-name etnews-delivery-failures \
  --key '{"date": {"S": "2026-01-27"}}' \
  --region ap-northeast-2
```

**검증**:
- ✅ DynamoDB에 `failure_count=3` 기록됨
- ✅ 3회째 실패 후 turtlesoup0@gmail.com에 관리자 알림 메일 수신
- ✅ 4회째 실행 시 "오늘 3회 이상 실패하여 건너뜁니다" 로그

**환경변수 복원**:
```bash
# 백업한 환경변수로 복원
aws lambda update-function-configuration \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --environment "Variables={...}"  # env_backup.json 내용 사용
```

---

### 6단계: EventBridge 스케줄 확인

```bash
# 타겟 설정 확인
aws events list-targets-by-rule \
  --region ap-northeast-2 \
  --rule etnews-daily-trigger

# Input 필드에 {"mode":"opr"} 확인
```

**예상 출력**:
```json
{
  "Targets": [
    {
      "Id": "1",
      "Arn": "arn:aws:lambda:ap-northeast-2:...:function:etnews-pdf-sender",
      "Input": "{\"mode\":\"opr\"}"
    }
  ]
}
```

---

## 롤백 절차

문제 발생 시 이전 버전으로 롤백:

### Lambda 함수 롤백

```bash
# 이전 버전 확인
aws lambda list-versions-by-function \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2

# 특정 버전으로 롤백 (예: 버전 3)
aws lambda update-alias \
  --function-name etnews-pdf-sender \
  --name LIVE \
  --function-version 3 \
  --region ap-northeast-2
```

### EventBridge Input 롤백

```bash
# Input 제거 (파라미터 없이 실행)
aws events put-targets \
  --region ap-northeast-2 \
  --rule etnews-daily-trigger \
  --targets "Id=1,Arn=<Lambda ARN>"
```

---

## 모니터링

### CloudWatch Logs Insights 쿼리

**테스트/운영 모드 실행 이력**:
```
fields @timestamp, execution_mode, message
| filter event = "lambda_start"
| sort @timestamp desc
| limit 20
```

**실패 추적 이력**:
```
fields @timestamp, message, error
| filter @message like /실패/
| sort @timestamp desc
| limit 50
```

**중복 발송 방지 이력**:
```
fields @timestamp, message, duration_ms
| filter event = "duplicate_delivery_prevented"
| sort @timestamp desc
| limit 20
```

### DynamoDB 모니터링

```bash
# 실패 이력 조회 (최근 7일)
for i in {0..6}; do
  DATE=$(date -v-${i}d +%Y-%m-%d)
  echo "===== $DATE ====="
  aws dynamodb get-item \
    --table-name etnews-delivery-failures \
    --key "{\"date\": {\"S\": \"$DATE\"}}" \
    --region ap-northeast-2 \
    --query 'Item.[failure_count.N, last_error.S]' \
    --output text
done
```

---

## 주의사항

### 1. TEST 모드 사용 권장
- 수동 트리거 시 항상 TEST 모드 먼저 실행
- OPR 모드는 확실할 때만 사용

### 2. 중복 방지 확인
- OPR 모드 실행 전 DynamoDB에서 `last_delivery_date` 확인
- 필요 시 `set-all-delivered-today` 명령으로 사전 설정

### 3. 실패 추적 리셋
- 실패 카운트는 성공 시 자동 리셋
- 수동 리셋 필요 시:
  ```bash
  aws dynamodb delete-item \
    --table-name etnews-delivery-failures \
    --key '{"date": {"S": "2026-01-27"}}' \
    --region ap-northeast-2
  ```

### 4. Lambda 타임아웃
- 현재: 900초 (15분)
- 실패 추적 로직 추가로 실행 시간 약간 증가 (무시할 수준)

---

## 문제 해결

### 문제 1: "실행 역할에 권한이 없습니다" 오류

**원인**: Lambda IAM 역할에 DynamoDB 권한 없음

**해결**:
```bash
# 3단계의 Lambda IAM 권한 추가 재실행
```

### 문제 2: TEST 모드에서도 실수신인에게 발송

**원인**: 코드 배포 실패 또는 event 파라미터 잘못 지정

**확인**:
```bash
# Lambda 함수 버전 확인
aws lambda get-function \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --query 'Configuration.[FunctionArn,LastModified,CodeSha256]'

# 로그에서 모드 확인
aws logs tail /aws/lambda/etnews-pdf-sender --region ap-northeast-2 | grep "모드"
```

### 문제 3: 실패 추적이 동작하지 않음

**원인**: DynamoDB 테이블 미생성 또는 권한 없음

**확인**:
```bash
# 테이블 존재 확인
aws dynamodb describe-table \
  --table-name etnews-delivery-failures \
  --region ap-northeast-2

# 로그에서 오류 확인
aws logs tail /aws/lambda/etnews-pdf-sender --region ap-northeast-2 | grep "failure"
```

---

**배포 완료 체크리스트**:
- [ ] GitHub Actions 배포 성공
- [ ] DynamoDB 테이블 생성 완료
- [ ] Lambda IAM 권한 추가 완료
- [ ] EventBridge Input 설정 완료
- [ ] TEST 모드 검증 완료
- [ ] OPR 모드 안전 검증 완료
- [ ] 실패 추적 기능 검증 완료 (선택)
- [ ] CloudWatch 모니터링 확인

---

**배포 완료**: 2026-01-27
**다음 점검**: 2026-02-27 (월 1회)
