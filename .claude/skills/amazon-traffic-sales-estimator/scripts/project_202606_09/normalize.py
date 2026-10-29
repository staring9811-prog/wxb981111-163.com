import json,re,math
from pathlib import Path
from collections import defaultdict,Counter
from prepare import unwrap

ROOT=Path(__file__).parent
MONTHS=['202606','202607','202608','202609']
SCHEMA=Path('D:/Codex/.codex/skills/amazon-traffic-sales-estimator/references/confirmed-output-schema.md')
def load(name):return json.loads((ROOT/name).read_text(encoding='utf8'))
def save(name,data):(ROOT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
def number(x):
 try:
  v=float(x)
  return v if v>=0 else None
 except (TypeError,ValueError):return None
def valid_id(a):return isinstance(a,str) and bool(re.fullmatch(r'[A-Z0-9]{10}',a))
def date(x):
 if isinstance(x,(int,float)):return x if x>0 else None
 if isinstance(x,str) and re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}',x):return x.replace('/','-')
 return None

def clean(x):return None if x in (None,'','-','--','N/A','null') else x

def first(*xs):return next((clean(x) for x in xs if clean(x) is not None),None)

def numfirst(*xs):return next((number(x) for x in xs if number(x) is not None),None)

def valid_count(v):return type(v) in (int,float) and math.isfinite(v) and v>=0 and v==int(v)

def feature_fields(a,parent,details):
 def text_for(asin):
  d=details.get(asin,{}).get('data') or {}
  return [s.strip() for s in d.get('features',[]) if isinstance(s,str) and s.strip()] if d.get('asin')==asin and isinstance(d.get('features'),list) else []
 lines=text_for(a);source=a if lines else None;state='子体详情' if lines else '未取得'
 if not lines and parent:
  lines=text_for(parent)
  if lines:source=parent;state='父体详情填充'
 return {'五点描述':'\n'.join(str(i)+'. '+s for i,s in enumerate(lines,1)) if lines else None,'五点来源':state,'五点来源ASIN':source}

def evaluation_states(a,d,failed,star):
 def count_state(field):
  if not d:return '查询失败' if failed else '未查询'
  if d.get('asin')!=a:return 'ASIN不匹配'
  if field not in d:return '字段未返回'
  v=d[field]
  if v is None or v=='':return '空值未知'
  if not valid_count(v):return '数值异常待核验'
  return '子体接口明确0' if v==0 else '子体接口值可参考'
 sr=count_state('variantRatings');sc=count_state('variantReviews')
 vr=d.get('variantRatings');vc=d.get('variantReviews')
 if valid_count(vr) and valid_count(vc) and vc>vr:sr=sc='数值异常待核验'
 ss='非明确子体口径' if star is not None else '空值未知' if d and 'rating' in d else '字段未返回' if d else '查询失败' if failed else '未查询'
 return '评分数：'+sr+'；评论数：'+sc+'；星级：'+ss

