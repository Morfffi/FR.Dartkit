import os
import requests
import pandas as pd
import numpy as np

try:
    import streamlit as st
    _DART_KEY_FROM_SECRETS = st.secrets.get("DART_API_KEY", "")
except Exception:
    _DART_KEY_FROM_SECRETS = ""

api_key = _DART_KEY_FROM_SECRETS or os.getenv("DART_API_KEY", "")

def set_api_key(k: str | None):
    """(옵션) 앱에서 키를 주입하고 싶을 때 사용. 내재화만 쓰면 호출 안해도 됨."""
    global api_key
    api_key = (k or "").strip()

def get_json(url, params=None, timeout=30):
    try:
        res = requests.get(url, params=params, timeout=timeout)
        res.raise_for_status()
    except requests.exceptions.RequestException as e:
        # Streamlit 로그/콘솔에서 확인 가능
        print(f"Request Error: {e}")
        return None

    try:
        data = res.json()
    except ValueError as e:
        print(f"Json Error: {e}")
        return None

    status = data.get("status")
    message = data.get("message")
    if status != "000":
        print(f"Dart Error = '{status}','{message}'")
        return None

    return data

# ──────────────────────────────────────────────
# 현금유입 총괄 (신주/채권/예탁증권)
# ──────────────────────────────────────────────
class CashIn:
    _COLS = ["구분","납입기일","증권의 종류","발행금액","조달목적","원본"]  # 원본: 어떤 API에서 왔는지

    @staticmethod
    def _normalize_df(df: pd.DataFrame | None, source: str) -> pd.DataFrame:
        if df is None or len(df) == 0:
            return pd.DataFrame(columns=CashIn._COLS)

        # 날짜(yyyymmdd → yyyy-mm-dd)
        def _fmt_date(s):
            if pd.isna(s): return np.nan
            s = str(s)
            if len(s) == 8 and s.isdigit():
                return f"{s[:4]}-{s[4:6]}-{s[6:]}"
            return s

        df = df.copy()
        if "납입기일" in df.columns:
            df["납입기일"] = df["납입기일"].apply(_fmt_date)

        if "발행금액" in df.columns:
            df["발행금액"] = pd.to_numeric(df["발행금액"], errors="coerce")

        df["원본"] = source

        for c in CashIn._COLS:
            if c not in df.columns:
                df[c] = np.nan
        return df[CashIn._COLS]

    @staticmethod
    def CashInStock(corp_code, bgn_de='20210101', end_de='20251231'):
        url = "https://opendart.fss.or.kr/api/estkRs.json"  # 신주
        data = get_json(url, params={"crtfc_key": api_key, "corp_code": corp_code,
                                     "bgn_de": bgn_de, "end_de": end_de})
        if not data or "list" not in data:
            return None
        records = []
        for i in data.get("list", []):
            records.append({
                "구분": "신주발행",
                "납입기일": i.get("pymd", np.nan),
                "증권의 종류": i.get("stksen", np.nan),
                "발행금액": i.get("amt", np.nan),
                "조달목적": i.get("se", np.nan),
            })
        return pd.DataFrame(records)

    @staticmethod
    def CashInBond(corp_code, bgn_de='20210101', end_de='20251231'):
        url = "https://opendart.fss.or.kr/api/bdRs.json"  # 채권
        data = get_json(url, params={"crtfc_key": api_key, "corp_code": corp_code,
                                     "bgn_de": bgn_de, "end_de": end_de})
        if not data or "list" not in data:
            return None
        records = []
        for i in data.get("list", []):
            records.append({
                "구분": "채권발행",
                "납입기일": i.get("pymd", np.nan),
                "증권의 종류": i.get("bdnmn", np.nan),
                "발행금액": i.get("amt", np.nan),
                "조달목적": i.get("se", np.nan),
            })
        return pd.DataFrame(records)

    @staticmethod
    def CashInYe(corp_code, bgn_de='20210101', end_de='20251231'):
        url = "https://opendart.fss.or.kr/api/stkdpRs.json"  # 증권예탁증권
        data = get_json(url, params={"crtfc_key": api_key, "corp_code": corp_code,
                                     "bgn_de": bgn_de, "end_de": end_de})
        if not data or "list" not in data:
            return None
        records = []
        for i in data.get("list", []):
            records.append({
                "구분": "증권예탁증권",
                "납입기일": i.get("pymd", np.nan),
                "증권의 종류": i.get("stksen", np.nan),
                "발행금액": i.get("amt", np.nan),
                "조달목적": i.get("se", np.nan),
            })
        return pd.DataFrame(records)

    @staticmethod
    def CashInSummary(corp_code, bgn_de='20210101', end_de='20251231', sort_desc=True) -> pd.DataFrame:
        dfs = []
        df_stock = CashIn.CashInStock(corp_code, bgn_de, end_de)
        dfs.append(CashIn._normalize_df(df_stock, "신주"))

        df_bond = CashIn.CashInBond(corp_code, bgn_de, end_de)
        dfs.append(CashIn._normalize_df(df_bond, "채권"))

        df_dep = CashIn.CashInYe(corp_code, bgn_de, end_de)
        dfs.append(CashIn._normalize_df(df_dep, "예탁증권"))

        out = pd.concat(dfs, ignore_index=True)
        out["납입기일_sort"] = pd.to_datetime(out["납입기일"], errors="coerce")
        out = (
            out.sort_values("납입기일_sort", ascending=not sort_desc)
               .drop(columns=["납입기일_sort"])
               .reset_index(drop=True)
        )
        return out

