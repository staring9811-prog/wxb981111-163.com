import q3paths
import json,html,re
R=json.load(open('d3.json')); D=json.load(open('data.json'))
E_=html.escape
CH=[('amazon','Amazon','#2a78d6'),('homedepot','Home Depot','#eb6834'),('lowes',"Lowe's",'#1baf7a'),('wayfair','Wayfair','#eda100')]
CN={c:n for c,n,_ in CH}
def I(x): return '—' if x is None else f'{x:,.0f}'
def pct(x,s=False): return '—' if x is None else (f'{"+" if s and x>0 else ""}{x*100:.1f}%')
def usd(x): return '—' if not x else f'${x:,.0f}'
def rt(x): return '—' if not x else f'{x:.2f}'
def tr(x): return '<span class="na">样本不足</span>' if x is None else f'<span class="{"up" if x>0.05 else "dn" if x<-0.05 else ""}">{"+" if x>0 else ""}{x*100:.1f}%</span>'
def rcf(ch,r):
    if r['d'] is None: return '<span class="na">样本不足</span>'
    d=r['d']; cl="up" if d>=0.05 else "dn" if d<=-0.05 else ""
    s=f'<span class="{cl}">{"+" if d>0 else ""}{d:.2f}</span>'
    return s+(f'<small>（{r["na"]}→{r["nb"]}评）</small>' if r.get('na') is not None else '')
def rating_cell(x): return '—' if not x else (f'<b class="dn">{x:.2f}</b>' if x<4.0 else f'{x:.2f}')
def qo(x): return f'<b class="dn">{x:.1f}</b>' if x>=5 else f'{x:.1f}'
HEAD={'品牌':['品牌','SKU数','月销量','销量占比','主销尺寸','加权均价','加权评分','36″ 销量','36″ 锚定价','月销/SKU','3M销量趋势','3M评分变化','质量机会值','属性锚定溢价（36″）'],
 'std':['标签','SKU数','月销量','销量占比','主销尺寸','加权均价','加权评分','36″ 销量','36″ 锚定价','月销/SKU','3M销量趋势','3M评分变化','供需指数','质量机会值','锚定溢价']}
TIPS={'质量机会值':'只算评分低于 4.5 的商品：销量占比 ×（4.5 − 评分）× 100。越大 = 卖得多但评价差，越值得做“更好的同款”。','供需指数':'销量占比 ÷ SKU 数占比。大于 1：一个 SKU 能分到的销量比平均多，竞争相对松。','锚定溢价':'只看 36″ 的真实商品：本行 36″ 均价 ÷ 本表各行 36″ 均价的中位数 − 1。正数 = 同尺寸下卖得更贵。','属性锚定溢价（36″）':'只看 36″ 的真实商品：本品牌 36″ 均价 ÷ 本表各品牌 36″ 均价的中位数 − 1。','36″ 锚定价':'只用 36″（33–39 in）商品的销量加权均价，不跨尺寸推算。','3M销量趋势':'2026-08 至 10 合计，对比 2026-05 至 07 合计。前 3 个月月均不足 50 件写“样本不足”。','3M评分变化':'近 3 个月新评论平均星级 − 前 3 个月的；括号里是前后评论条数。任一段不足 10 条写“样本不足”。Amazon 用每月页面评分的变化。','月销/SKU':'月销量 ÷ SKU 数。','加权评分':'按销量加权的页面评分；评分低于 4.0 标红。','月销量':'2026-08 至 10 的月均（件）。'}
def th(h): t=TIPS.get(h); return f'<th title="{E_(t)}">{h}<sup>?</sup></th>' if t else f'<th>{h}</th>'
def table(ch,rows,kind='std',dim=None):
    hs=HEAD['品牌' if kind=='品牌' else 'std']; nos=False; szt=kind=='尺寸'
    hs=hs[:1]+['每月走势（2026-01 至 10）']+hs[1:]
    out=['<div class="tw"><table class="dt"><tr>'+''.join(th(h) for h in hs)+'</tr>']
    for x in rows:
        if x['u']<1 and x['sku']<3: continue
        gray=' class="mute"' if x['k']=='未知品牌' or '未标' in x['k'] else ''
        anc_u='无尺寸拆分' if nos else I(x['anc_u']); anc_p='—' if nos else ('<span class="na">样本不足</span>' if x['anc_p'] is None else usd(x['anc_p']))
        prem='—' if nos else ('<span class="na">样本不足</span>' if x['prem'] is None else f'<span class="{"up" if x["prem"]>0.05 else "dn" if x["prem"]<-0.05 else ""}">{"+" if x["prem"]>0 else ""}{x["prem"]*100:.1f}%</span>')
        if szt and x['k']!='36″': anc_u=anc_p=prem='—'
        size='无尺寸拆分' if nos else x['size']
        cells=[E_(x['k']),trend_cell(ch,dim,x),I(x['sku']),I(x['u']),pct(x['share']),size,usd(x['price']),rating_cell(x['rating']),anc_u,anc_p,f"{x['per']:.1f}",tr(x['trend']),rcf(ch,x['rc'])]
        if kind!='品牌': cells.append('—' if x['sdi'] is None else f"{x['sdi']:.2f}")
        cells+= [qo(x['qo']),prem]
        out.append(f'<tr{gray}>'+''.join(f'<td>{c}</td>' for c in cells)+'</tr>')
    return ''.join(out)+'</table></div>'
