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
EXCEL_PATH = "wtr_Error_Code.xlsx"  # Railway에서 이 파일이 루트에 존재해야 함
last_modified = None
df = None   # 전역 변수


def load_excel():
    """
    Excel 파일의 변경을 감지해 자동으로 다시 로드하는 함수
    """
    global df, last_modified

    # 파일 존재 확인
    if not os.path.exists(EXCEL_PATH):
        print(f"[ERROR] Excel 파일 없음: {EXCEL_PATH}")
        df = pd.DataFrame(columns=["code", "err_name", "desc", "code_num"])
        return

    try:
        mtime = os.path.getmtime(EXCEL_PATH)
    except Exception as e:
        print(f"[ERROR] Excel 변경 시간 조회 실패: {e}")
        return

    # 최초 로드 또는 변경시 로드
    if last_modified is None or mtime != last_modified:
        print("[INFO] Excel 변경 감지됨. 재로드 중...")
        try:
            df_local = pd.read_excel(EXCEL_PATH)
            df_local["code_num"] = pd.to_numeric(df_local["code"], errors="coerce")
            df = df_local
            last_modified = mtime
        except Exception as e:
            print(f"[ERROR] Excel 로드 실패: {e}")
            df = pd.DataFrame(columns=["code", "err_name", "desc", "code_num"])


# 서버 부팅 시 1회 로드
load_excel()

# -----------------------------
# 2) 카카오 Request 모델
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
    if df is None or len(df) == 0:
        return [input_code]

    cands = set()
    cands.add(input_code)            # 입력값 그대로
    cands.add(map_code(input_code))  # 정방향 매핑

    # 역방향 매핑
    try:
        for v in df["code_num"].dropna().astype(int).tolist():
            if map_code(v) == input_code:
                cands.add(v)
    except Exception:
        pass

    return list(cands)


# -----------------------------
# 5) GET 테스트 API
# -----------------------------
@app.get("/test")
def test_error(code: int):
    load_excel()

    if df is None or len(df) == 0:
        return {
            "message": "Excel 파일이 로드되지 않았습니다.",
            "excel_path": EXCEL_PATH,
            "found": False
        }

    input_code = code
    candidates = generate_candidates(input_code)

    subset = df[df["code_num"].astype("Int64").isin(candidates)]

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

    subset = df[df["code_num"].astype("Int64").isin(candidates)]

    if len(subset) == 0:
        return simple_text(f"❗ 코드 {input_code} 관련 정보를 찾을 수 없습니다.")

    row = subset.iloc[0]

    message = f"[Error {row['code']}]\n{row['err_name']}\n\n{row['desc']}"
    return simple_text(message)


# -----------------------------
# 7) 카카오 simpleText 출력
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
# 8) 로컬 실행용 (Railway에는 영향 없음)
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
