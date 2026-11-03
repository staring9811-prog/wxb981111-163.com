import os, numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
os.environ['VER']='9'; os.environ['MODE']='库'
P='/home/user/wxb981111-163.com/opportunity-research/solution-v2/trial/回归预测.py'
src=open(P,encoding='utf-8').read(); G={'__file__':P}; exec(compile(src[:src.index('# ---------- 回测')],P,'exec'),G)
A,U,feat,newprod,END,ms,mi,PAN,FEAT,target,M0,KEYCOL,UNK=(G[k] for k in ('A','U','feat','newprod','END','ms','mi','PAN','FEAT','target','M0','KEYCOL','UNK'))
B=A[A['价格'].gt(0)&A['尺寸段'].notna()&A['装'].notna()].copy()
B['lp']=np.log(B['价格']/B.groupby(['m','尺寸段','装'])['价格'].transform('median')); B['w']=B['lp']*B['c']
# 1. 市场层：按新品占比分组，看溢价和份额变化（扣斜率）
parts=[]
for dims in PAN:
    df=pd.DataFrame({'m':B['m'].values,'c':B['c'].values,'w':B['w'].values})
    for d in dims: df[d]=KEYCOL[d].loc[B.index].values
    for d in dims:
        if d=='元素': df=df.explode(d)
    for d in dims: df=df[~df[d].map(UNK)]
    df['k']=df[list(dims)].astype(str).agg(' × '.join,axis=1); df['att']=' × '.join(dims); parts.append(df[['m','c','w','k','att']])
ALL=pd.concat(parts); out=[]
for T in range(M0+6, END-7):
    D=FEAT[T]; W=ALL[ALL['m'].between(T-6,T-1)].groupby(['att','k'])[['w','c']].sum(); prem=(W['w']/W['c']).reindex(D.index)
    for k in (6,8):
        if T+k+2>END: continue
        d=D.assign(y=target(D,T,k),prem=prem); d=d[d['近3月']>=300].dropna(subset=['y','prem'])
        X=np.c_[np.ones(len(d)),d['b6']]; rb=d['y']-X@np.linalg.lstsq(X,d['y'],rcond=None)[0]; d['rb']=rb
        hi=d[d['x5']>d['x5'].median()]; lo=d[d['x5']<=d['x5'].median()]
        out.append(dict(T=ms(T),k=k,新品多_溢价vs份额=round(spearmanr(hi.prem,hi.rb)[0],2),新品少_溢价vs份额=round(spearmanr(lo.prem,lo.rb)[0],2)))
print(pd.DataFrame(out).to_string())
# 2. 新品层：新家族上架前 6 个月，它的元素 / 尺寸×台面 的溢价，和做到
pre=lambda u,L,col,val: (lambda w: w['w'].sum()/w['c'].sum() if w['c'].sum()>0 else np.nan)(B[B['m'].between(L-6,L-1)&(B[col]==val)])
rows=[]
for u in U.index:
    L=U.at[u,'L']
    if L+5>END: continue
    f=feat[u]; s,t=f['主尺寸段'][0],f['台面类型'][0]
    w=B[B['m'].between(L-6,L-1)&(B['尺寸段']==s)&(B['台面类型']==t)]
    els=[e for e in f['元素'] if e not in ('未知','fluted','reeded')]
    we=B[B['m'].between(L-6,L-1)&B['元素一'].map(lambda x: any(e in x for e in els))] if els else B.iloc[:0]
    rows.append(dict(u=u,L=L,y=U.at[u,'y'],格子溢价=w['w'].sum()/w['c'].sum() if w['c'].sum()>0 else np.nan,元素溢价=we['w'].sum()/we['c'].sum() if we['c'].sum()>0 else np.nan))
R=pd.DataFrame(rows).set_index('u')
for c_ in ('格子溢价','元素溢价'):
    d=R.dropna(subset=[c_]); print(c_, len(d), 'AUC', round(roc_auc_score(d.y,d[c_]),3), '高 1/3 每 10 个', round(d[d[c_]>=d[c_].quantile(2/3)].y.mean()*10,1), '低 1/3', round(d[d[c_]<=d[c_].quantile(1/3)].y.mean()*10,1))
for Ts in ('2025-06','2025-08','2025-10','2025-12','2026-01'):
    T=mi(Ts); c=R[R['L'].between(T,T+3)].dropna(subset=['元素溢价'])
    p=pd.Series(newprod(T,False)(list(c.index)),index=c.index)
    print(Ts,len(c),'元素溢价 AUC',round(roc_auc_score(c.y,c['元素溢价']),2),'扣打分后相关',round(spearmanr(c['元素溢价'],c.y-p)[0],2), '格子溢价扣后', round(spearmanr(c['格子溢价'],c.y-p,nan_policy='omit')[0],2))