def vbars(pairs,color,h=170,w=520,unit='件'):
    n=len(pairs); mx=max(v for _,v in pairs) or 1; bw=(w-30)/n; s=[]
    for i,(k,v) in enumerate(pairs):
        bh=(h-46)*v/mx; x=20+i*bw; y=h-24-bh
        s.append(f'<g><title>{k}：{v:,.0f} {unit}</title><rect x="{x+3:.1f}" y="{y:.1f}" width="{bw-6:.1f}" height="{bh:.1f}" rx="3" fill="{color}"/><text x="{x+bw/2:.1f}" y="{y-4:.1f}" class="bv" text-anchor="middle">{v/1000:.1f}k</text><text x="{x+bw/2:.1f}" y="{h-8}" class="ax" text-anchor="middle">{int(k[5:])}月</text></g>')
    s.append(f'<line x1="18" x2="{w-8}" y1="{h-24}" y2="{h-24}" class="base"/>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart">{"".join(s)}</svg>'
eid=[0]
def ED(text,cls='say'):
    eid[0]+=1; return f'<div class="{cls} ed" contenteditable="true" data-k="e{eid[0]}" spellcheck="false">{text}</div>'
SELF={'homedepot':['Home Decorators Collection','Glacier Bay','Hampton Bay'],
 'lowes':['Style Selections','allen + roth','Project Source','Origin 21','Scott Living'],
 'wayfair':['Ebern Designs','Lark Manor','Wade Logan','Gracie Oaks','Charlton Home','Mercury Row','The Twillery Co.','Willa Arlo Interiors','Laurel Foundry Modern Farmhouse','Three Posts','Andover Mills','August Grove','Latitude Run','Sand & Stable','Beachcrest Home','Birch Lane','Longshore Tides','Mercer41','Wrought Studio','Orren Ellis','Brayden Studio','17 Stories','Red Barrel Studio','Union Rustic','Steelside','Foundstone','Zipcode Design','Ivy Bronx','Highland Dunes','Rosecliff Heights','Greyleigh','Joss & Main','AllModern','Mistana','Alcott Hill','Darby Home Co','Ophelia & Co.','Winston Porter','World Menagerie','Hashtag Home','Rebrilliant','Symple Stuff','Trule','Etta Avenue','Hokku Designs','Breakwater Bay','Millwood Pines','Loon Peak','Canora Grey','Corrigan Studio','Everly Quinn','Foundry Select','George Oliver','Langley Street','Harriet Bee','Isabelle & Max','Bungalow Rose','Kelly Clarkson Home','Dovecove','Lark Manor'],
 'amazon':['Amazon Basics']}
import re as _re2
def _bn(b): return _re2.sub(r'[™®©]','',b or '').strip().lower()
def selfstat(c):
    S={_bn(x) for x in SELF[c]}
    rows=[x for x in R[c]['T']['品牌'] if _bn(x['k']) in S]
    allb=[x for x in R[c]['T']['品牌']]
    return len(rows), sum(x['u'] for x in rows), (sum(x['u'] for x in rows)/R[c]['tot']['u'] if R[c]['tot']['u'] else 0), sum(x['sku'] for x in rows)
def mom(mon):
    if not mon or len(mon)<10 or not mon[8] or mon[8]<30: return None
    return mon[9]/mon[8]-1
def momf(x,ch=None):
    if ch=='lowes': return '—'
    return '<span class="na">样本少</span>' if x is None else f'<span class="{"up" if x>0.05 else "dn" if x<-0.05 else ""}">{"+" if x>0 else ""}{x*100:.0f}%</span>'

# ---------- heat helpers (keywords + trends)
import sqlite3 as _sq, collections as _C
_c=_sq.connect('pdt.sqlite3')
SV=_C.defaultdict(lambda:_C.defaultdict(float))
for d_,v_,m_,x_ in _c.execute("select dim,value,month,sum(volume) from search_volume where source='amazon' group by 1,2,3"): SV[(d_,v_)][m_]+=x_ or 0
AMZ=D['amz_share']
M12=[f'2025-{i:02d}' for i in range(10,13)]+[f'2026-{i:02d}' for i in range(1,10)]
CUR=['2026-07','2026-08','2026-09']; PRV=['2025-07','2025-08','2025-09']
HD2AMZ={'元素':'元素','拆装':'装','形态':'形态','尺寸':'尺寸段','价格带':'价位','台面':'台面材质','柜体':'柜体材质','主色':'主色'}
HD2KW={'元素':('元素',None),'尺寸':('尺寸',None),'形态':('形态',None),'主色':('主色',None),'台面':('台面',{'陶瓷':'陶瓷一体','树脂':'树脂一体','木板':'木板台面','不适用（不含台面）':'不含台面'})}
import json as _json,re as _re
_K=_json.load(open('kw.json'))
KWRE={('形态','落地式'):r'free ?standing|freestanding',('形态','悬浮式'):r'floating|wall[- ]?mount',('形态','开放式'):r'open (shelf|storage)|console',
 ('台面','陶瓷'):r'ceramic',('台面','岗石'):r'stone top|engineered stone',('台面','石英石'):r'quartz',('台面','卡拉拉大理石'):r'marble|carrara',('台面','树脂'):r'resin',('台面','木板'):r'wood top|butcher',('台面','不适用（不含台面）'):r'without (top|sink)|no top|base only',
 ('柜体','实木'):r'solid wood|real wood',('柜体','实木框架'):r'solid wood',('柜体','MDF'):r'\bmdf\b',
 ('主色','白'):r'\bwhite\b',('主色','黑'):r'\bblack\b',('主色','灰'):r'\bgr[ae]y\b',('主色','原木'):r'natural|oak|light wood|teak|walnut',('主色','深木'):r'espresso|dark wood|brown',('主色','蓝'):r'\bblue\b|navy',('主色','绿'):r'\bgreen\b|sage',
 ('元素','夏克式'):r'shaker',('元素','竖棱'):r'flut|reed',('元素','农场风装饰饰条'):r'farmhouse|barn',('元素','玻璃门'):r'glass door',('元素','rattan'):r'rattan|cane',('元素','rustic'):r'rustic',('元素','木条格栅'):r'slat',('元素','现代线条纹理'):r'modern',
 ('拆装','整装'):r'assembled',('拆装','拆装'):r'\brta\b|ready to assemble'}
def kw2(d,val):
    if d=='尺寸': return None
    p=KWRE.get((d,val))
    if not p: return None
    out={}; n=0
    for k,ser in _K.items():
        if _re.search(p,k,_re.I):
            n+=1
            for m,v in ser.items(): out[m]=out.get(m,0)+(v or 0)
    return (out,n) if n else None
def kw(d,val):
    if d not in HD2KW: return None
    dim,mp=HD2KW[d]; v=(mp or {}).get(val,val) if mp else val
    s=SV.get((dim,v))
    if not s or sum(s.get(m,0) for m in CUR)==0: return None
    return s
def amz_series(d,val): return [AMZ[HD2AMZ[d]].get(m,{}).get(val,0) for m in M12]
def mini_bars(v,w=96,h=22):
    mx=max(v) or 1; n=len(v); bw=w/n
    return f'<svg class="sp" width="{w}" height="{h}">'+''.join(f'<rect x="{i*bw+0.5:.1f}" y="{h-1-(h-2)*x/mx:.1f}" width="{bw-1.5:.1f}" height="{(h-2)*x/mx:.1f}" rx="1" fill="currentColor" opacity=".55"/>' for i,x in enumerate(v))+'</svg>'
def lab_bars(label,v,color=None,w=96,h=20,n_total=10,cls='t'):
    v=list(v)+[None]*(n_total-len(v))
    mx=max([x for x in v if x] or [1]); bw=w/n_total; s=''
    for i,x in enumerate(v):
        if x is None: continue
        hh=(h-2)*x/mx; s+=f'<rect x="{i*bw+0.5:.1f}" y="{h-1-hh:.1f}" width="{bw-1.5:.1f}" height="{hh:.1f}" rx="1" fill="{color or "currentColor"}" opacity="{1 if color else .55}"/>'
    return f'<div class="lb2 {cls}"><span>{label}</span><svg width="{w}" height="{h}">{s}</svg></div>'
M10=[f'2026-{i:02d}' for i in range(1,11)]
def mini_lines(a,b,w=96,h=22):
    def pl(v,extra):
        mx=max(v) or 1; n=len(v)
        return f'<polyline points="{" ".join(f"{1+i*(w-2)/(n-1):.1f},{h-2-(h-4)*x/mx:.1f}" for i,x in enumerate(v))}" fill="none" stroke="currentColor" stroke-width="1.6" {extra}/>'
    return f'<svg class="sp" width="{w}" height="{h}">'+pl(a,'')+(pl(b,'stroke-dasharray="3 2" opacity=".8"') if b else '')+'</svg>'
def yoy(s,ms1,ms0):
    a=sum(s.get(m,0) for m in ms1); b=sum(s.get(m,0) for m in ms0); return (a/b-1) if b else None
def wan(x): return f'{x/1e4:.1f}万' if x>=1e4 else f'{x:,.0f}'

CHAVG={c:(R[c]['tot']['u']/R[c]['tot']['act'] if R[c]['tot']['act'] else None) for c in R}
def sku_part(c,x,w=96):
    if not x.get('skum') or sum(x['skum'])==0: return ''
    if c=='lowes':
        per=x['u']/x['act'] if x['act'] else None
        s=f'<small class="kv skuv">父体 {x["act"]} 个 · 单父体 {per:,.0f} 件/月</small>' if per else ''
        if per and CHAVG[c]:
            r=per/CHAVG[c]
            if r>=1.5: s+=f'<b class="tg u">单父体贡献高 ×{r:.1f}</b>'
            elif r<=0.6: s+=f'<b class="tg d">单父体贡献低 ×{r:.1f}</b>'
        return s
    per=x['u']/x['act'] if x['act'] else None; s=lab_bars('SKU',x['skum'],'#3c8d7a',w=w,cls='k')
    U='SKU' if c=='amazon' else '父体'; UU='单款' if c=='amazon' else '单父体'
    s=s.replace('<span>SKU</span>',f'<span>{U}</span>')
    s+=f'<small class="kv skuv">在售 {U} {x["act"]} 个 · {UU} {per:,.0f} 件/月</small>' if per else ''
    if per and CHAVG[c]:
        r=per/CHAVG[c]
        if r>=1.5: s+=f'<b class="tg u">{UU}贡献高 ×{r:.1f}</b>'
        elif r<=0.6: s+=f'<b class="tg d">{UU}贡献低 ×{r:.1f}</b>'
    return s
SIZES=['18″','24″','28″','30″','36″','42″','48″','60″','72″+']
def size_ratio(val):
    tot_k=sum(sum(SV[('尺寸',v2)].get(m,0) for m in CUR) for v2 in SIZES)/3
    tot_u=sum(sum(AMZ['尺寸段'].get(m,{}).get(v2,0) for m in CUR) for v2 in SIZES)/3
    ks=sum(SV[('尺寸',val)].get(m,0) for m in CUR)/3; uu=sum(AMZ['尺寸段'].get(m,{}).get(val,0) for m in CUR)/3
    return (ks/tot_k)/(uu/tot_u) if uu and tot_k and ks else None
def tags(ch,dim,val,trend):
    s=''
    if ch=='amazon' and dim=='尺寸':
        r=size_ratio(val)
        if r and r>=1.3: s+=f'<b class="tg w">搜多买少 ×{r:.1f}</b>'
        elif r and r<=0.7: s+=f'<b class="tg c">买多搜少 ×{r:.1f}</b>'
        elif r: s+=f'<b class="tg o">搜销 ×{r:.1f}</b>'
    if trend is not None and trend>=0.2: s+=f'<b class="tg g">销量增长快 +{trend*100:.0f}%</b>'
    elif trend is not None and trend<=-0.2: s+=f'<b class="tg r">销量下降多 {trend*100:.0f}%</b>'
    return s
def trend_cell(ch,dim,x):
    if not x.get('mon') or sum(x['mon'])<=0: return '<span class="na">—</span>'
    if ch=='lowes': return '<div class="tc"><small class="kv">只有当下时间点，没有月度走势</small>'+sku_part(ch,x,w=110)+'</div>'
    s=lab_bars('销量',x['mon'],w=110)
    if ch=='amazon' and dim in HD2KW:
        k=kw(dim,x['k'])
        if k:
            ks=sum(k.get(m,0) for m in CUR)/3; ky=yoy(k,CUR,PRV)
            _a,_b,_c=gstats([k.get(m) for m in K24])
            s+=lab_bars('搜索',[k.get(m,0) for m in M10[:9]],'#7a5af0',w=110)+f'<small class="kv">搜 {wan(ks)}/月 · 环比 {pc(_a)} · 同比 {pc(_b)} · CAGR {pc(_c)}</small>'
    if ch=='amazon' and dim in HD2AMZ and x['k'] in AMZ[HD2AMZ[dim]].get('2026-10',{}):
        _a,_b,_c=gstats([AMZ[HD2AMZ[dim]].get(m,{}).get(x['k']) for m in M24]); yb=pc(_b)
    else:
        _a,_b,_c=gstats(x['mon']); yb='<span class="na">无去年</span>' if ch!='amazon' else '<span class="na">按品牌无两年数据</span>'
    s+=f'<small class="kv">销量 环比 {pc(_a)} · 同比 {yb} · CAGR {pc(_c)}</small>'
    return '<div class="tc">'+s+sku_part(ch,x,w=110)+tags(ch,dim,x['k'],x['trend'])+'</div>'
# ---------- 弹窗产品数据 + 顶部趋势数据
import pickle as _pk, sqlite3 as _sq3, csv as _csv
_RC=_pk.load(open('recs.pkl','rb'))
_db=_sq3.connect('pdt.sqlite3')
_AP={i:(t,im,l) for i,t,im,l in _db.execute("select item_id,title,image_url,link from product where channel='amazon'")}
_TR={(r['渠道'],r['pid'].split(' ')[0]):r for r in _csv.DictReader(open(q3paths.INPUT+'/渠道关键词/大词/三平台_商品表.csv',encoding='utf-8-sig'))}
_LWU={r['pid']:r['url'] for r in _pk.load(open(q3paths.CLEAN+'/lw.pkl','rb'))['rows']}
import html as _h
PROD={}
for c,_n,_ in CH:
    L=[]
    for r in _RC[c]:
        sep=r['u'].get('2026-09',0); octo=r['u'].get('2026-10',0)
        if sep<=0 and octo<=0: continue
        if c=='amazon':
            t,im,l=_AP.get(r['pid'],('','',''))
        else:
            rep=r.get('rep',r['pid']); _tr=_TR.get(({'homedepot':'Home Depot','wayfair':'Wayfair','lowes':"Lowe's"}[c],rep),{})
            t=r.get('title') or _tr.get('title',''); im=_tr.get('主图','')
            l={'homedepot':f'https://www.homedepot.com/p/{rep}','wayfair':f'https://www.wayfair.com/keyword.php?keyword={rep}','lowes':_LWU.get(rep,f'https://www.lowes.com/search?searchTerm={rep}')}[c]
        at=r['at']; at2=dict(at)
        L.append([r['pid'],r['brand'],_h.unescape(t or '')[:140],im or '',l or '',round(r['price']) if r['price'] else None,round(r['rating'],2) if r['rating'] else None,round(sep),round(octo),{'拆装':at['拆装'],'形态':at['形态'],'尺寸':at['尺寸'],'价格带':at['价格带'],'台面':at['台面'],'柜体':at['柜体'],'主色':at['主色'],'元素':at['元素']}])
    PROD[c]=L
M10x=[f'2026-{i:02d}' for i in range(1,11)]
M24=[f'2024-{i:02d}' for i in range(11,13)]+[f'2025-{i:02d}' for i in range(1,13)]+M10x          # 2024-11 至 2026-10
K24=[f'2024-{i:02d}' for i in range(10,13)]+[f'2025-{i:02d}' for i in range(1,13)]+[f'2026-{i:02d}' for i in range(1,10)]  # 搜索 2024-10 至 2026-09
def gstats(arr):
    """arr 按月排列（可含 None）。环比=最新月÷上月−1；同比=最新月÷12 个月前−1；CAGR=(最近 3 个月月均÷最早 3 个月月均)^(12/间隔月数)−1。"""
    v=[x for x in arr]
    idx=[k for k,x in enumerate(v) if x is not None]
    if not idx: return None,None,None
    L=idx[-1]; cur=v[L]
    mom=(cur/v[L-1]-1) if L>=1 and v[L-1] else None
    yoy=(cur/v[L-12]-1) if L>=12 and v[L-12] else None
    s=[x for x in v if x is not None]
    cagr=None
    if len(s)>=6:
        a=sum(s[:3])/3; b=sum(s[-3:])/3; gap=len(s)-3
        if a>0 and b>0: cagr=(b/a)**(12/gap)-1
    return mom,yoy,cagr
def pc(x,na='—'):
    return f'<span class="na">{na}</span>' if x is None else f'<span class="{"up" if x>0.02 else "dn" if x<-0.02 else ""}">{"+" if x>0 else ""}{x*100:.0f}%</span>'
_AM={r['m']:r for r in D['amz_month']}
_RC_tot=lambda c,m:sum(r['u'].get(m,0) for r in _RC[c])
TREND={'units':{},'rev':{}}
for c,_n,_ in CH:
    if c=='amazon':
        TREND['units'][c]=[round(_AM[m]['u']) if m in _AM else None for m in M24]
        TREND['rev'][c]=[round(_AM[m]['r']) if m in _AM else None for m in M24]
    elif c=='lowes':
        TREND['units'][c]=[None]*23+[round(_RC_tot(c,'2026-10'))]
        TREND['rev'][c]=[None]*23+[round(sum(r['u'].get('2026-10',0)*(r['price'] or 0) for r in _RC[c]))]
    else:
        TREND['units'][c]=[None]*14+[round(_RC_tot(c,m)) for m in M10x]
        TREND['rev'][c]=[None]*14+[round(sum(r['u'].get(m,0)*(r['price'] or 0) for r in _RC[c])) for m in M10x]
_core=D['kw']['core']; _tot=D['kw']['total']
TREND['price']={c:[(round(r/u) if (r is not None and u) else None) for u,r in zip(TREND['units'][c],TREND['rev'][c])] for c in TREND['units']}
KWS={'with sink':[round(_core['bathroom vanity with sink'].get(m,0)) for m in K24],'bathroom vanity':[round(_core['bathroom vanity'].get(m,0)) for m in K24]}
KWS['floating']=[round(_K['floating bathroom vanity'].get(m,0) or 0) for m in K24]
KWS['其他 336 个词']=[round(_tot.get(m,0)-KWS['with sink'][k]-KWS['bathroom vanity'][k]-KWS['floating'][k]) for k,m in enumerate(K24)]
# 搜索转化 = Amazon 当月销量 ÷ 339 词当月搜索量（两边都有的月份：2024-11 至 2026-09）
MC=M24[:-1]
CONV=[round(_AM[m]['u']/_tot[m]*100,2) if m in _AM and _tot.get(m) else None for m in MC]
def lines(series,months,w=520,h=230,unit='',fmt=None):
    vals=[v for s in series.values() for v in s[0] if v is not None]; mx=max(vals) if vals else 1
    n=len(months); X=lambda i:46+i*(w-66)/(n-1); Y=lambda v:h-30-(h-52)*v/mx
    def lab(v):
        if fmt: return fmt(v)
        return f'{v/1e6:.1f}M' if mx>=1e6 else (f'{v/1e4:.1f}万' if mx>=2e4 else f'{v:,.0f}')
    s=[f'<line x1="46" x2="{w-20}" y1="{h-30}" y2="{h-30}" class="base"/>']
    for k in range(0,5): v=mx*k/4; s.append(f'<text x="40" y="{Y(v)+4:.0f}" class="ax" text-anchor="end">{lab(v)}</text>')
    for i,m in enumerate(months):
        if i%3==0 or i==n-1: s.append(f'<text x="{X(i):.0f}" y="{h-12}" class="ax" text-anchor="middle">{m[2:4]}/{int(m[5:])}</text>')
    for key,(arr,col,lb) in series.items():
        pts=[(X(i),Y(v),v,i) for i,v in enumerate(arr) if v is not None]
        if len(pts)>1: s.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x,y,_,_ in pts)}" fill="none" stroke="{col}" stroke-width="2.4"/>')
        for x,y,v,i in pts: s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{5 if len(pts)==1 else 2.6}" fill="{col}"/><circle class="hit" cx="{x:.1f}" cy="{y:.1f}" r="9" fill="transparent" data-tip="{lb} · {months[i][:4]}年{int(months[i][5:])}月：{(fmt(v) if fmt else f'{v:,.0f}')}{unit}"/>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart">{"".join(s)}</svg>'
