# ITFIND 주간기술동향 PDF 다운로드 문제 정리

## 📋 프로젝트 개요

### 목적
- 매일 전자신문을 다운로드하여 이메일로 발송하는 Lambda 기반 자동화 시스템
- **새로운 기능**: 매주 수요일 ITFIND 주간기술동향 PDF를 다운로드하여 S3에 저장

### 기술 스택
- **런타임**: Python 3.12
- **인프라**: AWS Lambda (Container Image), S3, EventBridge
- **크롤링**: Playwright (브라우저 자동화), Requests (HTTP)
- **배포**: Docker, ECR
- **리전**: ap-northeast-2 (서울)

---

## 🏗️ 아키텍처 구조

### 현재 구조 (분리된 Lambda 함수)

```
┌─────────────────────────────────────────────────────────────┐
│                    EventBridge Scheduler                      │
│  - 매일: etnews-pdf-sender (전자신문)                         │
│  - 매주 수요일: itfind-pdf-downloader (주간기술동향)          │
└─────────────────────────────────────────────────────────────┘
                    │                      │
                    ▼                      ▼
    ┌───────────────────────┐  ┌──────────────────────────────┐
    │ etnews-pdf-sender     │  │ itfind-pdf-downloader        │
    │ Lambda (메인)          │  │ Lambda (ITFIND 전용)          │
    │ - 1024MB, 180s        │  │ - 2048MB, 300s               │
    │ - Playwright 포함     │  │ - Playwright 포함 (현재 미사용)│
    └───────────────────────┘  └──────────────────────────────┘
                    │                      │
                    ▼                      ▼
    ┌───────────────────────┐  ┌──────────────────────────────┐
    │ SES (이메일 발송)      │  │ S3: itnews-sender-pdfs       │
    └───────────────────────┘  │ - itfind/{YYYYMMDD}/         │
                                │   weekly_{호수}.pdf           │
                                └──────────────────────────────┘
```

### 파일 구조

```
itnews_sender/
├── lambda_handler.py              # 메인 Lambda (전자신문 발송)
├── lambda_itfind_downloader.py    # ITFIND Lambda (주간기술동향 다운로드)
├── Dockerfile                     # 메인 Lambda용
├── Dockerfile.itfind              # ITFIND Lambda용
├── src/
│   ├── itfind_scraper.py         # ITFIND 스크래퍼 (Playwright 기반)
│   └── ...
└── scripts/
    ├── deploy.sh                  # 메인 Lambda 배포
    └── deploy_itfind.sh           # ITFIND Lambda 배포
```

---

## ✅ 지금까지 확인된 내용

### 1. ITFIND 웹사이트 구조 분석

#### RSS 피드 (성공 ✅)
- **URL**: `https://www.itfind.or.kr/ccenter/rss.do?codeAlias=all&rssType=02`
- **결과**: 최신 주간기술동향 메타데이터 추출 성공
  - 제목: "AI-Ready 산업 생태계 조성을 위한 구조적 설계 [주간기술동향 2203호]"
  - 호수: 2203
  - Detail ID: 1388
  - Link: `http://www.itfind.or.kr/admin/getFile.htm?identifier=02-001-260122-000004`

#### PDF 다운로드 경로 추적

**경로 1: RSS Link → getFile.htm**
```
http://www.itfind.or.kr/admin/getFile.htm?identifier=02-001-260122-000004
→ 직접 PDF 다운로드는 안 됨 (StreamDocs 뷰어로 연결됨)
```

**경로 2: Detail Page → getStreamDocsRegi.htm**
```
https://www.itfind.or.kr/trend/weekly/weeklyDetail.do?id=1388
→ HTML에 링크 발견: getStreamDocsRegi.htm?identifier=TVOL_1388
```

**경로 3: getStreamDocsRegi.htm → JavaScript 리다이렉트**
```
https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_1388
→ JavaScript 리다이렉트 발견:
   top.location.href="https://www.itfind.or.kr/publication/regular/weeklytrend/weeklymailzine/view.do?boardParam1=1388&boardParam2=1380"
```

**경로 4: 최종 뷰어 페이지 (문제 발생 ❌)**
```
https://www.itfind.or.kr/publication/regular/weeklytrend/weeklymailzine/view.do?boardParam1=1388&boardParam2=1380
→ Requests로 접근 시: 거의 빈 페이지 (1808 bytes)
→ StreamDocs ID를 찾을 수 없음
```

### 2. StreamDocs API 구조

사용자가 제공한 정보:
- **뷰어 URL 형식**: `https://www.itfind.or.kr/streamdocs/view/sd;streamdocsId={ID}`
- **API URL 형식**: `https://www.itfind.or.kr/streamdocs/v4/documents/{ID}`
- **예시 ID**: `RtkNUpG5UfML1iXVCbU0-QqbinAUTQxwz58xRm02GRs`

