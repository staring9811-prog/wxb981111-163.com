import os, numpy as np, pandas as pd
from scipy.stats import spearmanr
os.environ['MODE']='库'
P='/home/user/wxb981111-163.com/opportunity-research/solution-v2/trial/回归预测.py'
src=open(P,encoding='utf-8').read(); src=src[:src.index("FEAT = {T")]
ns={'__file__':P}; exec(compile(src,P,'exec'),ns)
PAN,ms,mi,END,M0=(ns[k] for k in ('PAN','ms','mi','END','M0'))
E=0.002
S=[]  # 每个单元的份额矩阵、销量
for dims,(C,F,den,vals) in PAN.items():
    sh=C.div(den.replace(0,np.nan),axis=1); sh.index=[' × '.join(dims)+'：'+v for v in sh.index]; c=C.copy(); c.index=sh.index
    S.append((sh,c))
SH=pd.concat([s for s,_ in S]); CC=pd.concat([c for _,c in S])
def slope(T,n,w=None):
    cols=list(range(T-n,T)); y=np.log(SH[cols]+E); x=np.arange(n)-(n-1)/2
    return (y*x).sum(axis=1)/(x**2).sum(), y.mean(axis=1)   # 每月对数斜率、中心水平
rows=[]
for T in range(M0+6,END-4):
    for k in (3,6):
        if T+k+2>END: continue
        base6=np.log(SH[list(range(T-6,T))].mean(axis=1)+E); base3=np.log(SH[list(range(T-3,T))].mean(axis=1)+E)
        fut=np.log(SH[list(range(T+k,T+k+3))].mean(axis=1)+E); vol=CC[list(range(T-3,T))].mean(axis=1)
        b6,l6=slope(T,6)
        d=pd.DataFrame({'T':T,'k':k,'vol':vol,'y6':fut-base6,'y3':fut-base3,'x1':base3-np.log(SH[list(range(T-6,T-3))].mean(axis=1)+E),'b6':b6,'dev':base3-l6})
        if T-9>=M0: d['b9']=slope(T,9)[0]
        if T-12>=M0:
            d['b12']=slope(T,12)[0]; d['m66']=base6-np.log(SH[list(range(T-12,T-6))].mean(axis=1)+E)
        rows.append(d)
R=pd.concat(rows); R=R[R['vol']>=300]
print('≥300 件单元，按 (T,k) 的秩相关：目标 y6 = 未来 3 个月份额 对 近 6 个月平均 的对数变化')
out=[]
for (T,k),d in R.groupby(['T','k']):
    r={'T':ms(T),'k':k,'n':len(d)}
    for f in ('x1','b6','b9','b12','m66','dev'):
        if f in d and d[f].notna().sum()>10: r[f]=round(spearmanr(d[f],d['y6'],nan_policy='omit')[0],2)
    r['x1→y3']=round(spearmanr(d['x1'],d['y3'])[0],2)
    out.append(r)
print(pd.DataFrame(out).to_string())
