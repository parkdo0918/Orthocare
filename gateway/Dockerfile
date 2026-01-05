FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# FastAPI 및 uvicorn 설치 (게이트웨이용)
RUN pip install --no-cache-dir fastapi uvicorn python-multipart

# 공유 모듈 복사
COPY shared /app/shared

# 서비스 모듈 복사
COPY bucket_inference /app/bucket_inference
COPY exercise_recommendation /app/exercise_recommendation
COPY gateway /app/gateway

# 데이터 디렉토리는 볼륨으로 마운트
# VOLUME /app/data

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]