### 3. 로컬 테스트 결과 (성공 ✅)

**이전 테스트 (scripts/test_itfind_scraper.py)**:
```bash
✅ RSS 피드로 주간기술동향 조회 성공
✅ StreamDocs ID 추출: RtkNUpG5UfML1iXVCbU0-QqbinAUTQxwz58xRm02GRs
✅ PDF 다운로드: 2,975,167 bytes (2.84 MB)
저장 위치: /tmp/itfind_weekly_20260128.pdf
```

**사용 방법**: Playwright 브라우저로 페이지를 실제로 렌더링하여 네트워크 요청 캡처

---

## ❌ 현재 문제 상황

### 문제 1: Playwright 브라우저 크래시 (Lambda 환경)

**증상**:
```
Browser.new_page: Target page, context or browser has been closed
```

**발생 위치**: `src/itfind_scraper.py:461`

**로그 분석**:
```
[INFO] Playwright 시작 중...                     ← 성공
[INFO] Chromium 브라우저 실행 중...                ← 성공
[INFO] 브라우저 실행 완료 (connected: True)       ← 성공
[INFO] RSS 피드에서 최신 주간기술동향 조회        ← 성공
[INFO] ✅ 주간기술동향 발견: ... (2203호)        ← 성공
[INFO] 상세 페이지에서 직접 다운로드 링크 찾기    ← 실패 지점
[ERROR] Browser.new_page: Target closed          ← 크래시
```

**Duration**: 약 15초 만에 실패 (브라우저 시작 후 페이지 접근 시도 시 즉시 크래시)

**원인 추정**:
1. Lambda의 `/tmp` 디렉토리 권한 문제
2. 메모리 부족 (2048MB 할당했으나 496MB만 사용)
3. Playwright의 Lambda 환경 호환성 문제
4. 브라우저 프로세스가 Lambda 실행 환경에서 강제 종료됨

### 문제 2: 브라우저 없이 StreamDocs ID 추출 실패

**시도한 방법**:
```python
# 1. getStreamDocsRegi.htm 페이지 접근
response = requests.get("https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_1388")
# → JavaScript 리다이렉트 URL 추출 성공

# 2. 리다이렉트된 페이지 접근
redirect_url = "https://www.itfind.or.kr/publication/regular/weeklytrend/weeklymailzine/view.do?boardParam1=1388&boardParam2=1380"
response = requests.get(redirect_url)
# → 거의 빈 페이지 반환 (1808 bytes)
# → StreamDocs ID를 찾을 수 없음

# 3. HTML 패턴 검색
re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response.text)  # ← None
re.search(r'/streamdocs/view/sd;streamdocsId=([A-Za-z0-9_-]+)', response.text)  # ← None
```

**문제 원인**:
- 최종 뷰어 페이지가 JavaScript로 동적 렌더링됨
- Requests만으로는 JavaScript 실행 불가
- 세션/쿠키 기반 인증이 필요할 가능성

---

## 🔍 핵심 질문

### 1. StreamDocs ID 획득 방법
**문제**: `TVOL_1388` → `RtkNUpG5UfML1iXVCbU0-QqbinAUTQxwz58xRm02GRs` 변환 방법을 모름

**가능한 해결책**:
- [ ] A. 숨겨진 API 엔드포인트 존재? (예: `/api/getStreamDocsId?identifier=TVOL_1388`)
- [ ] B. `TVOL_1388`과 StreamDocs ID 사이 암호화/인코딩 규칙?
- [ ] C. 세션/쿠키 기반 인증 후 접근 가능?
- [ ] D. 브라우저 없이는 불가능하고 Playwright 필수?

### 2. Lambda에서 Playwright 안정화
**문제**: 브라우저가 시작 직후 크래시

**시도한 해결책**:
- [x] 메모리 증가 (2048MB)
- [x] 타임아웃 증가 (300s)
- [x] ARM64 아키텍처 사용
- [ ] 브라우저 실행 옵션 조정 (`--no-sandbox`, `--disable-dev-shm-usage` 등)
- [ ] `/tmp` 디렉토리 크기 증가 (EphemeralStorage)

---

## 📊 현재 코드 상태

### Lambda 함수: `lambda_itfind_downloader.py`

**현재 로직 (브라우저 없는 버전)**:
```python
async def download_itfind_pdf():
    # 1. RSS에서 메타데이터 조회 (성공 ✅)
    trend = get_latest_weekly_trend_from_rss()

    # 2. StreamDocs ID 추출 시도 (실패 ❌)
    streamdocs_id = extract_streamdocs_id_from_detail_page(trend['detail_id'])
    # → None 반환

    # 3. PDF 다운로드 (실행 안 됨)
    download_pdf_direct(streamdocs_id, local_path)

    # 4. S3 업로드 (실행 안 됨)
    s3_client.put_object(...)
```

