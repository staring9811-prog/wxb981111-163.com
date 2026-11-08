import q3paths
"""把干净数据源 + wen 打标（v2）变成报告用的小平台记录：一条 = 一个父体。
尺寸、价格、评分取父体“代表链接”（在榜排名最高的那个，即这个形态里卖得最好的）；Lowe's 只有当下时间点。"""
import pickle,csv,re,openpyxl,os,html
D=q3paths.INPUT+'/渠道关键词/大词'
CL=q3paths.CLEAN
TAG=q3paths.TAG
def band(p):
    if p is None: return '未标'
    return '<$200' if p<200 else '$200–399' if p<400 else '$400–699' if p<700 else '$700–999' if p<1000 else '≥$1000'
def band10(w):
    for lo,hi,b in [(15,21,'18″'),(21,26,'24″'),(26,29,'28″'),(29,33,'30″'),(33,39,'36″'),(39,45,'42″'),(45,54,'48″'),(54,66,'60″'),(66,999,'72″+')]:
        if w is not None and lo<=w<hi: return b
    return '未标'
def norm_elem(v):
    v=(v or '').strip()
    if not v: return '未标'
    if v.startswith('夏克式'): return '夏克式'
    return {'纯色平板':'纯色','藤编':'rattan'}.get(v,v)
def nz(v): return v if v not in (None,'') else '未标'
def f2(x):
    try: v=float(x)
    except (TypeError,ValueError): return None
    return None if v!=v else v
def load():
    rows=list(csv.DictReader(open(D+'/三平台_商品表.csv',encoding='utf-8-sig')))
    by={(r['渠道'],r['pid'].split(' ')[0]):r for r in rows}
    wb=openpyxl.load_workbook(TAG,read_only=True); T={}
    for sh in ['Home Depot','Wayfair',"Lowe's"]:
        it=wb[sh].iter_rows(values_only=True); h=next(it); ix={k:i for i,k in enumerate(h)}
        for r in it: T[(sh,str(r[0]))]={k:r[ix['确认：'+k]] for k in ['拆装/整装','台面材质','柜体材质','元素','形态']}
    H=pickle.load(open(CL+'/hd.pkl','rb')); W=pickle.load(open(CL+'/wf.pkl','rb')); L=pickle.load(open(CL+'/lw.pkl','rb'))
    out={'homedepot':[],'wayfair':[],'lowes':[]}; excl=[]
    def mk(ch,fid,rep_pid,brand,title,price,rating,size,vp,nv,tags,extra=None):
        if (tags.get('元素') or '')=='不是浴室柜': excl.append((ch,fid)); return
        u={m:50*vp.get(m,0)+20*nv.get(m,0) for m in set(vp)|set(nv)}
        rec=dict(pid=fid,fam=fid,brand=brand or '未知品牌',price=price,rating=rating,u=u,vp=dict(vp),nv=dict(nv),r={},
             at={'尺寸':size,'形态':{'站立式':'落地式'}.get(tags.get('形态') or '','未标' if not tags.get('形态') else tags['形态']),'拆装':nz(tags.get('拆装/整装')),
                 '台面':nz(tags.get('台面材质')),'柜体':nz(tags.get('柜体材质')),'主色':'未标','元素':norm_elem(tags.get('元素')),'价格带':band(price)},
             rep=rep_pid,title=title,listed=True,src='父体（代表链接 '+rep_pid+'）')
        if extra: rec.update(extra)
        out[ch].append(rec)
    def hdbrand(i):
        if i.get('品牌'): return i['品牌']
        m=re.search(r'/svn/([a-z0-9-]+?)-(bathroom|vanit|vanity)',i.get('主图') or '')
        if not m: return ''
        return {'glacier-bay':'Glacier Bay','home-decorators-collection':'Home Decorators Collection','hampton-bay':'Hampton Bay','vanity-art':'Vanity Art','design-house':'Design House'}.get(m.group(1),m.group(1).replace('-',' ').title())
    for f in H['fams']:
        rep=min((rk,p) for rk,p in H['sel'] if H['info'][p]['fam']==f)[1]; i=H['info'][rep]; vp,nv=H['fam_rev'][f]
        mk('homedepot',f,rep,hdbrand(i),html.unescape(i['title']),f2(i['价格']),f2(i['评分']),band10(f2(i['宽'])) if f2(i['宽']) else (i['尺寸段'] or '未标'),vp,nv,T.get(('Home Depot',f),{}))
    for root,fm in W['fams'].items():
        rep=min(fm['members'],key=lambda p:W['L'][p]['rank']); i=W['info'][rep]
        mk('wayfair',fm['name'],rep,i['品牌'],html.unescape(i['title']),f2(i['价格']),f2(i['评分']),band10(f2(i['宽'])) if f2(i['宽']) else (i['尺寸段'] or '未标'),fm['vp'],fm['nv'],T.get(('Wayfair',fm['name']),{}))
    FX=pickle.load(open(CL+'/lw_fix.pkl','rb'))
    for r in L['rows']:
        i=by.get(("Lowe's",r['pid']),{}); fx=FX.get(r['pid'],(None,None,None))
        m=re.search(r'(\d{2}(?:\.\d+)?)[- ]?in\b',r['title'] or '')
        size=i.get('尺寸段') or band10(f2(fx[2])) if (i.get('尺寸段') or f2(fx[2])) else band10(float(m.group(1)) if m else None)
        v=r['sales']; vp={}; nv={}
        rec_u={'2026-08':v,'2026-09':v,'2026-10':v}
        mk('lowes',r['pid'],r['pid'],r['brand'],r['title'],f2(fx[0]) or f2(i.get('价格')),f2(fx[1]) or f2(i.get('评分')),size or '未标',{},{},T.get(("Lowe's",r['pid']),{}),
           extra=dict(u=rec_u,snapshot=True,src=r['how'],rank=r['rank']))
    return out,excl
if __name__=='__main__':
    o,e=load(); print({k:len(v) for k,v in o.items()},'剔除',e)
    import collections as C
    for ch in o: print(ch,C.Counter(x['at']['尺寸'] for x in o[ch]).most_common(5),C.Counter(x['at']['价格带'] for x in o[ch]).most_common(5))
