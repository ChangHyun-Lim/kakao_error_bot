from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import re
import threading
import time
import requests
import os

app = FastAPI()

# ----------------------------------------
# Excel 파일 경로 (3종류)
# ----------------------------------------
EXCEL_FILES = {
    "w": "wtr_Error_Code.xlsx",
    "a": "aligner_Error_Code.xlsx",
    "l": "loadport_Error_Code.xlsx",
}

excel_data = {}

# ----------------------------------------
# WTR 전용 코드 변환 함수
# ----------------------------------------
def map_code(num: int) -> int:
    if 1000 <= num <= 1100:
        return num - 700
    elif 2000 < num < 2100:
        return num - 1600
    elif -230 < num <= -200:
        return (-num) + 300
    elif -330 < num <= -300:
        return (-num) + 230
    elif -530 < num <= -500:
        return (-num) + 60
    elif -820 < num <= -700:
        return (-num) - 110
    elif -1060 < num <= -1000:
        return (-num) - 290
    elif -1570 < num <= -1500:
        return (-num) - 730
    elif -1620 < num <= -1600:
        return (-num) - 760
    elif -1750 < num <= -1700:
        return (-num) - 840
    elif -3020 < num <= -3000:
        return (-num) - 2090
    elif -3150 < num <= -3100:
        return (-num) - 2170
    else:
        return num

# ----------------------------------------
# Excel 최초 1회 로드
# ----------------------------------------
def load_all_excels():
    print("[INFO] Excel 최초 로드 시작!")

    for prefix, path in EXCEL_FILES.items():
        try:
            df = pd.read_excel(path)
            df["code_str"] = df["code"].astype(str).str.upper()
            df["code_num"] = pd.to_numeric(df["code"], errors="coerce")
            excel_data[prefix] = df
            print(f"[INFO] {prefix} → '{path}' 로드 완료 (rows={len(df)})")
        except Exception as e:
            print(f"[ERROR] {path} 로드 실패: {e}")

    print("[INFO] Excel 최초 로드 완료!")

# ----------------------------------------
# 서버 시작 시 자동 실행
# ----------------------------------------
@app.on_event("startup")
def startup_event():
    load_all_excels()
    start_keep_alive()

# ----------------------------------------
# keep-alive (Railway sleep 방지)
# ----------------------------------------
def start_keep_alive():
    def ping():
        time.sleep(5)
        while True:
            try:
                url = f"http://0.0.0.0:{os.getenv('PORT','8080')}/health"
                r = requests.get(url, timeout=3)
                print(f"[KEEP-ALIVE] Ping → {r.status_code}")
            except Exception as e:
                print(f"[KEEP-ALIVE] Error: {e}")
            time.sleep(20)

    threading.Thread(target=ping, daemon=True).start()

# ----------------------------------------
@app.get("/health")
def health():
    return {"status": "alive"}

@app.get("/")
def root():
    return {"status": "ok"}

# ----------------------------------------
# 카카오 요청 모델
# ----------------------------------------
class KakaoRequest(BaseModel):
    userRequest: dict
    action: dict

# ----------------------------------------
# WTR 전용 검색 (map_code 포함)
# ----------------------------------------
def search_wtr(df, input_code: str):
    input_upper = input_code.upper()

    # 숫자인 경우
    if input_upper.isdigit() or (input_upper.startswith("-") and input_upper[1:].isdigit()):
        original_num = int(input_upper)
        mapped_num = map_code(original_num)

        # 1) 변환된 코드 검색
        sub = df[df["code_num"] == mapped_num]
        if len(sub) > 0:
            return sub.iloc[0], None

        # 2) 원본 코드 검색
        sub = df[df["code_num"] == original_num]
        if len(sub) > 0:
            return sub.iloc[0], None

        return None, f"❗ 코드 '{input_code}' 관련 정보를 찾을 수 없습니다."

    # 문자코드(E02 등)
    sub = df[df["code_str"] == input_upper]
    if len(sub) > 0:
        return sub.iloc[0], None

    return None, f"❗ 코드 '{input_code}' 관련 정보를 찾을 수 없습니다."

# ----------------------------------------
# Aligner, Loadport 검색 (변환 없음)
# ----------------------------------------
def search_simple(df, input_code: str):
    input_upper = input_code.upper()

    # 문자코드
    sub = df[df["code_str"] == input_upper]
    if len(sub) > 0:
        return sub.iloc[0], None

    # 숫자코드
    try:
        num = int(input_upper)
        sub = df[df["code_num"] == num]
        if len(sub) > 0:
            return sub.iloc[0], None
    except:
        pass

    return None, f"❗ 코드 '{input_code}' 관련 정보를 찾을 수 없습니다."

# ----------------------------------------
# GET 테스트용 API
# ----------------------------------------
@app.get("/test")
def test(prefix: str, code: str):
    df = excel_data.get(prefix)
    if df is None:
        return {"error": "prefix 오류 (/w /a /l)"}

    if prefix == "w":
        row, err = search_wtr(df, code)
    else:
        row, err = search_simple(df, code)

    if err:
        return {"error": err}

    return {
        "prefix": prefix,
        "code": row["code"],
        "err_name": row["err_name"],
        "desc": row["desc"],
    }

# ----------------------------------------
# 카카오 스킬 API
# ----------------------------------------
@app.post("/kakao/skill")
def kakao_skill(request: KakaoRequest):

    utter = request.userRequest.get("utterance", "").strip()

    m = re.match(r"/([wal])\s+(.+)", utter, re.IGNORECASE)
    if not m:
        return simple_text("❗ 형식 오류\n예) /w E02   /a 1001   /l L05")

    prefix = m.group(1).lower()
    code = m.group(2).strip()

    df = excel_data.get(prefix)
    if df is None:
        return simple_text("❗ prefix 오류 (/w, /a, /l 중 선택)")

    # WTR → 변환 적용
    if prefix == "w":
        row, err = search_wtr(df, code)
    else:
        row, err = search_simple(df, code)

    if err:
        return simple_text(err)

    msg = f"[{prefix.upper()} Error {row['code']}]\n{row['err_name']}\n\n{row['desc']}"
    return simple_text(msg)

# ----------------------------------------
def simple_text(text: str):
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]}
    }

# favicon 처리
@app.get("/favicon.ico")
def favicon():
    return {}
