from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import re
import os

# -----------------------------
# 0) FastAPI 인스턴스 생성
# -----------------------------
app = FastAPI()


# -----------------------------
# 1) Excel 자동 업데이트 기능
# -----------------------------
EXCEL_PATH = "wtr_Error_Code.xlsx"
last_modified = None
df = None   # 전역 변수로 사용


def load_excel():
    global df, last_modified

    try:
        mtime = os.path.getmtime(EXCEL_PATH)
    except FileNotFoundError:
        print(f"[ERROR] Excel 파일을 찾을 수 없습니다: {EXCEL_PATH}")
        return

    if last_modified is None or mtime != last_modified:
        print("[INFO] Excel 변경 감지됨. 재로드 중...")
        df = pd.read_excel(EXCEL_PATH)
        df["code_num"] = pd.to_numeric(df["code"], errors="coerce")
        last_modified = mtime


# 서버 시작 시 최초 1회 로드
load_excel()


# -----------------------------
# 2) 카카오 요청 모델
# -----------------------------
class KakaoRequest(BaseModel):
    userRequest: dict
    action: dict


# -----------------------------
# 3) 코드 매핑 함수
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


# -----------------------------
# 4) 후보코드 생성
# -----------------------------
def generate_candidates(input_code: int):
    cands = set()

    cands.add(input_code)
    cands.add(map_code(input_code))

    for v in df["code_num"].dropna().astype(int).tolist():
        if map_code(v) == input_code:
            cands.add(v)

    return list(cands)


# -----------------------------
# 5) GET 테스트 API
# -----------------------------
@app.get("/test")
def test_error(code: int):
    load_excel()

    input_code = code
    candidates = generate_candidates(input_code)

    subset = df[df["code_num"].astype('Int64').isin(candidates)]

    if len(subset) == 0:
        return {
            "input_code": input_code,
            "candidates": candidates,
            "found": False,
            "message": "해당 코드 정보 없음"
        }

    row = subset.iloc[0]
    return {
        "input_code": input_code,
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
    load_excel()

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

    message = f"[Error {row['code']}]\n{row['err_name']}\n\n{row['desc']}"
    return simple_text(message)


# -----------------------------
# 7) 카카오 simpleText 형식
# -----------------------------
def simple_text(text: str):
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": text
                    }
                }
            ]
        }
    }


# -----------------------------
# 🔥 8) 브라우저용 favicon 요청 처리 (502 방지)
# -----------------------------
@app.get("/favicon.ico")
def favicon():
    return {}   # 항상 200 OK 반환


# -----------------------------
# 로컬 실행용
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
