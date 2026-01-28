#!/usr/bin/env python3
"""
PDF 손상 추적 스크립트 - 각 단계에서 파일 무결성 확인
"""
import boto3
import json
import base64
import hashlib
from pathlib import Path

def hex_dump(data, length=64):
    """첫/끝 hex dump"""
    print(f"  첫 {length} bytes:")
    for i in range(0, min(len(data), length), 16):
        hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
        print(f"    {i:04x}: {hex_part:<48} {ascii_part}")

    if len(data) > length:
        print(f"\n  끝 {length} bytes:")
        start = len(data) - length
        for i in range(start, len(data), 16):
            hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
            print(f"    {i:04x}: {hex_part:<48} {ascii_part}")

def check_pdf_integrity(data, label):
    """PDF 무결성 확인"""
    print(f"\n[{label}]")
    print(f"  크기: {len(data):,} bytes")
    print(f"  MD5: {hashlib.md5(data).hexdigest()}")
    print(f"  SHA256: {hashlib.sha256(data).hexdigest()}")

    # PDF 시그니처 확인
    if data[:5] == b'%PDF-':
        print(f"  ✅ PDF 시그니처 정상: {data[:8]}")
    else:
        print(f"  ❌ PDF 시그니처 오류: {data[:10]}")

    # PDF 끝 확인 (%%EOF)
    if b'%%EOF' in data[-100:]:
        print(f"  ✅ PDF EOF 정상")
    else:
        print(f"  ❌ PDF EOF 없음")

    hex_dump(data)
    return data

