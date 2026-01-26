# Playwright 공식 이미지를 기반으로 시작 (Python 3.12 포함)
FROM mcr.microsoft.com/playwright/python:v1.57.0-noble

# AWS Lambda Runtime Interface Client 설치
RUN pip3 install awslambdaric

# 작업 디렉토리 설정
WORKDIR /var/task

# requirements.txt 복사 및 의존성 설치
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY src/ ./src/
COPY lambda_handler.py .

# Lambda 런타임 엔트리포인트 설정
ENTRYPOINT [ "/usr/bin/python3", "-m", "awslambdaric" ]

# Lambda 핸들러 설정
CMD [ "lambda_handler.handler" ]
