# buyers 정제 전·후 비교 (dq_report)

- 원본(읽기만): `data/checkpoints/d2_start.xlsx` 시트 buyers · 150행 × 28열
- 결과: `workbench/day2/outputs/d2_buyers_clean.csv` · 150행 × 25열 (buyer_id 첫 열 · late_30d 마지막 열)
- 규칙: `workbench/day2/rules/정제규칙.md` 1–7칸 · 코드: `scripts/clean_buyers.py`
- 기준일 2026-08-31 · 환율 `fx_at_ref` 같은 날 행 · 시차 환율 `workbench/day2/data/fx_krw_daily.csv`

## 1. 표기 · 타입 (1·2·6칸)
| 열(원본 → 결과) | 전 | 후 |
|---|---|---|
| currency → ccy_clean | 9종 {'USD': 81, 'EUR': 18, 'US$': 15, 'usd': 14, 'JPY': 8, 'CNY': 5, 'euro': 5, 'RMB': 2, 'yen': 2} | 4종 {'USD': 110, 'EUR': 23, 'JPY': 10, 'CNY': 7} |
| ar_balance → amt_num | int:140, str:9, float:1 | float:150 |
| ar_current (중간값) | int:148, str:2 | float:150 |
| ar_1_30 (중간값) | int:148, str:2 | float:150 |
| oecd_crc → country_risk | int:93, str:57 ('-' 57건) | int:150 (범위 0~6) |

## 2. 글자 → 숫자 변환 13건 (2칸)
| 엑셀 행 | buyer_id | 열 | 원값 | 변환값 |
|---|---|---|---|---|
| 6 | B005 | ar_balance | ' 195900 ' | 195900.0 |
| 10 | B009 | ar_balance | 'CNY 317,000' | 317000.0 |
| 16 | B015 | ar_balance | '7,680' | 7680.0 |
| 35 | B034 | ar_balance | '200,520' | 200520.0 |
| 44 | B043 | ar_balance | '155,200 CNY' | 155200.0 |
| 84 | B083 | ar_balance | '2,200' | 2200.0 |
| 87 | B086 | ar_balance | 'EUR 143,620' | 143620.0 |
| 115 | B114 | ar_balance | ' 1458000 ' | 1458000.0 |
| 142 | B141 | ar_balance | '47.0k' | 47000.0 |
| 77 | B076 | ar_current | '51,970' | 51970.0 |
| 92 | B091 | ar_current | '7,980' | 7980.0 |
| 9 | B008 | ar_1_30 | '6,850' | 6850.0 |
| 73 | B072 | ar_1_30 | '8,320' | 8320.0 |

## 3. 단위 의심 · 잔액 보정 (4칸)
`unit_flag` = amt_num × USD 환산 계수 > credit_limit_usd × 10. amt_num ≠ 버킷 합이면 버킷 합으로 보정한 뒤 USD 환산한다.
| 엑셀 행 | buyer_id | ccy | amt_num | 버킷 합 | 보정값 | ar_balance_usd | 한도 | unit_flag |
|---|---|---|---|---|---|---|---|---|
| 73 | B072 | EUR | 8320000.0 | 8320.0 | 8320.0 | 9665.37 | 10000 | 1 |
| 142 | B141 | EUR | 47000.0 | 47030.0 | 47030.0 | 54634.89 | 80000 | 0 |

## 4. 결측 채우기 (3칸)
플래그를 먼저 만든 뒤 열별 중위수(채우기 전 150행 값)로 채웠다. `fin_missing` = 유동자산 · 유동부채 · 총부채 · 자기자본 · 매출 중 하나라도 빈칸 → **47행**.
late_ratio · dispute_ratio는 invoices_12m = 0이면 분모가 0이라 같은 규칙(중위수)을 따랐다.
| 열 | 원본 결측 | 채운 칸 | 중위수 |
|---|---|---|---|
| current_assets | 18 | 18 | 17593000.0 |
| current_liabilities | 39 | 39 | 11560000.0 |
| total_liabilities | 18 | 18 | 22628500.0 |
| equity | 34 | 34 | 14948000.0 |
| accounts_receivable | 39 | 39 | 6499000.0 |
| revenue | 18 | 18 | 44007000.0 |
| operating_income | 37 | 37 | 1704000.0 |
| avg_days_late_12m | 11 | 11 | 7.0 |
| avg_dpd_last3m | 33 | 33 | 0.0 |
| avg_dpd_prev3m | 42 | 42 | 0.0 |
| late_ratio | – | 11 | 0.1818 |
| dispute_ratio | – | 11 | 0.1429 |

## 5. 자본잠식 (5칸)
원값 equity ≤ 0 → `neg_equity=1`, `debt_to_equity`는 빈칸으로 둔다.
| 엑셀 행 | buyer_id | equity | total_liabilities |
|---|---|---|---|
| 14 | B013 | -15126000.0 | 109262000.0 |
| 49 | B048 | -37662000.0 | 160609000.0 |

