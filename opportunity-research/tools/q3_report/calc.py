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
