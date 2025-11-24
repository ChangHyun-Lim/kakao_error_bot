from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import re
import os
import threading
import time
import requests

app = FastAPI()

# ============================================
#  장비별 Excel 파일 설정 (/w, /a, /l)
# ============================================
FILE_MAP = {
    "/w": "wtr_Error_Code.xlsx",        # WTR
    "/a": "aligner_Error_Code.xlsx",    # Aligner (추가 예정)
    "/l": "loadport_Error_Code.xlsx",   # Loadport (추가 예정)
}

# prefix -> DataFrame
DATA_MAP = {}


# ============================================
#  Excel 로드 함수
# ============================================
def load_excel_file(prefix: str, path: str):
    """
    prefix: "/w", "/a", "/l"
    path  : 엑셀 파일 경로
    """
    try:
        df = pd.read_excel(path)
        # code 컬럼을 숫자로 변환해서 검색용으로 사용
        df["code_num"] = pd.to_numeric(df["code"], errors="coerce")
        DATA_MAP[prefix] = df
        print(f"[INFO] {prefix} Excel 로드 완료 → {path}")
    except Exception as e:
        # 파일이 없거나 로드 실패해도 전체 서버는 뜨도록
        DATA_MAP[prefix] = None
        print(f"[ERROR] {prefix} Excel 로드 실패 ({path}) → {e}")


def load_all_excels():
    print("[INFO] 장비별 Excel 로드 시작!")
    for prefix, path in FILE_MAP.items():
        load_excel_file(prefix, path)
    print("[INFO] 장비별 Excel 로드 시도 완료")


# ============================================
#  keep-alive 기능
# ============================================
def start_keep_alive():
    def ping():
        # 서버가 완전히 뜰 때까지 잠깐 대기
        time.sleep(5)

        port = os.getenv("PORT", "8080")
        url = f"http://0.0.0.0:{port}/health"

        while True:
            try:
                r = requests.get(url, timeout=3)
                print(f"[KEEP-ALIVE] Ping → {r.status_code}")
            except Exception as e:
                print(f"[KEEP-ALIVE] Ping Error: {e}")
            time.sleep(20)

    t = threading.Thread(target=ping, daemon=True)
    t.start()


# ============================================
#  FastAPI Startup 이벤트
# ============================================
@app.on_event("startup")
def startup_event():
    load_all_excels()
    start_keep_alive()


# ============================================
#  공통 유틸 함수들
# ============================================
def extract_prefix(utter: str):
    """
    utter 내용에서 /w, /a, /l 중 첫 번째 prefix 반환
    없으면 None
    """
    m = re.findall(r"(/w|/a|/l)", utter.lower())
    return m[0] if m else None


def get_df_by_prefix(prefix: str):
    """
    prefix로 DataFrame 반환 (/w, /a, /l)
    Excel 로드 실패했으면 None
    """
    return DATA_MAP.get(prefix)


def map_code(o: int) -> int:
    """
    기존에 사용하던 코드 매핑 규칙
    (지금은 모든 장비 공통으로 적용, 나중에 장비별로 분리 가능)
    """
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


def generate_candidates(input_code: int, df: pd.DataFrame):
    """
    - 입력 코드 그대로
    - map_code(input_code)
    - 반대로 엑셀에 있는 값 v 중 map_code(v) == input_code 인 것도 후보
    """
    if df is None:
        return []

    cands = set()
    cands.add(input_code)
    cands.add(map_code(input_code))

    for v in df["code_num"].dropna().astype(int).tolist():
        if map_code(v) == input_code:
            cands.add(v)

    return list(cands)


def simple_text(text: str):
    """
    카카오 i 오픈빌더 simpleText 응답 포맷
    """
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {"simpleText": {"text": text}}
            ]
        }
    }


# ============================================
#  Pydantic Request Model (카카오 스킬용)
# ============================================
class KakaoRequest(BaseModel):
    userRequest: dict
    action: dict


# ============================================
#  Health / Root / Favicon
# ============================================
@app.get("/health")
def health():
    return {"status": "alive"}


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/favicon.ico")
def favicon():
    # 에러 안 나게만 처리
    return {}


# ============================================
#  테스트용 GET /test  (브라우저/포스트맨 테스트)
#  예) /test?code=1001           → 기본 WTR(/w)
#      /test?code=1001&device=a  → /a (aligner)
#      /test?code=1001&device=l  → /l (loadport)
# ============================================
@app.get("/test")
def test_error(code: int, device: str = "w"):
    # device → prefix 형태로 변환
    device = device.lower()
    if not device.startswith("/"):
        prefix = "/" + device
    else:
        prefix = device

    if prefix not in FILE_MAP:
        return {
            "input_code": code,
            "device": device,
            "found": False,
            "message": f"지원하지 않는 장비 타입입니다. (사용 가능: /w, /a, /l)"
        }

    df = get_df_by_prefix(prefix)
    if df is None:
        return {
            "input_code": code,
            "device": prefix,
            "found": False,
            "message": f"{prefix} 장비의 Excel 데이터가 로드되지 않았습니다."
        }

    input_code = code
    candidates = generate_candidates(input_code, df)
    subset = df[df["code_num"].astype("Int64").isin(candidates)]

    if len(subset) == 0:
        return {
            "input_code": input_code,
            "device": prefix,
            "candidates": candidates,
            "found": False,
            "message": "해당 코드 정보 없음"
        }

    row = subset.iloc[0]
    return {
        "input_code": input_code,
        "device": prefix,
        "candidates": candidates,
        "found": True,
        "code": str(row["code"]),
        "err_name": str(row["err_name"]),
        "desc": str(row["desc"]),
    }


# ============================================
#  카카오 스킬 엔드포인트
#  예) /w 1001
#      /a 2001
#      /l -3050
# ============================================
@app.post("/kakao/skill")
def kakao_skill(request: KakaoRequest):
    # 1) 장비 prefix 추출 (/w, /a, /l)
    utter = request.userRequest.get("utterance", "")
    prefix = extract_prefix(utter)

    if prefix is None:
        return simple_text(
            "❗ 장비 구분을 찾지 못했습니다.\n"
            "예) /w 1001 (WTR)\n"
            "    /a 2001 (Aligner)\n"
            "    /l 3001 (Loadport)"
        )

    df = get_df_by_prefix(prefix)
    if df is None:
        return simple_text(f"❗ {prefix} 장비의 Excel 데이터가 로드되지 않았습니다.")

    # 2) 숫자 코드 추출
    match = re.findall(r"-?\d+", utter)
    if not match:
        return simple_text("❗ 숫자 코드가 포함되지 않았습니다.\n예) /w 1001")

    input_code = int(match[0])

    # 3) 후보 코드 생성 + 조회
    candidates = generate_candidates(input_code, df)
    subset = df[df["code_num"].astype("Int64").isin(candidates)]

    if len(subset) == 0:
        return simple_text(f"❗ {prefix} 장비의 코드 {input_code} 관련 정보를 찾을 수 없습니다.")

    row = subset.iloc[0]
    message = (
        f"[{prefix.upper()} Error {row['code']}]\n"
        f"{row['err_name']}\n\n"
        f"{row['desc']}"
    )

    return simple_text(message)
