"""从抓到的 Amazon 商品页文字判台盆、柜体材质。用法：python amz_pdp_classify.py [商品页 json 目录]；输出 data/amz_pdp_tags.json：asin -> {basin, basin_src, cab, cab_src, width}"""
import json,glob,re,os
import sys,os
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import q3paths
PAGES=sys.argv[1] if len(sys.argv)>1 else os.path.join(q3paths.DATA,'amz_pdp')   # 每个 ASIN 一个 json（标题、五点、描述、规格表）
NEAR=r'(?:\s+[\w\-/]+){0,3}?\s+(?:sinks?|basins?|vanity tops?|tops?|countertops?|bowls?)'
B=[('CM',r'cultured[\s\-]marble'),('树脂',r'\bresin\b|solid[\s\-]surface|acrylic|\bSMC\b|fiberglass|poly[\s\-]?marble'),('陶瓷',r'ceramic|porcelain|vitreous')]
NEG=re.compile(r'(?:than|unlike|instead of|vs\.?|versus|compared (?:to|with))\s+(?:\w+\s+){0,3}?(?:ceramic|porcelain|resin|acrylic)\w*(?:\s+\w+){0,2}',re.I)
def hits(t):
    t=NEG.sub(' ',t)
    near=sorted({nm for nm,p in B if re.search('(?:'+p+')'+NEAR,t,re.I)})
    anyb=sorted({nm for nm,p in B if re.search(p,t,re.I)})
    return near,anyb
def basin(parts,spec):
    for k in ('Sink Material','Sink Material Type','Basin Material','Countertop Material','Top Material Type','Vanity Top Material'):
        v=spec.get(k,'')
        hb=[nm for nm,p in B if re.search(p,v,re.I)]
        if len(hb)==1: return hb[0],f'规格表 {k}: {v}'
    # 按可信度依次看：标题 → 五点 → 描述 → 图文详情（图文详情常带别家对比表，最后看）
    for nm_src,t in parts:
        near,anyb=hits(t)
        if len(near)==1: return near[0],f'{nm_src}（材质+sink/top）'
        if len(near)>1: return '冲突',f'{nm_src}同时写了：'+'、'.join(near)
        if len(anyb)==1: return anyb[0],f'{nm_src}提及'
        if len(anyb)>1: return '冲突',f'{nm_src}同时出现：'+'、'.join(anyb)
    t=' '.join(x for _,x in parts)
    if re.search(r'integrated\s+(?:\w+\s+){0,2}(?:sink|basin|top)|one[\s\-]piece\s+(?:\w+\s+){0,2}(?:sink|top)|seamless\s+(?:\w+\s+){0,2}sink',t,re.I): return '一体盆未写材质','正文写一体盆'
    return '未写','未写材质'
C=[('实木框架',r'solid[\s\-]wood\s+frame|hardwood\s+frame|solid\s+wood\s+(?:and|&|\+)\s+(?:MDF|plywood|engineered)'),('实木',r'solid\s+(?:wood|oak|pine|rubberwood|birch|ash|walnut)|rubberwood|100%\s+solid'),('含胶合板',r'plywood'),('含刨花板',r'particle\s?board|\bP2\b|chipboard'),('MDF',r'\bMDF\b|medium[\s\-]density')]
def cab(t2,spec):
    t=t2
    hits=[nm for nm,p in C if re.search(p,t,re.I)]
    if hits: return hits[0],'正文：'+'、'.join(hits)
    v=' '.join(spec.get(k,'') for k in ('Frame Material Type','Material Type','Material'))
    if re.search(r'engineered wood',v,re.I): return '人造板（未细分）','规格表 Engineered Wood'
    return '未写',''
def width(spec):
    for k in ('Item Dimensions D x W x H','Product Dimensions','Item Dimensions  L x W x H','Size'):
        v=spec.get(k,'')
        m=re.search(r'([\d.]+)"?\s*W',v) or re.search(r'x\s*([\d.]+)\s*x',v)
        if m: return float(m.group(1))
    return None
out={}
for f in glob.glob(PAGES+'/*.json'):
    d=json.load(open(f));s=d.get('spec',{})
    t=' '.join([d.get('title',''),d.get('bullets',''),d.get('desc',''),d.get('overview',''),d.get('aplus',''),' '.join(f'{k} {v}' for k,v in s.items())])
    b,bs=basin([('标题',d.get('title','')),('五点',d.get('bullets','')),('描述',d.get('desc','')+' '+d.get('overview','')),('图文详情',d.get('aplus',''))],s);c,cs=cab(' '.join([d.get('title',''),d.get('bullets',''),d.get('desc',''),d.get('aplus','')]),s)
    out[d['asin']]=dict(basin=b,basin_src=bs,cab=c,cab_src=cs,width=width(s),title=d.get('title','')[:120])
json.dump(out,open(os.path.join(q3paths.DATA,'amz_pdp_tags.json'),'w'),ensure_ascii=False)
import collections;print(len(out),collections.Counter(v['basin'] for v in out.values()),collections.Counter(v['cab'] for v in out.values()))
