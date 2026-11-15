"""把用户提供的 SKU 打标表抽成带缓存值的干净 CSV，供数据小试使用（只读原件）。"""
import sys, glob, json, openpyxl, pandas as pd

src_dir, out_csv = sys.argv[1], sys.argv[2]
xlsx = glob.glob(src_dir + '/*.xlsx')[0]
ana = json.load(open(glob.glob(src_dir + '/*.analysis.json')[0], encoding='utf-8'))

wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
rows = list(wb['SKU估算明细'].iter_rows(values_only=True))
df = pd.DataFrame(rows[1:], columns=rows[0])
df['excelRow'] = range(2, len(df) + 2)

man = pd.DataFrame(ana['rowManifest'])[['excelRow', 'includeInBathroomAnalysis', 'estimated', 'crossMonthReuse', 'featureSource']]
df = df.merge(man, on='excelRow', how='left')

prow = list(wb['父体汇总'].iter_rows(values_only=True))
par = pd.DataFrame(prow[1:], columns=prow[0])
par.to_csv(out_csv.replace('.csv', '_parent.csv'), index=False)
df.to_csv(out_csv, index=False)
print(len(df), 'rows ->', out_csv, '| parents', len(par))
