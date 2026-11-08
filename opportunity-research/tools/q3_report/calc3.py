import os
import q3paths
import sqlite3,json,glob,os,collections as C,statistics as S
c=sqlite3.connect('pdt.sqlite3'); q=lambda s,*a:c.execute(s,a).fetchall()
RAW=q3paths.INPUT+'/渠道关键词/大词'   # 小平台评论星级（只在目录存在时读；当前报告小平台不算 3M 评分变化）
W=['2026-08','2026-09','2026-10']; P=['2026-05','2026-06','2026-07']; M=[f'2026-{i:02d}' for i in range(1,11)]
ANC='36″'; UNK={'','未知','未标','多尺寸未拆',None}
def nz(v): return '未标' if v in UNK else v
def band(p):
    if p is None: return '未标'
    return '<$200' if p<200 else '$200–399' if p<400 else '$400–699' if p<700 else '$700–999' if p<1000 else '≥$1000'
def elem(v):
    if not v: return '未标'
    v=v.split('|')[0]
    if v.startswith('纯色+'): return v.split('+')[-1]
    if v.startswith('夏克式+'): return '夏克式'
    return v
recs={}   # ch -> list of dict(pid,fam,brand,attrs,price,rating,u{month:units},vp{},nv{})
stars={}  # ch -> pid -> list (month,stars)
# Amazon
import sizeband
AMZW=sizeband.amz_band()
tags=C.defaultdict(dict)
for i,t,v in q("select item_id,tag,value from tag where channel='amazon'"): tags[i][t]=v
pinfo={i:(p or f,b) for i,p,f,b in q("select item_id,parent,family_key,brand from product where channel='amazon'")}
import amzfix
FIX,_=amzfix.corrections()
A=C.defaultdict(lambda:dict(u={},r={},price=None,rating=None))
for i,m,u,p,r,cu in q("select item_id,month,units,price,rating,json_extract(raw,'$.child_units') from snapshot where channel='amazon' and month>='2026-01' order by month"):
    a=A[i]; a['u'][m]=FIX.get((i,m),(cu if cu is not None else u) or 0)
    if r: a['r'][m]=r; a['rating']=r
    if p: a['price']=p
L=[];LALL=[]   # LALL：2026 年出现过的全部子体（交叉筛选算 1–10 月趋势用，避免 1–4 月只卖过的商品被漏掉）
for i,a in A.items():
    tg=tags.get(i,{}); fam,br=pinfo.get(i,(i,''))
    LALL.append(dict(pid=i,fam=fam,brand=br or '未知品牌',price=a['price'],rating=a['rating'],u=a['u'],r=a['r'],
      at={'尺寸':AMZW.get(i) or nz(tg.get('尺寸段')),'形态':nz(tg.get('形态')),'拆装':nz(tg.get('装')),'台面':nz(tg.get('台面材质')),'柜体':nz(tg.get('柜体材质')),'主色':nz(tg.get('主色')),'元素':elem(tg.get('元素')),'价格带':band(a['price'])},
      listed=any(m in a['u'] for m in W)))
    if any(m in a['u'] for m in W+P): L.append(LALL[-1])
