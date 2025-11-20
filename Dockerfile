FROM python:3.11-slim

# 캐시 무력화용 변수 (빌드마다 값이 달라짐)
ARG CACHE_BREAK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY wtr_Error_Code.xlsx .
COPY main.py .

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
