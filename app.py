import streamlit as st
import pandas as pd
import requests, zipfile, io
import xml.etree.ElementTree as ET
import core as core  # 같은 폴더의 core.py 사용

# ──────────────────────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="DART 조회 도구", layout="wide")

# 선택된 회사 배너(있을 때만) → 제목 위에 표시
_sel_name = st.session_state.get("corp_name_selected")
_sel_code = st.session_state.get("corp_code")
if _sel_name and _sel_code:
    st.markdown(
        f"""
        <div style="
            display:inline-block;
            padding:8px 12px;
            background:rgba(16,185,129,0.15);
            border:1px solid rgba(16,185,129,0.6);
            border-radius:8px;
            font-size:0.95rem;
            margin-bottom:10px;
        ">
            ✅ <strong>{_sel_name}</strong> <span style="opacity:.85;">(공시코드: {_sel_code})</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.title("📊 DART 조회 도구")

# 세션 기본값
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
    df = pd.DataFrame(data)
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
# 사이드바 UI (API Key/조회항목/실행 & 초기화 버튼)
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

    # 버튼들
    col_run, col_reset = st.columns(2)
    with col_run:
        run_clicked = st.button("조회", use_container_width=True)
    with col_reset:
        reset_clicked = st.button("초기화", use_container_width=True)

# 초기화 동작: 선택된 회사 정보/위젯 상태 제거 후 새로고침
if reset_clicked:
    for k in ("corp_code", "corp_name_selected", "corp_pick"):
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()

st.divider()

# ──────────────────────────────────────────────────────────────────────────────
# 메인 화면: 회사명 검색 → 정확일치 우선, 그다음 부분일치
# (선택 후에는 검색 레이아웃 숨기고 상단 배너만)
# ──────────────────────────────────────────────────────────────────────────────
corp_code = st.session_state.get("corp_code", None)
corp_name_selected = st.session_state.get("corp_name_selected", None)

df_codes: pd.DataFrame | None = None
if api_key_input:
    try:
        df_codes = load_codes(api_key_input)
    except Exception as e:
        st.error(f"기업목록(corpCode.xml) 불러오기 실패: {e}")

if corp_code is None:
    st.subheader("🏢 회사명으로 공시코드 검색")
    corp_name_query = st.text_input("회사명(정확 또는 일부)", value="", placeholder="예: 아이큐어, 삼성전자, 현대자동차 등")

    if df_codes is not None and corp_name_query:
        q = corp_name_query.strip().lower()

        # 1) 정확일치
        exact = df_codes[df_codes["_lc_name"] == q]
        # 2) 부분일치(정확일치 제외)
        contains = df_codes[df_codes["_lc_name"].str.contains(q, na=False)]
        if not exact.empty:
            contains = contains[~contains.index.isin(exact.index)]

        matches = pd.concat([exact, contains], ignore_index=False)
        MAX_SHOW = 200
        matches_show = matches[["corp_name", "corp_code", "stock_code"]].head(MAX_SHOW).reset_index(drop=True)

        if matches_show.empty:
            st.warning("해당 이름을 포함/일치하는 기업이 없습니다.")
        else:
            st.caption(f"검색 결과: 정확일치 {len(exact)}건 + 부분일치 {len(contains)}건 (표시는 최대 {MAX_SHOW}건)")
            st.dataframe(matches_show, use_container_width=True, height=300)

            options = (matches_show["corp_name"] + " (" + matches_show["corp_code"] + ")").tolist()
            default_index = 0  # 정확일치가 있으면 첫 항목이 정확일치가 되도록
            if len(exact) == 1:
                default_index = 0

            choice = st.radio("사용할 회사를 선택하세요", options, index=default_index, key="corp_pick")
            corp_code = choice.split("(")[-1].strip(")")
            corp_name_selected = choice.split("(")[0].strip()

            # 선택값을 세션에 저장 → 이후 검색 UI 숨기기
            st.session_state["corp_code"] = corp_code
            st.session_state["corp_name_selected"] = corp_name_selected
            st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# 실행: 사이드바 버튼으로 트리거
# ──────────────────────────────────────────────────────────────────────────────
if run_clicked:
    api_key = api_key_input or st.session_state.get("api_key", "")

    if not api_key or not corp_code:
        st.error("API Key와 회사명(→ 공시코드 선택)을 모두 입력/선택하세요.")
    else:
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

