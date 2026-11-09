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
C=[('实木框架',r'solid[\s\-]wood\s+frame|hardwood\s+frame|solid\s+wood\s+(?:and|&|\+)\s+(?:MDF|plywood|engineered)'),('实木',r'(?:100%|all|entirely|made (?:of|from)|constructed (?:of|from)|crafted (?:of|from)|built (?:of|from|with))\s+(?:premium\s+|high[- ]quality\s+|natural\s+)?solid\s+(?:wood|oak|pine|rubberwood|birch|ash|walnut)|solid (?:wood|oak|pine|rubberwood|birch) (?:cabinet|vanity|construction|body|board)|rubberwood'),('含胶合板',r'plywood'),('含刨花板',r'particle\s?board|\bP2\b|chipboard'),('MDF',r'\bMDF\b|medium[\s\-]density')]
def cab(t2,spec):
    t=t2
    hits=[nm for nm,p in C if re.search(p,t,re.I)]
    if hits: return hits[0],'正文：'+'、'.join(hits)
    v=' '.join(spec.get(k,'') for k in ('Frame Material Type','Material Type','Material'))
    if re.search(r'engineered wood',v,re.I): return '人造板（未细分）','规格表 Engineered Wood'
    return '未写',''

# ---- 补未标属性（只用来填原来没标的）----
NOTOP=re.compile(r'without (?:a )?(?:counter)?top|no (?:counter)?top|top (?:is )?not included|countertop not included|vanity base only|cabinet only|base only',re.I)
TOPS=[('石英石',r'\bquartz\b'),('岗石',r'\bgranite\b'),('岩板',r'sintered stone|rock (?:slab|plate)|\bslate\b'),('卡拉拉大理石',r'carrara'),('木板',r'(?:solid |natural )?wood(?:en)? (?:counter)?top|butcher ?block')]
def top(parts,basin_label):
    t=' '.join(x for _,x in parts[:3])
    if NOTOP.search(t): return '不适用（不含台面）'
    if basin_label in ('陶瓷','树脂'): return basin_label
    if basin_label=='CM': return 'Cultured Marble'
    for nm,p in TOPS:
        if re.search(p,t,re.I): return nm
    return None
COL=[('白',r'\bwhite|ivory|cream|off[- ]white'),('黑',r'\bblack|charcoal'),('灰',r'\bgr[ae]y|greige|slate gray'),('蓝',r'\bblue|navy'),('绿',r'\bgreen|sage|olive'),
     ('深木',r'walnut|espresso|dark (?:oak|wood|brown)|\bbrown|mahogany|cherry|chocolate|coffee'),('原木',r'\boak|natural|light (?:wood|brown)|maple|pine|teak|beige|honey|wood(?:en)? color')]
def color(spec,title):
    v=spec.get('Color','') or spec.get('Colour','') or spec.get('Finish Types','')
    for src in (v,title):
        for nm,p in COL:
            if re.search(p,src,re.I): return nm
    return None
EL=[('rattan',r'rattan|\bcane\b|wicker'),('玻璃门',r'glass door'),('竖棱',r'flut(?:ed|e)|reeded|ribbed|grooved'),('农场风装饰饰条',r'barn ?door|farmhouse|x[- ]?(?:shape|design|panel)'),
    ('夏克式',r'shaker'),('木条格栅',r'\bslat(?:s|ted)?\b|louver'),('自然木纹',r'wood ?grain'),('纯色',r'handle[- ]?(?:free|less)|flat[- ]panel|minimalist')]
def elem(parts):
    for _,t in parts[:2]:
        for nm,p in EL:
            if re.search(p,t,re.I): return nm
    return None
def width(spec):
    for k in ('Item Dimensions D x W x H','Product Dimensions','Item Dimensions  L x W x H','Size'):
        v=spec.get(k,'')
        m=re.search(r'([\d.]+)"?\s*W',v) or re.search(r'x\s*([\d.]+)\s*x',v)
        if m: return float(m.group(1))
    return None
# 开放层板（不带门的开放层板 / 储物格），规则同 solution-v2/数据准备/卖家精灵导出_打标.py 第 5 点
import html as _html
OPEN_RE=re.compile(r'\bopen(?:[ -]+(?:storage|display|side|bottom|lower|middle|upper|top|left|right|tier))*[ -]+(?:shel(?:f|ves|ving)|storage|cubb(?:y|ies)|cubes?|compartments?|spaces)\b'
    r'|\bopening\s+(?:bottom\s+|lower\s+|side\s+)?shel(?:f|ves)\b|\bside\s+(?:open\s+)?(?:storage\s+)?shel(?:f|ves)\b'
    r'|\b(?:2|3|two|three)[ -]tier(?:ed)?\s+(?:open\s+)?(?:side\s+)?(?:storage\s+)?shel(?:f|ves)\b|\bconsole\s+(?:vanity|sink|table)\b',re.I)
_NEG=re.compile(r'\b(?:no|not|without)\s+(?:an?\s+|any\s+)?$',re.I)
_MIR=re.compile(r'\b(?:mirror|medicine)\s+cabinet\b[^.|]{0,40}$',re.I)
_PIPE=re.compile(r'^[^.|]{0,20}\b(?:accommodat\w*|fits?|for|around|hid(?:es?|ing))\s+(?:the\s+)?(?:pipes?|plumbing)\b',re.I)
_DRB=re.compile(r'\bdoors?\s+(?:features?|has|have|with|includes?)\s+(?:an?\s+)?$',re.I); _DRA=re.compile(r'^\s*(?:on|inside|behind|in)\b',re.I)
def open_cue(text):
    t=_html.unescape(str(text or ''))
    for mm in OPEN_RE.finditer(t):
        b,a=t[max(0,mm.start()-60):mm.start()],t[mm.end():mm.end()+40]
        if _NEG.search(b[-20:]) or _MIR.search(b) or _PIPE.search(a): continue
        if re.match(r'(?:2|3|two|three)[ -]tier',mm.group(0),re.I) and 'open' not in mm.group(0).lower() and (_DRB.search(b) or _DRA.search(a)): continue
        return True
    return False