# ──────────────────────────────────────────────
# 회사 기본/지표/임원/소송 등 기존 클래스들
# ──────────────────────────────────────────────
class CorpInfo:
    @staticmethod
    def get_corp_info(corp_code):
        base_url = "https://opendart.fss.or.kr/api/company.json"
        data = get_json(base_url, params={"crtfc_key": api_key, "corp_code": corp_code})
        if data is None:
            return pd.DataFrame()

        corp_cls_map = {"Y": "유가증권", "K": "코스닥", "N": "코넥스", "E": "기타법인"}

        raw_cls = (data.get("corp_cls") or "").strip().upper()
        corp_cls = corp_cls_map.get(raw_cls, raw_cls)

        corp_info = {
            "회사명": data.get("corp_name"),
            "종목코드": data.get("stock_code"),
            "법인등록번호": data.get("jurir_no"),
            "사업자등록번호": data.get("bizr_no"),
            "업종코드": data.get("induty_code"),
            "설립일": data.get("est_dt"),
            "대표자명": data.get("ceo_nm"),
            "법인구분": corp_cls,
            "주소": data.get("adres"),
            "홈페이지": data.get("hm_url"),
            "결산월": data.get("acc_mt"),
        }
        return pd.DataFrame([corp_info])


class Shareholders:
    @staticmethod
    def get_major_shareholders(corp_code, years=range(2021, 2026)):
        base_url = "https://opendart.fss.or.kr/api/hyslrChgSttus.json"
        frames = []
        reprt_map = {11013: "1분기보고서", 11012: "반기보고서", 11014: "3분기보고서", 11011: "사업보고서"}
        reprt_codes = list(reprt_map.keys())

        def pick(d, *keys, default=np.nan):
            for k in keys:
                v = d.get(k)
                if v not in (None, "", " "):
                    return v
            return default

        for year in years:
            for rc in reprt_codes:
                data = get_json(
                    base_url,
                    params={"crtfc_key": api_key, "corp_code": corp_code, "bsns_year": year, "reprt_code": rc},
                )
                if data is None:
                    continue
                items = data.get("list", []) or []
                if isinstance(items, dict):
                    items = [items]
                if not items:
                    continue
                records = []
                for it in items:
                    shares = pick(it, "trmend_posesn_stock_co", "posesn_stock_co", "bsis_posesn_stock_co")
                    ratio = pick(it, "trmend_qota_rt", "qota_rt", "bsis_qota_rt")
                    rec = {
                        "사업연도": str(year),
                        "보고서종류": reprt_map.get(rc, rc),
                        "변동일": pick(it, "change_on"),
                        "최대주주명": pick(it, "mxmm_shrholdr_nm", "nm"),
                        "소유주식수": shares,
                        "지분율": ratio,
                        "변동사유": pick(it, "change_cause"),
                    }
                    records.append(rec)
                frames.append(pd.DataFrame(records))
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        preferred = ["사업연도", "보고서종류", "변동일", "최대주주명", "소유주식수", "지분율", "변동사유"]
        cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
        return df[cols]

