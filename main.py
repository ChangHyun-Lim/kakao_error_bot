from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import re
import os
import traceback

app = FastAPI()

EXCEL_PATH = "wtr_Error_Code.xlsx"
last_modified = None
df = None


def load_excel():
    global df, last_modified

    print("🔍 [load_excel] 시작")

    try:
        if not os.path.exists(EXCEL_PATH):
            print(f"❌ Excel 파일 없음: {EXCEL_PATH}")
        else:
            print(f"📂 Excel 파일 발견: {EXCEL_PATH}")

        mtime = os.path.getmtime(EXCEL_PATH)
        print(f"📄 Excel mtime: {mtime}")

        if last_modified is None or mtime != last_modified:
            print("[INFO] Excel 변경 감지됨 → 재로드 실행")
            df = pd.read_excel(EXCEL_PATH)
            df["code_num"] = pd.to_numeric(df["code"], errors="coerce")
            last_modified = mtime
            print(f"✅ Excel 로드 성공, row 수: {len(df)}")
        else:
            print("➡ Excel 변경 없음, 기존 df 사용")

    except Exception as e:
        print("❌ Excel 로드 중 오류 발생:")
        print(traceback.format_exc())


load_excel()


class KakaoRequest(BaseModel):
    userRequest: dict
    action: dict


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
    if df is None:
        print("❌ generate_candidates: df is None!!")
        return []

    cands = set()
    cands.add(input_code)
    cands.add(map_code(input_code))

    for v in df["code_num"].dropna().astype(int).tolist():
        if map_code(v) == input_code:
            cands.add(v)

    print(f"🧩 후보 코드: {cands}")
    return list(cands)


@app.get("/test")
def test_error(code: int):
    print(f"🔍 /test 호출됨 → code={code}")
    load_excel()

    if df is None:
        return {"error": "df is None → Excel 로드 실패"}

    input_code = code
    candidates = generate_candidates(input_code)

    subset = df[df["code_num"].astype('Int64').isin(candidates)]

    if len(subset) == 0:
        print("❌ 검색 결과 없음")
        return {
            "input_code": input_code,
            "candidates": candidates,
            "found": False,
            "message": "해당 코드 정보 없음"
        }

    row = subset.iloc[0]
    print("✅ 검색 성공")
    return {
        "input_code": input_code,
        "candidates": candidates,
        "found": True,
        "code": str(row["code"]),
        "err_name": str(row["err_name"]),
        "desc": str(row["desc"])
    }


@app.post("/kakao/skill")
def kakao_skill(request: KakaoRequest):
    print("🟣 카카오 skill 호출됨")
    load_excel()

    if df is None:
        return simple_text("❌ Excel 로딩 실패")

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
