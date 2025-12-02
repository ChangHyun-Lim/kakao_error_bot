from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import re, os, threading, time, requests

app = FastAPI()

#============================================================
#  Github raw file URL 정보 입력해야 동작!!!!! <<<<<<<<<<<<<
#============================================================
GITHUB_USER = "ChangHyun-Lim"
REPO_NAME   = "kakao_error_bot"

BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/main/files/"

#============================================================
#  Excel 파일 1회 로드
#============================================================
EXCEL_FILE = "wtr_Error_Code.xlsx"
df = None

def load_excel_once():
    global df
    print("[INFO] Excel Load...")
    df = pd.read_excel(EXCEL_FILE)
    df["code_str"] = df["code"].astype(str).str.upper()
    df["code_num"] = pd.to_numeric(df["code"], errors="ignore")
    df["attach"] = df["attach"].astype(str).str.strip()
    df["attach"] = df["attach"].replace({"nan":""})   # NaN → 빈문자 처리
    print("[INFO] Excel Loaded OK")

@app.on_event("startup")
def startup_event():
    load_excel_once()
    start_keep_alive()


#============================================================
# keep-alive
#============================================================
def start_keep_alive():
    def ping():
        time.sleep(5)
        url = f"http://0.0.0.0:{os.getenv('PORT','8080')}/health"
        while True:
            try:
                r = requests.get(url,timeout=3)
                print("[KEEP-ALIVE]",r.status_code)
            except:
                print("[KEEP-ALIVE] Error")
            time.sleep(15)
    threading.Thread(target=ping,daemon=True).start()


#============================================================
@app.get("/health")
def health():
    return {"status":"alive"}

@app.get("/")
def index():
    return {"status":"running"}


#============================================================
# 요청 모델
#============================================================
class KakaoRequest(BaseModel):
    userRequest:dict
    action:dict


#============================================================
# 로봇 코드 변환
#============================================================
def map_wtr(code: int):
    """
    3자리 표시용 WTR 에러코드를 -> 원본 에러코드(4자리 또는 음수)로 역변환
    """

    # ① 1000~1100 → 300~400
    if 300 <= code <= 400:
        return code + 700

    # ② 2000~2100 → 400~500
    if 400 <= code <= 500:
        return code + 1600

    # ③ -230~-200 → 300~330
    if 300 <= code <= 330:
        return -(code - 300)

    # ④ -330~-300 → 230~260
    if 230 <= code <= 260:
        return -(code - 230)

    # ⑤ -530~-500 → 60~100
    if 60 <= code <= 100:
        return -(code - 60)

    # ⑥ -820~-700 → -110~120
    if -110 <= code <= 120:
        return -(code + 110)

    # ⑦ -1060~-1000 → 710~760
    if 710 <= code <= 760:
        return -(code + 290)

    # ⑧ -1570~-1500 → 770~840
    if 770 <= code <= 840:
        return -(code + 730)

    # ⑨ -1620~-1600 → 840~860
    if 840 <= code <= 860:
        return -(code + 760)

    # ⑩ -1750~-1700 → 860~910
    if 860 <= code <= 910:
        return -(code + 840)

    # ⑪ -3020~-3000 → 910~930
    if 910 <= code <= 930:
        return -(code + 2090)

    # ⑫ -3150~-3100 → 930~980
    if 930 <= code <= 980:
        return -(code + 2170)

    return None


#============================================================
# 검색 엔진 수정 (row 반환 방식 안정화)
#============================================================
def search(code):
    code=str(code).upper()

    # 문자 코드 비교
    result=df[df["code_str"]==code]

    # 숫자 입력 → 변환 후 재검색
    if result.empty and code.isdigit():
        conv = map_wtr(int(code))
        if conv:
            result = df[df["code_num"]==conv]

    return None if result.empty else result.iloc[0]   # << row가 정확히 1행 반환됨



#============================================================
# 카카오 응답
#============================================================
def card_reply(title, desc, attach):

    # 첨부 없을 경우 → text로 대체
    if attach is None or attach.strip() == "":
        return text_reply(f"{title}\n\n{desc}\n\n📎 첨부파일 없음")

    return {
        "version":"2.0",
        "template":{
            "outputs":[{
                "basicCard":{
                    "title":title,
                    "description":desc,
                    "thumbnail":{
                        "imageUrl":BASE_URL+attach
                    },
                    "buttons":[
                        {
                            "label":"📄 다운로드",
                            "action":"webLink",
                            "webLinkUrl":BASE_URL+attach
                        }
                    ]
                }
            }]
        }
    }


def text_reply(msg):
    return {
        "version":"2.0",
        "template":{
            "outputs":[{"simpleText":{"text":msg}}]
        }
    }


#============================================================
# Kakao Skill 수정 (오류 해결)
#============================================================
@app.post("/kakao/skill")
def kakao_skill(request: KakaoRequest):

    utter = request.userRequest.get("utterance","").strip()
    m = re.match(r"/([wal])\s+(.+)", utter, re.IGNORECASE)
    if not m:
        return text_reply("❗ 명령어 형식 오류\n예) /w 865  /a E02  /l 10")

    prefix = m.group(1).lower()
    code    = m.group(2).strip()

    # 🔥 search_error -> search 로 변경
    row = search(code)

    if row is None:
        return text_reply(f"❗ '{code}' 관련 정보가 없습니다.")

    desc = row["desc"]
    attach = row.get("attach","").strip()

    if attach:
        return card_reply(f"{prefix.upper()} ERROR {row['code']}", desc, attach)

    return text_reply(
        f"[{prefix.upper()} ERROR {row['code']}]\n{row['err_name']}\n\n{desc}\n📎 첨부 없음"
    )

