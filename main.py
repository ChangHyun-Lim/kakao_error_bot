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
    "w": "wtr_Error_Code.xlsx",        # 로봇(WTR)
    "a": "aligner_Error_Code.xlsx",
    "l": "loadport_Error_Code.xlsx",
}

# Excel 데이터 저장용 (prefix → DataFrame)
excel_data = {}


# ----------------------------------------
# map_code (로봇 전용)
# ----------------------------------------
def map_code(o: int) -> int:
    if 1000 <= o <= 1100:
        return o - 700
    elif 2000 < o < 2100:
        return o - 1600
    elif -230 < o <= -200:
        return (-o) + 300
    elif -330 < o <= -300:
        return (-o) + 230
    elif -530 < o <= -500:
        return (-o) + 60
    elif -820 < o <= -700:
        return (-o) - 110
    elif -1060 < o <= -1000:
        return (-o) - 290
    elif -1570 < o <= -1500:
        return (-o) - 730
    elif -1620 < o <= -1600:
        return (-o) - 760
    elif -1750 < o <= -1700:
        return (-o) - 840
    elif -3020 < o <= -3000:
        return (-o) - 2090
    elif -3150 < o <= -3100:
        return (-o) - 2170
    else:
        return o


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
# Startup 시 자동 실행
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


@app.get("/health")
def health():
    return {"status": "alive"}


@app.get("/")
def root():
    return {"status": "ok"}


# ----------------------------------------
# 카카오 스킬 요청 모델
# ----------------------------------------
class KakaoRequest(BaseModel):
    userRequest: dict
    action: dict


# ----------------------------------------
# 에러코드 검색 함수
# ----------------------------------------
def search_error(prefix: str, input_code: str):
    """prefix(a/w/l) + 입력된 코드로 검색"""

    if prefix not in excel_data:
        return None, "❗ prefix 오류 (/w, /a, /l 중 선택)"

    df = excel_data[prefix]

    # 문자 검색 (E02, L05 등)
    code_upper = input_code.upper()
    subset = df[df["code_str"] == code_upper]

    # 숫자 처리
    try:
        input_num = int(input_code)

        # 로봇(/w) 만 map_code 변환 적용
        if prefix == "w":
            mapped = map_code(input_num)

            # 1차: 변환된 숫자로 검색
            subset = pd.concat([
                subset,
                df[df["code_num"] == mapped]
            ])

        # 2차: 원본 숫자 그대로 검색
        subset = pd.concat([
            subset,
            df[df["code_num"] == input_num]
        ])

    except:
        pass

    # 최종 결과
    if len(subset) == 0:
        return None, f"❗ 코드 '{input_code}' 관련 정보를 찾을 수 없습니다."

    return subset.iloc[0], None


# ----------------------------------------
# GET 테스트 API
# ----------------------------------------
@app.get("/test")
def test(prefix: str, code: str):
    row, err = search_error(prefix, code)
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
        return simple_text("❗ 형식 오류\n예) /w 865   /w E02   /a 001   /l L02")

    prefix = m.group(1).lower()
    code = m.group(2).strip()

    row, err = search_error(prefix, code)
    if err:
        return simple_text(err)

    msg = f"[{prefix.upper()} Error {row['code']}]\n{row['err_name']}\n\n{row['desc']}"
    return simple_text(msg)


# ----------------------------------------
def simple_text(text: str):
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}]
        }
    }


@app.get("/favicon.ico")
def favicon():
    return {}
