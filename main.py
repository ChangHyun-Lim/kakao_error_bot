from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import re
import os
import threading
import time
import requests

app = FastAPI()

# -----------------------------
# 0) Health check
# -----------------------------
@app.get("/health")
def health():
    return {"status": "alive"}

# -----------------------------
# 🚀 1) Keep-Alive (자동 자기 호출)
# -----------------------------
def keep_alive():
    """
    Railway 무료 플랜이 서버를 Sleep하지 않도록
    10초마다 자기 자신을 /health 로 호출하는 함수.
    """
    while True:
        try:
            url = f"http://127.0.0.1:{PORT}/health"
            requests.get(url, timeout=3)
        except Exception:
            pass
        time.sleep(10)  # 10초마다 ping


# -----------------------------
# 2) Excel 로딩 (초기 1회)
# -----------------------------
EXCEL_PATH = "wtr_Error_Code.xlsx"
df = None

def load_excel_first():
    global df
    print("[INFO] Excel 최초 로드 시작!")
    df = pd.read_excel(EXCEL_PATH)
    df["code_num"] = pd.to_numeric(df["code"], errors="coerce")
    print("[INFO] Excel 최초 로드 완료!")

load_excel_first()


# -----------------------------
# 3) Kakao Request Model
# -----------------------------
class KakaoRequest(BaseModel):
    userRequest: dict
    action: dict


# -----------------------------
# 4) 코드 매핑
# -----------------------------
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


def generate_candidates(input_code: int):
    cands = {input_code, map_code(input_code)}

    for v in df["code_num"].dropna().astype(int).tolist():
        if map_code(v) == input_code:
            cands.add(v)

    return list(cands)


# -----------------------------
# 5) TEST API
# -----------------------------
@app.get("/test")
def test(code: int):
    if df is None:
        return {"error": "Excel 데이터가 로드되지 않았습니다."}

    candidates = generate_candidates(code)
    subset = df[df["code_num"].astype('Int64').isin(candidates)]

    if len(subset) == 0:
        return {
            "input_code": code,
            "candidates": candidates,
            "found": False,
            "message": "해당 코드 정보 없음"
        }

    row = subset.iloc[0]

    return {
        "input_code": code,
        "candidates": candidates,
        "found": True,
        "code": str(row["code"]),
        "err_name": str(row["err_name"]),
        "desc": str(row["desc"])
    }


# -----------------------------
# 6) 카카오 스킬 API
# -----------------------------
@app.post("/kakao/skill")
def kakao_skill(request: KakaoRequest):
    if df is None:
        return simple_text("❗ Excel 데이터가 로드되지 않았습니다.")

    utter = request.userRequest.get("utterance", "")
    match = re.findall(r"-?\d+", utter)

    if not match:
        return simple_text("❗ 숫자 코드가 포함되지 않았습니다.\n예) /w 1001")

    input_code = int(match[0])
    candidates = generate_candidates(input_code)
    subset = df[df["code_num"].astype('Int64').isin(candidates)]

    if len(subset) == 0:
        return simple_text(f"❗ 코드 {input_code} 관련 정보를 찾을 수 없습니다.")

    row = subset.iloc[0]
    msg = f"[Error {row['code']}]\n{row['err_name']}\n\n{row['desc']}"

    return simple_text(msg)


# -----------------------------
# 7) simpleText
# -----------------------------
def simple_text(text: str):
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {"simpleText": {"text": text}}
            ]
        }
    }


# -----------------------------
# 8) favicon (502 방지)
# -----------------------------
@app.get("/favicon.ico")
def favicon():
    return {}


# -----------------------------
# 9) 서버 실행 (Keep-Alive 스레드 포함)
# -----------------------------
if __name__ == "__main__":
    import uvicorn

    PORT = int(os.getenv("PORT", 8080))

    # 🔥 Keep-alive thread 시작
    threading.Thread(target=keep_alive, daemon=True).start()

    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
