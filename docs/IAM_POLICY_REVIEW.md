# IAM 정책 최소권한 검증 및 개선 사항

## 현재 상태

Lambda 함수 `etnews-pdf-sender`의 실행 역할: `etnews-lambda-role`

### 관리형 정책
- ✅ `AWSLambdaBasicExecutionRole` - CloudWatch Logs 쓰기 권한 (필수)

### 인라인 정책 (6개)

#### 1. DynamoDBRecipientAccess
**목적**: 수신인 테이블 관리

```json
{
  "Action": [
    "dynamodb:Scan",
    "dynamodb:Query",
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:UpdateItem",
    "dynamodb:DeleteItem"
  ],
  "Resource": [
    "arn:aws:dynamodb:*:*:table/etnews-recipients",
    "arn:aws:dynamodb:*:*:table/etnews-recipients/index/*"
  ]
}
```

**검증 결과**: ✅ 적절함
- 실제 사용: `Scan` (활성 수신인 조회), `GetItem`, `UpdateItem`
- `DeleteItem`은 수신거부 시 사용 가능하지만, 현재는 status 변경으로 처리

#### 2. etnews-delivery-failures-access
**목적**: 실패 추적 및 실행 로그

```json
{
  "Action": [
    "dynamodb:PutItem",
    "dynamodb:GetItem",
    "dynamodb:UpdateItem",
    "dynamodb:DeleteItem"
  ],
  "Resource": [
    "arn:aws:dynamodb:*:*:table/etnews-delivery-failures",
    "arn:aws:dynamodb:*:*:table/etnews-execution-log"
  ]
}
```

**검증 결과**: ✅ 적절함
- `etnews-delivery-failures`: 실패 횟수 추적 (GetItem, PutItem, UpdateItem)
- `etnews-execution-log`: 멱등성 보장 (PutItem with condition)
- `DeleteItem`은 사용하지 않지만 관리 목적으로 유지 가능

#### 3. ITFindS3Access
**목적**: S3 버킷 접근 (ITFIND PDF 임시 저장용)

```json
{
  "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
  "Resource": "arn:aws:s3:::itnews-sender-pdfs/*"
}
```

**검증 결과**: ⚠️ **불필요 - 제거 권장**
- **이유**: P1 개선 작업에서 S3 사용을 제거하고 Lambda 간 직접 호출로 변경
- **현재 코드**: `lambda_client.invoke()` 사용, S3 미사용
- **권장**: 이 정책 삭제

#### 4. LambdaInvokeITFIND
**목적**: ITFIND Lambda 함수 호출

```json
{
  "Action": "lambda:InvokeFunction",
  "Resource": "arn:aws:lambda:*:*:function:itfind-pdf-downloader"
}
```

**검증 결과**: ✅ 적절함
- 수요일마다 `itfind-pdf-downloader` Lambda 함수를 동기 호출

#### 5. ParameterStoreReadAccess
**목적**: 레거시 Parameter Store 접근

```json
{
  "Action": ["ssm:GetParameter"],
  "Resource": "arn:aws:ssm:*:*:parameter/etnews/credentials"
}
```

**검증 결과**: ⚠️ **중복 - 통합 권장**
- **이유**: `SSMParameterStoreAccess`와 중복
- `SSMParameterStoreAccess`가 `/etnews/*` 전체를 커버하므로 불필요
- **권장**: 이 정책 삭제하고 `SSMParameterStoreAccess`만 유지

#### 6. SSMParameterStoreAccess ✨ (P1에서 추가)
**목적**: Parameter Store 접근 (새로운 통합 정책)

```json
{
  "Action": ["ssm:GetParameter", "ssm:GetParameters"],
  "Resource": ["arn:aws:ssm:*:*:parameter/etnews/*"]
}
```

**검증 결과**: ✅ 적절함
- `/etnews/*` 경로의 모든 Parameter 읽기 가능
- SecureString 복호화를 위한 KMS 권한 포함

---

## 개선 권장 사항

### 🔴 높은 우선순위

#### 1. S3 접근 정책 제거
**정책명**: `ITFindS3Access`

