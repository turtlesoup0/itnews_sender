# 📘 ITFIND 주간기술동향 PDF 자동 수집

## 문제 해결을 위한 총정리 가이드라인 (Agent Instruction)

---

## 0️⃣ 문제 정의 (요약)

* ITFIND 주간기술동향 PDF는 **StreamDocs**라는 외부 뷰어 솔루션으로 보호됨
* 그러나 **`streamdocsId`만 알면** 아래 API를 직접 호출해 **PDF 다운로드 가능**

```
https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocsId}
```

* 목표:

  * **공식 RSS를 기준으로 최신 주간기술동향을 감지**
  * **가능하면 브라우저 없이** streamdocsId를 획득
  * 실패 시 **Playwright를 최소 범위로 사용**
  * 최종적으로 **Lambda 환경에서 안정적으로 PDF 다운로드 후 S3 저장**

---

## 1️⃣ 반드시 지켜야 할 전제 조건 (중요)

### ✅ RSS는 ITFIND 공식 RSS만 사용

* RSS URL:

```
https://www.itfind.or.kr/ccenter/rss.do?codeAlias=all&rssType=02
```

* RSS 항목의 `link`는 다음 형식임:

```
http://www.itfind.or.kr/admin/getFile.htm?identifier=02-001-XXXXXX-XXXXXX
```

⚠️ **RSS에는 TVOL_XXXX 또는 streamdocsId가 직접 포함되지 않음**

---

## 2️⃣ 절대 하면 안 되는 접근 ❌

* ❌ RSS에서 `TVOL_` 패턴을 직접 찾으려 하지 말 것
* ❌ HTML 정적 파싱으로 `streamdocsId`를 찾으려 하지 말 것

  * `view.do` 페이지는 JS 렌더링 기반
* ❌ StreamDocs ID에 대해 "변환 규칙"이나 "인코딩 규칙"을 가정하지 말 것
  → **서버에서 동적으로 발급되는 opaque ID임**

---

## 3️⃣ 1차 목표: 브라우저 없이 StreamDocs ID 획득

### 🎯 핵심 아이디어

> **RSS 링크(getFile.htm)의 응답 / redirect chain / JS redirect 안에
> streamdocsId 또는 documents URL이 이미 노출되어 있을 가능성을 탐색한다**

---

### ✅ Step 1: RSS 링크를 "브라우저처럼" 호출

```python
headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Referer": "https://www.itfind.or.kr/",
}
response = requests.get(
    rss_item_link,
    headers=headers,
    allow_redirects=True,
)
```

---

### ✅ Step 2: 반드시 분석할 것 (중요)

1. `response.history`
2. 각 history response의:

   * `status_code`
   * `headers["Location"]`
3. 최종 `response.url`
4. `response.headers`
5. `response.text` (JS redirect 여부)

---

### ✅ Step 3: 다음 패턴을 우선적으로 탐색

#### ① Redirect URL에서

```
/streamdocs/view/sd;streamdocsId=XXXX
/streamdocs/v4/documents/XXXX
```

#### ② HTML / JS redirect에서

```html
location.href="...streamdocsId=XXXX"
```

```python
re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response.text)
```

---

### ✅ Step 4: streamdocsId를 얻었을 경우

```python
pdf_url = f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}"
pdf_response = requests.get(pdf_url, headers=headers)
```

* Content-Type: `application/pdf` 확인
* Content-Length > 0 확인
* 성공 시 S3 업로드

---

## 4️⃣ 브라우저 없이 실패할 경우 (플랜 B)

### 조건

* redirect / JS / header 어디에도 `streamdocsId`가 노출되지 않음
* Requests-only 접근이 불가능하다고 판단될 경우

---

## 5️⃣ 2차 목표: Playwright 최소 사용 전략

### 🎯 목표

> **Playwright는 "streamdocsId 1개 추출용"으로만 사용**

---

### ✅ Playwright 사용 가이드 (Lambda 기준)

#### 브라우저 옵션 (필수)

```python
args = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-zygote",
]
```

❌ `--single-process` 사용 금지

---

#### 환경 변수 (Dockerfile)

```dockerfile
ENV HOME=/tmp
ENV TMPDIR=/tmp
ENV PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers
```

---

#### Lambda 설정

* Memory: ≥ 2048MB
* Timeout: ≥ 300s
* EphemeralStorage: **10GB 필수**

---

### ✅ Playwright 로직 최소화

* 페이지 렌더링 ❌
* 스크롤 ❌
* DOM 탐색 ❌

**오직 이것만 수행**

1. `view.do` 페이지 진입
2. 네트워크 요청 감청
3. `/streamdocs/v4/documents/{id}` 요청에서 ID 추출
4. 브라우저 즉시 종료

---

## 6️⃣ 구조적으로 권장되는 최종 아키텍처

### 🥇 1순위 (안정성 최우선)

* **ECS Fargate (주 1회 RunTask)**
* Playwright 포함
* Lambda는 트리거 역할만 수행

---

### 🥈 2순위

* Lambda + Playwright (ID만 추출)
* PDF 다운로드는 Requests

---

### 🥉 3순위

