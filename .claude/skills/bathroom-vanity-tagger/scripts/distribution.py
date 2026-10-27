"""Per-field value distribution of a tagging run, split by evidence kind.

  python3 -I distribution.py --tag-dir OUT [--out-md 分布.md] [--out-xlsx 分布.xlsx]

Each field lists every value with row count, unique child ASINs, and how
many rows came from child text / business rule / parent fill / default.
"""
import argparse,json,sys
from collections import Counter,defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))  # works under python -I
from tag_cached import HEADERS

KIND={'text_supported':'子体文本','derived':'子体文本','conflict':'冲突','business_mapping':'业务归类','business_inference':'业务推导','business_assumption':'业务推导','order_inference':'尺寸规则','business_default':'默认值','parent_fill':'父体补充','parent_candidate':'父体候选','missing':'无'}
KINDS=['子体文本','业务归类','业务推导','尺寸规则','父体补充','父体候选','默认值','冲突','无']

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--tag-dir',required=True);ap.add_argument('--out-md');ap.add_argument('--out-xlsx');a=ap.parse_args()
    rows=[r for r in json.loads((Path(a.tag_dir)/'tagging_evidence.json').read_text(encoding='utf-8'))['rows'] if r['includeInBathroomAnalysis']]
    n=len(rows);asins=len({r['childASIN'] for r in rows})
    tables={}
    for h in HEADERS[:14]:
        cnt=Counter();uniq=defaultdict(set);kinds=defaultdict(Counter)
        for r in rows:
            v=r['tags'][h];v='空白' if v is None else str(v)
            if h.startswith('D9') and v not in ('空白',):
                f=float(v);v=str(int(f)) if f.is_integer() else v
            cnt[v]+=1;uniq[v].add(r['childASIN']);kinds[v][KIND.get(r['fields'].get(h,{}).get('status'),'无')]+=1
        tables[h]=[(v,c,len(uniq[v]),kinds[v]) for v,c in cnt.most_common()]
    md=['# 各字段打标现状分布','','范围 %d 行（子ASIN×月份），%d 个唯一子ASIN。'%(n,asins),'']
    for h,t in tables.items():
        md+=['## '+h,'','| 值 | 行数 | 占比 | 唯一子ASIN | 子体文本 | 业务归类/推导/尺寸规则 | 父体补充 | 默认值 | 冲突 |','|---|---|---|---|---|---|---|---|---|']
        limit=25 if h.startswith('D9') or h=='D7柜体材质' else 60
        for v,c,u,k in t[:limit]:
            md.append('| %s | %d | %.1f%% | %d | %d | %d | %d | %d | %d |'%(v,c,100*c/n,u,k['子体文本'],k['业务归类']+k['业务推导']+k['尺寸规则'],k['父体补充']+k['父体候选'],k['默认值'],k['冲突']))
        if len(t)>limit:md.append('| …其余 %d 个值 | %d | %.1f%% | | | | | | |'%(len(t)-limit,sum(c for v,c,u,k in t[limit:]),100*sum(c for v,c,u,k in t[limit:])/n))
        md.append('')
    text='\n'.join(md)
    if a.out_md:Path(a.out_md).write_text(text,encoding='utf-8')
    if a.out_xlsx:
        from openpyxl import Workbook
        wb=Workbook();ws=wb.active;ws.title='分布'
        ws.append(['字段','值','行数','占比','唯一子ASIN']+KINDS)
        for h,t in tables.items():
            for v,c,u,k in t:ws.append([h,v,c,c/n,u]+[k[x] for x in KINDS])
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for col,w in zip('ABCDE',(14,30,8,8,10)):ws.column_dimensions[col].width=w
        for row in ws.iter_rows(min_row=2,min_col=4,max_col=4):
            for c in row:c.number_format='0.0%'
        wb.save(a.out_xlsx)
    print(text if not a.out_md else 'written')

if __name__=='__main__':main()
