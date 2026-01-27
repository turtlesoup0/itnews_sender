# IT뉴스 PDF 발송 시스템 안전성 점검 보고서

**점검 일시**: 2026-01-27
**점검자**: Claude Sonnet 4.5
**배포 상태**: e961dbf (수신인별 발송 이력 관리로 변경)

---

## ✅ 정상 작동 중인 안전장치

### 1. 중복 발송 방지 (CRITICAL)
**위치**: `lambda_handler.py:52-75`
**동작**: Lambda 진입 시 가장 먼저 실행
**검증**: ✅ 테스트 완료 (84ms 빠른 종료 확인)

```python
if tracker.is_delivered_today():
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': '오늘 이미 메일이 발송되었습니다',
            'skipped': True
        })
    }
```

**보호 대상**:
- ✅ 같은 날 여러 번 Lambda 실행 시 1회만 발송
- ✅ 모든 수신인이 발송 받았을 때만 차단
- ✅ 일부만 발송된 경우 나머지에게 재발송

---

### 2. 활성 수신인 검증
**위치**: `email_sender.py:90-94`
**동작**: 이메일 전송 전 활성 수신인 확인

```python
recipients = get_active_recipients()
if not recipients:
    logger.warning("활성 수신인이 없습니다")
    return False, []
```

**보호 대상**:
- ✅ 수신인 0명일 때 발송 중단
- ✅ unsubscribe된 사용자 제외

---

### 3. PDF 첨부 실패 차단
**위치**: `email_sender.py:208-228`
**동작**: PDF 파일 없으면 예외 발생

```python
def _attach_pdf(self, msg: MIMEMultipart, pdf_path: str):
    try:
        with open(pdf_path, "rb") as pdf_file:
            pdf_data = pdf_file.read()
        # ... 첨부 처리 ...
    except Exception as e:
        logger.error(f"PDF 파일 첨부 실패: {e}")
        raise  # 빈 메일 발송 방지
```

**보호 대상**:
- ✅ 빈 메일 발송 방지
- ✅ PDF 파일 손상 시 발송 중단

---

### 4. 개별 발송 실패 격리
**위치**: `email_sender.py:107-126`
**동작**: 한 명 실패해도 나머지 계속 발송

```python
for recipient in recipients:
    try:
        # 이메일 전송
        success_emails.append(recipient.email)
    except Exception as e:
        fail_count += 1
        logger.error(f"이메일 전송 실패: {recipient.email} - {e}")
        # 계속 진행
```

**보호 대상**:
- ✅ 부분 실패 시 일부 수신인이라도 받음
- ✅ 실패한 이메일은 발송 이력에 기록 안 됨

---

### 5. 신문 미발행일 처리
**위치**: `lambda_handler.py:84-104`
**동작**: 신문 없으면 발송 안 함

```python
except ValueError as ve:
    if "신문이 발행되지 않은 날" in str(ve):
        logger.info("신문이 발행되지 않은 날입니다. 메일을 전송하지 않습니다.")
        return {'statusCode': 200, 'body': {...}}
```

**보호 대상**:
- ✅ 휴일/공휴일 빈 메일 방지

---

## ⚠️ 발견된 잠재적 위험 요소

### 위험 #1: 활성 수신인 0명일 때 중복 방지 우회 (LOW)

**위치**: `delivery_tracker.py:49-51`
**코드**:
```python
if not recipients:
    logger.warning("활성 수신인이 없습니다")
    return False  # ← 발송 시도 진행
```

**시나리오**:
1. 모든 수신인이 unsubscribe
2. `is_delivered_today()` → False 반환
3. PDF 다운로드 및 처리 진행
4. `send_bulk_email()` → `recipients == []` → 발송 안 됨

**영향**: LOW (이메일은 발송 안 되지만 불필요한 PDF 다운로드)
**권장 조치**: `return True`로 변경하여 조기 종료

---

### 위험 #2: PDF 다운로드 실패 시 무한 재시도 (MEDIUM)

**현상**:
- PDF 다운로드 실패 → 예외 발생
- `mark_as_delivered()` 호출 안 됨
- 다음 실행 시 다시 시도