class Execturives:
    @staticmethod
    def get_execturives(corp_code, years=range(2021, 2026)):
        base_url = "https://opendart.fss.or.kr/api/exctvSttus.json"
        frames = []
        reprt_map = {11013: "1분기보고서", 11012: "반기보고서", 11014: "3분기보고서", 11011: "사업보고서"}
        report_priority = {"사업보고서": 1, "3분기보고서": 2, "반기보고서": 3, "1분기보고서": 4}
        reprt_codes = list(reprt_map.keys())

        def pick(d, *keys, default=np.nan):
            for k in keys:
                v = d.get(k)
                if v not in (None, "", " "):
                    return v
            return default

        for year in years:
            for rc in reprt_codes:
                data = get_json(
                    base_url,
                    params={"crtfc_key": api_key, "corp_code": corp_code, "bsns_year": year, "reprt_code": rc},
                )
                if data is None:
                    continue
                items = data.get("list", []) or []
                if isinstance(items, dict):
                    items = [items]
                if not items:
                    continue
                records = []
                for it in items:
                    rec = {
                        "사업연도": str(year),
                        "보고서종류": reprt_map.get(rc, rc),
                        "보고서코드": str(rc),
                        "성명": pick(it, "nm"),
                        "출생년월": pick(it, "birth_ym"),
                        "직위": pick(it, "ofcps"),
                        "등기임원여부": pick(it, "rgist_exctv_at"),
                        "상근여부": pick(it, "fte_at"),
                        "담당업무": pick(it, "chrg_job"),
                        "주요경력": pick(it, "main_career"),
                        "최대주주와의 관계": pick(it, "mxmm_shrholdr_relate"),
                        "재직기간": pick(it, "hffc_pd"),
                        "임기만료일": pick(it, "tenure_end_on"),
                    }
                    records.append(rec)
                frames.append(pd.DataFrame(records))

        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        df["_연도정렬"] = pd.to_numeric(df["사업연도"], errors="coerce")
        df["_보고서정렬"] = df["보고서종류"].map(report_priority).fillna(0).astype(int)
        df = (
            df.sort_values(by=["성명", "출생년월", "_연도정렬", "_보고서정렬"], ascending=[True, True, False, False])
              .drop_duplicates(subset=["성명", "출생년월"], keep="first")
              .drop(columns=["_연도정렬", "_보고서정렬", "보고서코드"], errors="ignore")
        )
        preferred = ["사업연도", "보고서종류", "성명", "출생년월", "직위", "등기임원여부", "상근여부", "담당업무",
                     "주요경력", "최대주주와의 관계", "재직기간", "임기만료일"]
        cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
        return df[cols]

    @staticmethod
    def get_executive_shareholdings(corp_code):
        base_url = "https://opendart.fss.or.kr/api/elestock.json"
        data = get_json(base_url, params={"crtfc_key": api_key, "corp_code": corp_code})
        if data is None:
            return pd.DataFrame()
        items = data.get("list", []) or []
        if isinstance(items, dict):
            items = [items]
        if not items:
            return pd.DataFrame()
        records = []
        for item in items:
            rec = {
                "공시접수일자": item.get("rcept_dt", np.nan),
                "보고자": item.get("repror", np.nan),
                "등기임원여부": item.get("isu_exctv_rgist_at", np.nan),
                "직급": item.get("isu_exctv_ofcps", np.nan),
                "주식수": item.get("sp_stock_lmp_cnt", np.nan),
                "지분율": item.get("sp_stock_lmp_rate", np.nan),
            }
            records.append(rec)
        return pd.DataFrame(records)

class ConvertBond:
    @staticmethod
    def get_convert_bond(corp_code, bgn_de='20210101', end_de='20251231'):
        base_url = 'https://opendart.fss.or.kr/api/cvbdIsDecsn.json'
        data = get_json(base_url, params={"crtfc_key": api_key, "corp_code": corp_code, "bgn_de": bgn_de, "end_de": end_de})
        if data is None:
            return pd.DataFrame()
        items = data.get("list", []) or []
        if isinstance(items, dict):
            items = [items]
        if not items:
            return pd.DataFrame()
        records = []
        for i in items:
            rec = {
                "접수번호": i.get("rcept_no", np.nan),
                "CB회차": i.get("bd_tm", np.nan),
                "CB종류": i.get("cb_knd", np.nan),
                "발행방법": i.get("bdis_mthn", np.nan),
                "권면총액": i.get("bd_fta", np.nan),
                "운영자금목적": i.get("fdpp_op", np.nan),
                "채무상환목적": i.get("fdpp_dtrp", np.nan),
                "타법인증권취득목적": i.get("fdpp_ocsa", np.nan),
                "기타목적": i.get("fdpp_etc", np.nan),
                "발행일": i.get("pymd", np.nan),
                "만기일": i.get("bd_mtd", np.nan),
                "표시이자율": i.get("bd_intr_ex", np.nan),
                "만기이자율": i.get("bd_intr_sf", np.nan),
                "전환비율": i.get("cv_rt", np.nan),
                "주당 전환가액": i.get("cv_prc", np.nan),
                "전환발행주식수": i.get("cvisstk_tisstk_vs", np.nan),
                "전환청구 시작일": i.get("cvrqpd_bgdm", np.nan),
                "전환청구 종료일": i.get("cvrqpd_edd", np.nan),
                "전환가액 조정": i.get("act_mktprcfl_cvprc_lwtrsprc", np.nan),
                "전환가액 조정 근거": i.get("act_mktprcfl_cvprc_lwtrsprc_bs", np.nan),
                "전환가액 조정 하한": i.get("rmislmt_lt70p", np.nan),
            }
            records.append(rec)
        return pd.DataFrame(records)

