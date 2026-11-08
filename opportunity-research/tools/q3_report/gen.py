import q3paths
import json,html
D=json.load(open('data.json'))
E_=html.escape
CH=[('amazon','Amazon','#2a78d6'),('homedepot','Home Depot','#eb6834'),('lowes',"Lowe's",'#1baf7a'),('wayfair','Wayfair','#eda100')]
def fmt(x): return f'{x/1e4:.1f} 万' if x>=1e4 else f'{x:,.0f}'
def vbars(pairs,color,h=200,w=900,unit='件',hl=None):
    n=len(pairs); mx=max(v for _,v in pairs) or 1; bw=(w-40)/n; s=[]
    for i,(k,v) in enumerate(pairs):
        bh=(h-40)*v/mx; x=30+i*bw; y=h-25-bh
        col=color if not hl or hl(k) else '#9fb9d8'
        s.append(f'<g><title>{k}：{fmt(v)} {unit}</title><rect x="{x+1:.1f}" y="{y:.1f}" width="{bw-2:.1f}" height="{bh:.1f}" rx="3" fill="{col}"/>')
        if i%3==0 or i==n-1: s.append(f'<text x="{x+bw/2:.1f}" y="{h-8}" class="ax" text-anchor="middle">{k[2:].replace("-","/")}</text>')
        s.append('</g>')
    s.append(f'<line x1="28" x2="{w-8}" y1="{h-25}" y2="{h-25}" class="base"/>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">{"".join(s)}</svg>'
def pairbars(rows,w=430):
    # rows: (label, old%, new%)
    mx=max(max(a,b) for _,a,b in rows) or 1; h=len(rows)*34+10; s=[]
    for i,(k,a,b) in enumerate(rows):
        y=8+i*34; d=b-a; cls='up' if d>=1 else 'dn' if d<=-1 else 'fl'
        s.append(f'<text x="0" y="{y+15}" class="lb">{E_(k)}</text>')
        s.append(f'<g><title>{k}：去年同期 {a:.1f}% → 近 3 个月 {b:.1f}%</title><rect x="96" y="{y+2}" width="{(w-190)*a/mx:.1f}" height="9" rx="2" fill="#c9c7c0"/><rect x="96" y="{y+13}" width="{(w-190)*b/mx:.1f}" height="11" rx="2" fill="#2a78d6"/></g>')
        s.append(f'<text x="{w-88}" y="{y+19}" class="val">{b:.0f}%</text><text x="{w}" y="{y+19}" text-anchor="end" class="{cls}">{"+" if d>0 else ""}{d:.1f}</text>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart">{"".join(s)}</svg>'
def chbars(dim,order,w=430,skip=()):
    sh={}
    for c,_,_ in CH:
        s=D['ch'][c]['share'].get(dim,{}); t=sum(v for k,v in s.items() if k not in('未标','未知','多尺寸未拆'))
        sh[c]={k:100*v/t for k,v in s.items()} if t and c not in skip else None
    mx=max(v.get(k,0) for v in sh.values() if v for k in order) or 1
    h=len(order)*(4*8+16)+6; s=[]
    for i,k in enumerate(order):
        y=4+i*48; s.append(f'<text x="0" y="{y+20}" class="lb">{E_(k)}</text>')
        for j,(c,nm,col) in enumerate(CH):
            if sh[c] is None: continue
            v=sh[c].get(k,0); yy=y+j*8+2
            s.append(f'<g><title>{nm} · {k}：{v:.0f}%</title><rect x="96" y="{yy}" width="{max((w-150)*v/mx,1):.1f}" height="6" rx="2" fill="{col}"/></g>')
            if v>=1: s.append(f'<text x="{100+(w-150)*v/mx:.1f}" y="{yy+6}" class="sv">{v:.0f}</text>')
    return f'<svg viewBox="0 0 {w} {h}" class="chart">{"".join(s)}</svg>'
Y=D['yoy']
def py(dim,keys,lab=None): return pairbars([((lab or {}).get(k,k),Y[dim].get(k,[0,0])[0],Y[dim].get(k,[0,0])[1]) for k in keys])
am=D['amz_month']; units=[(r['m'],r['u']) for r in am]; rev=[(r['m'],r['r']) for r in am]
kwc=D['kw']['core']; months=[m for m in sorted(D['kw']['total']) if m>='2024-10']
kwt=[(m,D['kw']['total'][m]) for m in months]
kw1=[(m,kwc['bathroom vanity with sink'].get(m,0)+kwc['bathroom vanity'].get(m,0)) for m in months]
def kwtable(rows,cls):
    return '<table><tr><th>关键词</th><th class="r">近 12 个月月均搜索</th><th class="r">比上一年</th></tr>'+''.join(f'<tr><td>{E_(k)}</td><td class="r">{a:,.0f}</td><td class="r {("up" if g>0.05 else "dn" if g<-0.05 else "fl")}">{"+" if g>0 else ""}{100*g:.0f}%</td></tr>' for k,a,g in rows)+'</table>'
legend=''.join(f'<span class="lg"><i style="background:{c}"></i>{n}</span>' for _,n,c in CH)
chm={c:D['ch'][c]['month'] for c,_,_ in CH}
def chmon(c,col):
    ms=[f'2026-{i:02d}' for i in range(1,11)]; return vbars([(m,chm[c].get(m,0)) for m in ms],col,h=150,w=420)
tpl=open(q3paths.CODE+'/tpl.html').read()
out=tpl.format(**dict(
 u_chart=vbars(units,'#2a78d6'),
 r_chart=vbars([(m,v/1e4) for m,v in rev],'#2a78d6',unit='万美元'),
 kw_chart=vbars(kw1,'#6250d6',unit='次搜索'),
 kwall_chart=vbars(kwt,'#6250d6',unit='次搜索'),
 size=py('尺寸段',['18″','24″','28″','30″','36″','42″','48″','60″','72″+']),
 form=py('形态',['落地式','悬浮式','柱状盆']),
 color=py('主色',['白','黑','原木','深木','灰','绿','蓝']),
 cab=py('柜体材质',['MDF','实木框架','实木','含胶合板','含刨花板']),
 top=py('台面材质',['陶瓷','树脂','木板','岗石','石英石','岩板']),
 elem=py('元素',['夏克式','农场风装饰饰条','竖棱','纯色','自然木纹','横板条','搭叠式','玻璃门']),
 price=py('价位',['<$200','$200–399','$400–699','$700–999','≥$1000']),
 kw_top=kwtable(D['kw']['top'][:10],''), kw_up=kwtable(D['kw']['up'][:8],''), kw_dn=kwtable(D['kw']['down'][::-1],''),
 legend=legend,
 c_size=chbars('尺寸段',['24″','30″','36″','48″','60″','72″+'],skip=('lowes',)),
 c_asm=chbars('装',['拆装','整装']), c_form=chbars('形态',['落地式','悬浮式']),
 c_color=chbars('主色',['白','黑','原木','深木','灰','蓝','绿']),
 c_cab=chbars('柜体材质',['MDF','实木框架','含刨花板','实木']),
 c_top=chbars('台面材质',['陶瓷','树脂','岗石','Cultured Marble','石英石','卡拉拉大理石']),
 c_price=chbars('价位',['<$200','$200–399','$400–699','$700–999','≥$1000']),
 m_hd=chmon('homedepot','#eb6834'), m_lw=chmon('lowes','#1baf7a'), m_wf=chmon('wayfair','#eda100'),
))
open('Q3浴室柜_市场趋势与多渠道.html','w').write(out)
