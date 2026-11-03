import os, numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
os.environ['VER']='9'; os.environ['MODE']='库'
P='/home/user/wxb981111-163.com/opportunity-research/solution-v2/trial/回归预测.py'
src=open(P,encoding='utf-8').read(); G={'__file__':P}; exec(compile(src[:src.index('# ---------- 回测')],P,'exec'),G)
A,U,feat,END=(G[k] for k in ('A','U','feat','END'))
B=A.copy(); B['r']=pd.to_numeric(B['评分'],errors='coerce'); B=B[B['r'].between(1,5)]
rows=[]
for u in U.index:
    L=U.at[u,'L']
    if L+5>END: continue
    f=feat[u]; s,t=f['主尺寸段'][0],f['台面类型'][0]
    w=B[B['m'].between(L-6,L-1)&(B['尺寸段']==s)&(B['台面类型']==t)&(B['单位']!=u)]
    own=B[(B['单位']==u)&B['m'].between(L,L+2)]
    if w['c'].sum()==0 or own.empty: continue
    rows.append(dict(u=u,y=U.at[u,'y'],cell_r=(w['r']*w['c']).sum()/w['c'].sum(),own_r=own['r'].median()))
R=pd.DataFrame(rows); R['差']=R.own_r-R.cell_r
print('新家族', len(R), '平均做到', round(R.y.mean()*10,1))
print('新品评分 − 同格老品评分 与做到 AUC', round(roc_auc_score(R.y,R['差']),3))
R['格子老品评分']=pd.qcut(R.cell_r,3,labels=['老品评分低','中','老品评分高'])
R['新品']=np.where(R['差']>=0.1,'新品比老品高 ≥0.1',np.where(R['差']<=-0.1,'新品比老品低 ≥0.1','差不多'))
t=R.pivot_table(index='格子老品评分',columns='新品',values='y',aggfunc=['mean','size'],observed=True)
print((t['mean']*10).round(1).astype(str)+'（'+t['size'].astype(str)+'）')
print(R[['cell_r','own_r']].describe().round(2))