def stat_table(series,note='',full=None,fmt=None):
    h='<table class="st"><tr><th></th><th>最新月</th><th title="最新月 ÷ 上个月 − 1">环比</th><th title="最新月 ÷ 去年同月 − 1">同比</th><th title="(最近 3 个月月均 ÷ 最早 3 个月月均)^(12 ÷ 间隔月数) − 1，即按这段时间折算的年化增长">CAGR</th></tr>'
    for key,(arr,col,lb) in series.items():
        mo,yo,ca=gstats(arr); last=[x for x in arr if x is not None]
        if full: yo=gstats(full[key][0])[1]
        h+=f'<tr><td><i class="dot" style="background:{col}"></i>{lb}</td><td>{((fmt(last[-1]) if fmt else f"{last[-1]:,.0f}") if last else "—")}</td><td>{pc(mo)}</td><td>{pc(yo,"无去年数据")}</td><td>{pc(ca,"数据不足")}</td></tr>'
    return h+'</table>'+(f'<p class="hint">{note}</p>' if note else '')
_lab={c:(n,col) for c,n,col in CH}
SU={c:(TREND['units'][c],_lab[c][1],_lab[c][0]) for c,_n,_ in CH}
SR={c:(TREND['rev'][c],_lab[c][1],_lab[c][0]) for c,_n,_ in CH}
SP={c:(TREND['price'][c],_lab[c][1],_lab[c][0]) for c,_n,_ in CH}
SK={'a':(KWS['with sink'],'#7a5af0','bathroom vanity with sink'),'b':(KWS['bathroom vanity'],'#b49cf7','bathroom vanity'),'f':(KWS['floating'],'#d9a400','floating bathroom vanity（悬浮式最大词）'),'c':(KWS['其他 336 个词'],'#3d2a8a','其他 336 个浴室柜词')}
SC={'cv':(CONV,'#2a78d6','Amazon 销量 ÷ 搜索量')}
_cut=lambda S,n:{k:(a[-n:],c,l) for k,(a,c,l) in S.items()}
SU1,SR1,SK1,SP1,SC1=_cut(SU,10),_cut(SR,10),_cut(SK,9),_cut(SP,10),_cut(SC,9)
_usd=lambda v:f'${v:,.0f}'; _pct=lambda v:f'{v:.2f}%'
_PN='Amazon 均价 = 当月销售额 ÷ 当月销量（每个子体按自己的售价）；小平台用代表链接现价，均价变化只反映卖得多的款在变。'
TOPCH=('<h3 class="rowt">近一年趋势（2026-01 至 10）</h3><div class="grid3t">'
 '<div class="card"><h3>各渠道每月销量（件）</h3>'+lines(SU1,M10x,unit=' 件')+stat_table(SU1,'同比取 Amazon 去年同月；CAGR 按 1–10 月折算年化。',SU)+'</div>'
 '<div class="card"><h3>各渠道每月销售额（$）</h3>'+lines(SR1,M10x,unit=' 美元')+stat_table(SR1,'销售额 = Σ（每个商品月销 × 它的售价）。',SR)+'</div>'
 '<div class="card"><h3>各渠道加权均价（$）</h3>'+lines(SP1,M10x,fmt=_usd)+stat_table(SP1,_PN,SP,fmt=_usd)+'</div></div>'
 '<h3 class="rowt">两年趋势（2024-11 至 2026-10）</h3><div class="grid3t">'
 '<div class="card"><h3>各渠道每月销量（件）</h3>'+lines(SU,M24,unit=' 件')+stat_table(SU,'小平台只有 2026 年数据：没有同比，CAGR 按 1–10 月折算年化；Lowe&#39;s 只有当下一个点。')+'</div>'
 '<div class="card"><h3>各渠道每月销售额（$）</h3>'+lines(SR,M24,unit=' 美元')+stat_table(SR,'小平台销售额 = 父体月销 × 代表链接售价，只作参考。')+'</div>'
 '<div class="card"><h3>各渠道加权均价（$）</h3>'+lines(SP,M24,fmt=_usd)+stat_table(SP,_PN,fmt=_usd)+'</div></div>'
 '<h3 class="rowt">Amazon 关键词搜索（近一年 2026-01 至 09；两年 2024-10 至 2026-09）</h3><div class="grid3t">'
 '<div class="card"><h3>搜索量 · 近一年</h3>'+lines(SK1,K24[-9:],unit=' 次')+stat_table(SK1,'CAGR 按 1–9 月折算年化。',SK)+'</div>'
 '<div class="card"><h3>搜索量 · 两年</h3>'+lines(SK,K24,unit=' 次')+stat_table(SK,'数据来自卖家精灵，339 个已确认的浴室柜词；悬浮式取搜索量最大的 floating bathroom vanity。')+'</div>'
 '<div class="card"><h3>搜索转化（2024-11 至 2026-09）</h3>'+lines(SC,MC,fmt=_pct)+stat_table(SC,'搜索转化 = Amazon 当月销量 ÷ 339 个词当月搜索量。不是官方转化率，是“每 100 次搜索对应卖出几件”的指数，看走势用；近一年：'+'环比 {} · 同比 {} · CAGR {}'.format(*[pc(x) for x in (gstats(SC1['cv'][0])[0],gstats(CONV)[1],gstats(SC1['cv'][0])[2])])+'（CAGR 按 1–9 月年化）。',fmt=_pct)+'</div></div>'
 '<p class="key" style="margin-top:6px">环比 = 最新月 ÷ 上个月 − 1；同比 = 最新月 ÷ 去年同月 − 1；CAGR = (最近 3 个月月均 ÷ 最早 3 个月月均)^(12 ÷ 间隔月数) − 1，即按图里这段时间折算的年化增长率。Amazon 导出能看到的商品逐月变多，销量的同比和 CAGR 有一部分来自“看得更全”。</p>')
