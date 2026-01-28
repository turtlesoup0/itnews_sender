"""
수신거부 API Lambda 핸들러
Lambda Function URL을 통해 호출되어 수신거부 처리
"""
import json
import logging
import os
from ..config import Config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def verify_token(token: str, secret: str) -> tuple:
    """
    수신거부 토큰 검증

    Args:
        token: Base64 인코딩된 토큰
        secret: 시크릿 키

    Returns:
        (유효 여부, 이메일 주소)
    """
    from ..unsubscribe_token import verify_token as verify_token_impl
    return verify_token_impl(token, secret)


def handler(event, context):
    """
    수신거부 Lambda 핸들러

    Args:
        event: API Gateway 이벤트
        context: Lambda 컨텍스트

    Returns:
        API Gateway 응답
    """
    logger.info(f"수신거부 요청: {json.dumps(event)}")

    # CORS 헤더
    headers = {
        "Content-Type": "text/html; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET,OPTIONS"
    }

    # OPTIONS 요청 처리 (CORS preflight)
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": headers,
            "body": ""
        }

    try:
        # 쿼리 파라미터에서 토큰 추출
        query_params = event.get("queryStringParameters") or {}
        token = query_params.get("token")

        if not token:
            logger.warning("토큰 없음")
            return {
                "statusCode": 400,
                "headers": headers,
                "body": create_error_page("잘못된 요청입니다.")
            }

        # 시크릿 키 가져오기
        secret = os.getenv("UNSUBSCRIBE_SECRET", "etnews-unsubscribe-secret-2026")

        # 토큰 검증
        is_valid, email = verify_token(token, secret)

        if not is_valid:
            logger.warning("토큰 검증 실패")
            return {
                "statusCode": 400,
                "headers": headers,
                "body": create_error_page("유효하지 않은 링크입니다.")
            }

        # 수신거부 처리 (목록에서 완전 삭제)
        from ..recipients.recipient_manager import RecipientManager

        manager = RecipientManager()
        success = manager.delete_recipient(email)

        if success:
            logger.info(f"수신거부 처리 완료: {email}")
            return {
                "statusCode": 200,
                "headers": headers,
                "body": create_success_page(email)
            }
        else:
            logger.error(f"수신거부 처리 실패: {email}")
            return {
                "statusCode": 500,
                "headers": headers,
                "body": create_error_page("수신거부 처리 중 오류가 발생했습니다.")
            }

    except Exception as e:
        logger.error(f"수신거부 핸들러 오류: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": headers,
            "body": create_error_page("서버 오류가 발생했습니다.")
        }


def create_success_page(email: str) -> str:
    """수신거부 완료 페이지 생성"""
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>수신거부 완료</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                text-align: center;
            }}
            .success {{
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
                border-radius: 4px;
                padding: 20px;
                margin-bottom: 20px;
            }}
            h1 {{
                font-size: 24px;
                margin-bottom: 10px;
            }}
            p {{
                line-height: 1.6;
                color: #666;
            }}
            .email {{
                font-weight: bold;
                color: #333;
            }}
        </style>
    </head>
    <body>
        <div class="success">
            <h1>✓ 수신거부가 완료되었습니다</h1>
            <p class="email">{email}</p>
        </div>
        <p>IT뉴스 PDF 뉴스레터 수신이 중단되었습니다.</p>
        <p>다시 수신을 원하시면 {Config.ADMIN_EMAIL}으로 연락주세요.</p>
    </body>
    </html>
    """


def create_error_page(message: str) -> str:
    """오류 페이지 생성"""
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>오류</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                text-align: center;
            }}
            .error {{
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
                border-radius: 4px;
                padding: 20px;
                margin-bottom: 20px;
            }}
            h1 {{
                font-size: 24px;
                margin-bottom: 10px;
            }}
            p {{
                line-height: 1.6;
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="error">
            <h1>✗ 오류</h1>
            <p>{message}</p>
        </div>
        <p>문제가 계속되면 {Config.ADMIN_EMAIL}으로 연락주세요.</p>
    </body>
    </html>
    """


if __name__ == "__main__":
    # 로컬 테스트
    test_event = {
        "httpMethod": "GET",
        "queryStringParameters": {
            "token": "test-token"
        }
    }
    result = handler(test_event, None)
    print(json.dumps(result, indent=2))
