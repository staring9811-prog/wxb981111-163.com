import sqlite3,json,collections as C,amzfix,sizeband
AMZW=sizeband.amz_band()
FIX,_=amzfix.corrections()
c=sqlite3.connect('pdt.sqlite3'); q=lambda s,*a:c.execute(s,a).fetchall()
out={}
# Amazon totals
_mu=C.Counter()
_mr=C.Counter()  # 销售额 = 每个子体（修正后的子体销量 × 它自己的售价）求和，和销量同一口径
for i,m,u,p in q("select item_id,month,coalesce(json_extract(raw,'$.child_units'),units),price from snapshot where channel='amazon'"):
    uu=FIX.get((i,m),u or 0) or 0; _mu[m]+=uu; _mr[m]+=uu*(p or 0)
out['amz_month']=[dict(m=m,u=_mu[m],r=_mr[m],n=n) for m,n in q("select month,count(*) from snapshot where channel='amazon' group by 1 order by 1")]
tags=C.defaultdict(dict)
for i,t,v in q("select item_id,tag,value from tag where channel='amazon'"): tags[i][t]=v
snap=[(i,m,FIX.get((i,m),u),p) for i,m,u,p in q("select item_id,month,coalesce(json_extract(raw,'$.child_units'),units),price from snapshot where channel='amazon'")]
snap=[x for x in snap if x[2] and x[2]>0]
def band(p):
    if p is None: return ''
    return '<$200' if p<200 else '$200–399' if p<400 else '$400–699' if p<700 else '$700–999' if p<1000 else '≥$1000'
dims=['尺寸段','形态','装','主色','柜体材质','台面材质','元素','价位']
import csv as _csv0
_DM={'拆装':'装','尺寸':'尺寸段','台面':'台面材质','柜体':'柜体材质','价格带':'价位'}
import os as _os
_PDP=json.load(open('amz_pdp_tags.json',encoding='utf-8')) if _os.path.exists('amz_pdp_tags.json') else {}
def _bandw(w):
    return next((bb for lo,hi,bb in [(15,21,'18″'),(21,26,'24″'),(26,29,'28″'),(29,33,'30″'),(33,39,'36″'),(39,45,'42″'),(45,54,'48″'),(54,66,'60″'),(66,999,'72″+')] if lo<=w<hi),None)
