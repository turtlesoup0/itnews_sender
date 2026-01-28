#!/usr/bin/env python3
"""
통합 테스트: 메인 Lambda → ITFIND Lambda 호출 검증
"""
import boto3
import json
import base64

def test_integration():
    print("=" * 60)
    print("통합 테스트: 메인 Lambda → ITFIND Lambda 호출")
    print("=" * 60)

    # ITFIND Lambda 호출
    lambda_client = boto3.client('lambda', region_name='ap-northeast-2')

    print("\n1. ITFIND Lambda 호출 중...")
    response = lambda_client.invoke(
        FunctionName='itfind-pdf-downloader',
        InvocationType='RequestResponse',
        Payload=json.dumps({})
    )

    # 응답 파싱
    result_payload = json.loads(response['Payload'].read())

    print(f"   StatusCode: {response['StatusCode']}")
    print(f"   Lambda StatusCode: {result_payload.get('statusCode')}")

    if result_payload.get('statusCode') == 200 and result_payload['body']['success']:
        data = result_payload['body']['data']

        print(f"\n2. PDF 메타데이터:")
        print(f"   제목: {data['title']}")
        print(f"   호수: {data['issue_number']}호")
        print(f"   발행일: {data['publish_date']}")
        print(f"   파일명: {data['filename']}")
        print(f"   크기: {data['file_size']:,} bytes ({data['file_size'] / 1024 / 1024:.2f} MB)")
        print(f"   StreamDocs ID: {data['streamdocs_id']}")

        # Base64 디코딩 테스트
        print(f"\n3. Base64 디코딩 테스트...")
        pdf_base64 = data['pdf_base64']
        print(f"   Base64 길이: {len(pdf_base64):,} chars")

        pdf_data = base64.b64decode(pdf_base64)
        print(f"   디코딩 후 크기: {len(pdf_data):,} bytes")

        # PDF 시그니처 확인
        if pdf_data[:5] == b'%PDF-':
            print(f"   ✅ PDF 시그니처 확인: {pdf_data[:5]}")
        else:
            print(f"   ❌ PDF 시그니처 불일치: {pdf_data[:5]}")
            return False

        # 임시 파일로 저장 테스트
        test_path = f"/tmp/{data['filename']}"
        with open(test_path, 'wb') as f:
            f.write(pdf_data)

        print(f"   ✅ 파일 저장 성공: {test_path}")

        print("\n" + "=" * 60)
        print("✅ 통합 테스트 성공!")
        print("=" * 60)
        print("\n결론:")
        print("- ITFIND Lambda가 정상적으로 PDF를 다운로드")
        print("- Base64로 인코딩하여 반환")
        print("- 메인 Lambda에서 디코딩 및 파일 저장 가능")
        print("- 이메일 첨부 준비 완료")

        return True

    else:
        print(f"\n❌ ITFIND Lambda 호출 실패:")
        print(f"   {result_payload}")
        return False

if __name__ == '__main__':
    test_integration()
