# Lambda 테스트 이벤트 모음

## 1. 일반 TEST 모드 (멱등성 체크 O)
```json
{
  "mode": "test"
}
```
- 오늘 첫 실행만 성공
- 이미 실행했다면 중복 방지로 스킵

## 2. 재실행 가능 TEST 모드 (멱등성 체크 X)
```json
{
  "mode": "test",
  "skip_idempotency": true
}
```
- 여러 번 실행 가능
- DynamoDB 실행 이력 기록 안 함
- **테스트 목적으로만 사용**

## 3. OPR 모드 (운영)
```json
{
  "mode": "opr"
}
```
- 실제 수신인 전체에게 발송
- 멱등성 체크 O
- 발송 이력 DynamoDB 기록

## 4. OPR 모드 재실행 (주의!)
```json
{
  "mode": "opr",
  "skip_idempotency": true
}
```
- ⚠️ **위험**: 실제 수신인에게 중복 발송됨
- 긴급 상황에만 사용
- DynamoDB 실행 이력 기록 안 함

---

## 사용 예시

### 일반 테스트 (멱등성 O)
- 목적: 정상 동작 확인
- 이벤트: `{"mode": "test"}`
- 첫 실행 후 DynamoDB에 `2026-01-28#test` 기록됨
- 재실행 시 중복 방지로 스킵

### 반복 테스트 (멱등성 X)
- 목적: ITFIND 다운로드 로직 여러 번 테스트
- 이벤트: `{"mode": "test", "skip_idempotency": true}`
- DynamoDB 기록 안 함
- 여러 번 실행 가능 (turtlesoup0@gmail.com에게만 발송)

### 중복 발송 테스트
1. 첫 실행: `{"mode": "test"}` → 성공
2. 두 번째 실행: `{"mode": "test"}` → 중복 방지로 스킵 ✅
3. 강제 재실행: `{"mode": "test", "skip_idempotency": true}` → 성공 (테스트용)

---

**작성일**: 2026-01-28
