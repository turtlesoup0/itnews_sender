# Playwright 공식 이미지를 기반으로 시작 (Python 3.12 포함)
FROM mcr.microsoft.com/playwright/python:v1.57.0-noble

# 작업 디렉토리 설정
WORKDIR /var/task

# requirements.txt만 먼저 복사 (의존성 레이어 캐싱 최적화)
COPY requirements.txt .

# 의존성 설치 (코드 변경 시 이 레이어는 캐시됨)
RUN pip3 install --no-cache-dir awslambdaric && \
    pip3 install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사 (자주 변경되므로 마지막에)
COPY src/ ./src/
COPY lambda_handler.py .

# Lambda 런타임 엔트리포인트 설정
ENTRYPOINT [ "/usr/bin/python3", "-m", "awslambdaric" ]

# Lambda 핸들러 설정
CMD [ "lambda_handler.handler" ]
