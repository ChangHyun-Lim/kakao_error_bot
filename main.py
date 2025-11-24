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

# Excel 데이터 저장용
excel_data = {}


# ----------------------------------------
# Excel 최초 1회 로드
# ----------------------------------------
def load_all_excels():
    print("[INFO] Excel 최초 로드 시작!")

    for prefix, path in EXCEL_FILES.items():
        try:
            df = pd.read_excel(path)
            df["code_str"] = df["code"].astype(str).str.upper()   # 문자열 코드 검색 대비
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
# keep-alive 기능 (Railway sleep 방지)
# ----------------------------------------
def start_keep_alive():
    def ping():
        time.sleep(5)  # 서버 안정화 대기
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
# 카카오 스킬 요청 모델
# ----------------------------------------
class KakaoRequest(BaseModel):
    userRequest: dict
    action: dict


# ----------------------------------------
# 에러코드 검색 함수 (문자 + 숫자 모두 지원)
# ----------------------------------------
def search_error(prefix: str, input_code: str):

    if prefix not in excel_data:
        return None, "❗ prefix 오류 (/w, /a, /l 중 선택)"

    df = excel_data[prefix]

    code_upper = input_code.upper()

    # 1) 문자 코드 직접 비교 (E02 등)
    subset = df[df["code_str"] == code_upper]

    # 2) 숫자로 변환 가능하면 숫자 비교 추가
    try:
        code_int = int(input_code)
        subset = pd.concat([
            subset,
            df[df["code_num"] == code_int]
        ])
    except:
        pass  # 문자코드는 여기 안 들어옴

    if len(subset) == 0:
        return None, f"❗ 코드 '{input_code}' 관련 정보를 찾을 수 없습니다."

    row = subset.iloc[0]
    return row, None


# ----------------------------------------
# GET 테스트용 API
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

    # prefix 추출 (/w /a /l)
    m = re.match(r"/([wal])\s+(.+)", utter, re.IGNORECASE)
    if not m:
        return simple_text("❗ 형식 오류\n예) /w E02   /a 1001   /l L05")

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
