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
        # zip 안에 들어있는 XML 파일(보통 1개)
        xml_name = zf.namelist()[0]
        xml_data = zf.read(xml_name)

    root = ET.fromstring(xml_data)
    data = []
    for child in root.findall("list"):
        data.append({
            "corp_code": child.find("corp_code").text,
            "corp_name": child.find("corp_name").text,
            "stock_code": child.find("stock_code").text,
        })
    return pd.DataFrame(data)

# ──────────────────────────────────────────────────────────────────────────────
# 쿼리 실행 (api_key를 인자로 포함 → 사용자별/키별 캐시 분리)
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=600)
def run_query(task, corp_code, api_key, year_from=None, year_to=None):
    core.api_key = api_key  # core 모듈 전역 키 주입(저장 X)
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
# 사이드바 UI
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

    # 회사명(부분 일치) 입력
    corp_name_input = st.text_input("🏢 회사명(일부 입력 가능)", value="", help="예: 아이큐어")

    task = st.selectbox(
        "조회 항목",
        ["기업개황", "최대주주 변동현황", "임원현황(최신)", "임원 주식소유", "전환사채(의사결정)"]
    )
    if task in ("최대주주 변동현황", "임원현황(최신)"):
        year_from, year_to = st.slider("대상 연도 범위", 2016, 2026, (2021, 2025))

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# corp_name → corp_code 매핑 (API 키가 있어야 corpCode.xml을 받을 수 있음)
# ──────────────────────────────────────────────────────────────────────────────
df_codes = None
corp_code = None

if api_key_input:
    try:
        df_codes = load_codes(api_key_input)
    except Exception as e:
        st.error(f"기업목록(corpCode.xml) 불러오기 실패: {e}")

# 매핑 UI는 사이드바에 표시
with st.sidebar:
    if corp_name_input and df_codes is not None:
        matches = df_codes[df_codes["corp_name"].str.contains(corp_name_input, case=False, na=False)]

        if matches.empty:
            st.info("해당 이름을 포함하는 기업이 없습니다.")
        elif len(matches) == 1:
            corp_code = matches.iloc[0]["corp_code"]
            st.caption(f"자동 선택: {matches.iloc[0]['corp_name']} → corp_code = {corp_code}")
        else:
            options = (matches["corp_name"] + " (" + matches["corp_code"] + ")").tolist()
            choice = st.selectbox("여러 기업이 검색되었습니다. 선택하세요", options)
            corp_code = choice.split("(")[-1].strip(")")

    st.text_input("선택된 공시코드", value=corp_code or "", disabled=True)

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
