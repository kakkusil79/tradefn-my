"""1일차: EDA용 분석 표를 메모리에서 만든다 (원본 · 코드표는 읽기만 한다)

사용: 노트북 workbench/day1/notebooks/d1_eda.ipynb 에서 build_analysis_table() 호출
단독 확인: uv run python scripts/d1_eda_prep.py
근거: workbench/day1/outputs/d1_quality_report.md (진단) · d1_code_table.csv (결제조건 코드표)

정리 규칙
  R1 buyer_id 기준 중복 3행(B047 · B094 · B114) 제거, 엑셀에서 먼저 나온 행을 남김 → 150행
  R2 max_dpd_days: '90일' · '381 days' 처럼 숫자 + 단위는 숫자만 남김.
     '-' · '확인중' 처럼 숫자가 없는 값은 빈칸(NaN) + dpd_flag='확인 필요' (0으로 채우지 않음)
  R3 국가는 country_code 기준으로 표준 국가명(country_std)을 다시 붙임 (원래 country 열은 그대로 둠)
  R4 결제조건은 d1_code_table.csv 의 '원래 표기'(앞뒤 공백 포함 글자 그대로)로 조회 → payment_code.
     코드표가 '검토 필요'로 둔 표기는 그 값을 그대로 씀. 코드표에 없는 표기는 '코드표 없음'
  R5 연체 바이어 is_overdue = max_dpd_days > 0. 연체일을 모르는 행은 NaN(비율 계산에서 제외)
"""
import re
import sys

import pandas as pd

SRC = "data/day1/d1_buyers_raw.xlsx"
CODE_TABLE = "workbench/day1/outputs/d1_code_table.csv"

COUNTRY_STD = {
    "ARE": "아랍에미리트", "BRA": "브라질", "CHN": "중국", "DEU": "독일", "EGY": "이집트",
    "GBR": "영국", "IDN": "인도네시아", "IND": "인도", "JPN": "일본", "MEX": "멕시코",
    "MYS": "말레이시아", "NGA": "나이지리아", "NLD": "네덜란드", "POL": "폴란드",
    "SAU": "사우디아라비아", "THA": "태국", "TUR": "튀르키예", "TWN": "대만",
    "USA": "미국", "VNM": "베트남",
}


def parse_dpd(v):
    """연체일 원값 → (숫자 또는 NaN, 플래그)."""
    if isinstance(v, (int, float)) and not pd.isna(v):
        return float(v), ""
    if isinstance(v, str):
        m = re.fullmatch(r"\s*(\d+)\s*(일|days?)?\s*", v)
        if m:
            return float(m.group(1)), "단위 제거"
        return float("nan"), "확인 필요"
    return float("nan"), "확인 필요"


def build_analysis_table(src=SRC, code_table=CODE_TABLE):
    raw = pd.read_excel(src, sheet_name="buyers", dtype=object)
    raw.insert(0, "excel_row", raw.index + 2)  # 엑셀 행 번호(1행 = 머리글)

    df = raw.drop_duplicates("buyer_id", keep="first").copy()                      # R1

    parsed = df["max_dpd_days"].map(parse_dpd)                                       # R2
    df["dpd_raw"] = df["max_dpd_days"]
    df["max_dpd_days"] = parsed.map(lambda t: t[0])
    df["dpd_flag"] = parsed.map(lambda t: t[1])

    df["country_std"] = df["country_code"].map(COUNTRY_STD)                         # R3

    ct = pd.read_csv(code_table, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df["payment_code"] = df["payment_terms_raw"].map(                                # R4
        dict(zip(ct["원래 표기"], ct["표준 코드"]))).fillna("코드표 없음")

    df["is_overdue"] = (df["max_dpd_days"] > 0).where(df["max_dpd_days"].notna())  # R5
    return raw, df


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raw, df = build_analysis_table()
    print(f"원본 {len(raw)}행 → 분석 표 {len(df)}행 (buyer_id 고유 {df['buyer_id'].nunique()})")
    print(df["dpd_flag"].value_counts().to_dict())
    print(df["payment_code"].value_counts().to_dict())
    print("국가명 미매핑:", df["country_std"].isna().sum())
