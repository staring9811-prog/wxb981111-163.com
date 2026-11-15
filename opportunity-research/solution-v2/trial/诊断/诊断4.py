import os, itertools, numpy as np, pandas as pd
from scipy.stats import spearmanr
os.environ['MODE']='库'
P='/home/user/wxb981111-163.com/opportunity-research/solution-v2/trial/回归预测.py'
src=open(P,encoding='utf-8').read(); src=src[:src.index("FEAT = {T")]
ns={'__file__':P}; exec(compile(src,P,'exec'),ns)
A,PAN,ms,END,M0,KEYCOL,UNK,DIMS,MONTHS,search_yoy=(ns[k] for k in ('A','PAN','ms','END','M0','KEYCOL','UNK','DIMS','MONTHS','search_yoy'))
print('月龄 示例', A['月龄'].describe().round(1).to_dict(), '缺失', A['月龄'].isna().mean().round(3))
NEW=(A['月龄']<=6).values
NP={}
for dims in PAN:
    df=pd.DataFrame({'m':A['m'].values,'c':A['c'].values*NEW})
    for d in dims: df[d]=KEYCOL[d].values
    for d in dims:
        if d=='元素': df=df.explode(d)
    for d in dims: df=df[~df[d].map(UNK)]
    key=df[list(dims)].astype(str).agg(' × '.join,axis=1)
    NP[dims]=df.groupby([key,df['m']])['c'].sum().unstack(fill_value=0).reindex(columns=MONTHS,fill_value=0)
E=0.002; rows=[]
for T in range(M0+6, END-7):
  yo=search_yoy(T)
  for dims,(C,F,den,vals) in PAN.items():
    c6=list(range(T-6,T)); sh=C[c6].div(den.loc[T-6:T-1],axis=1)
    base=np.log(C[c6].sum(axis=1)/den.loc[T-6:T-1].sum()+E)
    x=np.arange(6)-2.5; b6=(np.log(sh+E)*x).sum(axis=1)/(x**2).sum()
    tot=C[c6].sum(axis=1); newsh=NP[dims][c6].sum(axis=1)/tot.replace(0,np.nan)
    catnew=sum(NP[dims][c6].sum().sum() for _ in [0])/max(C[c6].sum().sum(),1)
    for k in (6,8):
        a=T+k
        if a+2>END: continue
        fut=np.log(C[list(range(a,a+3))].sum(axis=1)/den.loc[a:a+2].sum()+E)
        s3=[np.array([yo.get((d,v),np.nan) for v in vals.loc[C.index,d]]) for d in dims if d!='材质']
        s3=np.nanmean(np.vstack(s3),axis=0) if s3 else np.full(len(C),np.nan)
        rows.append(pd.DataFrame({'T':T,'k':k,'vol':C[list(range(T-3,T))].mean(axis=1),'y':fut-base,'b6':b6,'new':newsh-catnew,'s3':s3}))
R=pd.concat(rows); R=R[R['vol']>=300].dropna(subset=['new'])
import statsmodels.api as sm
out=[]
for (T,k),d in R.groupby(['T','k']):
    rb=d['y']-np.polyval(np.polyfit(d['b6'],d['y'],1),d['b6'])
    out.append(dict(T=ms(T),k=k,n=len(d),b6=round(spearmanr(d.b6,d.y)[0],2),new=round(spearmanr(d.new,d.y)[0],2),new_resid=round(spearmanr(d.new,rb)[0],2),
      s3=round(spearmanr(d.s3,d.y,nan_policy='omit')[0],2), s3_resid=round(spearmanr(d.s3,rb,nan_policy='omit')[0],2)))
print(pd.DataFrame(out).to_string())
