import streamlit as st
import pandas as pd
import requests, zipfile, io
import xml.etree.ElementTree as ET
import core as core  # 같은 폴더의 core.py 사용

# ──────────────────────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="DART 조회 도구", layout="wide")
st.title("📊 DART 조회 도구")

# (선택) 브라우저 세션에만 키 저장
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

# ──────────────────────────────────────────────────────────────────────────────
# corpCode.xml → DataFrame 로더 (API 키로 실시간 다운로드)
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def load_codes(api_key: str) -> pd.DataFrame:
    """OpenDART corpCode.zip을 내려받아 기업목록 DataFrame 반환"""
    url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={api_key}"
    res = requests.get(url, timeout=30)
    res.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        xml_name = zf.namelist()[0]  # 보통 1개
        xml_data = zf.read(xml_name)

    root = ET.fromstring(xml_data)
    data = []
    for child in root.findall("list"):
        data.append({
            "corp_code": child.find("corp_code").text,
            "corp_name": child.find("corp_name").text,
            "stock_code": child.find("stock_code").text,
        })
    df = pd.DataFrame(data)
    # 검색 속도 향상을 위해 소문자 컬럼 추가 (내부용)
    df["_lc_name"] = df["corp_name"].str.lower()
    return df

# ──────────────────────────────────────────────────────────────────────────────
# 쿼리 실행 (api_key를 인자로 포함 → 사용자별/키별 캐시 분리)
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=600)
def run_query(task, corp_code, api_key, year_from=None, year_to=None):
    core.api_key = api_key  # core 모듈 전역 키 주입(서버 저장 X)
    if task == "기업개황":
        return core.CorpInfo.get_corp_info(corp_code)
    elif task == "최대주주 변동현황":
        return core.Shareholders.get_major_shareholders(corp_code, years=range(year_from, year_to + 1))
    elif task == "임원현황(최신)":
        return core.Execturives.get_execturives(corp_code, years=range(year_from, year_to + 1))
    elif task == "임원 주식소유":
        return core.Execturives.get_executive_shareholdings(corp_code)
    else:  # 전환사채(의사결정)
        return core.ConvertBond.get_convert_bond(corp_code)

# ──────────────────────────────────────────────────────────────────────────────
# 사이드바 UI (API Key/조회항목)
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("설정")

    remember = st.checkbox("세션에 내 키 잠시 저장하기(탭 닫으면 삭제)", value=False)
    api_key_input = st.text_input(
        "🔑 DART API Key",
        type="password",
        value=st.session_state.api_key if remember else "",
        help="오픈DART에서 발급받은 개인 API 키"
    )
    if remember:
        st.session_state.api_key = api_key_input

    task = st.selectbox(
        "조회 항목",
        ["기업개황", "최대주주 변동현황", "임원현황(최신)", "임원 주식소유", "전환사채(의사결정)"]
    )
    if task in ("최대주주 변동현황", "임원현황(최신)"):
        year_from, year_to = st.slider("대상 연도 범위", 2016, 2026, (2021, 2025))

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# 메인 화면: 회사명 검색 → 정확일치 우선, 그다음 부분일치
# ──────────────────────────────────────────────────────────────────────────────
st.subheader("🏢 회사명으로 공시코드 검색")

df_codes: pd.DataFrame | None = None
corp_code: str | None = None

if not api_key_input:
    st.info("먼저 왼쪽 사이드바에 DART API Key를 입력하세요.")
else:
    try:
        df_codes = load_codes(api_key_input)
    except Exception as e:
        st.error(f"기업목록(corpCode.xml) 불러오기 실패: {e}")

# 검색 입력
corp_name_query = st.text_input("회사명(정확 또는 일부)", value="", placeholder="예: 아이큐어, 삼성전자, 현대자동차 등")

if df_codes is not None and corp_name_query:
    q = corp_name_query.strip().lower()

    # 1) 정확일치
    exact = df_codes[df_codes["_lc_name"] == q]

    # 2) 부분일치(정확일치 제외)
    contains = df_codes[df_codes["_lc_name"].str.contains(q, na=False)]
    if not exact.empty:
        contains = contains[~contains.index.isin(exact.index)]

    # 합치기: 정확일치 → 부분일치
    matches = pd.concat([exact, contains], ignore_index=False)
    # 너무 많을 때 UI 과부화 방지 (원하면 조정)
    MAX_SHOW = 200
    matches_show = matches[["corp_name", "corp_code", "stock_code"]].head(MAX_SHOW).reset_index(drop=True)

    if matches_show.empty:
        st.warning("해당 이름을 포함/일치하는 기업이 없습니다.")
    else:
        st.caption(f"검색 결과: 정확일치 {len(exact)}건 + 부분일치 {len(contains)}건 (표시는 최대 {MAX_SHOW}건)")
        st.dataframe(matches_show, use_container_width=True, height=300)

        # 선택 위젯
        options = (matches_show["corp_name"] + " (" + matches_show["corp_code"] + ")").tolist()

        # 정확일치가 1건이면 그걸 기본 선택
        default_index = 0
        if len(exact) == 1:
            # matches_show는 exact가 앞에 오므로 index=0이 정확일치가 됨
            default_index = 0

        choice = st.radio("사용할 회사를 선택하세요", options, index=default_index, key="corp_pick")
        corp_code = choice.split("(")[-1].strip(")")
        st.success(f"선택된 공시코드: {corp_code}")

# ──────────────────────────────────────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────────────────────────────────────
if st.button("조회 실행"):
    api_key = api_key_input or st.session_state.get("api_key", "")

    if not api_key or not corp_code:
        st.error("API Key와 회사명(→ 공시코드 선택)을 모두 입력/선택하세요.")
        st.stop()

    with st.spinner("조회 중..."):
        if task in ("최대주주 변동현황", "임원현황(최신)"):
            df = run_query(task, corp_code, api_key, year_from, year_to)
        else:
            df = run_query(task, corp_code, api_key)

    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        st.warning("조회 결과가 없습니다.")
    else:
        st.success(f"조회 완료! (총 {len(df):,} 행)")
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "CSV 다운로드",
            df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{task}_{corp_code}.csv",
            mime="text/csv",
        )

st.caption("※ 각 사용자는 본인 오픈DART API Key를 입력해서 사용합니다. 데이터: 금융감독원 OpenDART API")
