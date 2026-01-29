from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import re, os, threading, time, requests
import math

def safe_str(value):
    """
    NaN / None 을 항상 안전한 문자열로 변환
    """
    if value is None:
        return ""
    # pandas / numpy NaN 처리
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    # float NaN 직접 체크
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)

app = FastAPI()

#============================================================
#  GitHub 파일 URL (첨부파일용)
#============================================================
GITHUB_USER = "ChangHyun-Lim"
REPO_NAME   = "kakao_error_bot"
BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/main/files/"

#============================================================
# 엑셀 파일 사전 로드
#============================================================
EXCEL_FILES = {
    "w": "wtr_Error_Code.xlsx",
    "a": "aligner_Error_Code.xlsx",
    "l": "loadport_Error_Code.xlsx",
    "v": "vp_Error_Code.xlsx"
}

df_map = {}   # w/a/l → dataframe 저장


def load_excel_once():
    print("[INFO] Excel Load...")
    for key, file in EXCEL_FILES.items():
        df = pd.read_excel(file)
        df["code_str"] = df["code"].astype(str).str.upper()
        df["code_num"] = pd.to_numeric(df["code"], errors="ignore")
        df["attach"] = df["attach"].astype(str).str.strip()
        df["attach"] = df["attach"].replace({"nan": ""})
        df_map[key] = df
        print(f"[INFO] Loaded {file}")
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
                r = requests.get(url, timeout=3)
                print("[KEEP-ALIVE]", r.status_code)
            except:
                print("[KEEP-ALIVE] Error")
            time.sleep(15)

    threading.Thread(target=ping, daemon=True).start()


#============================================================
@app.get("/health")
def health():
    return {"status": "alive"}

@app.get("/")
def index():
    return {"status": "running"}


#============================================================
# 요청 모델
#============================================================
class KakaoRequest(BaseModel):
    userRequest: dict
    action: dict


#============================================================
# WTR 전용 코드 역변환
#============================================================
def map_wtr(code: int):
    if 300 <= code <= 400:
        return code + 700

    if 400 <= code <= 500:
        return code + 1600

    if 300 <= code <= 330:
        return -(code - 300)

    if 230 <= code <= 260:
        return -(code - 230)

    if 60 <= code <= 100:
        return -(code - 60)

    if 590 <= code <= 709:
        return -(code + 110)

    if 710 <= code <= 760:
        return -(code + 290)

    if 770 <= code < 840:
        return -(code + 730)

    if 840 <= code < 860:
        return -(code + 760)

    if 860 <= code < 910:
        return -(code + 840)

    if 910 <= code < 930:
        return -(code + 2090)

    if 930 <= code <= 980:
        return -(code + 2170)

    return None


#============================================================
# 검색 엔진 (장비별 데이터프레임 선택)
#============================================================
def search(prefix: str, code: str):
    df = df_map[prefix]
    code = str(code).upper()

    # 문자 코드 일치 검색
    result = df[df["code_str"] == code]

    # 숫자 입력이면 역변환 적용 (WTR 전용)
    if result.empty and code.isdigit():
        num = int(code)
        if prefix == "w" \
            or prefix == "v" :       # 숫자 역변환은 WTR만 적용
            conv = map_wtr(num)
            if conv is not None:
                result = df[df["code_num"] == conv]
        else:
            # A / L 은 숫자 그대로 검색
            result = df[df["code_num"] == num]

    return None if result.empty else result.iloc[0]


#============================================================
# 응답 생성
#============================================================
def card_reply(title, desc, attach):
    # NaN / None 방지
    title = safe_str(title)
    desc = safe_str(desc)
    attach = safe_str(attach).strip()

    if not attach:
        return text_reply(f"{title}\n\n{desc}\n\n📎 첨부파일 없음")

    # "a.png, b.pdf" 처럼 쉼표로 구분된 여러 파일 처리
    files = [x.strip() for x in attach.split(",") if x.strip()]

    if not files:
        return text_reply(f"{title}\n\n{desc}\n\n📎 첨부파일 없음")

    # Kakao basicCard 버튼: 최대 3개
    buttons = []
    for fname in files[:3]:
        buttons.append({
            "label": f"📄 {fname}",
            "action": "webLink",
            "webLinkUrl": BASE_URL + fname
        })

    return {
        "version": "2.0",
        "template": {
            "outputs": [{
                "basicCard": {
                    "title": title,
                    "description": desc,
                    "thumbnail": {
                        # 첫 번째 파일을 썸네일로 사용
                        "imageUrl": BASE_URL + files[0]
                    },
                    "buttons": buttons
                }
            }]
        }
    }



def text_reply(msg):
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": msg}}]
        }
    }


#============================================================
# Kakao Skill 엔드포인트
#============================================================
@app.post("/kakao/skill")
def kakao_skill(request: KakaoRequest):

    utter = request.userRequest.get("utterance", "").strip()

    m = re.match(r"/([walv])\s+(.+)", utter, re.IGNORECASE)
    if not m:
        return text_reply("❗ 명령어 형식 오류\n예) /w 865  /a 001  /l 10 /v 405")

    prefix = m.group(1).lower()
    code    = m.group(2).strip()

    row = search(prefix, code)

    if row is None:
        return text_reply(f"❗ '{code}' 관련 정보가 없습니다.")
    
    desc = safe_str(row.get("desc", ""))
    attach = safe_str(row.get("attach", "")).strip()
    code_str = safe_str(row.get("code", ""))        # 숫자라도 문자열로
    err_name = safe_str(row.get("err_name", ""))
    
    title = f"{prefix.upper()} ERROR {code_str}"
    
    if attach:
        return card_reply(title, desc, attach)
    
    return text_reply(f"[{title}]\n{err_name}\n\n{desc}\n📎 첨부 없음")