def main():
 rows=load('input_rows.json');details=load('collected_details.json');history=load('historical_evidence.json');universe=set(load('candidate_children.json'));failures=load('detail_failures.json');status=load('status.json')
 target=set(load('target_children.json')) if (ROOT/'target_children.json').exists() else {r['asin'] for r in rows}
 universe.update(target)
 old_size=-1
 while old_size!=len(universe):
  old_size=len(universe)
  for a in list(universe):
   for v in details.get(a,{}).get('data',{}).get('variationList') or []:
    if valid_id(v.get('asin')):universe.add(v['asin'])
 coverage=load('parent_history_coverage.json') if (ROOT/'parent_history_coverage.json').exists() else {}
 headers=[]
 for block in re.split(r'\n## [1-4]\. ',SCHEMA.read_text(encoding='utf8'))[1:5]:
  headers.append([line.split('|')[1].strip() for line in block.splitlines() if line.startswith('| ') and not line.startswith('| 表头')])
 assert [len(h) for h in headers]==[62,27,13,12],str([len(h) for h in headers])
 inputs={m:{r['parent']:r for r in rows if r['month']==m} for m in MONTHS}
 supplements=load('supplementary_parent_inputs.json') if (ROOT/'supplementary_parent_inputs.json').exists() else []
 for r in supplements:inputs[r['month']][r['parent']]=r
 source={r['month']+'|'+r['asin']:r for r in rows}
 origins={m:defaultdict(set) for m in MONTHS}
 for r in rows:
  todo=[r['parent'],r['asin']];seen=set()
  while todo:
   a=todo.pop()
   if a in seen:continue
   seen.add(a)
   if a in universe:origins[r['month']][a].add(r['parent'])
   for v in details.get(a,{}).get('data',{}).get('variationList') or []:
    if valid_id(v.get('asin')) and v['asin'] not in seen:todo.append(v['asin'])
 for r in supplements:
  for a in coverage.get(r['month']+'|'+r['parent'],{}).get('children',[]):origins[r['month']][a].update(r['sourceParents'])
 output=[];method=[];metrics=[];monthly_members={};family_rows=[];used_records=set();seen_children=set();parent_sources={}
 def issue(kind,parent,child,month,name,state,result,body,action='',refs='',version='child-expansion-20261021'):
  method.append(dict(zip(headers[3],[kind,parent,child,'US',month,name,state,result,body,action,refs,version])))
 issue('规则说明','','','','当前采集阶段','已说明','子体拓展与详情','当前仅展开实际返回子体并核验目标月归属。流量词及销量分摊尚未执行，相关数值留空。')
 issue('规则说明','','','','跨月流量词复用','已说明','用户已确认','下一阶段优先采7月、9月词数；6月与7月同子ASIN复用7月，8月与9月同子ASIN复用9月；仅早月存在的子体补采早月。各月父销量和子体分母分别计算。')
 issue('规则说明','','','','变体数量口径','已说明','按实际清单','不以接口变体数量与返回清单不相等判错。逐条处理实际返回候选并去重。')
 issue('规则说明','','','','月份及归属证据','已说明','来源分开保留','用户月度导出的父子记录是对应月份证据。当前详情关系只代表采集快照；目标月API与月度导出冲突时显式标记，不重复分配。')
 issue('规则说明','','','','历史父体拓展接口','已说明','competitor_lookup；variation=N','对每月输入父ASIN直接批量查询并取完分页，保留实际返回的历史子体。当前详情变体只作为候选，不据此增加历史估算范围。')
 issue('规则说明','','','','当前范围外候选详情','已说明','保留候选记录','未由当月父体完整查询或月度原表确认的当前变体，继续保留候选和原始返回，不逐个补采与目标月无直接关联的当前商品详情。')
 issue('规则说明','','','','产品筛选口径','已说明','按最新要求','排除洗衣水槽柜、独立盆台和配件、普通高柜；保留便携带水箱洗手站。')
 issue('规则说明','','','','调用限额','已说明','40次/分钟；4000次/月','前期28次/分钟，后续36次/分钟，均低于40次。套餐月上限不是账户实时余额。成功数据落盘复用，完整原始响应单独保存。')
 issue('规则说明','','','','字段复用与时点','已说明','批量JSON、原导出、已有详情合并','商品价格、Prime价格、配送费、评分、评分数量、卖家、配送方式、SKU属性优先使用对应目标月批量记录，再用同月原导出，最后以已有详情快照补充；回退字段逐行注明。标题、品牌、链接、尺寸、重量等同样复用已有响应。首次评分日期、评论数、更新时间仅用真实返回，不推算。详情接口BSR排名仅使用详情快照，历史排名另列。未为了批量接口缺少的字段对全部子体重复请求详情。')
 issue('规则说明','','','','商品数据缺失','已说明','保留空值和字段','首次评分日期、评论数、优惠券、更新时间等并非所有响应均有有效值。保留全部已确认表头；未取得数据留空，不冒充接口已返回或成功查询。无单独详情响应的子体仍可从月度批量JSON取得大部分商品字段。')
 issue('规则说明','','','','父体唯一归属判断','已说明','目标月API优先','同一子体同月多次API返回的父体一致时，优先采用同月API父体，保留原月度导出不同归属及当前快照。API父体不在当月输入范围时保留唯一归属但不挪用旧父体销量；原输入父体记录继续保留。')
 issue('规则说明','','','','币种及商品链接','已说明','USD；Amazon美国站','币种由US站点确定为USD；响应无商品链接时以真实子ASIN构造https://www.amazon.com/dp/链接。不能据链接构造声称已访问商品页面。')
 issue('规则说明','','','','归属变更家庭补采','已说明','MCP2；6个同月唯一父体；2次批量商品调用','仅追踪原输入代表商品同月API确认的新父体：8月4个、9月2个；按月合并请求并完整取回分页。新家庭父销量取该月API明确父级units，不能直接迁移旧输入父销量。原输入父体记录保留，新增对应核验家庭，不做独立父体发现。')
 issue('规则说明','','','','子体评分数与评论数','已说明','variantRatings；variantReviews','评分数量仅使用返回ASIN与目标子ASIN一致的variantRatings，评论数量仅使用variantReviews。通用ratings/reviews可能为链接或共享口径，不作为子体计数回填，原值保留JSON。子体字段缺失留空、不按0补；有效0保留。这些值是已有商品详情快照，不因关联历史销量月份而成为历史月末值。流量词统计JSON不含这些字段，不为重复取得通用计数逐个重新下载详情。商品评分星级仍为其原接口口径，不能据此声称是独立子体星级。')
 for m in MONTHS:
  members=defaultdict(list);pending=defaultdict(set);family_candidates=defaultdict(set);family_excluded=defaultdict(set);outside=0;conflicts=0
  parent_set=set(inputs[m]);eligible={}
  for a in sorted(universe):
   evidence=history.get(m+'|'+a,{});h=evidence.get('item') or {};hp=h.get('parent');src=source.get(m+'|'+a);origin=origins[m].get(a,set())
   if not origin and not src and hp not in parent_set:continue
   if evidence.get('sourceRecordId'):used_records.add(evidence['sourceRecordId'])
   drec=details.get(a,{});d=drec.get('data',{});cur=d.get('parent');owner=None;core=False;notes=[]
   for p in origin:family_candidates[p].add(a)
   if drec.get('sourceRecordId'):used_records.add(drec['sourceRecordId'])
   if src and valid_id(hp) and hp!=src['parent']:
    owner=hp;core=hp in parent_set;relation='目标月已核验'
    notes.append('月度导出父体'+src['parent']+'与同月API父体'+hp+'不同；同月API各响应归属一致，采用'+hp+'作为该月唯一父体，保留原归属证据。')
    if not core:notes.append('核验父体不在当月输入范围，不能沿用原输入父体销量。')
    issue('异常记录',src['parent'],a,m,'目标月唯一父体判断','已处理',hp,notes[-1],refs=evidence.get('sourceRecordId',''))
   elif src:
    owner=src['parent'];core=True;relation='目标月已核验';notes.append('目标月归属由用户当月卖家精灵导出确认。')
   elif valid_id(hp):
    owner=hp;relation='目标月已核验';core=hp in parent_set
    if not core:outside+=1;notes.append('目标月父体'+hp+'不在当月保留输入范围。仅保留拓展候选，不纳入该月销量分配。')
   else:
    relation='仅当前关系已核验' if valid_id(cur) else '归属缺失'
    notes.append('已由当前变体清单拓展，目标月归属未取得直接证据；不能把当前父体直接当成历史父体。')
   excluded_product=bool(re.search(r'laundry sink cabinet',str(d.get('title') or h.get('title') or '').lower()))
   if excluded_product:
    core=False;notes.append('洗衣水槽柜按最新产品范围排除；保留接口返回记录，不进入后续流量词分配清单。')
   if core:members[owner].append(a);eligible[a]=owner;family_candidates[owner].add(a)
   elif hp and hp not in parent_set or excluded_product:
    for p in origin:family_excluded[p].add(a)
   else:
    for p in origin:pending[p].add(a)
   if cur and owner and cur!=owner:notes.append('当前父体'+cur+'与目标月父体不同。')
   if not d:
    if h:notes.append('商品字段复用目标月competitor_lookup批量JSON；未额外逐子体调用详情。')
    elif src:notes.append('商品字段复用用户对应月份导出；未额外逐子体调用详情。')
    elif a in failures:notes.append('子体详情未成功取得。')
    else:notes.append('仅当前候选，未确认属于目标月份，本阶段未逐个补查其当前详情。')
   refs=[x for x in [drec.get('sourceRecordId'),evidence.get('sourceRecordId')] if x]
   if src:refs.append('源表:'+src['sourceFile']+'!'+str(src['sourceRow']))
   original_parent=inputs[m].get(owner) if core else None
   label=number(h.get('amzUnit'))
   label_scope='未知口径' if label is not None else '缺失'
   label_window='近30日参考值；以更新日期为准，不认定为自然月真实成交量' if label is not None else None
   if label is None and src and number(src['raw'].get('V')) is not None:
    label=number(src['raw'].get('V'));label_scope='未知口径';label_window='源月度导出的子体销量参考值，原始窗口尚未核实'
   sub=(h.get('subcategories') or [])
   if isinstance(sub,dict):sub=[sub]
   bsr=next((x for x in sub if str(x.get('code'))=='6810202011'),sub[0] if sub else {})
   raw=src['raw'] if src else {}
   hs=h.get('sku');hs=' | '.join(hs) if isinstance(hs,list) else hs
   sku=first(hs,src.get('sku') if src else None,' | '.join(d.get('skuList') or []))
   if not sku:
    sku=next((v.get('attribute','') for o in origin for v in details.get(o,{}).get('data',{}).get('variationList') or [] if v.get('asin')==a),'')
   brandurl=first(h.get('brandUrl'),raw.get('E'),d.get('brandUrl'))
   if brandurl and brandurl.startswith('/'):brandurl='https://www.amazon.com'+brandurl
   historical_map={'商品价格':('price','Y'),'Prime价格':('primePrice','Z'),'配送费':('deliveryPrice','AM'),'商品评分':('rating','AE'),'卖家数量':('sellers','AO')}
   numeric={name:numfirst(h.get(hf),raw.get(sf),d.get(hf)) for name,(hf,sf) in historical_map.items()}
   snapshot_fallback=[name for name,(hf,sf) in historical_map.items() if number(h.get(hf)) is None and number(raw.get(sf)) is None and number(d.get(hf)) is not None]
   if snapshot_fallback:notes.append('以下字段仅有已有详情快照，非目标月历史值：'+ '、'.join(snapshot_fallback)+'。')
   if d:notes.append('首次评分日期、商品数据更新时间及详情BSR取自已有'+str(drec.get('sourceTool') or 'asin_detail')+'商品详情对象，非按月查询。')
   exact_child=d.get('asin')==a
   child_ratings=d.get('variantRatings') if exact_child and valid_count(d.get('variantRatings')) else None
   child_reviews=d.get('variantReviews') if exact_child and valid_count(d.get('variantReviews')) else None
   if child_ratings is not None or child_reviews is not None:notes.append('评分数量使用variantRatings，评论数量使用variantReviews；仅保留实际有值的子体快照计数，不是目标月月末计数。')
   if child_ratings is not None and child_reviews is not None and child_reviews>child_ratings:notes.append('子体评论数量'+str(child_reviews)+'大于评分数量'+str(child_ratings)+'，字段时点/口径或采集值需核验；保留原值，不能视为准确性已验证。')
   if numeric['商品评分'] is not None:notes.append('商品评分为通用rating星级，未确认是子体独立星级。')
   if child_ratings is None or child_reviews is None:notes.append('子体'+('评分数量' if child_ratings is None else '')+('、' if child_ratings is None and child_reviews is None else '')+('评论数量' if child_reviews is None else '')+'未取得明确字段，留空；不把通用ratings/reviews当作子体值。')
   if h and not clean(h.get('sku')) and d.get('skuList'):notes.append('SKU属性缺失时复用已有详情快照属性。')
   if any(token in str(first(h.get('title'),raw.get('F'),d.get('title')) or '').lower() for token in ['medicine cabinet','vanity top','linen cabinet','over toilet','over the toilet','wall storage cabinet','tall bathroom storage']):
    notes.append('家族包含疑似独立盆台/镜柜/高柜等非浴室柜子体；保留家族完整证据，后续须逐SKU筛选，不能删除其权重后把整父体销量全部分给浴室柜。')
   row={
    '输入父ASIN':', '.join(sorted(origin|({src['parent']} if src else set())|({hp} if hp in parent_set and not inputs[m][hp].get('sourceType') else set()))),'核验父ASIN':owner,'子ASIN':a,'SKU属性':sku,'站点':'US','目标月份':m,'父子关系状态':relation,
    '父体实际返回子体数':None,'流量词查询状态':'未查询','父体月销量预测':number(original_parent['raw'].get('R')) if original_parent else None,'父体销量来源类型':'同月父级字段' if original_parent else '缺失',
    '子体原始销量参考值':label,'子体原始销量口径':label_scope,'子体原始销量对应月份或窗口':label_window,'子体原始销量更新日期':date(h.get('amzUnitDate')),
    '估算状态':None if core else '数据冲突' if relation=='归属冲突待核验' else '目标月归属待核验' if not hp else None,'异常说明':'；'.join(notes),
    '商品标题':first(h.get('title'),raw.get('F'),d.get('title')),'品牌':first(h.get('brand'),raw.get('D'),d.get('brand')),
    '商品链接':first(raw.get('H'),d.get('asinUrl')) or 'https://www.amazon.com/dp/'+a,'品牌链接':brandurl,'主图链接':d.get('zoomImageUrl') or first(h.get('imageUrl'),raw.get('I'),d.get('imageUrl')),
    '上架日期':first(date(h.get('availableDate')),date(raw.get('AJ')),date(d.get('availableDate'))),'首次评分日期':date(d.get('firstRatingDate')),'商品价格':numeric['商品价格'],'币种':'USD','Prime价格':numeric['Prime价格'],
    '优惠券':first(raw.get('AA'),d.get('coupon')),'配送费':numeric['配送费'],'商品尺寸':first(h.get('dimension'),raw.get('BG'),d.get('dimensions')),'商品重量':first(h.get('weight'),raw.get('BE'),d.get('weight')),'配送方式':first(h.get('fulfillment'),raw.get('AL'),d.get('fulfillment')),'商品数据更新时间':date(d.get('updatedTime')),
    '子体详情查询状态':'成功' if d else '查询失败' if a in failures else '未查询','BSR大类名称':d.get('bsrLabel'),'详情接口BSR排名':number(d.get('bsrRank')),
    '子类目列表':json.dumps(first(h.get('subcategories'),d.get('subcategories')),ensure_ascii=False) if first(h.get('subcategories'),d.get('subcategories')) else None,'类目节点ID':str(first(h.get('nodeId'),d.get('nodeId'))) if first(h.get('nodeId'),d.get('nodeId')) else None,'类目名称路径':first(h.get('nodeLabelPath'),raw.get('K'),d.get('nodeLabelPath')),
    '目标月校验类目节点':str(bsr['code']) if bsr.get('code') else '6810202011' if src and src['raw'].get('P')=='Bathroom Vanities' else None,
    '目标月校验小类BSR':number(bsr.get('rank')) if bsr else number(src['raw'].get('Q')) if src else None,
    '商品评分':numeric['商品评分'],'评分数量':child_ratings,'评论数量':child_reviews,'子体评价数据可用性':evaluation_states(a,d,a in failures,numeric['商品评分']),'卖家名称':first(h.get('sellerName'),raw.get('AP'),d.get('sellerName')),'卖家数量':numeric['卖家数量'],'关联原始记录ID':'; '.join(refs),'当前父ASIN':cur,
    '_eligible':core,'_outside_input_scope':bool(hp and hp not in parent_set and not src) or excluded_product,'_origin_parents':sorted(origin)
   }
   row.update(feature_fields(a,owner,details))
   output.append(row);seen_children.add(a)
  for row in output:
   if row['目标月份']==m and row['_eligible']:row['父体实际返回子体数']=len(members[row['核验父ASIN']])
  for parent,src in sorted(inputs[m].items()):
   meta=details.get(parent,{});d=meta.get('data',{});aa=sorted(members[parent]);pp=sorted(pending[parent]);all_returned=sorted(family_candidates[parent]);excluded=family_excluded[parent]
   representative_parent=(history.get(m+'|'+src['asin'],{}).get('item') or {}).get('parent')
   moved=not aa and valid_id(representative_parent) and representative_parent!=parent
   moved_note=('输入父体未取得目标月子体，原商品同月API唯一父体为'+representative_parent+'；'+('已完成该父体目标月拓展，由对应家庭记录承接，不重复计父销量。' if representative_parent in parent_set else '该父体不在原输入清单，新家庭完整清单待补查。')+'原导出父销量参考值='+str(src['raw'].get('R'))+'，暂不作新家庭分配基数。') if moved else ''
   supplement_note=('同月API归属核验补充家庭，来自输入父体'+', '.join(src['sourceParents'])+'。父级units取代表子体'+src['asin']+'该月返回值；家庭内返回父级units候选值='+str(src.get('returnedParentUnitValues'))+'，不相加。') if src.get('sourceType') else ''
   if moved:issue('异常记录',parent,src['asin'],m,'输入父体无子体且归属变更','已处理' if representative_parent in parent_set else '待核验',representative_parent,moved_note,refs=history.get(m+'|'+src['asin'],{}).get('sourceRecordId',''))
   family_rows.append({
    '输入父ASIN':', '.join(src['sourceParents']) if src.get('sourceType') else parent,'核验父ASIN':None if moved else parent,'站点':'US','目标月份':m,'接口变体数量':d.get('variations'),'实际返回唯一子体数':len(all_returned),
    '目标月归属已核验子体数':len(aa),'待核验子体数':len(pp),'父体月销量预测':None if moved else number(src['raw'].get('R')),'父体销量来源类型':'缺失' if moved else '同月父级字段',
    '父体销量来源接口':'competitor_lookup' if src.get('sourceType') else '卖家精灵月度导出','父体销量来源字段':'units' if src.get('sourceType') else '月销量','父体销量查询ASIN':parent if src.get('sourceType') else src['asin'],'父体销量取值依据':supplement_note if src.get('sourceType') else src['sourceFile']+'；原商品ASIN '+src['asin']+'；源行 '+str(src['sourceRow']),
    '关系清单处理状态':'仍有候选待处理' if moved and representative_parent not in parent_set else '实际返回候选已处理完' if m+'|'+parent in coverage else '查询受阻','真单子体核验状态':'已核验多子体' if len(aa)>1 else '无法确认',
    '异常说明':'当前处于子体拓展阶段，流量词、销量分摊及BSR排序校验尚未执行。'+moved_note+supplement_note+('存在仅当前关系候选，后续分配须核实。' if pp else '')+('已识别范围外候选'+str(len(excluded))+'个，不纳入本月估算。' if excluded else ''),'子体ASIN清单':', '.join(all_returned),'估算规则版本':'child-expansion-20261021'})
  monthly_members[m]={p:sorted(v) for p,v in members.items()}
  metrics.append({'month':m,'inputParents':sum(r['month']==m for r in rows),'supplementaryCanonicalParents':sum(r['month']==m for r in supplements),'verifiedChildren':len(eligible),'candidateRows':sum(r['目标月份']==m for r in output),'outsideInputScope':outside,'conflictingRows':conflicts,'pendingRelationRows':sum(r['目标月份']==m and not r['_eligible'] and not r['_outside_input_scope'] for r in output)})
  issue('验收结果','','',m,'目标月子体归属覆盖','已通过',len(eligible),'输入父体'+str(len(parent_set))+'个；目标月已核验子体'+str(len(eligible))+'个。当前候选及范围外候选继续保留并分别标明。')
 missing=universe-seen_children
 for a in sorted(missing):
  # Do not invent a historical month or parent for isolated extra results.
  d=details.get(a,{}).get('data',{})
  output.append({'子ASIN':a,'站点':'US','父子关系状态':'归属缺失','流量词查询状态':'未查询','估算状态':'目标月归属待核验','异常说明':'接口额外返回的候选，尚未建立目标月份关联。','商品标题':d.get('title'),'商品链接':d.get('asinUrl'),'主图链接':d.get('zoomImageUrl') or d.get('imageUrl'),'当前父ASIN':d.get('parent'),'子体详情查询状态':'成功' if d else '查询失败','_eligible':False})
  issue('异常记录','',a,'','额外候选关联','待核验','无目标月份','不为无归属候选补造月份或父体。')
 logrows=[]
 old=json.loads(Path('D:/Codex/Outputs/BathroomVanities_202606_work/payload_v2.json').read_text(encoding='utf8'))
 for i,r in enumerate(old['logs']):
  rid=r.get('记录ID',str(i))
  if rid not in used_records:continue
  req=json.loads(r.get('请求参数') or '{}');j=unwrap(r.get('原始返回'))
  logrows.append(dict(zip(headers[2],[rid,r['接口'],r['ASIN'],r.get('站点','US'),req.get('month'),r.get('请求参数'),r.get('调用日期'),'成功' if j.get('code')=='OK' else '失败',j.get('code'),j.get('message'),0,'复用缓存','D:/Codex/Outputs/BathroomVanities_202606_work/payload_v2.json'])))
 paths=sorted((ROOT/'raw').glob('*.json'))+[ROOT/'pilot_native_detail.json',ROOT/'history_parent_pilot.json']
 for path in paths:
  rr=json.loads(path.read_text(encoding='utf8'));req=rr['request'];q=req.get('request',req);j=unwrap(rr.get('response'));data=j.get('data');code=j.get('code',rr.get('transportError','UNKNOWN'));ok=code=='OK'
  query=q.get('asin') or q.get('q') or ', '.join(q.get('asins',q.get('asinList',[])));state='成功' if ok and data else '成功但无数据' if ok else '失败'
  message=str(j.get('message',''))
  if '额度' in message or '可用次数' in message:state='额度不足'
  if '频率' in message or '限流' in message:state='限流'
  logrows.append(dict(zip(headers[2],[path.stem,rr['tool'],query,'US',q.get('month') or q.get('historyDate'),json.dumps(q,ensure_ascii=False),None if rr.get('timestampNote') else rr.get('timestamp'),state,code,message,0,'本次调用',str(path)])))
 # Number retry attempts on the same normalized request, keeping separate failure records intact.
 repeats=Counter()
 for r in logrows:
  key=(r['接口名称'],r['请求参数JSON']);r['重试序号']=repeats[key];repeats[key]+=1
 issue('验收结果','','','','唯一子体候选保留','已通过',len(universe),'所有实际返回子体候选均保留。跨月行数不能当成跨月唯一子体数量。')
 issue('验收结果','','','','目标子体详情响应覆盖','已说明',sum(a in details for a in target),'目标子体'+str(len(target))+'；已有详情对象'+str(sum(a in details for a in target))+'；其余优先复用历史批量JSON及原导出，不因未单独查询详情而把已有字段留空。首次评分日期等未返回字段仍保留空值。')
 issue('验收结果','','','','父体月份分页覆盖','已通过' if len(coverage)==len(rows)+len(supplements) else '待核验',len(coverage),'输入父体月度记录'+str(len(rows))+'条；归属变更补充家庭'+str(len(supplements))+'条；已完整查询并取完分页'+str(len(coverage))+'条。')
 issue('验收结果','','','','采集状态','已通过' if status['stage'] in ['collection_complete','expansion_complete_with_field_gaps'] else '待核验',status['stage'],'累计保存本任务tools/call记录'+str(len(paths))+'条。完整响应保留在采集记录引用文件。本轮合并复用未增加网络调用。拓展完成不代表所有可选详情字段完整。')
 output.sort(key=lambda r:(r.get('目标月份') or '999999',r.get('核验父ASIN') or 'ZZZZZZZZZZ',r['子ASIN']))
 save('monthly_verified_children.json',monthly_members)
 save('expansion_payload.json',{'headers':headers,'detailRows':output,'parentRows':family_rows,'logRows':logrows,'methodRows':method,'metrics':metrics,'universeCount':len(universe),'targetChildCount':len(target),'targetDetailSuccess':sum(a in details for a in target),'detailSuccess':sum(a in details for a in universe),'status':status,'extraUnassignedCandidates':len(missing),'stage':'子体拓展完成，流量词未采集'})
 print(json.dumps({'metrics':metrics,'universeCount':len(universe),'detailRows':len(output),'parentRows':len(family_rows),'logRows':len(logrows),'extraUnassignedCandidates':len(missing)},ensure_ascii=True))

if __name__=='__main__':main()
