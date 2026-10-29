import json,re
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).parent
def unwrap(x):
 if isinstance(x,str):
  try:return unwrap(json.loads(x))
  except (ValueError,TypeError):return {}
 if not isinstance(x,dict):return {}
 if 'code' in x:return x
 if 'result' in x:return unwrap(x['result'])
 for b in x.get('content',[]):
  if b.get('type')=='text':
   q=unwrap(b.get('text',''))
   if 'code' in q:return q
 return x

if __name__=='__main__':
 source=json.loads(Path('D:/Codex/Data/BathroomVanities_202606_09_filter/filter_payload.json').read_text(encoding='utf8'))
 rows=[r for r in source['rows'] if r['result']=='保留']
 old=json.loads(Path('D:/Codex/Outputs/BathroomVanities_202606_work/payload_v2.json').read_text(encoding='utf8'))
 details={}; history={}; logs=[]
 for n,r in enumerate(old['logs']):
  j=unwrap(r.get('原始返回'))
  if j.get('code')!='OK':continue
  if r['接口']=='asin_detail' and j.get('data',{}).get('asin'):
   details[r['ASIN']]={'asin':r['ASIN'],'data':j['data'],'timestamp':r.get('调用日期'),'sourceFile':'D:/Codex/Outputs/BathroomVanities_202606_work/payload_v2.json','sourceRecordId':r.get('记录ID',str(n))}
  if r['接口']=='competitor_lookup':
   try:req=json.loads(r['请求参数'])
   except Exception:continue
   month=req.get('month')
   if not month or req.get('variation')!='N':continue
   logs.append({'request':req,'data':j.get('data',{}),'sourceRecordId':r.get('记录ID',str(n))})
   for item in j.get('data',{}).get('items',[]):
    history[month+'|'+item['asin']]={'item':item,'sourceFile':'D:/Codex/Outputs/BathroomVanities_202606_work/payload_v2.json','sourceRecordId':r.get('记录ID',str(n))}
 # Negative results are reusable only if all result pages for the exact request were captured.
 groups=defaultdict(list)
 for r in logs:
  q={k:v for k,v in r['request'].items() if k!='page'}
  groups[json.dumps(q,sort_keys=True)].append(r)
 for rr in groups.values():
  pages=max(int(r['data'].get('pages',1) or 1) for r in rr)
  seen={int(r['request'].get('page',1)) for r in rr}
  if not all(i in seen for i in range(1,pages+1)):continue
  q=rr[0]['request']; found={i['asin'] for r in rr for i in r['data'].get('items',[])}
  for a in q.get('asins',[]):
   if a not in found:history.setdefault(q['month']+'|'+a,{'item':None,'sourceFile':'D:/Codex/Outputs/BathroomVanities_202606_work/payload_v2.json','sourceRecordId':rr[0]['sourceRecordId'],'reason':'successful_complete_query_not_returned'})
 (ROOT/'input_rows.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
 (ROOT/'cached_details.json').write_text(json.dumps(details,ensure_ascii=False),encoding='utf8')
 (ROOT/'cached_history.json').write_text(json.dumps(history,ensure_ascii=False),encoding='utf8')
 parents=sorted({r['parent'] for r in rows}); seeds=sorted({r['asin'] for r in rows})
 stats={'inputParentMonths':len(rows),'uniqueInputParents':len(parents),'sourceChildASINs':len(seeds),'cachedDetails':len(details),'cachedInputParents':len(set(parents)&details.keys()),'cachedSourceChildren':len(set(seeds)&details.keys()),'monthParents':dict(Counter(r['month'] for r in rows)),'pilotAlreadyCached':'B0H6S3XGBN' in details,'cacheHistoricalItems':len(history)}
 (ROOT/'input_manifest.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(stats,ensure_ascii=True))
