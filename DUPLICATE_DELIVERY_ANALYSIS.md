# 다중 발송 원인 분석 및 해결 방안

**발생 일시**: 2026-01-27 18:47~18:49 (KST)
**증상**: 1번의 테스트 명령으로 3통의 이메일 발송
**영향**: turtlesoup0@gmail.com에 동일 내용 3회 수신

---

## 원인 분석

### 1. 직접 원인: AWS CLI Read Timeout

#### 실행 흐름
```
18:47:10 - Lambda 실행 시작 (RequestId: b8f3ee99)
  ↓ Lambda 처리 중 (88초)
18:47:38 - AWS CLI timeout 발생 → 자동 재시도 (RequestId: 0407cbb2)
  ↓ 첫 번째 Lambda 계속 실행 중
18:48:10 - AWS CLI 2차 재시도 (RequestId: 355b138d)
  ↓
18:48:19 - 첫 번째 Lambda 완료 (Duration: 88초)
18:49:05 - 두 번째 Lambda 완료 (Duration: 107초)
18:49:38 - 세 번째 Lambda 완료 (Duration: 87초)
```

#### 근본 원인
- **Lambda 실행 시간**: 평균 90초 (PDF 다운로드 + 처리 + 이메일 발송)
- **AWS CLI 기본 Read Timeout**: 60초 (추정)
- **결과**: Lambda는 정상 실행 중이지만 CLI는 timeout으로 판단 → 자동 재시도

#### 증거
```bash
# /private/tmp/claude/tasks/bcfc4f1.output
Read timeout on endpoint URL: "https://lambda.ap-northeast-2.amazonaws.com/..."
```

### 2. 구조적 원인: 멱등성(Idempotency) 미보장

현재 TEST 모드는 **멱등성이 보장되지 않습니다**:

```python
# lambda_handler.py (현재)
if not is_test_mode:
    # OPR 모드에만 중복 체크
    if tracker.is_delivered_today():
        return {...}
```

**문제점**:
- TEST 모드는 중복 발송 체크를 건너뜀
- 동일한 event를 여러 번 받으면 여러 번 발송됨
- AWS Lambda의 at-least-once 전달 보장과 충돌

### 3. AWS 인프라 특성

AWS Lambda는 다음 상황에서 중복 실행될 수 있습니다:

1. **클라이언트 재시도**
   - AWS CLI/SDK 자동 재시도 (timeout, 5xx 에러)
   - 지수 백오프 재시도 정책

2. **Lambda 서비스 재시도**
   - 비동기 호출 시 실패하면 자동 재시도 (최대 2회)
   - EventBridge 재시도 정책

3. **네트워크 문제**
   - 응답 패킷 손실 시 클라이언트는 실패로 간주 → 재시도
   - 하지만 Lambda는 실행 완료

---

## 해결 방안

### Solution 1: AWS CLI Timeout 증가 (즉시 적용)

**구현**:
```bash
# scripts/test_lambda.sh (신규)
#!/bin/bash
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --cli-read-timeout 300 \
  --cli-connect-timeout 60 \
  --payload '{}' \
  /tmp/response.json

echo "Lambda 호출 완료. 결과:"
cat /tmp/response.json | jq .
```

**장점**: 즉시 적용 가능
**단점**: 근본 해결 아님 (네트워크 문제, EventBridge 재시도 등은 여전히 발생 가능)

---

### Solution 2: Lambda 멱등성 보장 (권장)

#### 2-1. Request ID 기반 중복 실행 방지

**DynamoDB 테이블**: `etnews-execution-log`
- 파티션 키: `request_id` (String)
- 속성: `execution_time`, `status`, `ttl`

**구현**:
```python
# src/idempotency_handler.py (신규)
class IdempotencyHandler:
    def __init__(self, table_name="etnews-execution-log"):
        self.table_name = table_name
        self.db_client = DynamoDBClient(table_name, "ap-northeast-2")

    def is_already_executed(self, request_id: str) -> bool:
        """이미 실행된 요청인지 확인"""
        table = self.db_client._get_table()
        response = table.get_item(Key={"request_id": request_id})
        return "Item" in response

    def mark_as_executed(self, request_id: str, ttl_hours: int = 24):
        """실행 완료 기록 (24시간 후 자동 삭제)"""
        table = self.db_client._get_table()
        now = datetime.now(timezone.utc)
        ttl = int((now + timedelta(hours=ttl_hours)).timestamp())

        table.put_item(Item={
            "request_id": request_id,
            "execution_time": now.isoformat(),
            "status": "completed",
            "ttl": ttl
        })
```

**lambda_handler.py 수정**:
```python
def handler(event, context):
    # 멱등성 체크 (TEST/OPR 모두 적용)
    request_id = context.request_id
    idempotency = IdempotencyHandler()

    if idempotency.is_already_executed(request_id):
        logger.info(f"이미 처리된 요청: {request_id}")
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': '이미 처리된 요청입니다',
                'request_id': request_id,
                'skipped': True
            })
        }

    # ... 기존 로직 ...

    # 실행 완료 후 기록
    idempotency.mark_as_executed(request_id)
```

**장점**:
- 동일한 RequestId로 여러 번 실행되어도 1번만 처리
- AWS Lambda의 at-least-once 보장과 조화
- TEST/OPR 모드 모두 보호

**단점**:
- DynamoDB 읽기/쓰기 비용 증가 (하루 1~2회 실행이므로 무시 가능)

---

#### 2-2. 날짜 기반 중복 실행 방지 (간단한 방법)

**기존 테이블 활용**: `etnews-execution-log`
- 파티션 키: `date` (String, YYYY-MM-DD)
- 속성: `execution_count`, `last_request_id`, `updated_at`

