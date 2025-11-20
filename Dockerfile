FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY wtr_Error_Code.xlsx .
COPY main.py .

EXPOSE 8080

CMD ["python", "main.py"]
