FROM python:3.11-slim

# Python 기본 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 캐시 무력화용 (필요하면 값만 바꿔도 빌드 강제)
ARG CACHE_BREAK=1

WORKDIR /app

# 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 엑셀 + 소스 복사
# 지금은 WTR 파일만 존재한다고 가정 (Aligner/Loadport는 나중에 추가)
COPY wtr_Error_Code.xlsx .
COPY main.py .
COPY aligner_Error_Code.xlsx .
COPY loadport_Error_Code.xlsx .

# Cloud Run / 일반 Docker 둘 다 대응 (PORT 미지정 시 8080)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]

