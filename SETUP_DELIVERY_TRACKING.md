# 중복 발송 방지 설정 가이드

중복 발송 방지 기능을 사용하려면 DynamoDB 테이블을 생성해야 합니다.

## 1. DynamoDB 테이블 생성 (AWS 콘솔)

### 방법 A: AWS 콘솔 사용

1. **AWS Console 접속**
   - https://console.aws.amazon.com/dynamodb
   - 리전: **ap-northeast-2 (서울)** 선택

2. **테이블 생성**
   - "테이블 만들기" 클릭
   - **테이블 이름**: `etnews-delivery-history`
   - **파티션 키**: `delivery_date` (문자열/String)
   - **테이블 설정**: 기본 설정 사용
   - **읽기/쓰기 용량 모드**: **온디맨드** 선택
   - "테이블 만들기" 클릭

3. **테이블 생성 완료 대기**
   - 상태가 "생성 중"에서 "활성"으로 변경될 때까지 대기 (약 30초)

### 방법 B: AWS CLI 사용 (관리자 권한 필요)

관리자 권한이 있는 AWS 계정으로 다음 명령 실행:

```bash
aws dynamodb create-table \
  --table-name etnews-delivery-history \
  --attribute-definitions AttributeName=delivery_date,AttributeType=S \
  --key-schema AttributeName=delivery_date,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=etnews-sender Key=Purpose,Value=delivery-tracking \
  --region ap-northeast-2
```

## 2. Lambda 실행 역할 권한 추가

Lambda 함수가 DynamoDB 테이블에 읽기/쓰기를 할 수 있도록 권한을 추가해야 합니다.

### 단계:

1. **IAM 콘솔 접속**
   - https://console.aws.amazon.com/iam
   - 좌측 메뉴에서 "역할" 클릭

2. **Lambda 역할 찾기**
   - 역할 이름: `etnews-lambda-role` 검색

3. **인라인 정책 추가**
   - "권한" 탭 → "권한 추가" → "인라인 정책 생성" 클릭
   - **JSON** 탭 선택 후 아래 내용 붙여넣기:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:Query"
            ],
            "Resource": "arn:aws:dynamodb:ap-northeast-2:269809345127:table/etnews-delivery-history"
        }
    ]
}
```

4. **정책 이름 입력**
   - 정책 이름: `DeliveryHistoryAccess`
   - "정책 생성" 클릭

## 3. 테이블 확인

테이블이 정상적으로 생성되었는지 확인:

```bash
python3 scripts/create_delivery_history_table.py describe
```

또는 AWS CLI:

```bash
aws dynamodb describe-table \
  --table-name etnews-delivery-history \
  --region ap-northeast-2
```

## 4. 동작 확인

Lambda 함수를 실행하여 중복 발송 방지가 작동하는지 확인:

```bash
# 첫 번째 실행 - 정상 발송
aws lambda invoke --function-name etnews-pdf-sender --region ap-northeast-2 response.json
cat response.json

# 두 번째 실행 - 중복 발송 방지
aws lambda invoke --function-name etnews-pdf-sender --region ap-northeast-2 response2.json
cat response2.json
# 예상 결과: "오늘 이미 메일이 발송되었습니다 (중복 발송 방지)"
```

## 5. 발송 이력 조회

DynamoDB 콘솔에서 발송 이력 확인:

```bash
aws dynamodb scan \
  --table-name etnews-delivery-history \
  --region ap-northeast-2
```

## 테이블 구조

| 속성명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `delivery_date` | String (파티션 키) | 발송 날짜 (YYYY-MM-DD) | "2026-01-27" |
| `timestamp` | String | 발송 시각 (ISO 8601) | "2026-01-27T06:05:32+09:00" |
| `recipient_count` | Number | 수신인 수 | 6 |
| `pdf_title` | String | PDF 제목 | "IT뉴스 [2026-01-27]" |
| `status` | String | 발송 상태 | "delivered" |

## 비용

- **스토리지**: 거의 무료 (하루 1건 × 365일 = 연간 약 $0.01 미만)
- **읽기/쓰기**: 하루 2회 요청 (중복 체크 1회 + 기록 1회) = 월 60회 = 무료 (월 100만 건까지 무료)

## 주의사항

- 테이블이 없어도 Lambda는 정상 작동하며, 경고 로그만 출력됩니다
- 중복 발송 방지 기능을 사용하지 않으려면 테이블 생성을 건너뛰어도 됩니다
- 테이블은 KST(한국 시간) 기준으로 날짜를 저장합니다
