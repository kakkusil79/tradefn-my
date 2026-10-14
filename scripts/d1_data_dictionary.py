"""1일차: d1_buyers_raw.xlsx 데이터 사전용 숫자 (읽기 전용)

실행: uv run python scripts/d1_data_dictionary.py
결측 수 · 숫자형 값의 관측 범위 · 범주 열의 값 목록을 출력한다.
보고서: workbench/day1/outputs/d1_data_dictionary.md
"""
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

df = pd.read_excel("data/day1/d1_buyers_raw.xlsx", sheet_name="buyers", dtype=object)
print(f"{len(df)}행 (buyer_id 고유 {df['buyer_id'].nunique()})\n")
for c in df.columns:
    s = df[c]
    nums = pd.to_numeric(s.where(s.map(lambda v: isinstance(v, (int, float)))), errors="coerce").dropna()
    texts = s[s.map(lambda v: isinstance(v, str))]
    line = f"{c}: 결측 {int(s.isna().sum())}"
    if len(nums):
        line += f" | 숫자 {len(nums)}개 범위 {nums.min()} ~ {nums.max()} · 중앙값 {nums.median()}"
        line += f" · 음수 {int((nums < 0).sum())} · 0 {int((nums == 0).sum())}"
    if len(texts) and s.nunique() <= 12:
        line += f" | 값 {texts.value_counts().to_dict()}"
    elif len(texts) and len(nums):
        line += f" | 글자 {len(texts)}개"
    print(line)