def ovs(c,v):
    if c=='lowes': return ['—','—','—']
    if c=='amazon': s=[_AM[m]['u'] if m in _AM else None for m in M24]
    else: s=[x['u'] for x in v['mon']]
    mo,yo,ca=gstats(s); return [pc(mo),pc(yo,'无去年数据'),pc(ca)]
# ---------- overview
ov=['<div class="tw"><table class="dt ov"><tr><th>渠道</th>'+''.join(th(h) for h in ['SKU数（小平台=父体数）','父体数','品牌数','月销量','环比（10月比9月）','同比','CAGR','自营品牌（品牌数 · 商品数）','自营品牌月销','加权均价','加权评分','主销尺寸','主销台面','主销柜体','主销颜色','拆装占比','悬浮式占比','月销/SKU','3M销量趋势','3M评分变化','质量机会值','前 5 品牌占比','36″ 锚定价'])+'</tr>']
for c,n,col in CH:
    v=R[c]; t=v['tot']; m=v['main']; nos=False
    ov.append(f'<tr><td><i class="dot" style="background:{col}"></i><b>{n}</b></td>'+''.join(f'<td>{x}</td>' for x in [I(t['sku']),I(t['fam']),I(v['brands']),f"<b>{I(t['u'])}</b>",*ovs(c,v),(f"{selfstat(c)[0]} 个品牌 · {selfstat(c)[3]} 个{'SKU' if c=='amazon' else '父体'}" if selfstat(c)[0] else '0'),(f"{I(selfstat(c)[1])}（{selfstat(c)[2]*100:.0f}%）" if selfstat(c)[0] else '—'),usd(t['price']),rating_cell(t['rating']),'无尺寸拆分' if nos else f"{m['尺寸'][0]}（{m['尺寸'][1]*100:.0f}%）",f"{m['台面'][0]}（{m['台面'][1]*100:.0f}%）",f"{m['柜体'][0]}（{m['柜体'][1]*100:.0f}%）",f"{m['主色'][0]}（{m['主色'][1]*100:.0f}%）",pct(v['asm']),pct(v['fl']),f"{t['per']:.1f}",tr(t['trend']),rcf(c,t['rc']),qo(t['qo']),pct(v['top5']),'—' if nos else usd(t['anc_p'])])+'</tr>')