_PDPB={a:{'陶瓷':'陶瓷','树脂':'树脂','CM':'Cultured Marble'}[p['basin']] for a,p in _PDP.items() if p.get('basin') in ('陶瓷','树脂','CM') and not (p.get('width') and _bandw(p['width']) and AMZW.get(a) and _bandw(p['width'])!=AMZW.get(a))}
_OVA={(r['商品ID'],_DM.get(r['属性'],r['属性'])):r['改成'] for r in _csv0.DictReader(open('tag_override.csv',encoding='utf-8')) if r['渠道']=='amazon'}
share=C.defaultdict(lambda:C.defaultdict(C.Counter))  # dim->month->value
for i,m,u,p in snap:
    tg=tags.get(i,{})
    for d in dims:
        v=band(p) if d=='价位' else ((AMZW.get(i) or tg.get(d,'')) if d=='尺寸段' else tg.get(d,''))
        if d=='装' and p:   # 价格线（与 calc3 一致）：高于整装线 → 整装；低于拆装线 → 拆装
            _sz=AMZW.get(i) or tg.get('尺寸段','')
            if p>={'18″':400,'24″':500,'28″':800,'30″':800,'36″':1000,'42″':1200,'48″':1200,'60″':1500,'72″+':1500}.get(_sz,1e9): v='整装'
            elif p<{'18″':300,'24″':300,'28″':300,'30″':400,'36″':400,'42″':500,'48″':500,'60″':500,'72″+':500}.get(_sz,0): v='拆装'
            if v=='拆装':   # 石材台面拆装（与 calc3 一致）
                _tv=tg.get('台面材质') or '未标'
                if _tv in ('陶瓷','树脂','未标') and i in _PDPB: _tv=_PDPB[i]
                if _tv in ('未标',''): _tv=(_PDP.get(i) or {}).get('top') or _tv
                _tv=_OVA.get((i,'台面材质'),_tv); _pa_=(_PDP.get(i) or {}).get('asm')
                _ln={'18″':450,'24″':450,'28″':500,'30″':500,'36″':550,'42″':700,'48″':700,'60″':1000,'72″+':1200}.get(_sz)
                if _tv in ('石英石','岗石','卡拉拉大理石','岩板') and (_pa_=='整装' or (_pa_ is None and _ln and p>=_ln)): v='整装'
        if d=='台面材质' and (v or '未标') in ('陶瓷','树脂','未标') and i in _PDPB: v=_PDPB[i]   # 商品页明确写了的按页面
        elif d=='台面材质' and p and (v or '未标') in ('陶瓷','未标'):   # 大尺寸树脂盆规则（只对页面没写的；与 calc3 一致）
            _sz=AMZW.get(i) or tg.get('尺寸段','')
            _k=tg.get('装')
            if p>={'18″':400,'24″':500,'28″':800,'30″':800,'36″':1000,'42″':1200,'48″':1200,'60″':1500,'72″+':1500}.get(_sz,1e9): _k='整装'
            elif p<{'18″':300,'24″':300,'28″':300,'30″':400,'36″':400,'42″':500,'48″':500,'60″':500,'72″+':500}.get(_sz,0): _k='拆装'
            if _k=='拆装' and p<{'48″':700,'60″':1000,'72″+':900}.get(_sz,0): v='树脂'
        if not v or v=='未标':   # 原来没标的，用商品页补（与 calc3 一致）
            _pp=_PDP.get(i) or {}
            v={'台面材质':_pp.get('top'),'柜体材质':{'实木':'实木框架','实木框架':'实木框架','MDF':'MDF','人造板（未细分）':'MDF','含刨花板':'含刨花板','含胶合板':'含胶合板'}.get(_pp.get('cab')),'主色':_pp.get('color'),'元素':_pp.get('elem')}.get(d) or v
        if d=='柜体材质' and v=='实木': v='实木框架'
        if d=='形态' and v=='落地式' and (_PDP.get(i) or {}).get('struct')=='开放式': v='开放式'   # 与 calc3 一致
        if (i,d) in _OVA: v=_OVA[(i,d)]
        if d=='元素' and v: v=v.split('|')[0].split('+')[-1] if v.startswith('纯色+') else v.split('+')[0] if v.startswith('夏克式+') else v
        share[d][m][v or '未标']+=u
out['amz_share']={d:{m:dict(cn) for m,cn in ms.items()} for d,ms in share.items()}
# channels 2026-01..10
cur={'homedepot':10,'lowes':12,'wayfair':11}
ch={}
for chn,vid in cur.items():
    prod={r[0]:r[1:] for r in q("select pid,color,cab,top,price,elements from research_product where version_id=?",vid)}
    agg=C.defaultdict(C.Counter); mon=C.Counter()
    for pid,size,asm,form,m,u in q("select pid,size,asm,form,month,units from research_monthly where version_id=? and month between '2026-01' and '2026-10'",vid):
        if not u: continue
        mon[m]+=u
        pr=prod.get(pid,('','','',None,''))
        for d,v in [('尺寸段',size),('形态',form),('装',asm),('主色',pr[0]),('柜体材质',pr[1]),('台面材质',pr[2]),('价位',band(pr[3]))]:
            agg[d][v or '未标']+=u
    ch[chn]=dict(month=dict(mon),share={d:dict(v) for d,v in agg.items()},nprod=q("select count(distinct pid),count(distinct fam) from research_product where version_id=?",vid)[0])
# Amazon same period
agg=C.defaultdict(C.Counter)
for d,ms in share.items():
    for m,cn in ms.items():
        if '2026-01'<=m<='2026-10': agg[d].update(cn)
ch['amazon']=dict(month={r['m']:r['u'] for r in out['amz_month'] if '2026-01'<=r['m']<='2026-10'},share={d:dict(v) for d,v in agg.items()})
out['ch']=ch
out['sv']=[list(r) for r in q("select dim,value,source,keyword,month,volume from search_volume where dim!='尺寸'")]
json.dump(out,open('data.json','w'),ensure_ascii=False)
for chn,v in ch.items():
    t=sum(v['month'].values()); print(chn,round(t), v.get('nprod'))
    for d in ['尺寸段','形态','装','主色','柜体材质','台面材质','价位']:
        s=v['share'].get(d,{}); tt=sum(s.values()) or 1
        print('  ',d,sorted([(k,round(100*x/tt)) for k,x in s.items()],key=lambda z:-z[1])[:7])