recs['amazon']=L
# small platforms
V={'homedepot':10,'lowes':12,'wayfair':11}
for ch,v in V.items():
    pr={r[0]:dict(zip(['pid','fam','brand','top','color','cab','price','rating','reviews'],r)) for r in q("select pid,fam,brand,top,color,cab,price,rating,reviews from research_product where version_id=?",v)}
    fb=C.defaultdict(list)
    for x in pr.values(): fb[x['fam']].append(x)
    def fill(x,k):
        if x[k] not in UNK: return x[k]
        best=sorted([y for y in fb[x['fam']] if y[k] not in UNK],key=lambda y:-(y['reviews'] or 0))
        return best[0][k] if best else None
    G=C.defaultdict(lambda:dict(u=C.Counter(),vp=C.Counter(),nv=C.Counter()))
    meta={}
    for pid,size,asm,form,m,vp_,nv_,u in q("select pid,size,asm,form,month,vp,nonvp,units from research_monthly where version_id=?",v):
        k=(pid,nz(size)); g=G[k]; g['u'][m]+=u or 0; g['vp'][m]+=vp_ or 0; g['nv'][m]+=nv_ or 0; meta[k]=(asm,form)
    L=[]
    for (pid,size),g in G.items():
        x=pr.get(pid)
        if not x: continue
        price=fill(x,'price'); rating=fill(x,'rating'); br=fill(x,'brand')
        asm,form=meta[(pid,size)]
        L.append(dict(pid=pid,fam=x['fam'],brand=br or '未知品牌',price=price,rating=rating,u=dict(g['u']),vp=dict(g['vp']),nv=dict(g['nv']),
          at={'尺寸':size,'形态':nz(form),'拆装':nz(asm),'台面':nz(x['top']),'柜体':nz(x['cab']),'主色':nz(x['color']),'元素':'未标','价格带':band(price)},listed=True))
    # products without monthly rows still count as SKU
    seen={r['pid'] for r in L}
    for pid,x in pr.items():
        if pid in seen: continue
        price=fill(x,'price')
        L.append(dict(pid=pid,fam=x['fam'],brand=fill(x,'brand') or '未知品牌',price=price,rating=fill(x,'rating'),u={},vp={},nv={},
          at={'尺寸':'未标','形态':'未标','拆装':'未标','台面':nz(x['top']),'柜体':nz(x['cab']),'主色':nz(x['color']),'元素':'未标','价格带':band(price)},listed=True))
    recs[ch]=L
import clean_recs as _cr
_o,_ex=_cr.load(); recs.update(_o); print('小平台换成干净父体数据',{k:len(v) for k,v in _o.items()},'剔除非浴室柜',len(_ex))
# 整装价格线：某尺寸售价 ≥ 线价，一律按整装（wen 2026-11-07 定：贵的大柜子不可能是拆装）
ASM_LINE={'18″':400,'24″':500,'28″':800,'30″':800,'36″':1000,'42″':1200,'48″':1200,'60″':1500,'72″+':1500}
_fl=[]
for _ch,_L in list(recs.items())+[('amazon',LALL)]:
    for _r in _L:
        _ln=ASM_LINE.get(_r['at'].get('尺寸')); _p=_r.get('price')
        if _ln and _p and _p>=_ln and _r['at'].get('拆装')!='整装':
            _fl.append((_ch,_r['pid'],_r['brand'],_r['at']['尺寸'],_p,str(_r['at'].get('拆装'))+' → 整装',round(sum(_r['u'].get(m,0) for m in ('2026-08','2026-09','2026-10'))/3,1)))
            _r['at']['拆装']='整装'
# 拆装价格线（只用于 Amazon；线下渠道便宜款多是整装，不能套）：售价低于线价一律拆装
KD_LINE={'18″':300,'24″':300,'28″':300,'30″':400,'36″':400,'42″':500,'48″':500,'60″':500,'72″+':500}
_seen=set()
for _r in recs['amazon']+LALL:
    if id(_r) in _seen: continue
    _seen.add(id(_r))
    _ln=KD_LINE.get(_r['at'].get('尺寸')); _p=_r.get('price')
    if _ln and _p and _p<_ln and _r['at'].get('拆装')!='拆装':
        _fl.append(('amazon',_r['pid'],_r['brand'],_r['at']['尺寸'],_p,_r['at'].get('拆装')+' → 拆装',round(sum(_r['u'].get(m,0) for m in ('2026-08','2026-09','2026-10'))/3,1)))
        _r['at']['拆装']='拆装'
# 商品页明确写了台盆材质的，按页面算（wen 2026-11-08：写了是什么就是什么）。只改一体台盆类（陶瓷/树脂/未标），石材、木板台面不动。
import json as _js
_PDP=_js.load(open('amz_pdp_tags.json',encoding='utf-8')) if os.path.exists('amz_pdp_tags.json') else {}
_BM={'陶瓷':'陶瓷','树脂':'树脂','CM':'Cultured Marble'}
def _pdp_ok(pid,size):
    p=_PDP.get(pid)
    if not p or p.get('basin') not in _BM: return None
    w=p.get('width')
    if w:
        b=next((bb for lo,hi,bb in [(15,21,'18″'),(21,26,'24″'),(26,29,'28″'),(29,33,'30″'),(33,39,'36″'),(39,45,'42″'),(45,54,'48″'),(54,66,'60″'),(66,999,'72″+')] if lo<=w<hi),None)
        if b and b!=size: return None   # 页面已被改成别的尺寸，不采信
    return _BM[p['basin']]
