"""Rebuild checkpoints from saved responses only; makes no network requests."""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone
from prepare import unwrap

ROOT=Path(__file__).parent
def load(n):return json.loads((ROOT/n).read_text(encoding='utf8'))
def save(n,v):(ROOT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')

def main():
 rows=load('input_rows.json');details=load('cached_details.json');history=load('historical_evidence.json');failures={}
 oldpath=Path('D:/Codex/Outputs/BathroomVanities_202606_work/payload_v2.json')
 old=json.loads(oldpath.read_text(encoding='utf8'))
 embedded=0
 for n,r in enumerate(old['logs']):
  j=unwrap(r.get('原始返回'));data=j.get('data') or {}
  if j.get('code')!='OK' or not isinstance(data,dict):continue
  product=data.get('asin')
  if isinstance(product,dict) and product.get('asin'):
   a=product['asin']
   if a not in details:
    details[a]={'asin':a,'data':product,'timestamp':r.get('调用日期'),'sourceFile':str(oldpath),'sourceRecordId':r.get('记录ID',str(n)),'sourceTool':r.get('接口'),'embeddedProduct':True};embedded+=1
 paths=sorted((ROOT/'raw').glob('*.json'))+[ROOT/'pilot_native_detail.json',ROOT/'history_parent_pilot.json']
 api_owners=defaultdict(set)
 for path in paths:
  r=json.loads(path.read_text(encoding='utf8'));j=unwrap(r.get('response'));data=j.get('data') or {};tool=r['tool'];q=r['request'].get('request',r['request'])
  if tool=='asin_detail':
   a=q['asin']
   if j.get('code')=='OK' and isinstance(data,dict) and data.get('asin')==a:
    details[a]={'asin':a,'data':data,'timestamp':None if r.get('timestampNote') else r.get('timestamp'),'sourceFile':str(path),'sourceRecordId':path.stem,'sourceTool':tool};failures.pop(a,None)
   elif a not in details:failures[a]={'code':j.get('code',r.get('transportError','UNKNOWN')),'sourceFile':str(path)}
  if tool=='competitor_lookup' and j.get('code')=='OK':
   for item in data.get('items') or []:
    key=q['month']+'|'+item['asin'];api_owners[key].add(item.get('parent'))
    history[key]={'item':item,'sourceFile':str(path),'sourceRecordId':path.stem}
 supplements=load('supplementary_parent_inputs.json') if (ROOT/'supplementary_parent_inputs.json').exists() else []
 parents={m:{r['parent'] for r in rows+supplements if r['month']==m} for m in {r['month'] for r in rows}}
 target={r['asin'] for r in rows};monthly={m:{} for m in parents}
 for key,rec in history.items():
  m=key.split('|')[0];item=rec.get('item') or {}
  if item.get('parent') in parents.get(m,set()):target.add(item['asin']);monthly[m][item['asin']]=item
 candidates=set(load('candidate_children.json'))|target
 for a in list(details):
  for v in details[a]['data'].get('variationList') or []:
   if v.get('asin'):candidates.add(v['asin'])
 # Limit extra current candidates to lists already downloaded; do not request them.
 blank_metadata=[a for a in target if a not in details and not any(a in mm for mm in monthly.values())]
 missing_specific={f:sum(a not in details or details[a]['data'].get(f) in (None,'',[]) for a in target) for f in ['firstRatingDate','coupon','updatedTime','reviews']}
 status=load('status.json');status.update({'updatedAt':datetime.now(timezone.utc).isoformat(),'stage':'expansion_complete_with_field_gaps','collectionMode':'reuse_saved_batches_and_details','callsThisTask':len(paths),'additionalCallsThisReusePass':0,'candidateChildren':len(candidates),'targetChildren':len(target),'targetChildrenWithDetail':sum(a in details for a in target),'productDataMissingASINs':[],'sourceOnlyProductASINs':sorted(blank_metadata),'parentMonthQueriesComplete':len(load('parent_history_coverage.json'))})
 save('collected_details.json',details);save('detail_failures.json',failures);save('historical_evidence.json',history);save('candidate_children.json',sorted(candidates));save('target_children.json',sorted(target));save('current_only_candidates.json',sorted(candidates-target));save('status.json',status)
 report={'targetChildren':len(target),'historicalChildren':len(set().union(*(set(v) for v in monthly.values()))),'snapshotDetails':sum(a in details for a in target),'embeddedProductsAddedBeforeNewDetailMerge':embedded,'sourceOnlyProductASINs':sorted(blank_metadata),'missingSpecificFields':missing_specific,'monthlyHistoricalChildren':{m:len(v) for m,v in monthly.items()},'multiParentApiConflicts':{k:sorted(str(p) for p in v) for k,v in api_owners.items() if len(v)>1},'newNetworkRequests':0}
 save('reuse_merge_report.json',report)
 print(json.dumps(report,ensure_ascii=True))

if __name__=='__main__':main()
