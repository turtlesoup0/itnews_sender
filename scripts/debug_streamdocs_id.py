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

            # 5. JavaScript redirect 추적
            content = response.text
            print(f"\n🔎 JavaScript redirect 추적:")

            js_redirect_match = re.search(r'location\.href\s*=\s*["\']([^"\']+)["\']', content)
            if js_redirect_match:
                js_redirect_url = js_redirect_match.group(1)
                print(f"  📍 JS redirect 발견: {js_redirect_url}")

                # JS redirect 페이지 접근
                if not js_redirect_url.startswith('http'):
                    js_redirect_url = f"https://www.itfind.or.kr{js_redirect_url}"

                print(f"  🌐 리다이렉트 페이지 접근 중...")
                response2 = session.get(js_redirect_url, headers=headers, timeout=30)

                print(f"    상태: {response2.status_code}")
                print(f"    URL: {response2.url}")
                print(f"    Content-Length: {len(response2.text)}")

                content = response2.text

            # 6. StreamDocs ID 패턴 검색 (전체 응답에서)
            print(f"\n🔎 StreamDocs ID 패턴 검색:")

            # 패턴 1: 최종 URL에서 (response2가 있으면 response2.url 우선)
            final_url = response2.url if 'response2' in locals() else response.url

            if 'streamdocsId=' in final_url:
                match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', final_url)
                if match:
                    print(f"  ✅ URL에서 발견: {match.group(1)}")
                    return match.group(1)

            # 패턴 2: HTML/JS에서
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

            # 패턴 5: iframe src에서
            iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']*streamdocs[^"\']*)["\']', content, re.IGNORECASE)
            if iframe_match:
                iframe_src = iframe_match.group(1)
                print(f"  📺 iframe 발견: {iframe_src}")

                # iframe src에서 ID 추출
                match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', iframe_src)
                if match:
                    print(f"  ✅ iframe에서 발견: {match.group(1)}")
                    return match.group(1)

            print(f"  ❌ StreamDocs ID를 찾을 수 없음")
            print(f"\n📄 Response 샘플 (처음 1000자):")
            print(content[:1000])

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