_seen=set();_pdpn=0
for _r in recs['amazon']+LALL:
    if id(_r) in _seen: continue
    _seen.add(id(_r))
    _b=_pdp_ok(_r['pid'],_r['at'].get('尺寸'))
    _r['_pdp']=bool(_b)
    if _b and _r['at'].get('台面') in ('陶瓷','树脂','未标') and _r['at']['台面']!=_b:
        _r['at']['台面']=_b; _pdpn+=1
print('按商品页改台盆',_pdpn,'条（商品页已抓',len(_PDP),'）')
# 原来没标的属性，用商品页（标题、五点、规格表）补上
_CABM={'实木':'实木','实木框架':'实木框架','MDF':'MDF','含刨花板':'含刨花板','含胶合板':'含胶合板'}
_fill=C.Counter();_seen=set()
for _r in recs['amazon']+LALL:
    if id(_r) in _seen: continue
    _seen.add(id(_r)); _p=_PDP.get(_r['pid'])
    if not _p: continue
    a=_r['at']
    for k,v in (('台面',_p.get('top')),('柜体',_CABM.get(_p.get('cab'))),('主色',_p.get('color')),('元素',_p.get('elem'))):
        if v and a.get(k) in ('未标',None,''): a[k]=v; _fill[k]+=1
print('用商品页补未标',dict(_fill))
# 大尺寸树脂盆规则（wen 2026-11-08）：拆装、48″ 及以上、售价低于线价，台面标的是陶瓷或没标 → 树脂盆。
# 高于线价的多是石材台面；木板台面、不含台面不动。
RESIN_LINE={'48″':700,'60″':1000,'72″+':900}
_seen=set()
for _r in recs['amazon']+LALL:
    if id(_r) in _seen: continue
    _seen.add(id(_r))
    _ln=RESIN_LINE.get(_r['at'].get('尺寸')); _p=_r.get('price')
    if _ln and _p and _p<_ln and not _r.get('_pdp') and _r['at'].get('拆装')=='拆装' and _r['at'].get('台面') in ('陶瓷','未标'):
        _fl.append(('amazon',_r['pid'],_r['brand'],_r['at']['尺寸'],_p,str(_r['at'].get('台面'))+' → 树脂（大尺寸价格线）',round(sum(_r['u'].get(m,0) for m in ('2026-08','2026-09','2026-10'))/3,1)))
        _r['at']['台面']='树脂'
# 人工改标（最高优先级，覆盖打标和价格线）：tag_override.csv 每行 渠道,商品ID,属性,改成
import csv as _csv0
_OV=[r for r in _csv0.DictReader(open('tag_override.csv',encoding='utf-8'))]
for _ch,_L in list(recs.items())+[('amazon',LALL)]:
    _ix={}
    for _r in _L: _ix.setdefault(_r['pid'],[]).append(_r)
    for _o in _OV:
        if _o['渠道']==_ch:
            for _r in _ix.get(_o['商品ID'],[]): _r['at'][_o['属性']]=_o['改成']
print('人工改标',len(_OV),'条')
import csv as _csv
with open('asm_flips.csv','w',encoding='utf-8-sig',newline='') as _f:
    _w=_csv.writer(_f); _w.writerow(['渠道','商品ID','品牌','尺寸','售价','原标','近3月月均销量']); _w.writerows(sorted(_fl,key=lambda x:-x[6]))
