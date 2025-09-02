import streamlit as st
import pandas as pd
import core as core
import xml.etree.ElementTree as ET


st.set_page_config(page_title="DART 조회 도구", layout="wide")
st.title("📊 DART 조회 도구")

# --- 공시코드 테이블 로딩 ---
@st.cache_resource
def load_codes(path="corpcode/CORPCODE.xml"):
    tree = ET.parse(path)
    root = tree.getroot()
    data = []
    for child in root.findall("list"):
        data.append({
            "corp_code": child.find("corp_code").text,
            "corp_name": child.find("corp_name").text,
            "stock_code": child.find("stock_code").text,
        })
    return pd.DataFrame(data)

df_codes = load_codes()
corp_code = None  # 사명 검색 결과로 채워질 변수






# --- (선택) 브라우저 세션에만 보관하기 ---
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

with st.sidebar:
    st.subheader("설정")
    remember = st.checkbox("세션에 내 키 잠시 저장하기(브라우저 탭 닫으면 삭제)", value=False)
    api_key_input = st.text_input("🔑 DART API Key", type="password",
                                  value=st.session_state.api_key if remember else "")
    if remember:
        st.session_state.api_key = api_key_input

        corp_name = st.text_input("🏢 회사명(일부 입력 가능)", value="", help="예: 아이큐어")
    # 사명으로 corp_code 자동 매핑
    if corp_name:
        matches = df_codes[df_codes["corp_name"].str.contains(corp_name, case=False, na=False)]
        if matches.empty:
            st.info("해당 이름을 포함하는 기업이 없습니다.")
        elif len(matches) == 1:
            corp_code = matches.iloc[0]["corp_code"]
            st.caption(f"자동 선택: {matches.iloc[0]['corp_name']} → corp_code = {corp_code}")
        else:
            option = st.selectbox(
                "여러 기업이 검색되었습니다. 선택하세요",
                (matches["corp_name"] + " (" + matches["corp_code"] + ")").tolist()
            )
            corp_code = option.split("(")[-1].strip(")")
    # 선택된 공시코드 보여주기(읽기전용)
    st.text_input("선택된 공시코드", value=corp_code or "", disabled=True)
    
    task = st.selectbox(
        "조회 항목",
        ["기업개황", "최대주주 변동현황", "임원현황(최신)", "임원 주식소유", "전환사채(의사결정)"]
    )
    if task in ("최대주주 변동현황", "임원현황(최신)"):
        year_from, year_to = st.slider("대상 연도 범위", 2016, 2026, (2021, 2025))

st.divider()

# --- 캐시: api_key를 인자로 포함시켜 사용자별 호출 분리 ---
@st.cache_data(show_spinner=False, ttl=600)
def run_query(task, corp_code, api_key, year_from=None, year_to=None):
    core.api_key = api_key  # 핵심: 모듈 전역 키 주입(저장은 하지 않음)
    if task == "기업개황":
        return core.CorpInfo.get_corp_info(corp_code)
    elif task == "최대주주 변동현황":
        return core.Shareholders.get_major_shareholders(corp_code, years=range(year_from, year_to + 1))
    elif task == "임원현황(최신)":
        return core.Execturives.get_execturives(corp_code, years=range(year_from, year_to + 1))
    elif task == "임원 주식소유":
        return core.Execturives.get_executive_shareholdings(corp_code)
    else:
        return core.ConvertBond.get_convert_bond(corp_code)

# --- 실행 ---
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