* Lambda 단독 + Requests (redirect chain 성공 시)

---

## 7️⃣ 성공 조건 정의 (완료 기준)

* [ ] RSS로 최신 주간기술동향 감지
* [ ] streamdocsId 획득 (경로 무관)
* [ ] `/streamdocs/v4/documents/{id}` 직접 호출
* [ ] PDF 정상 다운로드
* [ ] S3 업로드 성공
* [ ] Playwright 사용 시 실행 시간 ≤ 5초

---

## 8️⃣ 한 줄 요약 (에이전트용)

> **StreamDocs는 완전한 DRM이 아니며,
> RSS → redirect / JS / network 분석으로 streamdocsId를 잡아
> documents API를 직접 호출하는 것이 최우선 전략이다.
> 브라우저는 최후의 수단으로만 최소 사용한다.**

---

## 9️⃣ 즉시 실행 가능한 디버깅 체크리스트

### 🔍 Phase 1: RSS 링크 분석 (브라우저 없이)

**목표**: RSS → getFile.htm → redirect chain에서 streamdocsId 발견

```bash
# 디버깅 스크립트 실행
python3 scripts/debug_streamdocs_id.py
```

**체크포인트**:
- [ ] RSS에서 최신 주간기술동향 link 추출
- [ ] getFile.htm 응답 상태 코드 (200? 302?)
- [ ] response.history 길이 (redirect 횟수)
- [ ] 각 redirect의 Location 헤더
- [ ] 최종 response.url
- [ ] response.text에서 streamdocsId 패턴 검색
- [ ] response.text에서 /streamdocs/ 경로 검색

**예상 결과**:
```
✅ Success: streamdocsId found in redirect URL
✅ Success: streamdocsId found in HTML/JS
❌ Failed: streamdocsId not found → Playwright 필요
```

---

### 🔍 Phase 2: Playwright 네트워크 캡처 (필요 시)

**목표**: 브라우저로 페이지 로드 후 네트워크 요청에서 streamdocsId 추출

```bash
# Playwright 디버깅
python3 scripts/debug_playwright_capture.py
```

**체크포인트**:
- [ ] Playwright 브라우저 시작 성공
- [ ] 페이지 로드 성공
- [ ] 네트워크 요청 캡처 개수
- [ ] /streamdocs/v4/documents/ 요청 발견
- [ ] streamdocsId 추출 성공
- [ ] 브라우저 정상 종료

**예상 소요 시간**: < 10초

---

### 🔍 Phase 3: Lambda 환경 테스트

**체크포인트**:
- [ ] Docker 이미지 빌드 성공
- [ ] ECR 푸시 성공
- [ ] Lambda 함수 업데이트 성공
- [ ] Lambda invoke 성공
- [ ] CloudWatch 로그 확인
- [ ] PDF 다운로드 성공
- [ ] S3 업로드 성공

---

## 🛠️ 디버깅 스크립트

### 스크립트 1: RSS 링크 전체 분석

**파일**: `scripts/debug_streamdocs_id.py`

```python
#!/usr/bin/env python3
"""
RSS 링크 → redirect chain 전체 분석
StreamDocs ID를 브라우저 없이 찾을 수 있는지 확인
"""
import requests
import xml.etree.ElementTree as ET
import re

def analyze_rss_link():
    # 1. RSS 조회
    rss_url = "https://www.itfind.or.kr/ccenter/rss.do?codeAlias=all&rssType=02"
    print(f"🔍 RSS 조회: {rss_url}")

    rss_response = requests.get(rss_url, timeout=30)
    root = ET.fromstring(rss_response.content)

    # 2. 최신 주간기술동향 찾기
    for item in root.findall('.//item'):
        title = item.find('title').text
        if '[주간기술동향' in title:
            link = item.find('link').text
            print(f"\n✅ 발견: {title}")
            print(f"📎 Link: {link}")

            # 3. getFile.htm 호출 (redirect 추적)
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "*/*",
                "Referer": "https://www.itfind.or.kr/",
            }

            print(f"\n🔄 Redirect Chain 분석:")
            session = requests.Session()
            response = session.get(link, headers=headers, allow_redirects=True)

            # 4. History 분석
            for i, hist in enumerate(response.history):
                print(f"  [{i}] {hist.status_code} → {hist.headers.get('Location', 'N/A')}")

            print(f"  [Final] {response.status_code} → {response.url}")

            # 5. StreamDocs ID 패턴 검색
            print(f"\n🔎 StreamDocs ID 패턴 검색:")

            # 패턴 1: URL에서
            if 'streamdocsId=' in response.url:
                match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response.url)
                if match:
                    print(f"  ✅ URL에서 발견: {match.group(1)}")
                    return match.group(1)

            # 패턴 2: HTML/JS에서
            content = response.text
            match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', content)
            if match:
                print(f"  ✅ HTML/JS에서 발견: {match.group(1)}")
                return match.group(1)

            # 패턴 3: /streamdocs/v4/documents/ 경로
            match = re.search(r'/streamdocs/v4/documents/([A-Za-z0-9_-]+)', content)
            if match:
                print(f"  ✅ Documents API에서 발견: {match.group(1)}")
                return match.group(1)

            # 패턴 4: /streamdocs/view/sd 경로
            match = re.search(r'/streamdocs/view/sd;streamdocsId=([A-Za-z0-9_-]+)', content)
            if match:
                print(f"  ✅ Viewer URL에서 발견: {match.group(1)}")
                return match.group(1)

            print(f"  ❌ StreamDocs ID를 찾을 수 없음")
            print(f"\n📄 Response 샘플 (처음 500자):")
            print(content[:500])

            break

    return None

if __name__ == "__main__":
    streamdocs_id = analyze_rss_link()

    if streamdocs_id:
        print(f"\n🎉 성공! StreamDocs ID: {streamdocs_id}")

        # PDF 다운로드 테스트
        pdf_url = f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}"
        print(f"\n📥 PDF 다운로드 테스트: {pdf_url}")

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/pdf,*/*",
            "Referer": "https://www.itfind.or.kr/",
        }

        pdf_response = requests.get(pdf_url, headers=headers, stream=True)

        if pdf_response.status_code == 200:
            content_type = pdf_response.headers.get('content-type', '')
            content_length = pdf_response.headers.get('content-length', '0')

            print(f"  ✅ 상태: {pdf_response.status_code}")
            print(f"  📄 Content-Type: {content_type}")
            print(f"  📦 크기: {int(content_length):,} bytes ({int(content_length)/1024/1024:.2f} MB)")

            if 'application/pdf' in content_type:
                print(f"\n✅ PDF 다운로드 성공! 브라우저 불필요!")
            else:
                print(f"\n⚠️ Content-Type이 PDF가 아님")
        else:
            print(f"  ❌ 실패: {pdf_response.status_code}")
    else:
        print(f"\n❌ 실패: Playwright 필요")
```