## 6. 환율 · 시차 (7칸)
USD 환산 계수 = 통화 KRW ÷ USD KRW(JPY는 100엔당 값 ÷ 100). `fx_chg_30d_lag30` = 2026-07-31 종가 ÷ 2026-07-01 종가 − 1.
검산: 일별 파일로 계산한 2026-08-31의 30일 변화(직전 관측일 기준)가 `fx_at_ref`의 chg_30d와 4종 모두 일치(차이 < 0.0001).
| ccy | USD 환산 계수(×) | fx_chg_30d | fx_chg_30d_lag30 |
|---|---|---|---|
| USD | 1.0 | -0.0477 | -0.0734 |
| EUR | 1.161703 | -0.0396 | -0.0624 |
| CNY | 0.148818 | -0.0433 | -0.0674 |
| JPY | 0.00626 | -0.0512 | -0.0545 |

## 7. 결과 열 요약
남은 빈칸: {'debt_to_equity': 2} (5칸 규칙으로 남긴 것뿐)
| 열 | count | mean | min | 50% | max |
|---|---|---|---|---|---|
| amt_num | 150.0 | 574017.3245 | 0.0 | 10160.0 | 32072000.0 |
| ar_balance_usd | 150.0 | 29320.6691 | 0.0 | 9328.475 | 232944.67 |
| pct_current | 150.0 | 0.9097 | 0.0 | 1.0 | 1.0 |
| pct_ar_31p | 150.0 | 0.0488 | 0.0 | 0.0 | 1.0 |
| pct_91plus | 150.0 | 0.0267 | 0.0 | 0.0 | 1.0 |
| avg_days_late | 150.0 | 17.028 | 0.0 | 7.0 | 304.0 |
| late_ratio | 150.0 | 0.2291 | 0.0 | 0.1818 | 1.0 |
| dpd_trend | 150.0 | -1.63 | -129.5 | 0.0 | 58.0 |
| dispute_ratio | 150.0 | 0.156 | 0.0 | 0.1429 | 1.0 |
| current_ratio | 150.0 | 1.8128 | 0.1807 | 1.5196 | 32.5401 |
| debt_to_equity | 148.0 | 1.8902 | 0.2434 | 1.5138 | 10.4589 |
| dso_buyer | 150.0 | 73.8373 | 4.73 | 60.35 | 367.26 |
| op_margin | 150.0 | 0.0559 | -0.2487 | 0.0462 | 0.3163 |
| fin_missing | 150.0 | 0.3133 | 0.0 | 0.0 | 1.0 |
| neg_equity | 150.0 | 0.0133 | 0.0 | 0.0 | 1.0 |
| country_risk | 150.0 | 1.8867 | 0.0 | 2.0 | 6.0 |
| crc_unclassified | 150.0 | 0.38 | 0.0 | 0.0 | 1.0 |
| unit_flag | 150.0 | 0.0067 | 0.0 | 0.0 | 1.0 |
| fx_chg_30d | 150.0 | -0.0465 | -0.0512 | -0.0477 | -0.0396 |
| fx_chg_30d_lag30 | 150.0 | -0.0702 | -0.0734 | -0.0734 | -0.0545 |

## 8. 계산식
| 열 | 식 |
|---|---|
| pct_current | ar_current ÷ 버킷 합 (잔액 0이면 1) |
| pct_ar_31p | (ar_31_60 + ar_61_90 + ar_91p) ÷ 버킷 합 (잔액 0이면 0) |
| pct_91plus | ar_91p ÷ 버킷 합 (잔액 0이면 0) |
| avg_days_late | avg_days_late_12m (중위수 채움) |
| late_ratio | late_invoices_12m ÷ invoices_12m |
| dpd_trend | avg_dpd_last3m − avg_dpd_prev3m (각각 중위수 채움 후) |
| dispute_ratio | dispute_cnt_12m ÷ invoices_12m |
| current_ratio | current_assets ÷ current_liabilities |
| debt_to_equity | total_liabilities ÷ equity (neg_equity=1이면 빈칸) |
| dso_buyer | accounts_receivable ÷ revenue × 365 |
| op_margin | operating_income ÷ revenue |

## 9. 확인 필요
- B029 소수(ar_balance 60,187.68 · ar_31_60 21,007.68)는 규칙대로 그대로 두었다. 센트인지 오류인지 근거 없음.
- 4칸: B141은 보정했지만 한도 × 10 기준에는 걸리지 않아 unit_flag = 0이다. 보정 행 전부에 플래그를 달지는 규칙에서 정해야 한다.
- 결측 플래그 `{열}_missing`(거래 3열)은 결과 열 목록에 없어 CSV에 넣지 않았다.
- 중위수는 150행 전체로 구했다. 3일차에 학습·검증을 나누면 학습 데이터만으로 다시 구해야 하는지 확인 필요.