ov.append('</table></div>')
# ---------- heat table（统一格子：每格同样的位置放同样的数）
DIMS=[('拆装',['拆装','整装']),('形态',['落地式','悬浮式','开放式']),('尺寸',['18″','24″','28″','30″','36″','42″','48″','60″','72″+']),('价格带',['<$200','$200–399','$400–699','$700–999','≥$1000']),('台面',['陶瓷','树脂','岗石','Cultured Marble','石英石','卡拉拉大理石','木板','不适用（不含台面）']),('柜体',['MDF','实木框架','实木','含刨花板','含胶合板']),('主色',['白','黑','灰','原木','深木','蓝','绿']),('元素',['夏克式','农场风装饰饰条','竖棱','纯色','自然木纹','横板条','搭叠式','现代线条纹理','玻璃门','rattan','rustic','木条格栅'])]
CC={c:col for c,_,col in CH}
def fmt_n(x): return '—' if x is None else (f'{x/1e4:.1f}万' if x>=1e4 else f'{x:,.0f}')
def hcell(c,d,val,row,s,mx):
    if row is None or (row['u']<=0 and row['sku']==0):
        return '<td class="hc0"><div class="hc"><div class="hs"><b>0%</b></div><div class="nodata">没有这个取值</div></div></td>'
    top=' top' if s==mx and s>0 else ''
    w=s/mx*100 if mx else 0
    kws=('<span class="na">无相关搜索词</span>' if c=='amazon' else '—'); kwy=''
    kk=None; nkw=''
    if c=='amazon':
        if d=='尺寸': kk=kw(d,val)
        else:
            z=kw2(d,val)
            if z: kk,nn=z; nkw=f'<small class="nk">{nn} 词</small>'
        k=kk
        if k and sum(k.get(m,0) for m in CUR)>0:
            ks=sum(k.get(m,0) for m in CUR)/3; ky=yoy(k,CUR,PRV); kws=fmt_n(ks)+nkw
            kwy='' if ky is None else f'<em class="{"up" if ky>0.05 else "dn" if ky<-0.05 else ""}">{"+" if ky>0 else ""}{ky*100:.0f}%</em>'
    tr_=row['trend']; trs='—' if tr_ is None else f'<em class="{"up" if tr_>0.05 else "dn" if tr_<-0.05 else ""}">{"+" if tr_>0 else ""}{tr_*100:.0f}%</em>'
    if c=='lowes': cs=('—','—','—')
    elif c=='amazon':
        _ser=[D['amz_share'][HD2AMZ[d]].get(m,{}).get(val) for m in M24]
        _mo,_yo,_ca=gstats(_ser); cs=(pc(_mo),pc(_yo),pc(_ca))
    else:
        _mo,_yo,_ca=gstats(row.get('mon') or []); cs=(pc(_mo),'<span class="na">无去年</span>',pc(_ca))
    sline=''
    if c=='amazon' and kk and sum(kk.get(m,0) for m in CUR)>0:
        _a,_b,_c=gstats([kk.get(m) for m in K24])
        sline=f'<div class="sl">搜索 环比 {pc(_a)} · 同比 {pc(_b)} · CAGR {pc(_c)}</div>'
    U='SKU' if c=='amazon' else '父体'
    per=row['u']/row['act'] if row.get('act') else None
    rt_=row['rating']; rts='—' if not rt_ else (f'<span class="lowr">{rt_:.2f}</span>' if rt_<4.0 else f'{rt_:.2f}')
    bars=''
    if c!='lowes' and row.get('mon') and sum(row['mon'])>0:
        bars='<div class="spk">'+lab_bars('销量',row['mon'],CC[c],w=104,h=18)
        if c=='amazon' and kk and sum(kk.get(m,0) for m in CUR)>0: bars+=lab_bars('搜索',[kk.get(m,0) for m in M10[:9]],'#7a5af0',w=104,h=18)
        bars+='</div>'
    elif c=='lowes': bars='<div class="spk na">当下时间点，无走势</div>'
    tg=tags(c,d,val,tr_)
    if per and CHAVG[c]:
        r=per/CHAVG[c]
        if r>=1.5: tg+=f'<b class="tg u">单{"款" if c=="amazon" else "父体"}贡献高 ×{r:.1f}</b>'
        elif r<=0.6: tg+=f'<b class="tg d">单{"款" if c=="amazon" else "父体"}贡献低 ×{r:.1f}</b>'
    return (f'<td class="clk" data-c="{c}" data-d="{d}" data-v="{E_(val)}"><div class="hc"><div class="hs{top}"><b>{s*100:.0f}%</b><span class="sb"><i style="width:{w:.0f}%;background:{CC[c]}"></i></span></div>'
            f'<dl><dt>月销</dt><dd>{fmt_n(row["u"])}</dd><dt>3M</dt><dd>{trs}</dd>'
            f'<dt>环比</dt><dd>{cs[0]}</dd><dt>同比</dt><dd>{cs[1]}</dd>'
            f'<dt>CAGR</dt><dd>{cs[2]}</dd><dt>单{"款" if c=="amazon" else "父体"}</dt><dd>{fmt_n(per)} 件</dd>'
            f'<dt>均价</dt><dd>{usd(row["price"])}</dd><dt>评分</dt><dd>{rts}</dd>'
            f'<dt>搜索</dt><dd>{kws}</dd><dt>{U}</dt><dd>{I(row["act"])}</dd></dl>{sline}{bars}<div class="tgs">{tg}</div></div></td>')
