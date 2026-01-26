# 수동 트리거 가이드

구독 갱신 후 또는 테스트를 위해 Lambda 함수를 수동으로 실행하는 방법을 설명합니다.

## 🎯 언제 사용하나요?

- ✅ **구독 갱신 후**: 즉시 PDF를 다운로드하고 전송하고 싶을 때
- ✅ **테스트**: 시스템이 정상 작동하는지 확인하고 싶을 때
- ✅ **긴급 전송**: 예정된 06:00 실행을 기다리지 않고 즉시 전송하고 싶을 때
- ✅ **신문 미발행일 확인**: 오늘 신문이 발행되었는지 확인하고 싶을 때

## 방법 1: AWS CLI 사용 (가장 간단)

### 사전 요구사항
- AWS CLI 설치 및 인증 완료
- `aws configure`로 자격 증명 설정 완료

### 실행 명령

```bash
# Lambda 함수 호출
aws lambda invoke \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  response.json

# 결과 확인
cat response.json
```

### 실시간 로그 확인

```bash
# 별도 터미널에서 로그 스트림 확인
aws logs tail /aws/lambda/etnews-pdf-sender --follow --region ap-northeast-2
```

### 성공 예시

```json
{
    "statusCode": 200,
    "body": "{\"message\": \"IT뉴스 PDF 전송 성공\", \"pdf_path\": \"/tmp/etnews_20260126.pdf\", \"processed_pdf_path\": \"/tmp/etnews_20260126_processed.pdf\", \"duration_ms\": 45231.2}"
}
```

### 신문 미발행일 예시

```json
{
    "statusCode": 200,
    "body": "{\"message\": \"신문이 발행되지 않은 날입니다\", \"skipped\": true}"
}
```

## 방법 2: AWS Console 사용 (GUI)

### 단계별 가이드

1. **AWS Console 로그인**
   - https://console.aws.amazon.com/

2. **Lambda 서비스로 이동**
   - 상단 검색창에 "Lambda" 입력 → Lambda 클릭

3. **함수 선택**
   - `etnews-pdf-sender` 함수 클릭

4. **테스트 이벤트 생성**
   - **Test** 탭 클릭
   - **Create new event** 선택
   - **Event name**: `manual-trigger`
   - **Event JSON**:
     ```json
     {
       "source": "manual-trigger"
     }
     ```
   - **Save** 클릭

5. **실행**
   - **Test** 버튼 클릭
   - 실행 결과와 로그를 확인

6. **상세 로그 확인**
   - **Monitor** 탭 → **View CloudWatch logs** 클릭
   - 최신 로그 스트림 선택

## 방법 3: 로컬 Python 스크립트 (개발용)

### 사전 요구사항
- 로컬 환경에서 Python 가상환경 활성화
- AWS 자격 증명 설정 완료 (Parameter Store 접근용)

### 실행 방법

```bash
# 프로젝트 디렉토리로 이동
cd /Users/turtlesoup0/Documents/itnews_sender

# 가상환경 활성화
source venv/bin/activate

# 수동 트리거 스크립트 실행
python3 manual_trigger.py
```

### 장점
- ✅ 로컬에서 즉시 실행
- ✅ 디버깅이 쉬움
- ✅ 상세한 로그를 바로 확인

### 주의사항
- ⚠️ Playwright 브라우저가 설치되어 있어야 함
- ⚠️ AWS 자격 증명이 설정되어 있어야 함 (Parameter Store 접근)
- ⚠️ `/tmp` 디렉토리에 임시 PDF 파일이 생성됨

## 방법 4: EventBridge 스케줄 수동 실행

EventBridge 규칙을 통해 실행할 수도 있습니다:

```bash
# EventBridge 규칙 확인
aws events list-rules --region ap-northeast-2

# 수동으로 이벤트 발생 (EventBridge → Lambda)
aws events put-events \
  --entries '[{"Source":"manual.trigger","DetailType":"Manual Trigger","Detail":"{}"}]' \
  --region ap-northeast-2
```

**참고**: 이 방법은 EventBridge 규칙이 정확히 설정되어 있어야 합니다.

## 실행 결과 확인

### CloudWatch Logs에서 확인

```bash
# 최근 로그 확인
aws logs tail /aws/lambda/etnews-pdf-sender --since 5m --region ap-northeast-2

# 실시간 로그 스트리밍
aws logs tail /aws/lambda/etnews-pdf-sender --follow --region ap-northeast-2

# JSON 구조화 로그 필터링
aws logs filter-log-events \
  --log-group-name /aws/lambda/etnews-pdf-sender \
  --filter-pattern '{ $.event = "lambda_success" }' \
  --region ap-northeast-2
```

### 주요 로그 이벤트

| 이벤트 타입 | 의미 |
|-----------|------|
| `lambda_start` | Lambda 실행 시작 |
| `newspaper_not_published` | 신문 미발행일 감지 |
| `email_sent` | 이메일 전송 성공 |
| `email_failed` | 이메일 전송 실패 |
| `lambda_success` | Lambda 정상 완료 |
| `lambda_error` | Lambda 오류 발생 |

## 문제 해결

### Lambda 타임아웃 발생

**증상**: 15분 후 "Task timed out" 오류

**해결**:
```bash
# 타임아웃 시간 확인
aws lambda get-function-configuration \
  --function-name etnews-pdf-sender \
  --region ap-northeast-2 \
  --query Timeout

# 타임아웃 연장 (최대 900초 = 15분)
aws lambda update-function-configuration \
  --function-name etnews-pdf-sender \
  --timeout 900 \
  --region ap-northeast-2
```

### PDF 다운로드 실패

**증상**: "PDF 다운로드 중 오류" 로그

**확인 사항**:
1. 구독이 유효한지 확인
2. 로그인 자격 증명이 올바른지 확인 (Parameter Store)
3. 웹사이트가 정상 작동하는지 확인

### 이메일 전송 실패

**증상**: "이메일 전송 실패" 로그

**확인 사항**:
1. Gmail 앱 비밀번호가 올바른지 확인
2. Gmail 계정의 2단계 인증이 활성화되어 있는지 확인
3. Parameter Store의 `GMAIL_APP_PASSWORD` 값 확인

```bash
# Parameter Store 값 확인
aws ssm get-parameter \
  --name /etnews/credentials \
  --with-decryption \
  --region ap-northeast-2 \
  --query Parameter.Value \
  --output text | jq .
```

## 비용 주의사항

- Lambda 실행 시마다 비용이 발생합니다 (프리티어: 월 100만 건 무료)
- 수동 트리거는 필요할 때만 사용하세요
- 테스트 목적으로 과도하게 실행하지 마세요

## 다음 자동 실행 일정

```bash
# EventBridge 규칙 확인
aws events describe-rule \
  --name etnews-daily-schedule \
  --region ap-northeast-2 \
  --query ScheduleExpression
```

현재 설정: **매일 한국시간 06:00** (UTC 21:00)