print('按价格线改标',len(_fl),'其中改拆装',sum(1 for x in _fl if x[5].endswith('拆装')),{c:sum(1 for x in _fl if x[0]==c) for c in recs})
# review stars
st=C.defaultdict(list)
for i,m,s in q("select item_id,month,stars from channel_hist_review where channel='homedepot' and stars is not null and month between '2026-05' and '2026-10'"): st[i].append((m,s))
stars['homedepot']=st
st=C.defaultdict(list)
for f in glob.glob(RAW+'/lowes_reviews/*.json'):
    d=json.load(open(f))
    for x in (d.get('reviews') or {}).values():
        if x.get('r') and '2026-05'<=x['d'][:7]<='2026-10': st[x.get('pid') or os.path.basename(f)[:-5]].append((x['d'][:7],x['r']))
stars['lowes']=st
st=C.defaultdict(list); seenr=set()
def wf(pid,rv):
    for x in rv:
        dt=x.get('date') or ''
        if len(dt)!=10 or not x.get('rating'): continue
        m=f'{dt[6:10]}-{dt[0:2]}'
        key=(pid,dt,x.get('rating'),(x.get('text') or '')[:30])
        if key in seenr: continue
        seenr.add(key)
        if '2026-05'<=m<='2026-10': st[pid].append((m,x['rating']))
for f in glob.glob(RAW+'/pdp/wayfair/*.json'):
    d=json.load(open(f)); wf(os.path.basename(f)[:-5], d.get('reviews_embedded') or [])
for f in glob.glob(RAW+'/wayfair_apify/wayfair/apify/*.json'):
    d=json.load(open(f)); wf(os.path.basename(f)[:-5], d['item'].get('reviews') or [])
stars['wayfair']=st
for ch in stars: print(ch,'review pids',len(stars[ch]),'reviews',sum(len(v) for v in stars[ch].values()))

for _ch in ('homedepot','lowes','wayfair'): stars[_ch]={}   # 小平台按父体，不做 3M 评分变化
def metrics(ch,rows,tot_u,tot_sku):
    pids={r['pid'] for r in rows}
    w=sum(sum(r['u'].get(m,0) for m in W) for r in rows)/3
    p=sum(sum(r['u'].get(m,0) for m in P) for r in rows)
    def wavg(key,flt=lambda r:True):
        n=d=0
        for r in rows:
            if not flt(r) or r[key] is None: continue
            uu=sum(r['u'].get(m,0) for m in W); n+=uu*r[key]; d+=uu
        return n/d if d else None
    sz=C.Counter()
    for r in rows: sz[r['at']['尺寸']]+=sum(r['u'].get(m,0) for m in W)
    sz.pop('未标',None)
    anc_u=sum(sum(r['u'].get(m,0) for m in W) for r in rows if r['at']['尺寸']==ANC)/3
    anc_p=wavg('price',lambda r:r['at']['尺寸']==ANC)
    # rating change
    if ch=='amazon':
        def pr_(ms):
            n=d=0
            for r in rows:
                for m in ms:
                    if m in r['r'] and r['u'].get(m): n+=r['u'][m]*r['r'][m]; d+=r['u'][m]
            return n/d if d else None
        a,b=pr_(W),pr_(P); rc=dict(d=(a-b) if a and b else None,na=None,nb=None)
    else:
        sa=[s for pid in pids for m,s in stars[ch].get(pid,[]) if m in W]; sb=[s for pid in pids for m,s in stars[ch].get(pid,[]) if m in P]
        rc=dict(d=(S.mean(sa)-S.mean(sb)) if len(sa)>=10 and len(sb)>=10 else None,na=len(sb),nb=len(sa))
    qo=0
    for r in rows:
        if r['rating'] is not None and r['rating']<4.5 and tot_u: qo+=sum(r['u'].get(m,0) for m in W)/3/tot_u*(4.5-r['rating'])*100
    mon_=[sum(r['u'].get(m,0) for r in rows) for m in M]
    skum_=[len({r['pid'] for r in rows if r['u'].get(m,0)>0}) for m in M]
    act_=len({r['pid'] for r in rows if any(r['u'].get(m,0)>0 for m in W)})
    return dict(skum=skum_,act=act_,mon=mon_,sku=len(pids),fam=len({r['fam'] for r in rows}),u=w,share=w/tot_u if tot_u else 0,size=sz.most_common(1)[0][0] if sz else '—',
        price=wavg('price'),rating=wavg('rating'),anc_u=anc_u,anc_p=anc_p if anc_u>=20 else None,per=w/len(pids) if pids else 0,
        trend=(w*3/p-1) if p>=150 else None,rc=rc,sdi=(w/tot_u)/(len(pids)/tot_sku) if tot_u and pids else None,qo=qo,p3=p)