DN={'拆装': '拆装 / 整装', '形态': '形态（站立 / 悬浮 / 开放）', '尺寸': '尺寸（小平台 = 父体代表链接）', '价格带': '价格带（小平台 = 父体代表链接）', '台面': '台面材质', '柜体': '柜体材质', '主色': '主色（只有 Amazon）', '元素': '门板元素'}
ht=['<div class="tw2"><table class="heat2"><tr class="hd"><th>取值</th>'+''.join(f'<th><i class="dot" style="background:{col}"></i>{n}</th>' for _,n,col in CH)+'</tr>']
for d,vals in DIMS:
    sh={}; rowsby={}
    for c,_,_ in CH:
        rows=[x for x in R[c]['T'][d] if x['k']!='未标']; s=sum(x['u'] for x in rows)
        sh[c]={x['k']:(x['u']/s if s else 0) for x in rows}; rowsby[c]={x['k']:x for x in R[c]['T'][d]}
    for j,val in enumerate(vals):
        mx=max((sh[c].get(val,0) for c,_,_ in CH if not (d=='主色' and c!='amazon')),default=0)
        cells=[]
        for c,_,_ in CH:
            if d=='主色' and c!='amazon': cells.append('<td class="hc0"><div class="hc"><div class="nodata">小平台没有颜色打标</div></div></td>'); continue
            cells.append(hcell(c,d,val,rowsby[c].get(val),sh[c].get(val,0),mx))
        if j==0: ht.append(f'<tr class="grp" data-g="{E_(d)}" title="点击收起 / 展开"><td colspan="5"><span><i class="car">▾</i>{DN[d]}</span></td></tr>')
        ht.append(f'<tr class="gr" data-g="{E_(d)}"><td class="val">{E_(val)}</td>'+''.join(cells)+'</tr>')