# 拆装 / 整装：页面明确写了到货已组装 → 整装；写了要组装或只部分预装 → 拆装；都没写 → None（wen 2026-11-09，用于全部 Amazon 商品）
ASM_RE=re.compile(r'fully[\s-]+assembled|pre[\s-]?assembled|(?:comes?|arrives?|ships?|delivered)\s+(?:fully\s+|already\s+)?assembled|no\s+assembly\s+(?:is\s+)?(?:required|needed)|already\s+assembled|factory[\s-]assembled|cabinet\s+(?:is\s+)?(?:fully\s+)?assembled',re.I)
KD_RE=re.compile(r'ready[\s-]to[\s-]assemble|\bRTA\b|flat[\s-]?pack|easy\s+(?:to\s+)?assembl|simple\s+assembl|assembly\s+(?:is\s+)?required|requires?\s+assembly|labell?ed\s+parts|assembl(?:e|y)\s+(?:the\s+)?(?:vanity\s+)?cabinet',re.I)
PARTIAL=re.compile(r'(?:partially|partly|mostly|semi|largely|\d+\s*%|(?:some|most)\s+(?:of\s+(?:its|the)\s+)?(?:components?|parts?)(?:\s+(?:are|is))?)[\s-]+(?:pre[\s-]?)?assembled|some\s+assembly\s+(?:is\s+)?required|\b(?:no|not|without)\s+(?:\w+\s+){0,2}?(?:pre[\s-]?|fully\s+)?assembled|fully\s+assembl\w*\s+required|(?:needs?|has|have|must)\s+(?:to\s+)?be\s+(?:fully\s+)?assembled|requires?\s+(?:you\s+to\s+)?(?:fully\s+)?assemble',re.I)   # 部分预装、否定、要求自己组装都算拆装（wen 2026-11-09）
NOTDELIV=re.compile(r'(?:once|when|after|if|until|till)\s+(?:\w+\s+){0,3}?(?:fully\s+)?assembled|assembled\s+(?:size|dimensions?|height|width|weight)',re.I)   # “装好之后……”不算到货已组装
def asm_of(t):
    t2=NOTDELIV.sub(' ',PARTIAL.sub(' ',t))
    if ASM_RE.search(t2): return '整装'
    return '拆装' if (PARTIAL.search(t) or KD_RE.search(t)) else None
OLD=json.load(open(os.path.join(q3paths.DATA,'amz_pdp_tags.json'),encoding='utf-8')) if os.path.exists(os.path.join(q3paths.DATA,'amz_pdp_tags.json')) else {}
out={}
for f in glob.glob(PAGES+'/*.json'):
    d=json.load(open(f));s=d.get('spec',{})
    t=' '.join([d.get('title',''),d.get('bullets',''),d.get('desc',''),d.get('overview',''),d.get('aplus',''),' '.join(f'{k} {v}' for k,v in s.items())])
    b,bs=basin([('标题',d.get('title','')),('五点',d.get('bullets','')),('描述',d.get('desc','')+' '+d.get('overview','')),('图文详情',d.get('aplus',''))],s);c,cs=cab(' '.join([d.get('title',''),d.get('bullets',''),d.get('desc','')]),s)
    parts=[('标题',d.get('title','')),('五点',d.get('bullets','')),('描述',d.get('desc','')+' '+d.get('overview','')),('图文详情',d.get('aplus',''))]
    out[d['asin']]=dict(basin=b,basin_src=bs,cab=c,cab_src=cs,width=width(s),title=d.get('title','')[:120],
        top=top(parts,b),color=color(s,d.get('title','')),elem=elem(parts))
    out[d['asin']]['asm']=asm_of(' '.join([d.get('title',''),d.get('bullets',''),d.get('desc',''),' '.join(f'{k} {v}' for k,v in s.items())]))
    o=OLD.get(d['asin'],{})   # 柜体结构：已有的（统一打标表 / 看图）优先，没有才看页面文字
    out[d['asin']]['struct']=o.get('struct') or ('开放式' if open_cue(' '.join([d.get('title',''),d.get('bullets',''),' '.join(f'{k} {v}' for k,v in s.items())])) else None)
    if o.get('struct_src'): out[d['asin']]['struct_src']=o['struct_src']
for a,o in OLD.items():   # 没抓页面、只带柜体结构的 ASIN 保留
    if a not in out and o.get('struct'): out[a]={'struct':o['struct'],'struct_src':o.get('struct_src')}
json.dump(out,open(os.path.join(q3paths.DATA,'amz_pdp_tags.json'),'w'),ensure_ascii=False)
import collections;print(len(out),'开放式',sum(v.get('struct')=='开放式' for v in out.values()),'台盆',dict(collections.Counter(v.get('basin') for v in out.values())),'柜体',dict(collections.Counter(v.get('cab') for v in out.values())),'台面',dict(collections.Counter(v.get('top') for v in out.values())),'主色',dict(collections.Counter(v.get('color') for v in out.values())),'元素',dict(collections.Counter(v.get('elem') for v in out.values())))
