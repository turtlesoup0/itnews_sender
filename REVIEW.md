# 전자신문 PDF 자동화 시스템 전체 검토

## Problem 1-Pager

### 배경 (Background)
- 기존에 구현된 전자신문 PDF 다운로드/전송 시스템이 AWS Lambda로 마이그레이션됨
- 다중 수신인 관리 기능과 수신거부 기능이 추가됨
- 민감정보를 Parameter Store로 이전하여 보안 강화
- 프로덕션 배포를 앞두고 전체 코드/아키텍처 검증 필요

### 문제 (Problem)
1. 현재 코드베이스에 크리티컬한 보안 이슈가 있는가?
2. 아키텍처 설계에 근본적인 문제가 있는가?
3. 과도하게 복잡한 구현이나 불필요한 추상화가 있는가?
4. 함수가 너무 길거나 책임이 과다한 모듈이 있는가?
5. 누락된 에러 핸들링, 로깅, 테스트가 있는가?
6. Lambda 제약사항(타임아웃, 메모리, 콜드 스타트)을 제대로 고려했는가?
7. DynamoDB 설계가 적절한가? (인덱스, 파티션 키 선택)
8. 비용 최적화 관점에서 개선할 점이 있는가?

### 목표 (Goal)
- **안정성**: 프로덕션 환경에서 안정적으로 동작
- **보안**: 민감정보 노출 제로, OWASP Top 10 취약점 없음
- **유지보수성**: 코드가 명확하고 수정이 용이
- **비용 효율성**: AWS 프리티어 내에서 운영 가능
- **모니터링**: 장애 발생 시 빠른 감지 및 대응 가능

### 비목표 (Non-goals)
- 대규모 트래픽 처리 (수신인은 100명 이하)
- 실시간 처리 (하루 1회 배치 처리)
- 고가용성 설계 (단일 리전, 단일 Lambda 충분)
- 복잡한 재시도 로직 (간단한 에러 로깅으로 충분)
- 웹 관리 대시보드 (CLI 도구로 충분)

### 제약 (Constraints)
- **비용**: AWS 프리티어 내 운영 (월 $5 이하)
- **Lambda 타임아웃**: 최대 15분
- **Lambda 메모리**: 최소 256MB ~ 최대 10GB
- **DynamoDB**: 프리티어 25GB, 200M 요청/월
- **Parameter Store**: Standard tier (무료, 10,000 파라미터)
- **보안**: 민감정보는 반드시 암호화 저장
- **언어**: Python 3.11 (Lambda 지원 최신 버전)

---

## 전체 아키텍처 검토

### 현재 아키텍처
```
EventBridge Scheduler (매일 06:00 KST)
    ↓
Main Lambda (etnews-pdf-sender)
    → Scraper: 전자신문 로그인 + PDF 다운로드
    → PDF Processor: 광고 페이지 제거
    → Recipient Manager: DynamoDB에서 활성 수신인 조회
    → Email Sender: 개별 이메일 전송 (수신거부 링크 포함)
    → iCloud Uploader (선택)

사용자 수신거부 클릭
    ↓
Lambda Function URL (etnews-unsubscribe-handler)
    → Token 검증 (HMAC)
    → DynamoDB에서 수신인 삭제
    → HTML 확인 페이지 반환
```

### ✅ 장점
1. **서버리스**: 운영 부담 없음
2. **비용 효율적**: 프리티어 활용
3. **명확한 책임 분리**: Main / Unsubscribe 분리
4. **확장 가능**: 수신인 100명까지 무리 없음

### ⚠️ 개선 필요 사항

#### 1. **보안 이슈**

##### 🔴 Critical: HMAC 토큰 생성 로직 취약
**파일**: `src/email_sender.py` (lines 141-178)
**문제**: 현재 토큰 생성 시 `email:month` 조합만 서명하고, 실제 토큰에는 `email:signature` 형태로 저장
**취약점**: 공격자가 다른 사용자의 이메일을 알고 있다면 토큰 재사용 가능

**현재 코드**:
```python
# email_sender.py
message = f"{email}:{datetime.now().strftime('%Y-%m')}"
signature = hmac.new(secret, message.encode(), hashlib.sha256).digest()
token = base64.urlsafe_b64encode(signature).decode()
return base64.urlsafe_b64encode(f"{email}:{token}".encode()).decode()
```

**검증 코드 (unsubscribe_handler.py)**:
```python
# email:signature 형식으로 디코딩
decoded = base64.urlsafe_b64decode(token).decode()
email, signature = decoded.split(":")
# email:month로 재생성하여 검증
```

**수정 필요**: 토큰 생성과 검증 로직이 일치하지 않음

##### 🔴 Critical: Parameter Store에 평문 이메일 주소 저장
**파일**: `src/config.py`
**문제**: `RECIPIENT_EMAIL` 환경변수가 사용되지 않고 있지만 여전히 코드에 존재
**수정**: 불필요한 코드 제거

##### 🟡 Medium: Lambda Function URL에 Rate Limiting 없음
**문제**: 무제한 호출 가능 (DDoS 취약)
**해결**: AWS WAF 또는 CloudFront 추가 (비용 고려 시 일단 보류)

#### 2. **코드 품질 이슈**

