"""Apply confirmed verified-20261021 rules to cached June--September data."""
import json,sys,math
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path(__file__).parent
sys.path.insert(0,'D:/Codex/.codex/skills/amazon-traffic-sales-estimator/scripts')
from allocate_sales import allocate_verified_group,valid_number
load=lambda n:json.loads((ROOT/n).read_text(encoding='utf8'))
write=lambda n,v:(ROOT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
p=load('expansion_payload.json');words=load('source_keyword_counts.json');resolved=load('resolved_monthly_keyword_counts.json');hist=load('historical_evidence.json')
kwmap={(r['targetMonth'],r['childASIN']):r for r in resolved};groups=defaultdict(list);parents={(r['目标月份'],r['核验父ASIN']):(i+2,r) for i,r in enumerate(p['parentRows']) if r.get('核验父ASIN')}
scope=load('step1_macro_audit.json')['confirmedNonTargetProducts'];formulas=defaultdict(dict);engine_inputs=[];details=[];parent_calc=[];checks=[]
def col(n):
    s=''
    while n:n,d=divmod(n-1,26);s=chr(65+d)+s
    return s
hs=p['headers'][0];hp=p['headers'][1]
def ref(h,n):return col(hs.index(h)+1)+str(n)
def fmain(n,h,formula):formulas['SKU估算明细'][ref(h,n)]=formula
def fparent(n,h,formula):formulas['父体汇总'][col(hp.index(h)+1)+str(n)]=formula
def note(r,s):r['异常说明']=(r.get('异常说明') or '')+'；'+s
for n,r in enumerate(p['detailRows'],2):
    if not r.get('_eligible'):
        r['实际采用估算规则']='无法估算';r['估算状态']=r.get('估算状态') or '目标月归属待核验'
        continue
    key=(r['目标月份'],r['核验父ASIN']);groups[key].append((n,r))
    w=kwmap[(r['目标月份'],r['子ASIN'])];raw=words[w['keywordSourceMonth']+'|'+r['子ASIN']]
    assert w['available'] and valid_number(w['effectiveTotalKeywords'],True)
    r.update({'流量词数量':w['effectiveTotalKeywords'],'自然流量词数量':w['naturalKeywords'],'广告流量词数量':raw.get('ads'),'流量词查询状态':w['status']})
    r['_keywordSourceMonth']=w['keywordSourceMonth'];r['_crossMonthReuse']=w['reusedAcrossMonths'];r['_marketExcluded']=r['子ASIN'] in scope
    note(r,'词数来源月='+w['keywordSourceMonth']+('，按用户规则跨月复用' if w['reusedAcrossMonths'] else '')+'；全部词数用作权重，自然搜索词数单独保留、不相加。')
    if w['rawTotalKeywords'] is None:note(r,'接口未收录或未给词数，按已确认规则计算用0；原始缺失状态保留，不代表真实零销量。')
    if w['naturalKeywords'] is None:note(r,'自然搜索词数未取得有效数值，留空，不伪造为明确0。')
    if r['_marketExcluded']:note(r,'非浴室柜子体：'+scope[r['子ASIN']]+'；保留家庭分摊权重及结果，浴室柜市场汇总排除。')
    ids=[Path(x).stem for x in raw.get('sourceFiles') or []]
    r['关联原始记录ID']=(r.get('关联原始记录ID') or '')+'; '+'; '.join(ids)
for (m,parent),rr in groups.items():
    pn,pr=parents[(m,parent)];sales=pr.get('父体月销量预测');assert valid_number(sales)
    first,last=rr[0][0],rr[-1][0];assert len(rr)==pr['目标月归属已核验子体数']
    single=False;single_evidence=None
    if len(rr)==1:
        child=rr[0][1]['子ASIN'];h=(hist.get(m+'|'+child) or {}).get('item') or {}
        single=h.get('variations')==1
        if single:single_evidence='目标月完整实际清单仅一子体，且该月商品记录variations=1'
    pr['真单子体核验状态']='已核验单子体' if single else '已核验多子体' if len(rr)>1 else '无法确认'
    children=[]
    for n,r in rr:
        w=kwmap[(m,r['子ASIN'])];h=(hist.get(m+'|'+r['子ASIN']) or {}).get('item') or {};label=r.get('子体原始销量参考值')
        children.append({'child_asin':r['子ASIN'],'month':m,'keyword_source_month':w['keywordSourceMonth'],'keyword_count':w['rawTotalKeywords'],'query_success':w['rawTotalKeywords'] is not None,'raw_child_monthly_sales':label,'interval_lower':label if valid_number(label) and label>0 else None,'interval_upper':None,'interval_window_verified':False,'bsr':r.get('目标月校验小类BSR'),'bsr_node':r.get('目标月校验类目节点'),'bsr_month':m if r.get('目标月校验类目节点') else None})
    g={'rule_version':'verified-20261021','parent_asin':parent,'marketplace':'US','month':m,'parent_sales_month':m,'parent_monthly_sales':sales,'parent_sales_scope':'proxy' if pr.get('父体销量来源类型')=='子体代理' else 'parent','proxy_authorized':True,'relationship_verified_target_month':True,'relationship_conflict':False,'children_complete':True,'expected_child_count':len(rr),'keyword_scope':'child','keyword_minimum':1,'missing_keywords_as_zero':True,'single_child_verified':single,'single_child_evidence':single_evidence,'legacy_correction_enabled':False,'use_hard_intervals':True,'eligible':True,'bsr_node':'6810202011','children':children}
    dd,pc=allocate_verified_group(g);engine_inputs.append(g);details.extend(dd);parent_calc.append(pc)
    denominator=sum(r['流量词数量'] for n,r in rr)
    for (n,r),d in zip(rr,dd):
        assert r['子ASIN']==d['child_asin']
        r.update({'父体全部子体流量词合计':denominator,'子体流量词占比':d['share'],'父体月销量预测':sales,'父体销量来源类型':pr['父体销量来源类型'],'流量词基础估算销量':d['base_estimated_child_sales'],'最终SKU月销量估算':d['estimated_child_sales'],'旧版规则对照销量':d['legacy_estimated_child_sales']})
        r['实际采用估算规则']='真单子体回填' if d['rule_applied']=='single_child_fallback' and d['status']=='ok' else '流量词比例分摊' if d['status']=='ok' else '无法估算'
        warn=r['流量词查询状态'] not in ('成功有词','成功返回0') or r['_crossMonthReuse'] or d['soft_interval_conflict'] or d['bsr_check'] or r['_marketExcluded']
        r['估算状态']=('可估算但需核验' if warn else '可估算') if d['status']=='ok' else '全体无词无法分摊' if 'zero_denominator' in d['status'] else '父销量缺失' if 'missing_parent_sales' in d['status'] else '数据冲突'
        if d['rule_applied']=='single_child_fallback' and d['status']=='ok':note(r,'真单子体无词回填父体月预测；证据：'+single_evidence+'。')
        if d['status']!='ok':note(r,'家庭全部词数为0且无真单子体回填依据，估算留空；未匹配不代表实际零销量。')
        if d['soft_interval_conflict']:note(r,'词数分摊值低于子体销量参考值；该参考值的来源/窗口未对齐，仅提示，不机械替换。')
        if d['legacy_estimated_child_sales'] is not None and abs(d['legacy_estimated_child_sales']-(d['base_estimated_child_sales'] or 0))>1e-9:note(r,'旧4.5/1.5规则仅保留在隐藏对照列，主结果执行已确认优化规则。')
        if r.get('目标月校验类目节点')!='6810202011':r['BSR校验状态']='同期或节点证据不足'
        elif not valid_number(r.get('目标月校验小类BSR')) or not r.get('目标月校验小类BSR'):r['BSR校验状态']='排名缺失'
        else:
            ranks={x.get('目标月校验小类BSR') for _,x in rr if x.get('目标月校验类目节点')=='6810202011' and x.get('目标月校验小类BSR')}
            r['BSR校验状态']='共享排名不适用' if len(rr)>1 and len(ranks)==1 else '发现排序异常' if d['bsr_check'] else '未发现排序异常'
        if d['bsr_check']:note(r,'同月同类目BSR与估算销量稠密排名差超旧规则阈值，只作提示，不改销量。')
        fmain(n,'父体月销量预测',f"='父体汇总'!M{pn}")
        fmain(n,'父体全部子体流量词合计',f"='父体汇总'!L{pn}")
        fmain(n,'子体流量词占比',f'=IF(M{n}>0,I{n}/M{n},'+('1)' if single else '"")'))
        fmain(n,'流量词基础估算销量',f'=IF(ISNUMBER(N{n}),N{n}*O{n},"")')
        fmain(n,'最终SKU月销量估算',f'=IF(ISNUMBER(U{n}),U{n},"")')
        fmain(n,'旧版规则对照销量',f'=IF(ISNUMBER(U{n}),IF(AND(ISNUMBER(Q{n}),Q{n}>0,O{n}>4.5*Q{n}),1.5*Q{n},U{n}),"")')
    sum_final=sum(d['estimated_child_sales'] for d in dd) if all(d['estimated_child_sales'] is not None for d in dd) else None
    share=sum(d['share'] for d in dd) if all(d['share'] is not None for d in dd) else None
    if sum_final is not None:assert math.isclose(sum_final,sales,abs_tol=1e-8)
    pr.update({'有词子体数':sum(r['流量词数量']>0 for _,r in rr),'成功返回0词子体数':sum(r['流量词查询状态']=='成功返回0' for _,r in rr),'词数缺失或查询失败子体数':sum(r['流量词查询状态'] not in ['成功有词','成功返回0'] for _,r in rr),'家庭流量词合计':denominator,'子体最终估算销量合计':sum_final,'与父体销量差额':sum_final-sales if sum_final is not None else None,'子体分摊比例合计':share,'家庭估算状态':'无法估算' if sum_final is None else '可估算但需核验' if any(r['估算状态']=='可估算但需核验' for _,r in rr) else '可估算','估算规则版本':'verified-20261021 + source-counts/reuse-20261023'})
    pr['异常说明']=(pr.get('异常说明') or '').replace('当前处于子体拓展阶段，流量词、销量分摊及BSR排序校验尚未执行。','')+'按本月核验清单分摊；词数按确认的7月/9月跨月复用规则；家庭缺失词数按0。'+('家庭全体无词且不满足真单子体回填，未分配父销量。' if sum_final is None else '')
    if single_evidence:pr['异常说明']+='真单子体证据：'+single_evidence+'。'
    rg=lambda column:f"'SKU估算明细'!{column}{first}:{column}{last}"
    fparent(pn,'有词子体数',f'=COUNTIF({rg("I")},">0")')
    fparent(pn,'成功返回0词子体数',f'=COUNTIF({rg("L")},"成功返回0")')
    fparent(pn,'词数缺失或查询失败子体数',f'=COUNTIF({rg("L")},"未收录")+COUNTIF({rg("L")},"成功但词数缺失")+COUNTIF({rg("L")},"查询失败")')
    fparent(pn,'家庭流量词合计',f'=SUM({rg("I")})')
    fparent(pn,'子体最终估算销量合计',f'=IF(COUNT({rg("V")})=0,"",SUM({rg("V")}))')
    fparent(pn,'与父体销量差额',f'=IF(ISNUMBER(S{pn}),S{pn}-M{pn},"")')
    fparent(pn,'子体分摊比例合计',f'=IF(COUNT({rg("N")})=0,"",SUM({rg("N")}))')
    checks.append({'month':m,'parent':parent,'children':len(rr),'parentSales':sales,'allocatedSales':sum_final,'difference':sum_final-sales if sum_final is not None else None,'singleVerified':single,'status':pc['status']})
for pr in p['parentRows']:
    if (pr['目标月份'],pr.get('核验父ASIN')) not in groups:
        pr['家庭估算状态']='无法估算';pr['估算规则版本']='verified-20261021 + source-counts/reuse-20261023'
        pr['异常说明']=(pr.get('异常说明') or '').replace('当前处于子体拓展阶段，流量词、销量分摊及BSR排序校验尚未执行。','')
for r in p['methodRows']:
    if r.get('事项')=='当前采集阶段':pass
    for h,v in r.items():
        if isinstance(v,str):r[h]=v.replace('当前仅展开实际返回子体并核验目标月归属。流量词及销量分摊尚未执行，相关数值留空。','已完成词数统计与四个月SKU销量分摊。保留原始缺失状态、跨月来源与估算异常。').replace('子体拓展与详情','SKU销量估算完成').replace('下一阶段优先采7月、9月词数','本次已采7月、9月词数')
mh=p['headers'][3]
def method(month,name,result,body,state='已说明'):
    p['methodRows'].append(dict(zip(mh,['规则说明','','','US',month,name,state,result,body,'','', 'verified-20261021 + source-counts/reuse-20261023'])))
method('','估算主公式','父体月预测×子词数/家庭子词数之和','全部词数用keywords，自然搜索词数单独保留。旧版4.5/1.5仅作隐藏对照；参考销量窗口未知时不作硬区间或中点替换。')
method('','子体评价数据可用性','已新增确认列','按评分数、评论数、星级分别标记。数字0与空值、未返回、异常分开。仅详情明确variantRatings/variantReviews用于子体计数；通用星级未确认独立子体口径。未重复调用接口补空值。')
method('','产品范围与家庭分母','保留全部家庭子体','已确认非浴室柜子体同样参与家庭分母；浴室柜市场汇总排除这些SKU分配值，不将其份额转给其他浴室柜子体。')
metrics=[]
for m in ['202606','202607','202608','202609']:
    rows=[r for r in p['detailRows'] if r.get('_eligible') and r['目标月份']==m];pp=[x for x in checks if x['month']==m]
    metric={'month':m,'eligibleSKUCount':len(rows),'estimatedSKUCount':sum(r.get('最终SKU月销量估算') is not None for r in rows),'unestimatedSKUCount':sum(r.get('最终SKU月销量估算') is None for r in rows),'estimatedFamilies':sum(x['allocatedSales'] is not None for x in pp),'unestimatedFamilies':sum(x['allocatedSales'] is None for x in pp),'parentForecastTotal':sum(x['parentSales'] for x in pp),'allocatedTotalAllFamilyChildren':sum(x['allocatedSales'] or 0 for x in pp),'bathroomOnlyAllocatedTotal':sum(r.get('最终SKU月销量估算') or 0 for r in rows if not r['_marketExcluded']),'nonTargetAllocatedTotal':sum(r.get('最终SKU月销量估算') or 0 for r in rows if r['_marketExcluded']),'unallocatedParentForecast':sum(x['parentSales'] for x in pp if x['allocatedSales'] is None),'singleChildFallbacks':sum(r['实际采用估算规则']=='真单子体回填' for r in rows),'crossMonthReuseRows':sum(r['_crossMonthReuse'] for r in rows)}
    metrics.append(metric)
    method(m,'月度估算结果',metric['bathroomOnlyAllocatedTotal'],'浴室柜可估算销量合计；目标月SKU '+str(metric['eligibleSKUCount'])+'条，可估算 '+str(metric['estimatedSKUCount'])+'条，未估算 '+str(metric['unestimatedSKUCount'])+'条。未能分摊的父体月预测 '+str(metric['unallocatedParentForecast'])+'件，不能当作0或加到已估算结果。','已通过')
assert len({(r.get('目标月份'),r['子ASIN']) for r in p['detailRows']})==len(p['detailRows'])
assert len(details)==10831 and sum(x['crossMonthReuseRows'] for x in metrics)==3930
assert all(x['difference'] is None or abs(x['difference'])<1e-8 for x in checks)
p.update({'formulas':dict(formulas),'salesMetrics':metrics,'stage':'SKU销量估算完成','ruleVersion':'verified-20261021 + source-counts/reuse-20261023'})
write('sales_payload.json',p);write('sales_engine_inputs.json',engine_inputs);write('sales_engine_details.json',details);write('sales_engine_parent_results.json',parent_calc);write('sales_calculation_audit.json',{'familiesChecked':len(checks),'allCalculatedFamiliesReconciled':True,'monthly':metrics,'families':checks,'newAPICalls':0})
print(json.dumps({'families':len(checks),'rows':len(details),'metrics':metrics,'formulaCounts':{k:len(v) for k,v in formulas.items()}},ensure_ascii=True))