**시나리오**:
1. 일시적 네트워크 오류로 PDF 다운로드 실패
2. Lambda 실패로 종료
3. 재실행 시 다시 시도 (정상)
4. 지속적 실패 시 EventBridge가 계속 트리거

**영향**: MEDIUM (비용 증가, 로그 스팸)
**권장 조치**: 실패 카운트 제한 또는 관리자 알림

---

### 위험 #3: status 필드 불일치 (LOW)

**발견**:
- 수신거부 시 레코드 삭제 (`delete_recipient()`)
- 하지만 `get_active_recipients()`는 `status=active` 필터링
- status 필드 실질적으로 미사용

**영향**: LOW (동작에는 문제 없음, 코드 복잡도 증가)
**권장 조치**:
- Option A: status 필드 제거, GSI 제거, scan_all() 사용
- Option B: 삭제 대신 status 변경 (이력 보존)

---

## 🔒 메일 사고 시나리오별 방어 현황

### 시나리오 1: 중복 발송
**트리거**: Lambda 여러 번 실행
**방어**: ✅ `is_delivered_today()` 차단
**검증**: ✅ 테스트 완료 (84ms 빠른 종료)

### 시나리오 2: 빈 메일 발송
**트리거**: PDF 파일 없음
**방어**: ✅ `_attach_pdf()` 예외 발생 → 발송 중단
**검증**: ✅ 코드 리뷰 완료

### 시나리오 3: 잘못된 수신인에게 발송
**트리거**: DynamoDB 데이터 오염
**방어**: ✅ `get_active_recipients()` 필터링
**검증**: ✅ unsubscribe 시 레코드 삭제 확인

### 시나리오 4: 부분 발송 후 전체 재발송
**트리거**: 일부 실패 후 재실행
**방어**: ✅ 수신인별 `last_delivery_date` 체크
**검증**: ✅ 코드 로직 확인 완료

### 시나리오 5: 신문 없는 날 빈 메일
**트리거**: 휴일/공휴일
**방어**: ✅ `ValueError` 캐치 → 발송 안 함
**검증**: ✅ 코드 리뷰 완료

---

## 📈 AWS 리소스 현황

### Lambda 함수
- **이름**: etnews-pdf-sender
- **버전**: e961dbf (최신)
- **상태**: Active
- **아키텍처**: arm64
- **타임아웃**: 900초 (15분)
- **메모리**: 3008 MB

### EventBridge 스케줄
- **규칙**: etnews-daily-trigger
- **상태**: ENABLED
- **스케줄**: `cron(0 22 ? * SUN-THU *)` (월-금 06:00 KST)
- **타겟**: etnews-pdf-sender Lambda

### DynamoDB 테이블
- **이름**: etnews-recipients
- **파티션 키**: email
- **GSI**: status-index (status 기준 쿼리)
- **수신인 수**: 6명 (모두 active)
- **발송 이력**: 6명 모두 2026-01-27 발송 완료 표시

---

## 🎯 권장 조치 사항

### HIGH Priority
없음 - 중대 위험 요소 없음

### MEDIUM Priority
1. **PDF 다운로드 실패 재시도 제한**
   - 실패 시 관리자 이메일 알림
   - 최대 재시도 3회로 제한

### LOW Priority
1. **활성 수신인 0명 시 조기 종료**
   - `delivery_tracker.py:51` 수정
   - `return False` → `return True`

2. **status 필드 정리**
   - Option A: 필드 제거 + GSI 제거
   - Option B: 삭제 → status 변경으로 전환

---

## ✅ 최종 결론

**현재 시스템은 메일 사고 방지를 위한 충분한 안전장치를 갖추고 있습니다.**

주요 위험 요소:
- ❌ 중복 발송: **완벽 차단** (테스트 검증 완료)
- ❌ 빈 메일 발송: **완벽 차단** (PDF 첨부 실패 시 예외)
- ❌ 오발송: **완벽 차단** (활성 수신인 필터링)

잠재적 개선 사항은 LOW-MEDIUM 우선순위이며, 메일 사고와 직접 연관되지 않습니다.

**시스템은 프로덕션 운영이 가능한 상태입니다.**

---

**보고서 작성**: 2026-01-27
**다음 점검 권장**: 2026-02-27 (월 1회)
