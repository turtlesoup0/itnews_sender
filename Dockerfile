# Python 3.12 slim 이미지로 시작 (경량화)
FROM python:3.12-slim

# 작업 디렉토리 설정
WORKDIR /var/task

# 시스템 의존성 설치 (Playwright Chromium용)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    && rm -rf /var/lib/apt/lists/*

# requirements.txt만 먼저 복사 (의존성 레이어 캐싱 최적화)
COPY requirements.txt .

# 의존성 설치 (코드 변경 시 이 레이어는 캐시됨)
RUN pip3 install --no-cache-dir awslambdaric && \
    pip3 install --no-cache-dir -r requirements.txt && \
    playwright install chromium

# 애플리케이션 코드 복사 (자주 변경되므로 마지막에)
COPY src/ ./src/
COPY lambda_handler.py .

# Lambda 런타임 엔트리포인트 설정
ENTRYPOINT [ "/usr/bin/python3", "-m", "awslambdaric" ]

# Lambda 핸들러 설정
CMD [ "lambda_handler.handler" ]
