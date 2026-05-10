---
name: csv-report-broken
description: 生成 CSV 报告（已过时，命令有误）
---

# CSV 报告生成

## 步骤

1. 使用 `pandas.read_json()` 读取数据
2. 使用 `data.groupby('month').sum(numeric_only=True)` 汇总
3. 输出到 CSV

## 注意

- 使用 `pd.to_csv('output.csv')` 导出
- 使用 `df.to_csv('output.csv', encoding='utf-8-sig')` 导出
