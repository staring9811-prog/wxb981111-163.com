import sqlite3,json,collections as C
c=sqlite3.connect('pdt.sqlite3'); D=json.load(open('data.json'))
# Lowe's size from product
ps=dict(c.execute("select pid,size from research_product where version_id=12"))
cn=C.Counter()
for pid,u in c.execute("select pid,units from research_monthly where version_id=12 and month between '2026-01' and '2026-10'"):
    if u: cn[ps.get(pid) or '未标']+=u
print('lowes size',cn.most_common(10))
D['ch']['lowes']['share']['尺寸段']=dict(cn)
# Amazon YoY share change
A=D['amz_share']; rec=['2026-08','2026-09','2026-10']; old=['2025-08','2025-09','2025-10']
yoy={}
for d,ms in A.items():
    def sh(months):
        t=C.Counter()
        for m in months: t.update(ms.get(m,{}))
        s=sum(t.values()); return {k:v/s for k,v in t.items()}
    a,b=sh(old),sh(rec)
    yoy[d]={k:[round(100*a.get(k,0),1),round(100*b.get(k,0),1)] for k in set(a)|set(b) if k!='未标'}
    print(d,sorted(yoy[d].items(),key=lambda z:-(z[1][1]-z[1][0]))[:4],'| down',sorted(yoy[d].items(),key=lambda z:(z[1][1]-z[1][0]))[:3])
D['yoy']=yoy
K=json.load(open('kw.json'))
def s(k,ms): return sum(K[k].get(m,0) for m in ms)
L=[f'2025-{i:02d}' for i in range(10,13)]+[f'2026-{i:02d}' for i in range(1,10)]
P=[f'2024-{i:02d}' for i in range(10,13)]+[f'2025-{i:02d}' for i in range(1,10)]
rows=[(k,s(k,L)/12,s(k,P)/12) for k in K]
rows=[(k,a,b,(a/b-1) if b>0 else None) for k,a,b in rows]
big=sorted(rows,key=lambda r:-r[1])[:12]
print('top kw',[(k,round(a),round(100*g) if g is not None else None) for k,a,b,g in big])
gr=sorted([r for r in rows if r[1]>=3000 and r[3] is not None],key=lambda r:-r[3])
print('fast up',[(k,round(a),round(100*g)) for k,a,b,g in gr[:12]])
print('down',[(k,round(a),round(100*g)) for k,a,b,g in gr[-8:]])
tot={m:sum(v.get(m,0) for v in K.values()) for m in sorted({m for v in K.values() for m in v}) if m>='2024-01'}
D['kw']=dict(core={k:K[k] for k in ['bathroom vanity','bathroom vanity with sink']},total=tot,top=[(k,a,g) for k,a,b,g in big],up=[(k,a,g) for k,a,b,g in gr[:10]],down=[(k,a,g) for k,a,b,g in gr[-6:]])
print('total yoy', sum(tot[m] for m in L)/sum(tot[m] for m in P))
json.dump(D,open('data.json','w'),ensure_ascii=False)