ht.append('</table></div>')
# ---------- channel panels
def auto(c):
    v=R[c]; T=v['T']; t=v['tot']
    b=[x for x in T['品牌'] if x['k']!='未知品牌']
    hq=sorted(b,key=lambda x:-x['qo'])[0]
    pr=[x for x in b if x['prem'] is not None]; hp=max(pr,key=lambda x:x['prem']) if pr else None
    sz=[x for x in T['尺寸'] if x['k']!='未标']
    tc=[x for x in T['台面 × 柜体'] if '未标' not in x['k']]
    s=f'{CN[c]} 月销约 {I(t["u"])} 件，加权均价 {usd(t["price"])}，加权评分 {rt(t["rating"])}；前 5 品牌占 {pct(v["top5"])}。'
    if sz: s+=f'销量最大的尺寸是 {sz[0]["k"]}（{pct(sz[0]["share"])}）。'
    if tc: s+=f'最大的台面 × 柜体组合是 {tc[0]["k"]}（{pct(tc[0]["share"])}，评分 {rt(tc[0]["rating"])}）。'
    s+=f'质量机会值最高的品牌是 {hq["k"]}（{hq["qo"]:.1f}，评分 {rt(hq["rating"])}）'
    if hp: s+=f'；36″ 卖得最贵的品牌是 {hp["k"]}（比中位数 +{hp["prem"]*100:.0f}%）'
    return s+'。'
SEC=[('品牌','品牌（前 20）'),('尺寸','尺寸档'),('价格带','价格带'),('台面 × 柜体','核心组合：台面 × 柜体（前 15）'),('台面','台面'),('柜体','柜体材质'),('主色','主色'),('元素','门板 / 设计元素'),('形态','安装形态'),('拆装','拆装 / 整装')]
panels=[]; tabs=[]
for i,(c,n,col) in enumerate(CH):
    v=R[c]; mon=v['mon']
    chart=vbars([(x["m"],x["u"]) for x in mon],col) if c!='lowes' else '<p class="na" style="padding:40px 0;text-align:center">Lowe\'s 用销量标签 + BSR 曲线估算，只有当下一个时间点，没有月度走势。</p>'
    parts=[f'<div class="grid2"><div class="card"><h3>每月销量（2026-01 至 10）</h3>{chart}</div><div class="card"><h3>本渠道结论</h3>{ED(auto(c),"say big")}<p class="hint">自动生成的初稿，点击可直接改。</p></div></div>']
    mt='<div class="tw"><table class="dt"><tr><th>月份</th><th>销量（件）</th>'+('<th>销售额</th>' if c=='amazon' else '<th>VP 评论</th><th>非 VP 评论</th>')+'<th>相对 2026-10</th></tr>'
    last=mon[-1]['u'] or 1
    for x in mon: mt+=f'<tr><td>{x["m"]}</td><td>{I(x["u"])}</td>'+(f'<td>{usd(x.get("rev"))}</td>' if c=='amazon' else f'<td>{I(x["vp"])}</td><td>{I(x["nv"])}</td>')+f'<td>{x["u"]/last*100:.0f}%</td></tr>'
    if c!='lowes': parts.append(f'<details class="card"><summary>月度销量明细表</summary>{mt}</table></div></details>')
    for key,title in SEC:
        if False:
            parts.append(f'<div class="card"><h3>{title}</h3><p class="na">Lowe\'s 评论里没有买的尺寸，销量拆不到尺寸档，暂不展示。</p></div>'); continue
        if key=='主色' and c!='amazon': continue
        if c!='amazon' and key in ('尺寸','价格带'): title=title+'（按父体代表链接：在榜排名最高、这个形态里卖得最好的那个链接）'
        parts.append(f'<div class="card"><h3>{title}</h3>{table(c,v["T"][key],key if key in ("品牌","尺寸") else "std",dim=key)}{ED("这说明什么：（点击填写）","say")}</div>')
    tabs.append(f'<button class="tab{" on" if i==0 else ""}" data-t="{c}" style="--c:{col}">{n}</button>')
    panels.append(f'<div class="panel{" on" if i==0 else ""}" id="p-{c}">{"".join(parts)}</div>')
# ---------- reuse older sections (Amazon YoY + keywords) from previous file
old=open('Q3浴室柜_市场趋势与多渠道.html').read()
def grab(sec):
    m=re.search(r'(<section id="%s">.*?</section>)'%sec,old,re.S); return m.group(1)
s1,s2,s3=grab('s1'),grab('s2'),grab('s3')
def mk_ed(sec):
    return re.sub(r'<p class="say( warn)?">(.*?)</p>',lambda m:ED(m.group(2),'say'+(m.group(1) or '')),sec,flags=re.S)
MAP={'id="s1"':'id="s4"','id="s2"':'id="s5"','id="s3"':'id="s6"','<span class="no">①</span>':'<span class="no">④</span>','<span class="no">②</span>':'<span class="no">⑤</span>','<span class="no">③</span>':'<span class="no">⑥</span>'}
def remap(x):
    return re.sub('|'.join(re.escape(k) for k in MAP),lambda m:MAP[m.group(0)],x)
