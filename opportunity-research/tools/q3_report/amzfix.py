"""卖家精灵某些月份把多子体家族里的子体当成“单子体链接”，并把整个家族月销记到这个子体上。
修正：相邻月份它属于一个多子体家族 → 本月也并回那个家族；家族本月总销量不重复计，按相邻月份的子体占比分给这些子体。"""
import sqlite3,collections as C,statistics as S
def corrections(db='pdt.sqlite3'):
    c=sqlite3.connect(db)
    rows=c.execute("select item_id,month,json_extract(raw,'$.family_key'),json_extract(raw,'$.fam_units'),coalesce(json_extract(raw,'$.child_units'),units) from snapshot where channel='amazon'").fetchall()
    fk={(i,m):f for i,m,f,fu,cu in rows}; fu_={(i,m):fu for i,m,f,fu,cu in rows}; cu_={(i,m):cu or 0 for i,m,f,fu,cu in rows}
    months=sorted({m for _,m,*_ in rows}); idx={m:k for k,m in enumerate(months)}
    size=C.Counter((m,f) for (i,m),f in fk.items())
    members=C.defaultdict(list)
    for (i,m),f in fk.items(): members[(m,f)].append(i)
    orphan={}   # (i,m) -> (g, neighbor month)
    for (i,m),f in fk.items():
        if size[(m,f)]!=1: continue
        for d in (-1,1,-2,2):
            k=idx[m]+d
            if 0<=k<len(months):
                n=months[k]; g=fk.get((i,n))
                if g and g!=f and size[(n,g)]>1: orphan[(i,m)]=(g,n); break
    fix={}; log=[]
    groups=C.defaultdict(list)
    for (i,m),(g,n) in orphan.items(): groups[(m,g)].append((i,n))
    for (m,g),orph in groups.items():
        base=[i for i in members.get((m,g),[]) if (i,m) not in orphan]
        tot=S.median([fu_[(i,m)] for i in base if fu_[(i,m)]]) if base and any(fu_[(i,m)] for i in base) else S.median([fu_[(i,m)] or 0 for i,_ in orph])
        sh={}
        for i,n in orph:
            nf=fu_.get((i,n)) or 0; sh[i]=(cu_.get((i,n),0)/nf) if nf else 0
        so=min(sum(sh.values()),1.0)
        for i,_ in orph: fix[(i,m)]=tot*sh[i]
        bsum=sum(cu_[(i,m)] for i in base)
        if base and bsum>0:
            k=tot*(1-so)/bsum
            for i in base: fix[(i,m)]=cu_[(i,m)]*k
        before=sum(cu_[(i,m)] for i,_ in orph)+bsum; after=sum(fix[(i,m)] for i,_ in orph)+(tot*(1-so) if base and bsum>0 else bsum)
        log.append((m,g,len(orph),round(before),round(after)))
    # 第二种：同一个月里，同品牌好几个“单子体”链接各自记了几乎一样的家族销量（卖家精灵没认出它们是一家）→ 合成一个家族，总量只算一次，平均分
    tt={i:(t or '') for i,t in c.execute("select item_id,title from product where channel='amazon'")}
    br={i:(b or '') for i,b in c.execute("select item_id,brand from product where channel='amazon'")}
    import re as _re
    def stem(i): return ' '.join(_re.findall(r'[a-z]+',tt.get(i,'').lower())[:3])
    singles=C.defaultdict(list)
    for (i,m),f in fk.items():
        if size[(m,f)]==1 and (i,m) not in orphan and fu_[(i,m)] and fu_[(i,m)]>=20: singles[(m,br.get(i,''),stem(i))].append(i)
    for (m,b,st),ii in singles.items():
        if len(ii)<2 or not b: continue
        ii=sorted(ii,key=lambda i:fu_[(i,m)])
        cl=[[ii[0]]]
        for i in ii[1:]:
            if fu_[(i,m)]<=fu_[(cl[-1][0],m)]*1.06: cl[-1].append(i)
            else: cl.append([i])
        for g in cl:
            if len(g)<2: continue
            tot=S.median([fu_[(i,m)] for i in g])
            for i in g: fix[(i,m)]=tot/len(g)
            log.append((m,'同品牌合并:'+b,len(g),round(sum(cu_[(i,m)] for i in g)),round(tot)))
    return fix,log
if __name__=='__main__':
    fix,log=corrections()
    by=C.defaultdict(lambda:[0,0,0])
    for m,g,n,b,a in log: by[m][0]+=n; by[m][1]+=b; by[m][2]+=a
    for m in sorted(by): print(m,'子体',by[m][0],'修正前',by[m][1],'修正后',by[m][2])
    print('B0HF3ZM8B8 2026-10 ->',round(fix.get(('B0HF3ZM8B8','2026-10'),-1),1))
