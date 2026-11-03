import os, itertools, numpy as np, pandas as pd
from scipy.stats import spearmanr
os.environ['VER']='9'; os.environ['MODE']='库'
P='/home/user/wxb981111-163.com/opportunity-research/solution-v2/trial/回归预测.py'
src=open(P,encoding='utf-8').read(); G={'__file__':P}; exec(compile(src[:src.index('# ---------- 回测')],P,'exec'),G)
A,PAN,FEAT,target,ms,END,M0,KEYCOL,UNK=(G[k] for k in ('A','PAN','FEAT','target','ms','END','M0','KEYCOL','UNK'))
B=A[A['价格'].gt(0)&A['尺寸段'].notna()&A['装'].notna()].copy()
B['lp']=np.log(B['价格']/B.groupby(['m','尺寸段','装'])['价格'].transform('median'))
PR={}
for dims in PAN:
    df=pd.DataFrame({'m':B['m'].values,'c':B['c'].values,'lp':B['lp'].values})
    for d in dims: df[d]=KEYCOL[d].loc[B.index].values
    for d in dims:
        if d=='元素': df=df.explode(d)
    for d in dims: df=df[~df[d].map(UNK)]
    df['k']=df[list(dims)].astype(str).agg(' × '.join,axis=1); df['att']=' × '.join(dims); df['w']=df['c']*df['lp']
    PR[dims]=df
ALL=pd.concat(PR.values())
out=[]
for T in range(M0+6, END-7):
    D=FEAT[T]; w=ALL[ALL['m'].between(T-6,T-1)].groupby(['att','k'])[['w','c']].sum(); prem=(w['w']/w['c']).reindex(D.index)
    # 溢价变化：近 3 个月 vs 再前 3 个月
    w1=ALL[ALL['m'].between(T-3,T-1)].groupby(['att','k'])[['w','c']].sum(); w0=ALL[ALL['m'].between(T-6,T-4)].groupby(['att','k'])[['w','c']].sum()
    dprem=((w1['w']/w1['c'])-(w0['w']/w0['c'])).reindex(D.index)
    for k in (6,8):
        if T+k+2>END: continue
        y=target(D,T,k) if G['BASE']=='份额6' else None
        d=D.assign(y=y,prem=prem,dprem=dprem); d=d[d['近3月']>=300].dropna(subset=['y','prem'])
        X=np.c_[np.ones(len(d)),d['b6'],d['x5']]; rb=d['y']-X@np.linalg.lstsq(X,d['y'],rcond=None)[0]
        out.append(dict(T=ms(T),k=k,n=len(d),溢价=round(spearmanr(d.prem,d.y)[0],2),溢价_扣斜率新品=round(spearmanr(d.prem,rb)[0],2),溢价变化=round(spearmanr(d.dprem,d.y,nan_policy='omit')[0],2),溢价变化_扣=round(spearmanr(d.dprem,rb,nan_policy='omit')[0],2)))
print(pd.DataFrame(out).to_string())