s1,s2,s3=[remap(mk_ed(x)) for x in (s1,s2,s3)]
css=re.search(r'<style>(.*?)</style>',old,re.S).group(1)
tpl=open(q3paths.CODE+'/tpl3.html').read()
_GMV={c:sum(sum(r['u'].get(m,0) for m in ('2026-08','2026-09','2026-10'))/3*(r['price'] or 0) for r in _RC[c]) for c,_n,_ in CH}; _GT=sum(_GMV.values())
cards=''.join(f'<div class="chc" style="--c:{col}"><h4>{n}</h4><div class="n">{I(R[c]["tot"]["u"])}<small> 件/月</small></div><dl><dt>{"SKU 数" if c=="amazon" else "父体数"}</dt><dd>{I(R[c]["tot"]["sku"])}</dd><dt>加权均价</dt><dd>{usd(R[c]["tot"]["price"])}</dd><dt>月销售额</dt><dd>${_GMV[c]/1e6:.2f}M（占四渠道 {_GMV[c]/_GT*100:.0f}%）</dd><dt>加权评分</dt><dd>{rt(R[c]["tot"]["rating"])}</dd><dt>拆装占比</dt><dd>{pct(R[c]["asm"])}</dd><dt>质量机会值</dt><dd>{R[c]["tot"]["qo"]:.1f}</dd></dl></div>' for c,n,col in CH)
_g=lambda c:_GMV[c]/_GT*100
_CONC=[('① 渠道总览',f'按销售额，Lowe&#39;s 最大（约 ${_GMV["lowes"]/1e6:.1f}M/月，占四渠道 {_g("lowes"):.0f}%），Amazon {_g("amazon"):.0f}%、Wayfair {_g("wayfair"):.0f}%、Home Depot {_g("homedepot"):.0f}%。Amazon 件数和 Lowe&#39;s 差不多，但均价只有一半（$354 对 $654）。线下两家自营品牌占销量 75%–81%，Wayfair 自营 79%。'),
 ('② 多渠道对照','四个渠道卖的不是一种货：Amazon 89% 是拆装、主销 30″、陶瓷台面；Home Depot、Lowe&#39;s 近九成是整装、主销 24″、人造大理石（Cultured Marble）台面；Wayfair 主销 36″、岗石台面、拆装占 63%。'),
 ('③ 分渠道明细','头部集中度差别很大：Home Depot 前 5 品牌占 99.9%，Lowe&#39;s 83%，Wayfair 49%，Amazon 27%。线下渠道基本是自营 + 一两个大牌；Amazon 最分散，新品牌最容易进。质量机会值 Home Depot 38.9、Lowe&#39;s 35.8 最高，Wayfair 7.6 最低。'),
 ('④ Amazon 大盘','近 3 个月销量比去年同期 +27%，销售额 +41%，加权均价从 $323 升到 $360。导出能看到的商品比去年多，涨幅有一部分是“看得更全”，看方向不看绝对值。'),
 ('⑤ Amazon 结构变化','48″、60″ 份额翻倍，18″ 腰斩；原木色份额翻倍，灰色减半；竖棱、农场风饰条在涨，纯色平板、横板条在退；悬浮式份额从 29% 降到 19%。'),
 ('⑥ 关键词趋势','339 个词总搜索比上一年少约 6%；大词 bathroom vanity 同比 −51%，买家转向带尺寸、带款式的长尾词。悬浮式最大词 floating bathroom vanity 同比 +19%。搜索转化（销量 ÷ 搜索量）2026-09 为 2.99%，同比 +15%，说明搜的人少了，但买的比例在升。'),
 ('趋势提醒（小平台）','Home Depot 4 月见顶后回落，8–10 月比 1–3 月低约 10%（CAGR −16%）。Wayfair 销量在涨（CAGR +16%），销售额却略降（−2%）：加权均价从 1–3 月约 $697 降到 8–10 月约 $630，多卖的是便宜款。小平台售价用代表链接现价，均价变化只反映卖得多的款在变。')]
CONC='<h3 class="rowt">各板块结论</h3><div class="conc">'+''.join(f'<div class="card"><h3>{t}</h3>{ED(x+"（点击可改）","say")}</div>' for t,x in _CONC)+'</div>'
D8=[d for d,_ in DIMS]
XO={d:list(v) for d,v in DIMS}
XD={}
for c,_n,_ in CH:
    L=[]
    for r in (_pk.load(open('recs_amz_all.pkl','rb')) if c=='amazon' else _RC[c]):
        at=r['at']
        for d in D8:
            v=at.get(d) or '未标'
            if v not in XO[d]: XO[d].append(v)
        L.append([r['pid'],round(r['price'],2) if r['price'] else None,round(r['rating'],2) if r['rating'] else None,[XO[d].index(at.get(d) or '未标') for d in D8],[round(r['u'].get(m,0),1) for m in M10x]])
    XD[c]=L
XJS=json.dumps({'dims':D8,'vals':XO,'data':XD,'ch':[[c,n,col] for c,n,col in CH],'months':M10x},ensure_ascii=False,separators=(',',':'))
out=tpl.replace('/*XJSON*/',XJS).replace('<!--CONC-->',CONC).replace('<!--TOPCH-->',TOPCH).replace('/*PRODJSON*/',json.dumps(PROD,ensure_ascii=False)).replace('<!--CARDS-->',cards).replace('/*CSS*/',css).replace('<!--OV-->',''.join(ov)).replace('<!--HEAT-->',''.join(ht)).replace('<!--TABS-->',''.join(tabs)).replace('<!--PANELS-->',''.join(panels)).replace('<!--S1-->',s1).replace('<!--S2-->',s2).replace('<!--S3-->',s3)
out=re.sub(r'<!--ED:(.*?)-->',lambda m:ED(m.group(1),'say'),out,flags=re.S)
out=re.sub(r'<!--EDB:(.*?)-->',lambda m:ED(m.group(1),'say big'),out,flags=re.S)
import hashlib
from pathlib import Path
report=Path('Q3浴室柜_市场与渠道数据报告.html')
version=hashlib.md5(out.encode()).hexdigest()[:8]
previous=''
if report.exists():
    prior=report.read_text(encoding='utf-8')
    old_key=re.search(r"var KEY='q3vanity-report-([0-9a-f]{8})';",prior)
    old_previous=re.search(r"var previousVersion='([0-9a-f]{8})';",prior)
    if old_key:
        previous=old_key[1] if old_key[1]!=version else (old_previous[1] if old_previous else '')
out=out.replace('__VER__',version).replace('__PREV_VER__',previous)
report.write_text(out,encoding='utf-8')
print('ok',eid[0])
