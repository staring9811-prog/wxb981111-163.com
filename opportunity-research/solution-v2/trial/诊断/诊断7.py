import os, numpy as np, pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
os.environ['VER']='9'; os.environ['MODE']='库'
P='/home/user/wxb981111-163.com/opportunity-research/solution-v2/trial/回归预测.py'
src=open(P,encoding='utf-8').read(); G={'__file__':P}; exec(compile(src[:src.index('# ---------- 回测')],P,'exec'),G)
A,U,feat,newprod,END,ms=(G[k] for k in ('A','U','feat','newprod','END','ms'))
B=A.copy(); B['r']=pd.to_numeric(B['评分'],errors='coerce'); B=B[B['r'].between(1,5)]
B['low']=(B['r']<=4.0)*B['c']; B['价比l']=np.nan
rows=[]
for u in U.index:
    L=U.at[u,'L']; s=feat[u]['主尺寸段'][0]; t=feat[u]['台面类型'][0]
    w=B[B['m'].between(L-6,L-1)&(B['尺寸段']==s)&(B['台面类型']==t)]
    wa=B[B['m'].between(L-6,L-1)]
    rows.append(dict(u=u,L=L,y=U.at[u,'y'],cell_low=w['low'].sum()/max(w['c'].sum(),1)-wa['low'].sum()/wa['c'].sum(),cell_n=w['c'].sum()))
R=pd.DataFrame(rows).set_index('u'); R=R[(R['L']+5<=END)&(R['cell_n']>0)]
print('全部新家族', len(R), '低分高销（格子，相对品类）与做到 秩相关', round(spearmanr(R.cell_low,R.y)[0],3), 'AUC', round(roc_auc_score(R.y,R.cell_low),3))
# 按批：扣掉第一版打分
for Ts in ('2025-06','2025-08','2025-10','2025-12','2026-01'):
    T=G['mi'](Ts); c=R[R['L'].between(T,T+3)]
    if len(c)<15: continue
    p=pd.Series(newprod(T,False)(list(c.index)),index=c.index)
    res=c['y']-p
    print(Ts,len(c),'AUC 低分高销',round(roc_auc_score(c.y,c.cell_low),2),'AUC 打分',round(roc_auc_score(c.y,p),2),'扣打分后相关',round(spearmanr(c.cell_low,res)[0],2))