**extract_streamdocs_id_from_detail_page() 함수**:
```python
def extract_streamdocs_id_from_detail_page(detail_id: str):
    # 1. getStreamDocsRegi.htm 접근
    url = f"https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_{detail_id}"
    response = requests.get(url)

    # 2. JavaScript 리다이렉트 URL 추출 (성공 ✅)
    redirect_url = parse_js_redirect(response.text)
    # → "https://www.itfind.or.kr/publication/.../view.do?boardParam1=1388&boardParam2=1380"

    # 3. 리다이렉트 페이지에서 StreamDocs ID 찾기 (실패 ❌)
    response2 = requests.get(redirect_url)
    # → 빈 페이지 (JavaScript 렌더링 필요)
    streamdocs_id = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response2.text)
    # → None

    return None
```

### 이전 버전 (Playwright 사용, Lambda에서 크래시)

**src/itfind_scraper.py**:
```python
async def download_weekly_pdf(self, pdf_url, save_path, detail_url=None):
    # Playwright 브라우저로 페이지 접근
    page = await self.browser.new_page()  # ← 여기서 크래시

    # 네트워크 요청 캡처
    await page.goto(detail_url)
    # StreamDocs API 요청에서 document ID 추출
    # → 로컬에서는 성공, Lambda에서는 실패
```

---

## 🎯 필요한 해결 방법

### 옵션 1: StreamDocs ID 직접 획득 (브라우저 불필요)
**장점**: Lambda 안정성 ↑, 비용 ↓, 속도 ↑
**단점**: 방법을 모름

**필요한 조사**:
1. ITFIND 웹사이트의 숨겨진 API 탐색
2. 브라우저 개발자 도구로 네트워크 요청 분석
3. `TVOL_1388` → StreamDocs ID 변환 규칙 발견

### 옵션 2: Lambda에서 Playwright 안정화
**장점**: 로컬 테스트에서 검증됨
**단점**: Lambda 환경에서 불안정

**필요한 조정**:
```dockerfile
# Dockerfile.itfind에 추가
ENV PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright
ENV HOME=/tmp

# Lambda 함수 설정 증가
EphemeralStorage: 10240  # /tmp 10GB
```

```python
# 브라우저 실행 옵션 추가
browser = await playwright.chromium.launch(
    headless=True,
    args=[
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--single-process',
        '--no-zygote'
    ]
)
```

### 옵션 3: 하이브리드 접근
1. RSS로 메타데이터 조회
2. 경량 브라우저(Selenium Chrome headless)로 StreamDocs ID만 추출
3. Requests로 PDF 직접 다운로드

---

## 📝 검토 요청 사항

1. **StreamDocs ID 획득 방법**
   - ITFIND 웹사이트에서 브라우저 없이 StreamDocs ID를 얻을 수 있는 방법이 있는가?
   - `TVOL_1388` → `RtkNUpG5UfML1iXVCbU0-QqbinAUTQxwz58xRm02GRs` 변환 규칙은?

2. **Lambda Playwright 안정화**
   - Lambda 환경에서 Playwright 브라우저가 크래시하지 않도록 하는 설정은?
   - 필요한 Dockerfile 설정, 브라우저 옵션, Lambda 설정은?

3. **대안 아키텍처**
   - EC2/ECS에서 브라우저 실행 후 S3에 업로드하는 방식?
   - API Gateway → Lambda (비동기) → SQS → EC2 패턴?

---

## 🔗 관련 파일 위치

- **문제 파일**: `/Users/turtlesoup0/Documents/itnews_sender/lambda_itfind_downloader.py`
- **스크래퍼**: `/Users/turtlesoup0/Documents/itnews_sender/src/itfind_scraper.py`
- **Dockerfile**: `/Users/turtlesoup0/Documents/itnews_sender/Dockerfile.itfind`
- **배포 스크립트**: `/Users/turtlesoup0/Documents/itnews_sender/scripts/deploy_itfind.sh`

---

## 📞 추가 정보

- **AWS Account ID**: 269809345127
- **Lambda Function**: `itfind-pdf-downloader`
- **ECR Repository**: `itfind-pdf-downloader`
- **S3 Bucket**: `itnews-sender-pdfs` (수동 생성 필요)
- **IAM Role**: `etnews-lambda-role`
- **Base Image**: `mcr.microsoft.com/playwright/python:v1.57.0-noble`

---

**작성일**: 2026-01-28
**최종 테스트**: Lambda invoke → 404 (StreamDocs ID 추출 실패)
**상태**: 🔴 블로커 - StreamDocs ID 획득 방법 필요