##### 🟡 `email_sender.py` 파일이 너무 길고 책임이 과다
**현재**: 278줄, 여러 책임 혼재
- SMTP 연결 관리
- 이메일 메시지 생성
- 다중 전송 로직
- HMAC 토큰 생성
- HTML 템플릿 생성

**제안**: 다음과 같이 분리
- `email_sender.py`: SMTP 전송만 담당
- `email_template.py`: HTML 템플릿 생성
- `unsubscribe_token.py`: 토큰 생성/검증 로직 (email_sender와 unsubscribe_handler에서 공유)

##### 🟡 `scraper.py`가 동기/비동기 혼재
**현재**: `download_pdf_sync()`와 `download_pdf()` 두 함수 존재
**문제**: Lambda는 비동기 이벤트 루프가 없으므로 동기 함수만 필요
**제안**: 비동기 함수 제거, 동기 함수만 유지

##### 🟢 `recipient_manager.py` 잘 설계됨
**장점**: 책임이 명확하고 테스트 가능한 구조

#### 3. **에러 핸들링 이슈**

##### 🟡 `lambda_handler.py`에서 부분 실패 처리 부족
**현재**: PDF 다운로드 실패 시 전체 실패
**문제**: iCloud 업로드 실패는 무시하지만, 이메일 전송 부분 실패는 처리 안 됨
**제안**: 이메일 전송 실패 시에도 성공한 수신인 수 로깅

##### 🟡 `email_sender.py`에서 개별 전송 실패 로깅 부족
**현재**: 성공/실패 카운트만 로깅
**제안**: 실패한 이메일 주소 명시적 로깅

##### 🟢 `unsubscribe_handler.py` 에러 핸들링 우수
**장점**: 각 단계별 명확한 에러 메시지와 HTTP 상태 코드

#### 4. **성능 이슈**

##### 🟢 개별 이메일 전송 방식 적절
**현재**: 100명 이하이므로 순차 전송으로 충분
**개선 가능**: 50명 이상 시 병렬 전송 고려 (현재는 불필요)

##### 🟡 PDF 파일 크기 제한 없음
**문제**: 대용량 PDF 시 Lambda 메모리 부족 가능
**제안**: PDF 파일 크기 체크 추가 (예: 50MB 제한)

##### 🟢 DynamoDB 설계 적절
**장점**:
- 파티션 키로 `email` 사용 (균등 분산)
- GSI로 `status` 인덱스 (효율적 쿼리)

#### 5. **테스트 및 모니터링**

##### 🔴 단위 테스트 전무
**문제**: `tests/` 디렉토리가 비어있음
**제안**: 최소한 핵심 로직 테스트 추가
- `test_unsubscribe_token.py`: 토큰 생성/검증
- `test_recipient_manager.py`: DynamoDB 작업 (Moto 사용)

##### 🟡 CloudWatch Logs 구조화 로깅 부족
**현재**: 일반 로그 메시지
**제안**: JSON 구조화 로깅 (검색/필터링 용이)

##### 🟡 알림 메커니즘 없음
**문제**: Lambda 실패 시 수동 확인 필요
**제안**: CloudWatch Alarm + SNS 이메일 알림

#### 6. **문서화**

##### 🟢 문서화 우수
**장점**:
- `REFACTORING_PLAN.md`: 상세한 설계 문서
- `SECURITY_SETUP.md`: 보안 설정 가이드
- `DEPLOYMENT.md`: 배포 가이드

##### 🟡 API 문서 부족
**제안**: 함수 docstring에 타입 힌트와 예제 추가

---

## 우선순위별 수정 계획

### 🔴 Critical (즉시 수정)
1. ✅ HMAC 토큰 생성/검증 로직 통일
2. ✅ 불필요한 환경변수 제거
3. ✅ PDF 크기 제한 추가

### 🟡 High (이번 리팩토링에서 수정)
4. ✅ `email_sender.py` 책임 분리
5. ✅ 비동기 함수 제거 (scraper.py)
6. ✅ 에러 로깅 개선
7. ✅ 구조화 로깅 추가

### 🟢 Medium (다음 단계)
8. ⏸️ 단위 테스트 추가 (시간이 허락하면)
9. ⏸️ CloudWatch Alarm 설정 (배포 후)

---

## 검토 결론

### 크리티컬 이슈
- **HMAC 토큰 로직 불일치**: 보안 취약점, 즉시 수정 필요

### 아키텍처 평가
- **전반적으로 건전함**: 서버리스 설계 적절
- **비용 효율적**: 프리티어 내 운영 가능
- **확장성**: 현재 요구사항에 적합

### 개선 방향
1. 보안 강화: 토큰 로직 수정
2. 코드 품질: 파일 분리, 책임 명확화
3. 관찰성: 로깅 및 모니터링 개선

### 과도한 구현 여부
- ❌ 과도한 추상화 없음
- ❌ 불필요한 복잡도 없음
- ✅ 요구사항에 적합한 수준

---

## 다음 단계
1. 토큰 생성/검증 로직 별도 모듈로 분리 및 수정
2. `email_sender.py` 책임 분리
3. 불필요한 코드 제거
4. 로깅 개선
5. Git 커밋 및 GitHub Actions 배포
