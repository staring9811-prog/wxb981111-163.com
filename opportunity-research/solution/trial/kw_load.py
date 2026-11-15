"""抽取关键词历史趋势（2024.10–2026.09）与打标、竞争表为 CSV。"""
import sys, openpyxl, pandas as pd
f, out = sys.argv[1], sys.argv[2]
wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
def sheet(name, hdr_row=5):
    rows = list(wb[name].iter_rows(values_only=True))
    return pd.DataFrame(rows[hdr_row + 1:], columns=rows[hdr_row]).dropna(how='all')
sheet('Amazon历史趋势').to_csv(out + '_trend.csv', index=False)
sheet('关键词打标').to_csv(out + '_tags.csv', index=False)
sheet('关键词竞争').to_csv(out + '_comp.csv', index=False)
sheet('Amazon搜索需求').to_csv(out + '_demand.csv', index=False)
print('ok')