**구현**:
```python
# src/execution_tracker.py (신규)
class ExecutionTracker:
    def __init__(self, table_name="etnews-execution-log"):
        self.table_name = table_name
        self.db_client = DynamoDBClient(table_name, "ap-northeast-2")

    def should_skip_execution(self, mode: str) -> bool:
        """
        오늘 이미 실행되었는지 확인

        Args:
            mode: "test" 또는 "opr"

        Returns:
            건너뛰어야 하면 True
        """
        today = self._get_today_date()
        key = f"{today}#{mode}"  # 날짜 + 모드로 키 생성

        table = self.db_client._get_table()
        response = table.get_item(Key={"execution_key": key})

        if "Item" in response:
            logger.info(f"오늘 이미 실행됨: {key}")
            return True

        return False

    def mark_execution(self, mode: str, request_id: str):
        """오늘 실행 기록"""
        today = self._get_today_date()
        key = f"{today}#{mode}"
        now = datetime.now(timezone.utc).isoformat()

        table = self.db_client._get_table()
        table.put_item(Item={
            "execution_key": key,
            "date": today,
            "mode": mode,
            "request_id": request_id,
            "execution_time": now
        })
        logger.info(f"실행 기록: {key} (RequestId: {request_id})")
```

**lambda_handler.py 수정**:
```python
def handler(event, context):
    mode = event.get("mode", "test")
    is_test_mode = (mode != "opr")

    # 날짜 기반 중복 실행 방지
    exec_tracker = ExecutionTracker()
    if exec_tracker.should_skip_execution(mode):
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'오늘 이미 {mode} 모드로 실행되었습니다',
                'skipped': True
            })
        }

    # ... 기존 로직 ...

    # 실행 완료 후 기록
    exec_tracker.mark_execution(mode, context.request_id)
```

**장점**:
- 간단한 구현
- TEST 모드도 하루 1회만 실행
- OPR 모드의 기존 중복 방지 로직과 보완

**단점**:
- 의도적으로 여러 번 테스트하고 싶을 때 DynamoDB 수동 삭제 필요

---

### Solution 3: 비동기 호출 사용

**구현**:
```bash
# 응답을 기다리지 않음 (Fire and Forget)
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --invocation-type Event \
  --payload '{}' \
  /dev/null

# 결과는 CloudWatch Logs에서 확인
aws logs tail /aws/lambda/etnews-pdf-sender --follow
```

**장점**:
- Timeout 없음
- 즉시 반환

**단점**:
- 실행 성공/실패를 즉시 알 수 없음
- 에러 발생 시 Lambda가 자동으로 재시도 (최대 2회)

---

### Solution 4: Lambda Reserved Concurrency 설정

**목적**: 동시 실행 수를 1로 제한

```bash
aws lambda put-function-concurrency \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --reserved-concurrent-executions 1
```

**효과**:
- 동시에 여러 요청이 와도 1개씩만 처리
- 나머지는 Queue에 대기 (최대 6시간)

**장점**: 완벽한 순차 실행 보장
**단점**: OPR 모드 정상 실행 중에 EventBridge 트리거가 오면 대기 → Timeout 가능

---

## 권장 해결 방안 조합

### Phase 1: 즉시 적용 (금일)
1. **AWS CLI Timeout 증가** (Solution 1)
   - `scripts/test_lambda.sh` 스크립트 생성
   - 모든 수동 테스트는 이 스크립트 사용

2. **날짜 기반 중복 실행 방지** (Solution 2-2)
   - `src/execution_tracker.py` 구현
   - TEST/OPR 모두 하루 1회만 실행 보장

### Phase 2: 장기 개선 (선택)
3. **Request ID 기반 멱등성** (Solution 2-1)
   - AWS Lambda의 재시도에도 안전
   - 완벽한 멱등성 보장

4. **Reserved Concurrency 설정** (Solution 4)
   - 극단적 안전 장치

---

## 테스트 시나리오

### 시나리오 1: CLI Timeout 재현 (해결 전)
```bash
# Timeout 짧게 설정
aws lambda invoke \
  --cli-read-timeout 10 \
  --function-name etnews-pdf-sender \
  --payload '{}' /tmp/response.json

# 예상: Timeout 에러 + 자동 재시도 → 다중 실행
```

### 시나리오 2: CLI Timeout 방지 (해결 후)
```bash
bash scripts/test_lambda.sh

# 예상: 정상 완료, 1회만 실행
```

### 시나리오 3: 의도적 중복 호출 (멱등성 테스트)
```bash
# 동일한 날짜에 3번 연속 호출
for i in {1..3}; do
  bash scripts/test_lambda.sh
  sleep 5
done

# 예상:
# - 1회차: 정상 실행
# - 2회차: "오늘 이미 실행됨" 스킵
# - 3회차: "오늘 이미 실행됨" 스킵
```

---

## 배포 계획

1. **DynamoDB 테이블 생성**:
```bash
aws dynamodb create-table \
  --table-name etnews-execution-log \
  --attribute-definitions AttributeName=execution_key,AttributeType=S \
  --key-schema AttributeName=execution_key,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

2. **Lambda IAM 권한 추가**:
```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:PutItem",
    "dynamodb:GetItem"
  ],
  "Resource": "arn:aws:dynamodb:ap-northeast-2:*:table/etnews-execution-log"
}
```

3. **코드 변경**:
   - `src/execution_tracker.py` 추가
   - `lambda_handler.py` 수정
   - `scripts/test_lambda.sh` 추가

4. **테스트**:
   - 시나리오 2, 3 실행

---

**작성일**: 2026-01-27
**다음 조치**: Phase 1 구현 (금일 완료 목표)