**이유**:
- P1 개선으로 S3 사용 제거됨
- Lambda 간 직접 호출로 변경
- 불필요한 권한은 공격 표면 증가

**작업**:
```bash
aws iam delete-role-policy \
  --role-name etnews-lambda-role \
  --policy-name ITFindS3Access
```

#### 2. 중복 Parameter Store 정책 제거
**정책명**: `ParameterStoreReadAccess`

**이유**:
- `SSMParameterStoreAccess`와 완전 중복
- `/etnews/credentials`는 `/etnews/*`에 포함됨

**작업**:
```bash
aws iam delete-role-policy \
  --role-name etnews-lambda-role \
  --policy-name ParameterStoreReadAccess
```

### 🟡 중간 우선순위

#### 3. DynamoDB DeleteItem 권한 검토
**정책명**: `DynamoDBRecipientAccess`, `etnews-delivery-failures-access`

**현재 상황**:
- `DeleteItem` 권한은 부여되어 있지만 코드에서 사용하지 않음
- 수신거부는 status 변경으로 처리 (soft delete)

**선택지**:
- **A (권장)**: 유지 - 향후 관리 작업 또는 데이터 정리 목적
- **B (엄격)**: 제거 - 최소권한 원칙 엄격 적용

### 🟢 낮은 우선순위

#### 4. Resource ARN 와일드카드 제거
**현재**: `arn:aws:kms:*:*:key/*` (KMS Decrypt)
**개선**: 특정 KMS 키 ARN으로 제한

**작업**:
```bash
# 사용 중인 KMS 키 확인
aws kms describe-key --key-id alias/aws/ssm --region ap-northeast-2

# 정책 업데이트 (특정 키 ARN 사용)
```

---

## 최종 권장 IAM 구조

### 필수 정책 (5개)

1. **AWSLambdaBasicExecutionRole** (관리형)
   - CloudWatch Logs 쓰기

2. **DynamoDBRecipientAccess** (인라인)
   - `etnews-recipients` 테이블 R/W

3. **etnews-delivery-failures-access** (인라인)
   - `etnews-delivery-failures` 테이블 R/W
   - `etnews-execution-log` 테이블 R/W

4. **LambdaInvokeITFIND** (인라인)
   - `itfind-pdf-downloader` 함수 호출

5. **SSMParameterStoreAccess** (인라인)
   - `/etnews/*` Parameter 읽기
   - KMS 복호화

### 제거할 정책 (2개)

1. ❌ **ITFindS3Access** - S3 사용 안 함
2. ❌ **ParameterStoreReadAccess** - 중복

---

## 실행 계획

```bash
# 1. S3 정책 제거
aws iam delete-role-policy \
  --role-name etnews-lambda-role \
  --policy-name ITFindS3Access

# 2. 중복 Parameter Store 정책 제거
aws iam delete-role-policy \
  --role-name etnews-lambda-role \
  --policy-name ParameterStoreReadAccess

# 3. 변경 후 테스트
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --payload '{"mode":"test"}' \
  /tmp/test-response.json

# 4. CloudWatch Logs에서 권한 오류 확인
aws logs tail /aws/lambda/etnews-pdf-sender --since 5m
```

---

## 보안 체크리스트

- ✅ 최소권한 원칙 적용
- ✅ 특정 리소스 ARN 사용 (와일드카드 최소화)
- ✅ 사용하지 않는 권한 제거
- ✅ 중복 정책 제거
- ⚠️ KMS 키 ARN 구체화 (낮은 우선순위)
- ✅ 정책 변경 후 테스트 필수

---

## 참고: 현재 사용 중인 AWS 리소스

| 서비스 | 리소스 | 용도 |
|--------|--------|------|
| Lambda | `etnews-pdf-sender` | 메인 함수 |
| Lambda | `itfind-pdf-downloader` | ITFIND PDF 다운로드 |
| DynamoDB | `etnews-recipients` | 수신인 목록 |
| DynamoDB | `etnews-delivery-failures` | 실패 추적 |
| DynamoDB | `etnews-execution-log` | 멱등성 보장 |
| SSM | `/etnews/*` | 설정 관리 |
| ~~S3~~ | ~~`itnews-sender-pdfs`~~ | ❌ 사용 안 함 |