def trace_corruption():
    print("=" * 80)
    print("PDF 손상 추적: ITFIND Lambda → 메인 Lambda → 이메일 첨부")
    print("=" * 80)

    # 1단계: ITFIND Lambda 호출
    print("\n" + "=" * 80)
    print("1단계: ITFIND Lambda 호출")
    print("=" * 80)

    lambda_client = boto3.client('lambda', region_name='ap-northeast-2')

    response = lambda_client.invoke(
        FunctionName='itfind-pdf-downloader',
        InvocationType='RequestResponse',
        Payload=json.dumps({})
    )

    result_payload = json.loads(response['Payload'].read())

    if result_payload.get('statusCode') != 200 or not result_payload['body']['success']:
        print(f"❌ ITFIND Lambda 실패: {result_payload}")
        return

    data = result_payload['body']['data']

    print(f"\n✅ ITFIND Lambda 응답:")
    print(f"  제목: {data['title']}")
    print(f"  파일명: {data['filename']}")
    print(f"  파일 크기: {data['file_size']:,} bytes")

    # 2단계: Base64 디코딩
    print("\n" + "=" * 80)
    print("2단계: Base64 디코딩")
    print("=" * 80)

    pdf_base64 = data['pdf_base64']
    print(f"\nBase64 문자열 정보:")
    print(f"  길이: {len(pdf_base64):,} chars")
    print(f"  첫 100자: {pdf_base64[:100]}")
    print(f"  끝 100자: {pdf_base64[-100:]}")

    # Base64 디코딩
    try:
        pdf_data = base64.b64decode(pdf_base64)
        print(f"\n✅ Base64 디코딩 성공")
    except Exception as e:
        print(f"\n❌ Base64 디코딩 실패: {e}")
        return

    check_pdf_integrity(pdf_data, "디코딩된 PDF")

    # 3단계: 파일 저장 (/tmp)
    print("\n" + "=" * 80)
    print("3단계: /tmp에 파일 저장")
    print("=" * 80)

    tmp_path = f"/tmp/{data['filename']}"
    with open(tmp_path, 'wb') as f:
        f.write(pdf_data)

    print(f"\n파일 저장: {tmp_path}")

    # 저장된 파일 다시 읽기
    with open(tmp_path, 'rb') as f:
        saved_pdf_data = f.read()

    check_pdf_integrity(saved_pdf_data, "저장 후 읽은 PDF")

    # 무결성 비교
    if pdf_data == saved_pdf_data:
        print(f"\n✅ 저장 전후 데이터 일치")
    else:
        print(f"\n❌ 저장 전후 데이터 불일치!")

    # 4단계: 로컬 PDF 뷰어로 열기 테스트
    print("\n" + "=" * 80)
    print("4단계: PDF 파일 검증 (file 명령어)")
    print("=" * 80)

    import subprocess
    try:
        file_output = subprocess.check_output(['file', tmp_path], text=True)
        print(f"\n  {file_output.strip()}")
        if 'PDF' in file_output:
            print(f"  ✅ 올바른 PDF 파일")
        else:
            print(f"  ❌ PDF 파일이 아님")
    except Exception as e:
        print(f"  ❌ file 명령어 실패: {e}")

    # pdfinfo로 상세 정보 확인
    try:
        pdfinfo_output = subprocess.check_output(['pdfinfo', tmp_path], text=True, stderr=subprocess.STDOUT)
        print(f"\n  PDF 정보:")
        for line in pdfinfo_output.split('\n')[:10]:
            if line.strip():
                print(f"    {line}")
    except subprocess.CalledProcessError as e:
        print(f"  ❌ pdfinfo 실패: {e.output}")
    except FileNotFoundError:
        print(f"  ⚠️  pdfinfo 명령어 없음 (설치 필요)")

    # 5단계: 이메일 첨부 시뮬레이션
    print("\n" + "=" * 80)
    print("5단계: 이메일 첨부 시뮬레이션 (MIMEApplication)")
    print("=" * 80)

    from email.mime.multipart import MIMEMultipart
    from email.mime.application import MIMEApplication
    from urllib.parse import quote
    from datetime import datetime

    msg = MIMEMultipart()
    msg['Subject'] = 'Test'
    msg['From'] = 'test@test.com'
    msg['To'] = 'test@test.com'

    # 현재 코드와 동일한 방식으로 첨부
    with open(tmp_path, 'rb') as pdf_file:
        pdf_attachment_data = pdf_file.read()

    print(f"\n파일 읽기:")
    check_pdf_integrity(pdf_attachment_data, "첨부 전 PDF 데이터")

    # MIMEApplication 생성
    pdf_attachment = MIMEApplication(pdf_attachment_data, _subtype="pdf")

    filename = data['filename']

    # 파일명 설정 (현재 코드)
    from email.utils import encode_rfc2231
    safe_filename = filename.encode('ascii', 'ignore').decode('ascii')
    if not safe_filename:
        safe_filename = f"attachment_{datetime.now().strftime('%Y%m%d')}.pdf"

    pdf_attachment.add_header(
        "Content-Disposition",
        f"attachment; filename=\"{safe_filename}\"; filename*=UTF-8''{quote(filename)}"
    )

    msg.attach(pdf_attachment)

    print(f"\n✅ MIMEApplication 첨부 완료")
    print(f"  Content-Type: {pdf_attachment.get_content_type()}")
    print(f"  Content-Disposition: {pdf_attachment.get('Content-Disposition')}")

    # 6단계: 이메일 메시지를 문자열로 변환 후 다시 파싱
    print("\n" + "=" * 80)
    print("6단계: 이메일 직렬화 → 역직렬화 테스트")
    print("=" * 80)

    # 이메일을 문자열로 변환
    email_string = msg.as_string()
    print(f"\n이메일 문자열 길이: {len(email_string):,} bytes")

    # 다시 파싱
    from email import message_from_string
    parsed_msg = message_from_string(email_string)

    # 첨부 파일 추출
    for part in parsed_msg.walk():
        if part.get_content_maintype() == 'application':
            attached_pdf_data = part.get_payload(decode=True)
            print(f"\n첨부 파일 추출:")
            check_pdf_integrity(attached_pdf_data, "역직렬화 후 PDF")

            # 무결성 비교
            if attached_pdf_data == pdf_data:
                print(f"\n✅ 원본 PDF와 일치!")
            else:
                print(f"\n❌ 원본 PDF와 불일치!")
                print(f"  원본 크기: {len(pdf_data):,} bytes")
                print(f"  추출 크기: {len(attached_pdf_data):,} bytes")
                print(f"  차이: {abs(len(pdf_data) - len(attached_pdf_data)):,} bytes")

            # 추출된 파일 저장
            extracted_path = "/tmp/extracted_from_email.pdf"
            with open(extracted_path, 'wb') as f:
                f.write(attached_pdf_data)
            print(f"\n추출된 파일 저장: {extracted_path}")

            # 추출된 파일 검증
            try:
                file_output = subprocess.check_output(['file', extracted_path], text=True)
                print(f"  {file_output.strip()}")
                if 'PDF' in file_output:
                    print(f"  ✅ 추출된 파일도 올바른 PDF")
                else:
                    print(f"  ❌ 추출된 파일이 손상됨")
            except:
                pass

            break

    # 최종 요약
    print("\n" + "=" * 80)
    print("최종 요약")
    print("=" * 80)
    print(f"""
1. ITFIND Lambda 다운로드: ✅ 성공 ({data['file_size']:,} bytes)
2. Base64 디코딩: {'✅ 성공' if pdf_data[:5] == b'%PDF-' else '❌ 실패'}
3. /tmp 저장: {'✅ 일치' if pdf_data == saved_pdf_data else '❌ 불일치'}
4. MIMEApplication 첨부: ✅ 완료
5. 이메일 직렬화/역직렬화: {'✅ 일치' if attached_pdf_data == pdf_data else '❌ 불일치'}

원본 MD5: {hashlib.md5(pdf_data).hexdigest()}
추출 MD5: {hashlib.md5(attached_pdf_data).hexdigest()}
    """)

if __name__ == '__main__':
    trace_corruption()
