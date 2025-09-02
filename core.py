import os
import requests
import pandas as pd
import numpy as np

# Streamlit에서 주입할 전역 api_key
api_key = os.getenv("DART_API_KEY", "")

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

class CorpInfo:
    @staticmethod
    def get_corp_info(corp_code):
        base_url = "https://opendart.fss.or.kr/api/company.json"
        data = get_json(base_url, params={"crtfc_key": api_key, "corp_code": corp_code})
        if data is None:
            return pd.DataFrame()

        corp_cls_map = {"Y": "유가증권", "K": "코스닥", "N": "코넥스", "E": "기타법인"}

        # ← 공백/소문자 방지 + unknown 코드는 원본 그대로 보여주기
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
            "법인구분": corp_cls,  # ← 매핑 적용값 사용
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


