"""
수신거부 Lambda 진입점 (독립 배포용)
"""
from src.api.unsubscribe_handler import handler

# Lambda가 이 파일의 handler 함수를 호출하도록 설정
