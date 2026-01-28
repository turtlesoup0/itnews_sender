#!/usr/bin/env python3
"""
ITFIND PDF 다운로드 검증 스크립트
- 파일 크기, HTTP 헤더, 리다이렉트 히스토리, 파일 덤프 등 모든 정보 출력
"""
import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime

def verify_itfind_download():
    print("=" * 80)
    print("ITFIND PDF 다운로드 검증")
    print("=" * 80)

    # 1. RSS 피드에서 최신 주간기술동향 조회
    print("\n[1단계] RSS 피드 조회")
    rss_url = "https://www.itfind.or.kr/ccenter/rss.do?codeAlias=all&rssType=02"
    print(f"RSS URL: {rss_url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "*/*",
        "Referer": "https://www.itfind.or.kr/",
    }

    session = requests.Session()
    rss_response = session.get(rss_url, headers=headers, timeout=30)

    print(f"\nRSS 응답 상태: {rss_response.status_code}")
    print(f"RSS Content-Type: {rss_response.headers.get('Content-Type')}")

    # RSS 파싱
    root = ET.fromstring(rss_response.content)
    items = root.findall('.//item')

    # 주간기술동향 찾기
    weekly_trend = None
    for item in items:
        title = item.find('title').text
        if '주간기술동향' in title and '[주간기술동향' in title:
            link = item.find('link').text
            # Detail ID 추출
            detail_id_match = re.search(r'identifier=(\w+)', link)
            if detail_id_match:
                detail_id = detail_id_match.group(1).replace('TVOL_', '')

                # 호수 추출
                issue_match = re.search(r'\[주간기술동향\s*(\d+)호\]', title)
                issue_number = issue_match.group(1) if issue_match else "unknown"

                weekly_trend = {
                    'title': title,
                    'link': link,
                    'detail_id': detail_id,
                    'issue_number': issue_number
                }
                break

    if not weekly_trend:
        print("\n❌ 주간기술동향을 찾을 수 없습니다.")
        return

    print(f"\n✅ 주간기술동향 발견:")
    print(f"   제목: {weekly_trend['title']}")
    print(f"   Detail ID: {weekly_trend['detail_id']}")
    print(f"   호수: {weekly_trend['issue_number']}")
    print(f"   RSS Link: {weekly_trend['link']}")

    # 2. StreamDocs ID 추출
    print("\n" + "=" * 80)
    print("[2단계] StreamDocs ID 추출")
    print("=" * 80)

    streamdocs_regi_url = f"https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_{weekly_trend['detail_id']}"
    print(f"\nStreamDocs Regi URL: {streamdocs_regi_url}")

    response1 = session.get(streamdocs_regi_url, headers=headers, timeout=30, allow_redirects=True)

    print(f"\n[Step 2-1] getStreamDocsRegi.htm 응답:")
    print(f"  Status: {response1.status_code}")
    print(f"  Content-Type: {response1.headers.get('Content-Type')}")
    print(f"  Content-Length: {response1.headers.get('Content-Length')}")
    print(f"  Final URL: {response1.url}")

    if response1.history:
        print(f"\n  리다이렉트 히스토리 ({len(response1.history)}개):")
        for i, resp in enumerate(response1.history, 1):
            print(f"    [{i}] {resp.status_code} -> {resp.headers.get('Location', 'N/A')}")

    # JavaScript 리다이렉트 URL 추출
    js_redirect_match = re.search(r'location\.href\s*=\s*["\']([^"\']+)["\']', response1.text)

    if not js_redirect_match:
        print("\n❌ JavaScript 리다이렉트 URL을 찾을 수 없습니다.")
        print("\nHTML 내용 (첫 500자):")
        print(response1.text[:500])
        return

    redirect_url = js_redirect_match.group(1)
    if not redirect_url.startswith('http'):
        redirect_url = f"https://www.itfind.or.kr{redirect_url}"

    print(f"\n✅ JavaScript 리다이렉트 URL 발견:")
    print(f"   {redirect_url}")

    # JavaScript 리다이렉트 따라가기
    print(f"\n[Step 2-2] JavaScript 리다이렉트 따라가기:")
    response2 = session.get(redirect_url, headers=headers, timeout=30, allow_redirects=True)

    print(f"  Status: {response2.status_code}")
    print(f"  Content-Type: {response2.headers.get('Content-Type')}")
    print(f"  Final URL: {response2.url}")

    if response2.history:
        print(f"\n  리다이렉트 히스토리 ({len(response2.history)}개):")
        for i, resp in enumerate(response2.history, 1):
            print(f"    [{i}] {resp.status_code} -> {resp.headers.get('Location', 'N/A')}")

    # StreamDocs ID 추출
    streamdocs_id_match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response2.url)

    if not streamdocs_id_match:
        print("\n❌ StreamDocs ID를 찾을 수 없습니다.")
        print(f"\nFinal URL: {response2.url}")
        return

    streamdocs_id = streamdocs_id_match.group(1)
    print(f"\n✅ StreamDocs ID 추출 성공:")
    print(f"   {streamdocs_id}")
    print(f"   (추출 원본: {response2.url})")

    # 3. PDF 다운로드
    print("\n" + "=" * 80)
    print("[3단계] PDF 다운로드")
    print("=" * 80)

    pdf_api_url = f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}"
    print(f"\nStreamDocs API URL: {pdf_api_url}")

    pdf_response = session.get(pdf_api_url, headers=headers, timeout=30, allow_redirects=True, stream=True)

    print(f"\n[3-1] HTTP 응답 상태:")
    print(f"  Status Code: {pdf_response.status_code}")
    print(f"  Reason: {pdf_response.reason}")

    print(f"\n[3-2] HTTP 응답 헤더 전체:")
    for key, value in pdf_response.headers.items():
        print(f"  {key}: {value}")

    if pdf_response.history:
        print(f"\n[3-3] 리다이렉트 히스토리 ({len(pdf_response.history)}개):")
        for i, resp in enumerate(pdf_response.history, 1):
            print(f"  [{i}] Status: {resp.status_code}")
            print(f"       Location: {resp.headers.get('Location', 'N/A')}")
            print(f"       URL: {resp.url}")

    print(f"\n[3-4] 최종 요청 URL:")
    print(f"  {pdf_response.url}")

    # PDF 데이터 읽기
    pdf_data = pdf_response.content

    print(f"\n[3-5] 파일 크기:")
    print(f"  {len(pdf_data):,} bytes ({len(pdf_data) / 1024 / 1024:.2f} MB)")

    print(f"\n[3-6] 파일 시그니처 (첫 10 bytes):")
    print(f"  Hex: {pdf_data[:10].hex()}")
    print(f"  ASCII: {pdf_data[:10]}")

    print(f"\n[3-7] 파일 첫 1KB 덤프:")
    print("  " + "=" * 76)
    first_kb = pdf_data[:1024]
    # Hex dump
    for i in range(0, min(len(first_kb), 256), 16):
        hex_part = ' '.join(f'{b:02x}' for b in first_kb[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in first_kb[i:i+16])
        print(f"  {i:04x}: {hex_part:<48} {ascii_part}")

    if len(first_kb) > 256:
        print(f"  ... (총 {len(first_kb)} bytes, 처음 256 bytes만 표시)")

    print("  " + "=" * 76)

    # PDF 검증
    print(f"\n[3-8] PDF 파일 검증:")
    if pdf_data[:5] == b'%PDF-':
        print(f"  ✅ 올바른 PDF 시그니처: {pdf_data[:8]}")
    else:
        print(f"  ❌ 잘못된 PDF 시그니처: {pdf_data[:8]}")

    # 파일 저장
    output_path = f"/tmp/itfind_verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    with open(output_path, 'wb') as f:
        f.write(pdf_data)

    print(f"\n[3-9] 파일 저장:")
    print(f"  경로: {output_path}")

    # 파일 타입 확인
    import subprocess
    try:
        file_output = subprocess.check_output(['file', output_path], text=True)
        print(f"  파일 타입: {file_output.strip()}")
    except:
        pass

    print("\n" + "=" * 80)
    print("✅ 검증 완료")
    print("=" * 80)

    # 요약
    print("\n[요약]")
    print(f"1. 파일 크기: {len(pdf_data):,} bytes")
    print(f"2. Content-Type: {pdf_response.headers.get('Content-Type')}")
    print(f"3. 리다이렉트 횟수: {len(pdf_response.history)}")
    print(f"4. 파일 시그니처: {pdf_data[:8]}")
    print(f"5. 최종 URL: {pdf_response.url}")
    print(f"6. StreamDocs ID: {streamdocs_id}")
    print(f"7. StreamDocs ID 추출 원본: {response2.url}")

if __name__ == '__main__':
    verify_itfind_download()