---

### 스크립트 2: Playwright 네트워크 캡처

**파일**: `scripts/debug_playwright_capture.py`

```python
#!/usr/bin/env python3
"""
Playwright로 네트워크 요청 캡처
StreamDocs ID 추출 테스트
"""
import asyncio
from playwright.async_api import async_playwright
import re

async def capture_streamdocs_id():
    print("🎭 Playwright 시작...")

    async with async_playwright() as p:
        # 브라우저 시작
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--no-zygote',
            ]
        )

        page = await browser.new_page()

        # 네트워크 요청 캡처
        captured_requests = []

        async def capture_request(request):
            url = request.url
            if 'streamdocs' in url:
                captured_requests.append(url)
                print(f"  📡 {url}")

        page.on('request', capture_request)

        # RSS에서 최신 링크 가져오기
        print("\n🔍 RSS 조회...")
        import requests
        import xml.etree.ElementTree as ET

        rss_url = "https://www.itfind.or.kr/ccenter/rss.do?codeAlias=all&rssType=02"
        rss_response = requests.get(rss_url, timeout=30)
        root = ET.fromstring(rss_response.content)

        link = None
        for item in root.findall('.//item'):
            title = item.find('title').text
            if '[주간기술동향' in title:
                link = item.find('link').text
                print(f"✅ 발견: {title}")
                break

        if not link:
            print("❌ 주간기술동향을 찾을 수 없음")
            await browser.close()
            return None

        # 페이지 로드
        print(f"\n🌐 페이지 로드: {link}")
        await page.goto(link, wait_until="networkidle", timeout=30000)

        # StreamDocs ID 추출
        print(f"\n🔎 캡처된 요청 분석:")
        streamdocs_id = None

        for url in captured_requests:
            # /streamdocs/v4/documents/{id}
            match = re.search(r'/streamdocs/v4/documents/([A-Za-z0-9_-]+)', url)
            if match:
                streamdocs_id = match.group(1)
                print(f"  ✅ Documents API에서 발견: {streamdocs_id}")
                break

            # streamdocsId={id}
            match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', url)
            if match:
                streamdocs_id = match.group(1)
                print(f"  ✅ 파라미터에서 발견: {streamdocs_id}")
                break

        await browser.close()
        return streamdocs_id

if __name__ == "__main__":
    streamdocs_id = asyncio.run(capture_streamdocs_id())

    if streamdocs_id:
        print(f"\n🎉 성공! StreamDocs ID: {streamdocs_id}")
    else:
        print(f"\n❌ 실패: StreamDocs ID를 찾을 수 없음")
```

---

## 📞 다음 작업자를 위한 체크리스트

### 즉시 실행할 것:

1. **scripts/debug_streamdocs_id.py 실행**
   ```bash
   python3 scripts/debug_streamdocs_id.py
   ```

2. **결과 분석**:
   - ✅ StreamDocs ID 발견 → lambda_itfind_downloader.py 수정
   - ❌ 발견 실패 → scripts/debug_playwright_capture.py 실행

3. **Playwright 결과 분석**:
   - ✅ 네트워크 캡처 성공 → Lambda Playwright 최적화
   - ❌ 캡처 실패 → ECS Fargate 아키텍처 검토

---

**작성일**: 2026-01-28
**버전**: 1.0
**상태**: 🔴 블로커 해결 대기 중