class Lawsuits:
    @staticmethod
    def get_lawsuits(corp_code, bgn_de='20210101', end_de='20251231'):
        """
        소송 등 중요 사건 공시 조회
        """
        base_url = "https://opendart.fss.or.kr/api/lwstLg.json"
        data = get_json(
            base_url,
            params={
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bgn_de": bgn_de,
                "end_de": end_de,
            },
        )
        if data is None:
            return pd.DataFrame()

        items = data.get("list", [])
        if isinstance(items, dict):
            items = [items]
        if not items:
            return pd.DataFrame()

        records = []
        for it in items:
            rec = {
                "접수번호": it.get("rcept_no", np.nan),
                "사건의 명칭": it.get("icnm", np.nan),
                "원고": it.get("ac_ap", np.nan),
                "청구내용": it.get("rq_cn", np.nan),
                "관할법원": it.get("cpct", np.nan),
                "향후대책": it.get("ft_ctp", np.nan),
                "제기일자": it.get("lgd", np.nan),
                "확인일자": it.get("cfd", np.nan),
            }
            records.append(rec)

        return pd.DataFrame(records)

class FinancialIdx:
    @staticmethod
    def get_financialidx(
        corp_code,
        years=range(2021, 2026),
        reprt_codes=(11011, 11014, 11012, 11013),   # 사업>3분기>반기>1분기
        idx_groups=("M210000", "M220000", "M230000", "M240000"),  # 수익성/안정성/성장성/활동성
        pivot=False,  # True면 지표명을 가로로 피벗
    ):
        """
        OpenDART fnlttSinglIndx.json 조회
        반환(세로형): [사업연도, 보고서종류, 지표군, 지표명, 지표값]
        pivot=True: [사업연도, 보고서종류] 기준으로 지표명을 가로 컬럼으로 전개
        """
        base_url = "https://opendart.fss.or.kr/api/fnlttSinglIndx.json"

        reprt_map = {
            11013: "1분기보고서",
            11012: "반기보고서",
            11014: "3분기보고서",
            11011: "사업보고서",
        }
        idx_map = {
            "M210000": "수익성지표",
            "M220000": "안정성지표",
            "M230000": "성장성지표",
            "M240000": "활동성지표",
        }

        def to_num(x):
            if x in (None, "", " "):
                return pd.NA
            return pd.to_numeric(str(x).replace(",", ""), errors="coerce")

        frames = []

        for y in years:
            for rc in reprt_codes:
                for ig in idx_groups:
                    data = get_json(
                        base_url,
                        params={
                            "crtfc_key": api_key,
                            "corp_code": corp_code,
                            "bsns_year": y,
                            "reprt_code": rc,
                            "idx_cl_code": ig,
                        },
                    )
                    if not data:
                        continue

                    items = data.get("list", []) or []
                    if isinstance(items, dict):
                        items = [items]
                    if not items:
                        continue

                    rows = []
                    for it in items:
                        rows.append(
                            {
                                "사업연도": str(y),
                                "보고서종류": reprt_map.get(rc, str(rc)),
                                "지표군": idx_map.get(ig, ig),
                                "지표명": it.get("idx_nm", pd.NA),
                                "지표값": to_num(it.get("idx_val")),
                            }
                        )
                    if rows:
                        frames.append(pd.DataFrame(rows))

        if not frames:
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)

        # 정렬: 연도 ↑, 보고서(사업>3분기>반기>1분기), 지표군, 지표명
        order = {"사업보고서": 1, "3분기보고서": 2, "반기보고서": 3, "1분기보고서": 4}
        df["_yr"] = pd.to_numeric(df["사업연도"], errors="coerce")
        df["_ord"] = df["보고서종류"].map(order).fillna(9).astype(int)
        df = df.sort_values(["_yr", "_ord", "지표군", "지표명"]).drop(columns=["_yr", "_ord"]).reset_index(drop=True)

        if not pivot:
            return df[["사업연도", "보고서종류", "지표군", "지표명", "지표값"]]

        # 가로 피벗
        wide = (
            df.pivot_table(
                index=["사업연도", "보고서종류"],
                columns="지표명",
                values="지표값",
                aggfunc="last",
            )
            .sort_index(level=["사업연도", "보고서종류"])
            .reset_index()
        )
        wide.columns.name = None
        return wide
