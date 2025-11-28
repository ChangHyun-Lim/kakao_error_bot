from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import re, os, threading, time, requests

app = FastAPI()

#============================================================
#  Github raw file URL 정보 입력해야 동작!!!!! <<<<<<<<<<<<<
#============================================================
GITHUB_USER = "GitHubUserName"
REPO_NAME   = "RepositoryName"

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
def map_wtr(code:int):
    mapping=[
        (1000,1100,-700),
        (2000,2100,-1600),
        (-230,-200,300),
        (-330,-300,230),
        (-530,-500,60),
        (-820,-700,-110),
        (-1060,-1000,-290),
        (-1570,-1500,-730),
        (-1620,-1600,-760),
        (-1750,-1700,-840),
        (-3020,-3000,-2090),
        (-3150,-3100,-2170)
    ]
    for a,b,off in mapping:
        if a<=code<=b: return code+(-off) if code<0 else code-off

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
def kakao_skill(req:KakaoRequest):

    query=req.userRequest.get("utterance","").strip()
    m=re.match(r"/w\s+(.+)",query,re.IGNORECASE)
    if not m: 
        return text_reply("❗ 사용법: /w 865 또는 /w ID2202")

    code=m.group(1)
    row=search(code)

    # 🔥 오류 해결 — Series 비교 금지 → None 판정만 사용
    if row is None:
        return text_reply(f"❗ '{code}' 정보 없음")

    attach = str(row.get("attach","")).strip()

    # 첨부파일 있는지 확인
    if attach and attach.lower() != "nan":
        file_url = f"{BASE_URL}{attach}"   # BASE_URL = RAW URL + /files/
        return card_reply(f"WTR Error {row['code']}", desc, attach)
    else:
        return text_reply(
            f"[WTR Error {row['code']}]\n{row['err_name']}\n\n{desc}\n\n📎 첨부파일 없음"
        )
