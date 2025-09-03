# app.py
import os
import io
import zipfile
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import streamlit as st
import core as core  # 같은 폴더의 core.py

# ──────────────────────────────────────────────────────────────
# 페이지 설정
# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="DART 조회 도구", layout="wide")

# 서버 비밀/환경변수에서 DART API Key 읽기 (내재화)
def _read_dart_key():
    try:
        return st.secrets.get("DART_API_KEY", "")
    except Exception:
        return os.getenv("DART_API_KEY", "") or ""

DEFAULT_DART_KEY = _read_dart_key()

# core.py에 주입 함수가 있으면 전달 (없으면 무시)
if hasattr(core, "set_api_key"):
    try:
        core.set_api_key(DEFAULT_DART_KEY)
    except Exception:
        pass

# ──────────────────────────────────────────────────────────────
# 선택된 회사 배너(있을 때만) → 제목 위 표시
# ──────────────────────────────────────────────────────────────
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

# ──────────────────────────────────────────────────────────────
# corpCode.xml → DataFrame 로더 (DART 키 필요)
# ──────────────────────────────────────────────────────────────
@st.cache_resource
def load_codes(dart_key: str) -> pd.DataFrame:
    if not dart_key:
        raise RuntimeError("DART API Key가 서버에 설정되어 있지 않습니다.")
    url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={dart_key}"
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

# ──────────────────────────────────────────────────────────────
# 쿼리 실행 (캐시)
# ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=600)
def run_query(task, corp_code, year_from=None, year_to=None):
    # core 모듈 함수 호출
    if task == "기업개황":
        return core.CorpInfo.get_corp_info(corp_code)
    elif task == "최대주주 변동현황":
        return core.Shareholders.get_major_shareholders(corp_code, years=range(year_from, year_to + 1))
    elif task == "임원현황(최신)":
        return core.Execturives.get_execturives(corp_code, years=range(year_from, year_to + 1))
    elif task == "임원 주식소유":
        return core.Execturives.get_executive_shareholdings(corp_code)
    elif task == "전환사채(의사결정)":
        return core.ConvertBond.get_convert_bond(corp_code)
    elif task == "소송현황":
        # 병합 통합 함수가 있으면 우선 사용
        if hasattr(core, "Lawsuits") and hasattr(core.Lawsuits, "get_lawsuits_merged"):
            return core.Lawsuits.get_lawsuits_merged(corp_code, "20210101", "20251231")
        # 없으면 기존 DART 전용으로 fallback
        return core.Lawsuits.get_lawsuits(corp_code, "20210101", "20251231")
    else:
        return pd.DataFrame()

# ──────────────────────────────────────────────────────────────
# 사이드바: 조회 항목 + 버튼들
# ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("설정")

    task = st.selectbox(
        "조회 항목",
        ["기업개황", "최대주주 변동현황", "임원현황(최신)", "임원 주식소유", "전환사채(의사결정)", "소송현황"]
    )
    if task in ("최대주주 변동현황", "임원현황(최신)"):
        year_from, year_to = st.slider("대상 연도 범위", 2016, 2026, (2021, 2025))
    else:
        year_from = year_to = None

    col_run, col_reset = st.columns(2)
    with col_run:
        run_clicked = st.button("조회 실행", use_container_width=True)
    with col_reset:
        reset_clicked = st.button("선택 초기화", use_container_width=True)

# 선택 초기화
if reset_clicked:
    for k in ("corp_code", "corp_name_selected", "corp_pick"):
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()

st.divider()

# ──────────────────────────────────────────────────────────────
# 회사명 검색(정확일치 우선→부분일치), 선택 후 UI 숨김
# ──────────────────────────────────────────────────────────────
corp_code = st.session_state.get("corp_code")
corp_name_selected = st.session_state.get("corp_name_selected")

df_codes = None
if DEFAULT_DART_KEY:
    try:
        df_codes = load_codes(DEFAULT_DART_KEY)
    except Exception as e:
        st.error(f"기업목록(corpCode.xml) 불러오기 실패: {e}")

if corp_code is None:
    st.subheader("🏢 회사명으로 공시코드 검색")
    corp_name_query = st.text_input("회사명(정확 또는 일부)", value="", placeholder="예: 아이큐어, 삼성전자, 현대자동차 등")

    if df_codes is not None and corp_name_query:
        q = corp_name_query.strip().lower()

        exact = df_codes[df_codes["_lc_name"] == q]
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
            choice = st.radio("사용할 회사를 선택하세요", options, index=0, key="corp_pick")
            pick_code = choice.split("(")[-1].strip(")")
            pick_name = choice.split("(")[0].strip()

            st.session_state["corp_code"] = pick_code
            st.session_state["corp_name_selected"] = pick_name
            st.rerun()

# ──────────────────────────────────────────────────────────────
# 실행: 사이드바 버튼 클릭 시
# ──────────────────────────────────────────────────────────────
if run_clicked:
    if not DEFAULT_DART_KEY:
        st.error("서버에 설정된 DART API Key가 없습니다. 관리자에게 문의하세요.")
    elif not corp_code:
        st.error("회사명(→ 공시코드 선택)을 먼저 완료하세요.")
    else:
        with st.spinner("조회 중..."):
            if task in ("최대주주 변동현황", "임원현황(최신)"):
                df = run_query(task, corp_code, year_from, year_to)
            else:
                df = run_query(task, corp_code)

        if isinstance(df, pd.DataFrame) and not df.empty:
            # 첫 컬럼명이 Unnamed로 시작하면 제거
            if len(df.columns) and str(df.columns[0]).startswith("Unnamed"):
                df = df.drop(df.columns[0], axis=1)

            # 인덱스 리셋 + UI에서 인덱스 숨김
            df = df.reset_index(drop=True)
            st.success(f"조회 완료! (총 {len(df):,} 행)")
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.download_button(
                "CSV 다운로드",
                df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"{task}_{corp_code}.csv",
                mime="text/csv",
            )

            # 소송현황 안내 문구
            if task == "소송현황":
                st.caption("※ 해당 자료는 **주요사항보고서에 기재된 소송만 표시**됩니다.")
        else:
            st.warning("조회 결과가 없습니다.")

# 하단 안내
st.caption("※ DART API Key는 서버/배포 환경에 안전하게 보관되어 자동 사용됩니다.")
