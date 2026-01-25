# 전자신문 PDF 자동 다운로드 및 전송 시스템

전자신문 웹사이트에서 매일 PDF 뉴스지면을 자동으로 다운로드하고, 광고 페이지를 제거한 후 이메일로 전송하는 Azure Functions 기반 자동화 시스템입니다.

## 주요 기능

- **자동 다운로드**: 매일 한국시간 06:00에 전자신문 PDF 자동 다운로드
- **광고 제거**: 웹 페이지 메타 정보와 PDF 텍스트 분석을 통한 전면광고 자동 감지 및 제거
- **이메일 전송**: Gmail SMTP를 통한 처리된 PDF 자동 전송
- **iCloud 업로드**: (선택사항) iCloud Drive에 연/월별 폴더 구조로 자동 업로드
- **구독 만료 알림**: PDF 서비스 구독 종료일 7일 전 자동 경고

## 시스템 요구사항

- Python 3.9+
- Azure Functions Core Tools (로컬 개발 시)
- Playwright (웹 브라우저 자동화)

## 설치 방법

### 1. 의존성 설치

\`\`\`bash
pip install -r requirements.txt

# Playwright 브라우저 설치
playwright install chromium
\`\`\`

### 2. 환경변수 설정

\`.env.example\` 파일을 복사하여 \`.env\` 파일을 생성하고 필요한 정보를 입력합니다.

**Gmail 앱 비밀번호 발급 방법:**
1. Google 계정 설정 → 보안 → 2단계 인증 활성화
2. 보안 → 앱 비밀번호 생성
3. 생성된 16자리 비밀번호를 GMAIL_APP_PASSWORD에 입력

## 로컬 테스트

\`\`\`bash
# Azure Functions 로컬 실행
func start

# 수동 트리거
curl -X POST http://localhost:7071/api/trigger
\`\`\`

## Azure 배포

Azure Portal 또는 Azure CLI를 사용하여 Functions 앱을 생성하고, 환경변수를 설정한 후 배포합니다.

\`\`\`bash
func azure functionapp publish etnews-pdf-sender
\`\`\`

## 프로젝트 구조

\`\`\`
itnews_sender/
├── function_app.py           # Azure Functions 진입점
├── requirements.txt          # Python 의존성
├── src/
│   ├── config.py            # 설정 관리
│   ├── scraper.py           # PDF 다운로드
│   ├── pdf_processor.py     # PDF 광고 제거
│   ├── email_sender.py      # 이메일 전송
│   └── icloud_uploader.py   # iCloud 업로드
└── debug/                   # 디버그 스크립트
\`\`\`

## 문제 해결

### Gmail SMTP 인증 실패
- 2단계 인증 활성화 확인
- 앱 비밀번호 정확히 입력

### iCloud 업로드 실패
- iCloud 업로드는 선택사항이며, 실패해도 프로그램은 계속 진행됩니다
- 현재는 이메일 전송이 주요 전달 방법입니다

## 라이선스

개인 사용 목적