def table(ch,keyfn,top=None,minu=0):
    rows=recs[ch]; tot_u=sum(sum(r['u'].get(m,0) for m in W) for r in rows)/3; tot_sku=len({r['pid'] for r in rows})
    g=C.defaultdict(list)
    for r in rows: g[keyfn(r)].append(r)
    out=[dict(k=k,**metrics(ch,v,tot_u,tot_sku)) for k,v in g.items()]
    out.sort(key=lambda x:(x['k']=='未知品牌' or '未标' in x['k'],-x['u']))
    if top: out=out[:top]
    ap=[x['anc_p'] for x in out if x['anc_p'] and x['k'] not in('未标','未知品牌')]
    base=S.median(ap) if len(ap)>=2 else None
    for x in out: x['prem']=(x['anc_p']/base-1) if base and x['anc_p'] else None
    return out
R={}
for ch in recs:
    rows=recs[ch]; tot=table(ch,lambda r:'全部')[0]
    T={'品牌':table(ch,lambda r:r['brand'],top=20),'尺寸':table(ch,lambda r:r['at']['尺寸']),'价格带':table(ch,lambda r:r['at']['价格带'])}
    for d in ['台面','柜体','主色','元素','形态','拆装']: T[d]=table(ch,lambda r,d=d:r['at'][d])
    T['台面 × 柜体']=table(ch,lambda r:f"{r['at']['台面']} × {r['at']['柜体']}",top=15)
    bt=table(ch,lambda r:r['brand']); top5=sum(sorted([x['share'] for x in bt if x['k']!='未知品牌'],reverse=True)[:5])
    def main(d):
        t=[x for x in T[d] if x['k']!='未标']; return (t[0]['k'],t[0]['u']/sum(y['u'] for y in t)) if t else ('—',0)
    def sh(d,v):
        t=[x for x in T[d] if x['k']!='未标']; s=sum(y['u'] for y in t); return sum(y['u'] for y in t if y['k']==v)/s if s else None
    mon=[dict(m=m,u=sum(r['u'].get(m,0) for r in rows),vp=sum(r.get('vp',{}).get(m,0) for r in rows),nv=sum(r.get('nv',{}).get(m,0) for r in rows)) for m in M]
    if ch=='amazon':
        rev=dict(q("select month,sum(revenue) from snapshot where channel='amazon' and month>='2026-01' group by 1"))
        for x in mon: x['rev']=rev.get(x['m'])
    R[ch]=dict(tot=tot,brands=len({r['brand'] for r in rows if r['brand']!='未知品牌'}),top5=top5,main={d:main(d) for d in ['台面','柜体','主色','尺寸']},
        asm=sh('拆装','拆装'),fl=sh('形态','悬浮式'),T=T,mon=mon,lowes_nosize=(ch=='lowes'))
json.dump(R,open('d3.json','w'),ensure_ascii=False,default=float)
for ch,v in R.items():
    t=v['tot']; print(ch,t['sku'],t['fam'],round(t['u']),round(t['price'] or 0),round(t['rating'] or 0,2),t['size'],round(t['qo'],1),t['trend'],t['rc'],v['main'],round(v['asm'] or 0,2),v['fl'],round(v['top5'],2),t['anc_p'])
    print('  brands',[(x['k'],round(x['u']),round(x['share']*100,1),x['rating'] and round(x['rating'],2),round(x['qo'],1),x['prem'] and round(x['prem']*100)) for x in v['T']['品牌'][:6]])
import pickle; pickle.dump(recs,open('recs.pkl','wb')); pickle.dump(LALL,open('recs_amz_all.pkl','wb'))
