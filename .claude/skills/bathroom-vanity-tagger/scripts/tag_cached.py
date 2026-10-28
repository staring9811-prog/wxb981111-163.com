"""Evidence-preserving, network-free bathroom vanity attribute tagging.

Consumes the current normalized payload and exact-ASIN detail cache. Produces
only JSON; workbook editing is separate (write_workbook.py). Parent
descriptions remain candidates.

v3 (2026-10-27): SellerSprite export 详细参数/亮点 as child evidence, parent
overview materials as candidates, 3H faucet-hole fix, list-style mirror/faucet
inclusion, more explicit single/double sink wording, D/W label-swap guard,
D×W×H order and swap-correction candidates (filled only with
--no-dim-rules to disable); v4: standard widths, parent fill, per-field feasibility classes and work queues.
"""
import argparse,html,json,re,hashlib
from pathlib import Path
from collections import Counter

VERSION='bathroom-vanity-tagger-20261028-v12'
# Solid-wood claims are checked against assembly and same-width MDF price (user 2026-10-27).
SOLID_WOOD_PRICE_RATIO=1.5
SOLID_WOOD_PRICE_FLOOR=500.0  # USD; used when no same-width MDF reference exists
# 2026-10-27 user: vanity widths are essentially standard sizes.
STANDARD_WIDTHS=(12,16,18,20,22,24,26,28,30,31,32,34,36,40,42,48,54,55,60,61,66,72,84)
STD_WIDTH_TOLERANCE=0.8
PARENT_SUFFIX='（父体候选）'
# User 2026-10-28: every pedestal form is 柱状盆, including pedestal sink storage cabinets.
# "Standing Pedestal Cabinet with ... vessel sink" names a freestanding vanity and does not match.
PEDESTAL_FORM=r'\bpedestal\s+(?:sink|basin|under[ -]?sink)\b|\bfor\s+(?:a\s+)?pedestal\s+sinks?\b'

def standard_width(v):
    # Nearest standard width within tolerance; ties (e.g. 31.5 between 31/32) stay raw.
    d=sorted((abs(v-w),w) for w in STANDARD_WIDTHS)
    if d[0][0]<=STD_WIDTH_TOLERANCE and (len(d)<2 or d[1][0]-d[0][0]>1e-9):return d[0][1]
    return None
HEADERS=['D1产品形态','D2安装方式','D3盆数','D4台面形态','D5元素','D6柜体颜色','D7柜体材质','D8台面材质','D8台盆材质','D9宽(in)','D9深(in)','D9高(in)','D10镜子','D11龙头','打标状态','打标说明']
UNKNOWN='信息不足'
def clean(s):return re.sub(r'\s+',' ',html.unescape(str(s or ''))).strip()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def match(pattern,text):return re.search(pattern,text,re.I)
def uniq(xs):return list(dict.fromkeys(xs))

# Parent overview keys that describe one representative variant, not the family.
PARENT_OVERVIEW_SKIP={'brand','color','size','product dimensions','dimensions','item weight','weight','dimensions & weight','recommended uses for product'}

def overviews(d):
    ov=(d or {}).get('overviews')
    if isinstance(ov,str):
        try:ov=json.loads(ov)
        except (ValueError,TypeError):ov={}
    return ov if isinstance(ov,dict) else {}

def role_hint_sink(clause,pos):
    # "wood sink" / "stone basin" right after the word: not a top.
    return bool(match(r'^\s+(?:\w+\s+){0,2}?(?:sinks?|basins?|bowls?)\b',clause[pos:]))

CABINET_ORDER=['MDF','胶合板','刨花板','竹材','玻璃']
def format_cabinet(value):
    """User 2026-10-27: several materials incl. solid wood -> 实木框架+<boards>;
    other combinations joined with '+' in a fixed order."""
    if not value or value==UNKNOWN:return value
    suffix=PARENT_SUFFIX if value.endswith(PARENT_SUFFIX) else ''
    labels=[x for x in value[:len(value)-len(suffix)].split('；') if x]
    frame=any(x in ('实木','实木框架','实木框架（其余未说明）') for x in labels)
    boards=[x for x in CABINET_ORDER if x in labels]+[x for x in labels if x not in CABINET_ORDER and x not in ('实木','实木框架','实木框架（其余未说明）')]
    if frame and boards:return '实木框架+'+'+'.join(boards)+suffix
    if frame:return ('实木框架' if '实木' not in labels else '实木')+suffix
    return '+'.join(boards)+suffix
    
def export_attributes(text):
    """SellerSprite 详细参数 is 'Key:Value | Key:Value'; values may contain ':'."""
    out=[]
    for part in str(text or '').split(' | '):
        k,sep,v=part.partition(':')
        if sep and clean(k) and clean(v):out.append((clean(k),clean(v)))
    return out

class Tagger:
    def __init__(self,row,details,feature_provenance=None,export_rows=None,enable_dim_rules=True,parent_fill=True,std_width=True,accessory_default=True):
        self.row=row;self.asin=row['子ASIN'];self.sources=[];self.notes=[];self.conflicts=[];self.tags={};self.evidence={}
        self.rejected_dims=[];self.enable_dim_rules=enable_dim_rules;self.parent_fill=parent_fill;self.std_width=std_width;self.accessory_default=accessory_default
        def add(field,text,scope='child',a=None,**meta):
            if clean(text):self.sources.append({'field':field,'text':clean(text),'scope':scope,'asin':a or self.asin,**meta})
        add('SKU属性',row.get('SKU属性'));add('商品标题',row.get('商品标题'))
        d=(details.get(self.asin) or {}).get('data') or {}
        if d.get('asin')!=self.asin:d={}
        self.has_child_detail=bool(d)
        for k,v in overviews(d).items():add('子体详情.overviews.'+k,clean(v))
        # Same-ASIN SellerSprite export rows are child evidence from the export month's snapshot.
        seen=set()
        for x in export_rows or []:
            for k,v in export_attributes(x.get('attributes')):
                if (k,v) in seen:continue
                seen.add((k,v));add('卖家精灵导出.详细参数.'+k,v,exportMonth=x.get('month'),exportFile=x.get('sourceFile'),exportRow=x.get('sourceRow'))
            if clean(x.get('features')) and ('亮点',clean(x['features'])) not in seen:
                seen.add(('亮点',clean(x['features'])));add('卖家精灵导出.亮点',x['features'],exportMonth=x.get('month'),exportFile=x.get('sourceFile'),exportRow=x.get('sourceRow'))
        self.has_export=bool(seen)
        if row.get('五点来源')=='子体详情':add('五点描述',row.get('五点描述'))
        elif row.get('五点来源')=='父体详情填充':add('五点描述',row.get('五点描述'),'parent',row.get('五点来源ASIN'))
        parent=row.get('核验父ASIN')
        pd=(details.get(parent) or {}).get('data') or {} if parent and parent!=self.asin else {}
        self.parent_detail=pd if pd.get('asin')==parent else {}
        if pd.get('asin')==parent:
            for k,v in overviews(pd).items():
                if k.lower() not in PARENT_OVERVIEW_SKIP:add('父体详情.overviews.'+k,clean(v),'parent',parent)
        add('商品尺寸',row.get('商品尺寸'))
        self.provenance=feature_provenance or {}
    def ev(self,source,label,quote,method='明确文本',extra=None):
        e={'label':label,'sourceField':source['field'],'sourceASIN':source['asin'],'sourceScope':source['scope'],'quote':clean(quote),'method':method}
        if source['field']=='五点描述':
            e['sourceRecordID']=self.provenance.get('sourceRecordID');e['requestTime']=self.provenance.get('requestTime')
        for k in ('exportMonth','exportFile','exportRow'):
            if source.get(k):e[k]=source[k]
        if extra:e.update(extra)
        return e
    def set(self,key,candidates,multi=False,default=UNKNOWN):
        candidates=[e for e in candidates if e['label']]
        direct=[e for e in candidates if e['sourceScope']=='child']
        selected=direct or candidates
        labels=uniq(e['label'] for e in selected)
        if not labels:self.tags[key]=default;self.evidence[key]={'status':'missing','candidates':[]};return
        if not multi and len(labels)>1:
            self.conflicts.append(key+'文本证据不一致：'+' / '.join(labels))
        value='；'.join(labels) if multi else labels[0]
        parent=not bool(direct)
        # User 2026-10-27: child lacks it -> use the parent's value (marked in JSON/notes).
        if parent and not self.parent_fill:value+=PARENT_SUFFIX
        self.tags[key]=value
        self.evidence[key]={'status':('parent_fill' if self.parent_fill else 'parent_candidate') if parent else 'conflict' if len(labels)>1 and not multi else 'text_supported','selected':selected,'otherParentCandidates':[e for e in candidates if e['sourceScope']=='parent'] if direct else []}
    def pattern_candidates(self,patterns,fields=None):
        out=[]
        for s in self.sources:
            if fields and not fields(s['field']):continue
            for label,pat in patterns:
                for m in re.finditer(pat,s['text'],re.I):
                    prefix=s['text'][max(0,m.start()-30):m.start()].lower()
                    if re.search(r'\b(?:not|no|without)\s+(?:a\s+)?$',prefix):continue
                    out.append(self.ev(s,label,s['text'][max(0,m.start()-35):min(len(s['text']),m.end()+55)]));break
        return out
    def structure(self):
        c=self.pattern_candidates([
            ('悬浮式',r'\b(?:floating|wall[ -]mount(?:ed)?|wall[ -]hung)\b'),
            ('落地式',r'\b(?:freestanding|free[ -]standing|floor[ -]mount(?:ed)?)\b'),
            ('开放式',r'\bconsole\s+(?:vanity|sink|table)\b'),
            ('转角式',r'\bcorner\s+(?:bathroom\s+)?(?:vanity|cabinet|sink)\b'),
            ('柱状盆',PEDESTAL_FORM)],lambda f:f!='商品尺寸')
        # Title/SKU naming a pedestal sink outranks floating/freestanding words (FORM-PEDESTAL-PRIORITY).
        ped=[e for e in c if e['label']=='柱状盆' and e['sourceField'] in ('商品标题','SKU属性')]
        self.set(HEADERS[0],ped or c)
        if ped:self.evidence[HEADERS[0]].update({'ruleID':'FORM-PEDESTAL-PRIORITY','note':'标题/SKU写明立柱盆，形态统一为柱状盆（用户2026-10-28）'})
        c=[]
        for s in self.sources:
            text=s['text']
            # Negative and partial-assembly wording must be read before bare assembly.
            if match(r'\b(?:partially|partly)\s+(?:pre[ -]?)?assembled\b|some components pre[ -]?assembled',text):
                c.append(self.ev(s,'部分预装',text[:350]));continue
            no=match(r'\bno assembly(?: required)?\b|assembly required\s*[:=]?\s*(?:no|false)\b|\b(?:fully|pre[ -]?)\s*assembled\b|\b(?:comes|arrives) assembled\b',text)
            yes=match(r'(?<!no )\b(?:self[ -])?assembly required\b|\bready[ -]to[ -]assemble\b|\bRTA\b|\b(?:easy|quick) assembly\b',text)
            if no:c.append(self.ev(s,'整装',text[max(0,no.start()-25):no.end()+60]))
            elif yes:c.append(self.ev(s,'拆装',text[max(0,yes.start()-25):yes.end()+60]))
        self.set(HEADERS[1],c)
        c=[];vanity_terms=[]
        for s in self.sources:
            t=s['text']
            no=match(r'\b(?:without|no) (?:a )?(?:sink|basin)\b|\b(?:sink|basin) (?:is )?(?:not included|sold separately)\b|\b(?:cabinet|vanity base) only\b',t)
            # Explicit count words only; adjectives such as "vessel"/"boat" may sit between.
            adj=r'(?:(?:oval|round|rectangular|rectangle|square|white|black|gr[ae]y|ceramic|porcelain|resin|smc|stone|marble|glass|undermount|undercounter|vessel|boat|integrated|drop[ -]in)\s+){0,3}'
            double=match(r'\b(?:double|dual|two|2)[ -]+'+adj+r'(?:sink|basin|bowl)s?\b|\bsize\s*:[^|]*\bdual\b',t)
            single=match(r'\b(?:single|one|1)[ -]+'+adj+r'(?:sink|basin|bowl)\b|\bsize\s*:[^|]*\bsingle\b',t)
            # Trade terms "single/double vanity" name the sink count but are weaker than sink wording.
            for label,pat in (('双盆',r'\bdouble\s+(?:bathroom\s+)?vanity\b'),('单盆',r'\bsingle\s+(?:bathroom\s+)?vanity\b')):
                vm=match(pat,t)
                if vm:vanity_terms.append(self.ev(s,label,t[max(0,vm.start()-20):vm.end()+55],'行业用语single/double vanity'))
            choices=[]
            if no:choices=[('无盆',no)]
            elif double and single:
                self.notes.append('文本同时列出单盆/双盆，未将多选描述强行归一');continue
            elif double:choices=[('双盆',double)]
            elif single:choices=[('单盆',single)]
            for label,m in choices:c.append(self.ev(s,label,t[max(0,m.start()-20):m.end()+55]))
        # Child SKU basin count is more specific than broad title variants.
        sku=[e for e in c if e['sourceField']=='SKU属性']
        if sku:
            for e in c:
                if e['sourceScope']=='child' and e['label']!=sku[0]['label']:self.conflicts.append('D3盆数：SKU与其他文本不一致')
            self.set(HEADERS[2],sku)
        else:self.set(HEADERS[2],c or [e for e in vanity_terms if len({x['label'] for x in vanity_terms})==1])
        if self.tags[HEADERS[2]]=='无盆':
            self.tags[HEADERS[3]]='不适用（无盆）';self.evidence[HEADERS[3]]={'status':'derived','basis':HEADERS[2]}
        else:self.set(HEADERS[3],self.pattern_candidates([
            ('台上盆',r'\bvessel\s+(?:sink|basin)|\babove[ -]counter\s+(?:sink|basin)\b'),
            ('台下盆',r'\bunder[ -]?(?:mount|counter)(?:ed)?\b'),
            ('台上盆',r'\bintegrat(?:ed|ion)\s+(?:sink|basin|countertop)|one[ -]piece\s+(?:sink|basin|countertop)'),
            ('嵌入盆',r'\bdrop[ -]in\s+(?:sink|basin)|\btop[ -]mount(?:ed)?\s+(?:sink|basin)')]))
        self.integrated_sink=any(match(r'\bintegrat(?:ed|ion)\s+(?:sink|basin|countertop)|one[ -]piece\s+(?:sink|basin|countertop)',x['text']) for x in self.sources)
        self.set(HEADERS[4],self.pattern_candidates([
            ('Fluted',r'\bfluted\b'),('Reeded',r'\breeded\b'),('Shaker',r'\bshaker\b|\brecessed panel\b'),
            ('Barn Door',r'\bbarn[ -]door\b'),('Farmhouse',r'\bfarmhouse\b|\bx[ -]design\b'),
            ('Slatted',r'\bslatted\b|\blouvered\b'),('Glass Door',r'\b(?:glass|glazed)\s+(?:cabinet\s+)?doors?\b'),
            ('Rattan',r'\b(?:rattan|wicker|cane)\b')],lambda f:f in ('商品标题','SKU属性','五点描述','卖家精灵导出.亮点') or 'style' in f.lower()),multi=True,default='待图片核验')

    def colors(self):
        patterns=[('灰绿色',r'gray[ -]green|grey[ -]green'),('灰蓝色',r'blue[ -]gr[ae]y|gr[ae]y[ -]blue'),('藏青色',r'navy(?: blue)?'),('胡桃木色',r'(?:dark )?walnut'),('深咖啡色',r'espresso|dark brown|coffee'),('白色',r'(?:milky |off[ -]|matte |pure )?white|cream|ivory'),('黑色',r'(?:matte |jet )?black|tuxedo'),('灰色',r'gr[ae]y|driftwood'),('原木色',r'natural(?: oak| wood)?|(?:light )?oak|wood color'),('米色',r'beige'),('棕色',r'brown'),('蓝色',r'blue'),('绿色',r'green|sage|mint|eucalyptus'),('粉色',r'pink|blush|rose pink'),('黄色',r'yellow|mustard'),('红色',r'red|burgundy|coral|rust red')]
        def found(t):
            hits=[]
            occupied=[]
            for label,pat in patterns:
                for m in re.finditer(r'(?<![a-z])(?:'+pat+r')(?![a-z])',t,re.I):
                    if any(m.start()<b and a<m.end() for a,b in occupied):continue
                    occupied.append(m.span());hits.append((m.start(),m.end(),label))
            return sorted(hits)
        candidates=[];sku_values=[]
        for s in self.sources:
            if s['field']!='SKU属性':continue
            m=match(r'colou?r\s*:\s*([^|]+)',s['text'])
            if m:
                hits=found(m.group(1));sku_values=uniq(h[2] for h in hits)
                if len(sku_values)==1:candidates.append(self.ev(s,sku_values[0],m.group(0),'SKU明确颜色'))
                elif len(sku_values)>1:self.notes.append('SKU含组合色；先区分柜体/盆/五金，不按词序取色')
        explicit=[]
        for s in self.sources:
            if s['field']=='SKU属性':continue
            t=s['text'];hits=found(t)
            for a,b,label in hits:
                tail=t[b:b+65];before=t[max(0,a-45):a]
                # Adjacent cabinet noun; avoid interpreting sink/faucet colors as cabinet.
                if match(r'^\s+(?:(?:bathroom|wood|wooden|painted|storage|vanity)\s+){0,3}(?:cabinet|vanity base|vanity)(?!\s+(?:sink|top))\b',tail) or match(r'\b(?:cabinet|cabinet finish|cabinet colou?r|cabinet body)\s*(?:is|in|:|of|with)?\s*$',before):
                    explicit.append(self.ev(s,label,t[max(0,a-35):b+70],'明确柜体颜色上下文'))
            if s['field']=='商品标题':
                tail=match(r'(?:,|\(|\bin)\s*([^,()]{1,35})\)?\s*$',t)
                if tail:
                    hh=found(tail.group(1))
                    if len(uniq(h[2] for h in hh))==1:explicit.append(self.ev(s,hh[0][2],tail.group(0),'标题末尾颜色，需与SKU核对'))
            if s['field'].lower().endswith('.color') or s['field'].lower().endswith('.colour'):
                hh=found(t)
                if len(uniq(h[2] for h in hh))==1:explicit.append(self.ev(s,hh[0][2],t,'ASIN匹配详情颜色'))
        if candidates:
            for e in explicit:
                if e['sourceScope']=='child' and e['label']!=candidates[0]['label']:self.conflicts.append('D6柜体颜色：SKU与标题/参数柜体颜色不一致')
            self.set(HEADERS[5],candidates)
        else:
            if len(sku_values)>1:explicit=[e for e in explicit if e['label'] in sku_values or e['sourceScope']=='parent']
            self.set(HEADERS[5],explicit)
            if len(sku_values)>1 and self.tags[HEADERS[5]]==UNKNOWN:self.notes.append('D6组合色未取得明确柜体归属')

    def materials(self):
        pats=[('MDF',r'\bmdf\b|medium[ -]density\s+fib(?:er|re)board|\bengineered\s+wood\b|\bcomposite\s+wood\b'),('胶合板',r'\bplywood\b'),('刨花板',r'\bparticle\s*board\b|\bchipboard\b'),('实木',r'\bsolid\s+(?:wood|oak|pine|rubberwood|birch|poplar)\b'),('人造大理石',r'\b(?:cultured|engineered|synthetic)\s+marble\b'),('人造石（未细分）',r'\bengineered\s+stone\b'),('石英石',r'\b(?:engineered\s+)?quartz(?:\s+stone)?\b'),('岩板',r'\bsintered\s+stone\b'),('大理石（天然性未核实）',r'\bmarble\b'),('陶瓷',r'\bceramic\b|\bporcelain\b'),('树脂',r'\bresin\b'),('亚克力',r'\bacrylic\b'),('SMC',r'\bsmc\b|sheet\s+moulding\s+compound|sheet\s+molding\s+compound'),('花岗岩',r'\bgranite\b'),('玻璃',r'\b(?:tempered\s+)?glass\b'),('不锈钢',r'\bstainless\s+steel\b'),('竹材',r'\bbamboo\b')]
        wood={'MDF','胶合板','刨花板','实木','工程木材（未细分）','竹材'}
        roles={'cabinet':r'\bcabinet(?:ry)?\b|\bvanity\s+(?:base|body|frame)\b|\bwood\s+frame\b|\bdoors?\b','top':r'\bcounter\s*top\b|\bvanity\s+top\b|\btable\s*top\b','sink':r'\bsinks?\b|\bbasins?\b|\bbowls?\b','hardware':r'\bhinges?\b|\bhandles?\b|\bfaucets?\b|\bdrains?\b|\bknobs?\b'}
        buckets={k:[] for k in ('cabinet','top','sink')}
        for s in self.sources:
            if s['field'] in ('SKU属性','商品尺寸'):continue
            for clause in re.split(r'(?<=[.;!?])\s+|\s*\|\|\s*|\n|,\s*',s['text']):
                hits=[];used=[]
                for label,pat in pats:
                    for m in re.finditer(pat,clause,re.I):
                        if any(m.start()<b and a<m.end() for a,b in used):continue
                        used.append(m.span())
                        nearby=clause[max(0,m.start()-35):m.end()+30]
                        if label=='大理石（天然性未核实）' and match(r'faux|marble[ -]?(?:look|pattern|texture|grain)|imitation|marble-like',nearby):continue
                        prefix=clause[max(0,m.start()-25):m.start()]
                        if match(r'not\s+(?:made\s+of\s+)?$|without\s+$|no\s+$',prefix):continue
                        # "solid wood legs / feet / handles" describe a part, not the cabinet.
                        if label=='实木' and match(r'^\s*(?:legs?|feet|foot|handles?|knobs?|trim|edges?|accents?|pulls?)\b',clause[m.end():]):
                            self.notes.append('D7：solid wood仅指腿/脚/把手，不作柜体材质');continue
                        hits.append((m.start(),m.end(),label))
                anchors=[(m.start(),m.end(),role) for role,pat in roles.items() for m in re.finditer(pat,clause,re.I)]
                for a,b,label in hits:
                    distances=[]
                    for x,y,role in anchors:
                        gap=max(0,x-b,a-y)
                        # Long clauses often contain an unrelated cabinet and sink.
                        if gap<=48:distances.append((gap+(2 if y<a else 0),role))
                    role=min(distances)[1] if distances else None
                    if label in wood:
                        # Board/wood descriptions belong to the cabinet unless
                        # the text explicitly attaches that material to a top.
                        local_top=match(re.escape(clause[a:b])+r'\s+(?:vanity\s+)?(?:countertop|top)\b',clause)
                        if local_top:role='top'
                        elif role in ('top','sink','hardware'):role=None
                    if not role and label in wood:
                        if 'material' in s['field'].lower() or match(r'vanity|cabinet',s['text']):role='cabinet'
                    if role=='hardware':continue
                    if role=='cabinet' and label not in wood:
                        # A generic ceramic/resin/metal mention near a cabinet noun
                        # is insufficient to assert the cabinet's construction.
                        if not match(r'(?:cabinet|body|frame).{0,18}(?:made|constructed|crafted).{0,10}'+re.escape(clause[a:b]),clause) and not match(re.escape(clause[a:b])+r'\s+cabinet\b',clause):continue
                    if role in buckets:
                        lab=label
                        if label=='实木' and match(r'\bsolid\s+wood\s+frame\b',clause):lab='实木框架（其余未说明）'
                        if label=='大理石（天然性未核实）' and match(r'\bnatural\s+marble\b',clause):lab='天然大理石'
                        buckets[role].append(self.ev(s,lab,clause[max(0,a-65):min(len(clause),b+90)],'部件绑定文本'))
        def reduced(es):
            direct=[e for e in es if e['sourceScope']=='child'];selected=direct or es
            labels={e['label'] for e in selected}
            if labels & {'MDF','胶合板','刨花板'}:selected=[e for e in selected if e['label']!='工程木材（未细分）']
            return selected
        cab=reduced(buckets['cabinet']);self.set(HEADERS[6],cab,multi=True)
        self.tags[HEADERS[6]]=format_cabinet(self.tags[HEADERS[6]])
        # Distinct sources claiming several homogeneous cabinet materials may be
        # a component combination or a variation conflict; expose ambiguity.
        labs=uniq(e['label'] for e in cab)
        if len(labs)>1:self.notes.append('D7有多种部件/材料线索，请按字段证据区分组合与冲突')
        self.surface_materials()

    def surface_materials(self):
        # Bind a material to its own component phrase before business grouping.
        # D7 remains the v1 cabinet classifier; this method replaces only D8.
        pats=[
            ('Cultured Marble',r'\b(?:cultured|clutred|cultred)\s+marble\b'),
            ('石英石',r'\b(?:engineered\s+)?quartz(?:\s+stone)?\b'),
            ('岩板',r'\bsintered\s+stone\b'),
            ('陶瓷',r'\bceramic\b|\bporcelain\b|\bvitreous\s+china\b'),
            ('SMC',r'\bsmc\b|sheet\s+mou?lding\s+compound'),
            ('亚克力',r'\bacrylic\b'),('树脂',r'\bresin\b'),
            ('engineered marble',r'\b(?:engineered|synthetic|artificial|cast)\s+marble\b'),
            ('engineered stone',r'\bengineered\s+stone\b'),
            ('marble',r'\bmarble\b'),
            ('Carrara / Calacatta',r'\b(?:carrara|calacatta)\b'),
            ('花岗岩',r'\bgranite\b'),('玻璃',r'\b(?:tempered\s+)?glass\b'),
            ('不锈钢',r'\bstainless\s+steel\b'),
            # User 2026-10-27: nobody writes "solid wood" for a top; wood is a top
            # only when written as "wood top / wooden countertop / oak tabletop".
            ('木板',r'\b(?:wood(?:en)?|oak|walnut|bamboo|teak|mdf|plywood)(?:[ -]+(?:grain|veneer|finish))?(?=\s+(?:counter\s*tops?|table\s*tops?|tops?)\b)'),
            ('stone',r'\b(?<!sintered )(?<!engineered )(?<!cultured )stone\b(?=\s+(?:counter\s*tops?|vanity\s+tops?|tops?)\b)')]
        rolepat=r'\b(?P<top>counter\s*tops?|vanity\s+tops?|table\s*tops?|tops?)\b|\b(?P<sink>sinks?|basins?|bowls?)\b|\b(?P<other>cabinets?|doors?|frames?|faucets?|handles?|drains?|hinges?)\b'
        buckets={'top':[],'sink':[]}
        all_evidence=[]
        for source in self.sources:
            if source['field'] in ('SKU属性','商品尺寸'):continue
            # Bracketed bullet heading is a mixed-material list, not a component assertion.
            text=re.sub(r'[【\[][^】\]]*(?:&| and )[^】\]]*[】\]]',' ',source['text'],flags=re.I)
            for clause in re.split(r'(?<=[;!?])\s+|(?<=\.)\s+(?=[A-Z])|\s*\|\|\s*|,\s*',text):
                hits=[];occupied=[]
                for raw,pat in pats:
                    for m in re.finditer(pat,clause,re.I):
                        if any(m.start()<b and a<m.end() for a,b in occupied):continue
                        occupied.append(m.span());hits.append((m.start(),m.end(),raw,m.group()))
                hits.sort()
                anchors=[]
                for m in re.finditer(rolepat,clause,re.I):
                    if m.group('sink') and match(r'^\s*(?:shape|style)\b',clause[m.end():]):continue
                    role='top' if m.group('top') else 'sink' if m.group('sink') else 'other'
                    if role=='sink' and match(r'^\s+(?:cabinet|vanity)\b',clause[m.end():]):role='other'
                    anchors.append((m.start(),m.end(),role))
                for a,b,raw,original in hits:
                    prefix=clause[max(0,a-28):a]
                    if match(r'\b(?:not(?: made of)?|without|no|unlike|instead of)\s*$',prefix):continue
                    if raw=='marble' and match(r'^\s*[- ]?(?:look|pattern|texture|grain|like)\b',clause[b:]):continue
                    if raw in ('木板','stone') and role_hint_sink(clause,b):continue
                    # Carrara/Calacatta next to an explicit non-marble material is a design name.
                    if raw=='Carrara / Calacatta' and any(c>=b and c-b<32 and lab not in ('Carrara / Calacatta','marble','engineered marble') for c,d,lab,o in hits):continue
                    forward=[x for x in anchors if x[0]>=b]
                    backward=[x for x in anchors if x[1]<=a]
                    role=None
                    if forward:
                        x,y,r=forward[0];gap=clause[b:x]
                        othermaterial=any(c>=b and d<=x for c,d,lab,o in hits)
                        # A material before its component noun, without crossing another part.
                        if r!='other' and len(gap)<=55 and not othermaterial and not match(r'[:;&]|\b(?:and|with|for|includes?|features?)\b',gap):role=r
                    if role is None and backward:
                        x,y,r=backward[-1];gap=clause[y:a]
                        # A noun followed by an explicit material predicate or field value.
                        if r!='other' and len(gap)<=65 and match(r'^\s*(?:(?:material|construction)\s*[:=]?|(?:(?:is|are)\s+)?(?:made|constructed|crafted|manufactured|molded|moulded|formed)(?:\s+from|\s+of|\s+with)?|[:=])\s*(?:a\s+|durable\s+|premium\s+|high[ -]quality\s+)*$',gap):role=r
                    if role is None:
                        field=source['field'].lower()
                        if match(r'(?:countertop|top)[ _-]*material',field) and not anchors:role='top'
                        elif match(r'(?:sink|basin)[ _-]*material',field) and not anchors:role='sink'
                    if role is None:continue
                    if raw in ('木板','stone'):role='top'
                    if role=='sink' and raw=='木板':continue
                    label=raw;method='部件绑定文本';rule='M-DIRECT'
                    if raw=='stone':label='岗石';method='用户业务归类';rule='M-STONE-UNSPECIFIED'
                    if raw in ('engineered marble','engineered stone','marble','Carrara / Calacatta'):
                        named=match(r'\b(?:carrara|calacatta)\b',clause[max(0,a-40):min(len(clause),b+40)])
                        label='卡拉拉大理石' if named and raw!='engineered stone' else '岗石'
                        method='用户业务归类';rule='M-MARBLE-NAMED' if label=='卡拉拉大理石' else 'M-MARBLE-UNSPECIFIED'
                    elif raw in ('SMC','亚克力','树脂'):
                        label='树脂';method='用户业务归类' if raw!='树脂' else method;rule='M-RESIN-GROUP'
                    if role=='sink':label={'陶瓷':'陶瓷盆','树脂':'树脂盆','玻璃':'玻璃盆','Cultured Marble':'Cultured Marble盆'}.get(label,label+'盆')
                    ev=self.ev(source,label,clause[max(0,a-65):min(len(clause),b+95)],method,{'rawMaterial':original,'materialSubtype':raw,'component':role,'ruleID':rule,'basisType':'business_mapping' if method=='用户业务归类' else 'direct_text'})
                    buckets[role].append(ev);all_evidence.append(ev)
        keys={'top':HEADERS[7],'sink':HEADERS[8]}
        # Unqualified "stone top" is a fallback: drop it when a specific material is named.
        if any(e.get('ruleID')!='M-STONE-UNSPECIFIED' for e in buckets['top']):
            buckets['top']=[e for e in buckets['top'] if e.get('ruleID')!='M-STONE-UNSPECIFIED']
        for role,key in keys.items():
            es=buckets[role]
            self.set(key,es)
            ev=self.evidence[key]
            if ev['status']=='text_supported' and any(e.get('basisType')=='business_mapping' for e in ev.get('selected',[])):ev['status']='business_mapping'
        # User 2026-10-27: "marble texture/look top" with no real stone word in the
        # child's own text is a wood (board) top.
        if self.tags[HEADERS[7]]==UNKNOWN:
            child_text=' || '.join(x['text'] for x in self.sources if x['scope']=='child' and x['field'] not in ('商品尺寸',))
            stone=match(r'\b(?:quartz|sintered|granite|stone|cultured|engineered\s+marble|marble\s+(?:counter\s*top|top)|calacatta|carrara)\b',child_text)
            faux=[]
            for x in self.sources:
                if x['scope']!='child':continue
                m=match(r'\b(?:faux[ -]?)?marble[ -]?(?:texture|look|pattern|grain|like|effect)(?:[ -]+\w+){0,2}?\s+(?:counter\s*tops?|table\s*tops?|tops?)\b',x['text'])
                if m:faux.append(self.ev(x,'木板',m.group(0),'用户业务归类：仿大理石纹台面且无石材词',{'rawMaterial':m.group(0),'materialSubtype':'marble texture','component':'top','ruleID':'M-FAUX-MARBLE-WOOD','basisType':'business_mapping'}))
            if faux and not stone:
                self.set(HEADERS[7],faux);self.evidence[HEADERS[7]]['status']='business_mapping'
            elif faux and stone:self.notes.append('D8台面：有仿大理石纹台面描述但同时出现石材词，未按木板归类')
        # Explicitly absent components override inferred combinations.
        no_top=self.pattern_candidates([('不适用（不含台面）',r'\bwithout\s+(?:a\s+)?(?:top|countertop)\b|\b(?:top|countertop)\s+(?:is\s+)?(?:not included|sold separately)\b|\bno\s+(?:top|countertop)\b|\b(?:vanity\s+)?base\s+only\b|\bcabinet\s+only\b')])
        direct_no=[e for e in no_top if e['sourceScope']=='child']
        if direct_no:
            if self.tags[HEADERS[7]]!=UNKNOWN:self.conflicts.append(HEADERS[7]+'包含状态与材料线索冲突')
            self.tags[HEADERS[7]]='不适用（不含台面）';self.evidence[HEADERS[7]]={'status':'text_supported','selected':direct_no}
        if self.tags[HEADERS[2]]=='无盆':
            self.tags[HEADERS[8]]='不适用（不含盆）';self.evidence[HEADERS[8]]={'status':'derived','basis':HEADERS[2]}
        # Same-material inference requires an explicit one-piece/molding assertion.
        for role,other in [('top','sink'),('sink','top')]:
            key=keys[role];otherkey=keys[other]
            if self.tags[key]!=UNKNOWN:continue
            candidates=[]
            for ev in self.evidence[otherkey].get('selected',[]):
                subtype=ev.get('materialSubtype')
                if subtype not in ('Cultured Marble','SMC','亚克力','树脂'):continue
                src=next((s for s in self.sources if s['field']==ev['sourceField'] and s['asin']==ev['sourceASIN']),None)
                if not src:continue
                # integrated alone does not establish same-material construction.
                mold=match(r'one[ -]piece.{0,70}(?:sink|basin|bowl|countertop)|(?:sink|basin|countertop).{0,70}one[ -]piece|(?:molded|moulded|cast).{0,50}(?:integral|integrated).{0,30}(?:sink|basin|bowl)|(?:sink|basin).{0,35}(?:same material|seamless one[ -]piece)',src['text'])
                if not mold:continue
                label=('Cultured Marble' if subtype=='Cultured Marble' else '树脂')+('盆' if role=='sink' else '')
                candidates.append(self.ev(src,label,mold.group(),'同材一体结构推导',{'basisType':'business_inference','basisField':otherkey,'basisMaterialEvidence':ev,'ruleID':'M-SAME-PIECE'}))
            if candidates:
                self.set(key,candidates)
                if self.evidence[key]['status']=='text_supported':self.evidence[key]['status']='business_inference'
        # User 2026-10-27 (R1/R2/R6): a one-piece sink-top is the sink's material.
        if self.tags[HEADERS[7]]==UNKNOWN and self.tags[HEADERS[8]] not in (UNKNOWN,'不适用（不含盆）'):
            sink_ev=self.evidence[HEADERS[8]].get('selected') or []
            base=next((e for e in sink_ev if e.get('materialSubtype')),None)
            onepiece=None
            for x in self.sources:
                m=match(r'\b(?:ceramic|porcelain|resin|smc|acrylic|glass|quartz|stone|marble|cultured\s+marble)\s+(?:\w+\s+){0,3}?(?:sink|basin|bowl)s?\s+tops?\b|\bintegrated\s+(?:\w+\s+){0,2}?(?:sink|basin)|\b(?:sink|basin)\s+(?:and|&|/)\s+(?:counter\s*)?top\s+(?:in\s+)?one\b|\bone[ -]piece\s+(?:\w+\s+){0,2}?(?:sink|basin|top)',x['text'])
                if m:onepiece=(x,m);break
            if base and (onepiece or self.integrated_sink):
                src,m=onepiece if onepiece else (next(s for s in self.sources if s['field']==base['sourceField'] and s['asin']==base['sourceASIN']),None)
                label=base['label'][:-1] if base['label'].endswith('盆') else base['label']
                ev=self.ev(src,label,m.group(0) if m else base['quote'],'一体盆台同材推导',{'basisType':'business_inference','ruleID':'M-SINK-TOP-ONEPIECE','basisField':HEADERS[8],'basisMaterialEvidence':base,'materialSubtype':base.get('materialSubtype'),'component':'top'})
                parent=src['scope']=='parent'
                self.tags[HEADERS[7]]=label+('' if self.parent_fill or not parent else '（父体候选）')
                self.evidence[HEADERS[7]]={'status':('parent_fill' if self.parent_fill else 'parent_candidate') if parent else 'business_inference','selected':[ev]}
        # User-approved pairing assumption; only when the product includes a basin.
        if self.tags[HEADERS[8]]==UNKNOWN:
            top=self.evidence[HEADERS[7]]
            selected=top.get('selected',[])
            labels={e['label'] for e in selected}
            includes=[]
            for src in self.sources:
                m=match(r'\bwith\s+(?:(?:an?|single|double|white|black|integrated|undermount|vessel|ceramic|porcelain|resin)\s+){0,5}(?:sink|basin)\b|\b(?:sink|basin)\s+(?:is\s+)?included\b',src['text'])
                if m:includes.append((src,m))
            if selected and len(labels)==1 and labels<={'石英石','岗石'} and top['status'] not in ('conflict','missing') and includes:
                child=[(src,m) for src,m in includes if src['scope']=='child'];src,m=(child or includes)[0]
                scope='child' if child and all(e['sourceScope']=='child' for e in selected) else 'parent'
                combined=dict(src);combined['scope']=scope
                ev=self.ev(combined,'陶瓷盆',m.group(),'用户配套经验推导',{'basisType':'business_assumption','ruleID':'M-STONE-CERAMIC','basisField':HEADERS[7],'basisMaterialEvidence':selected,'includedBasinEvidence':self.ev(src,'含盆',m.group())})
                self.tags[HEADERS[8]]='陶瓷盆'+(PARENT_SUFFIX if scope=='parent' and not self.parent_fill else '')
                self.evidence[HEADERS[8]]={'status':('parent_fill' if self.parent_fill else 'parent_candidate') if scope=='parent' else 'business_assumption','selected':[ev]}
        for key in keys.values():
            if key==HEADERS[8] and any(e['label'] not in ('陶瓷盆','树脂盆','Cultured Marble盆','玻璃盆','不适用（不含盆）') for e in self.evidence[key].get('selected',[])):
                self.conflicts.append(key+'出现常规业务组外盆材，保留原词候选待核验')
            if self.evidence[key]['status'] in ('business_mapping','business_inference','business_assumption'):
                self.notes.append(key+'含业务归类/推导，细分与来源见JSON')

    def dimensions(self):
        # No unlabelled dimension-order guessing and no standard-width snapping.
        dims={a:[] for a in ('W','D','H')}
        for s in self.sources:
            if s['scope']!='child':continue
            if s['field'] not in ('SKU属性','商品标题','商品尺寸') and not any(x in s['field'].lower() for x in ('dimension','size')):continue
            t=s['text'];cm=bool(match(r'\bcm\b',t)) and not match(r'inch|\bin\b|["″]',t)
            factor=1/2.54 if cm else 1
            for m in re.finditer(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(["″]|inches|inch|\bin\b|cm)?\s*([WDH])(?=\s|[x×,;)]|$)',t,re.I):
                v=float(m.group(1))*factor;axis=m.group(3).upper()
                # A bare "3H" is a faucet-hole code (e.g. 'Size: 48" -3H'), not a height;
                # unitless letters count only inside an "a x b x c" dimension run.
                triad=match(r'^\s*[x×*]\s*\d',t[m.end():m.end()+8]) or match(r'\d\s*["″]?\s*[LWDH]?\s*[x×*]\s*$',t[max(0,m.start()-12):m.start()])
                if not m.group(2) and not triad:
                    if axis=='H' and v<=8:
                        self.rejected_dims.append(self.ev(s,v,t[max(0,m.start()-20):m.end()+20],'无单位nH按龙头孔位处理，不作高度',{'ruleID':'DIM-HOLE-CODE','faucetHoles':int(v) if v.is_integer() else v}))
                        self.notes.append('SKU/标题中“%sH”按%s孔龙头孔位处理，未作高度'%(m.group(1),m.group(1)))
                    continue
                if 1<v<150:dims[axis].append((v,s,self.ev(s,v,m.group(0),'方向标记尺寸')))
            for m in re.finditer(r'(?<![A-Za-z])([WDH])\s*[:=]?\s*(\d{1,3}(?:\.\d+)?)\s*(["″]|inches|inch|\bin\b|cm)',t):
                # '24"W 18"D' — the letter is the previous number's suffix, not a prefix.
                if match(r'[\d"″]\s*$',t[max(0,m.start()-3):m.start()]):continue
                v=float(m.group(2))*(1/2.54 if m.group(3).lower()=='cm' else 1);axis=m.group(1).upper()
                if 1<v<150:dims[axis].append((v,s,self.ev(s,v,m.group(0),'方向标记尺寸（字母在前）')))
            if s['field']=='SKU属性':
                m=match(r'(?:size|pattern name)\s*:\s*([^|]+)',t)
                # Drop a trailing faucet-hole code ('48" -3H') before reading the width.
                size=re.sub(r'\s*-\s*[1-8]\s*H\b(?!\s*[x×])','',m.group(1)) if m else ''
                if m and not match(r'\b(?:depth|deep|height|tall)\b|\d\s*["″]?\s*[DH]\b',size):
                    mm=match(r'^\s*(\d{1,3}(?:\.\d+)?)\s*(?:inch(?:es)?|["″]|\bin\b|cm)(?!\s*(?:deep|depth))',size)
                    if mm:
                        v=float(mm.group(1))*factor
                        if 5<v<150:dims['W'].insert(0,(v,s,self.ev(s,v,m.group(0),'SKU名义宽度')))
                    elif match(r'^\s*\d{1,3}(?:\.\d+)?\s*$',size):
                        v=float(size)
                        # Bare SKU size is only usable when the child title
                        # independently spells out the same vanity width.
                        title=clean(self.row.get('商品标题'))
                        if 5<v<150 and match(r'(?<![\d.])'+re.escape(str(int(v)) if v.is_integer() else str(v))+r'\s*(?:["″]|inch(?:es)?|\bin\b)\s*(?:wide\s+)?(?:[a-z -]{0,45})?(?:vanity|cabinet)',title):
                            dims['W'].insert(0,(v,s,self.ev(s,v,m.group(0),'SKU裸尺寸与子体标题同值相互支持')))
            if s['field']=='商品标题':
                mm=match(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(?:["″]|inch(?:es)?|\bin\b)\s*(?:wide\s+)?(?:[a-z -]{0,45})?(?:vanity|cabinet)',t)
                if mm and not match(r'\b(?:depth|height|faucet|mirror)\b',mm.group(0)):
                    v=float(mm.group(1))
                    if 5<v<150:dims['W'].append((v,s,self.ev(s,v,mm.group(0),'子体标题浴室柜宽度上下文')))
        dims['W'].sort(key=lambda x:0 if x[1]['field']=='SKU属性' else 1)
        # Sellers sometimes swap D/W labels ('30"D x 18.3"W'): a source whose W
        # disagrees with the chosen width while its D equals that width. Its W
        # is not a width conflict; its D is handled below.
        swapped=[]
        if dims['W']:
            width=dims['W'][0][0]
            for s in {id(x[1]):x[1] for x in dims['D']}.values():
                own_w=[v for v,s2,e in dims['W'] if s2 is s];own_d=[v for v,s2,e in dims['D'] if s2 is s]
                if own_w and own_d and abs(own_w[0]-width)>2.5 and abs(own_d[0]-width)<=1.0:swapped.append(s)
        # Prefer a depth from a source whose labels are consistent.
        dims['D'].sort(key=lambda x:1 if any(x[1] is s for s in swapped) else 0)
        for axis,key in zip(('W','D','H'),HEADERS[9:12]):
            values=dims[axis]
            if values:
                value=values[0][0];self.tags[key]=round(value,3);self.evidence[key]={'status':'text_supported','selected':[values[0][2]],'otherCandidates':[v[2] for v in values[1:]]}
                if any(abs(v[0]-value)>2.5 and not (axis in ('W','D') and any(v[1] is s for s in swapped)) for v in values[1:]):self.conflicts.append(key+'尺寸来源差异超过2.5in，保留首选值待核验')
            else:self.tags[key]=None;self.evidence[key]={'status':'missing','candidates':[]}
        if self.rejected_dims:self.evidence[HEADERS[11]]['rejectedCandidates']=self.rejected_dims
        # If the chosen depth comes from a swapped source it is really the width: blank it.
        width=self.tags[HEADERS[9]];depth=self.tags[HEADERS[10]]
        if width is not None and depth is not None and dims['D']:
            src=dims['D'][0][1]
            own=[v for v,s2,e in dims['W'] if s2 is src]
            if any(src is s for s in swapped):
                ev=self.evidence[HEADERS[10]]
                fixed=self.ev(src,round(own[0],3),dims['D'][0][2]['quote'],'D/W标签互换纠正：取同一来源标W值作深度',{'ruleID':'DIM-DW-SWAP','basisType':'order_inference','crossCheckWidth':width})
                ev.update({'status':'conflict','swapCorrectedCandidate':fixed,'rejectedValue':depth,'selected':[]})
                ev['rejectedCandidates']=ev.get('rejectedCandidates',[])+[dims['D'][0][2]]
                self.tags[HEADERS[10]]=None
                if self.enable_dim_rules:
                    self.tags[HEADERS[10]]=fixed['label'];ev.update({'status':'order_inference','selected':[fixed]})
                    self.notes.append('D9深：来源D/W标签互换，已按同源标W值纠正')
                else:self.conflicts.append(HEADERS[10]+'：来源D/W标签疑似互换（标D=%s≈已选宽度，标W=%s），深度留空待核验'%(depth,round(own[0],3)))
        self.dwh_order_candidates()

    def dwh_order_candidates(self):
        # Unlabelled 'a x b x c inches' is usually Amazon's D×W×H with the letters
        # stripped. Use it only when b independently matches the selected width.
        width=self.tags.get(HEADERS[9])
        if width is None or (self.tags[HEADERS[10]] is not None and self.tags[HEADERS[11]] is not None):return
        s=next((x for x in self.sources if x['field']=='商品尺寸' and x['scope']=='child'),None)
        m=s and match(r'^\s*(\d{1,3}(?:\.\d+)?)\s*[x×]\s*(\d{1,3}(?:\.\d+)?)\s*[x×]\s*(\d{1,3}(?:\.\d+)?)\s*(inches|inch|in|cm)?\s*$',s['text'])
        if not m:return
        f=1/2.54 if (m.group(4) or '').lower()=='cm' else 1
        a,b,c=(float(m.group(i))*f for i in (1,2,3))
        if abs(b-width)>1.0:return
        for key,v in ((HEADERS[10],a),(HEADERS[11],c)):
            if self.tags[key] is not None or not 1<v<150:continue
            ev=self.ev(s,round(v,3),s['text'],'无方向商品尺寸按D×W×H顺序推断（中间值与已选宽度一致）',{'ruleID':'DIM-DWH-ORDER','basisType':'order_inference','crossCheckWidth':width})
            self.evidence[key]['orderInferenceCandidate']=ev
            if self.enable_dim_rules:
                self.tags[key]=round(v,3);self.evidence[key].update({'status':'order_inference','selected':[ev]})
        if self.enable_dim_rules and any(self.evidence[k].get('status')=='order_inference' for k in HEADERS[10:12]):
            self.notes.append('D9深/高按无方向商品尺寸D×W×H顺序推断，宽度已交叉核对')

    def parent_dimensions(self):
        # Parent detail is one representative variant: its depth/height apply only
        # when that variant has the same (standard) width as this child.
        width=self.tags.get(HEADERS[9])
        if not self.parent_fill or width is None or (self.tags[HEADERS[10]] is not None and self.tags[HEADERS[11]] is not None):return
        text=clean(self.parent_detail.get('dimensions'))
        lab={ax:float(v) for v,ax in re.findall(r'(\d{1,3}(?:\.\d+)?)\s*["″]?\s*([DWH])\b',text)}
        if 'W' not in lab:return
        pw=lab['W'];cw=width
        same=abs(pw-cw)<=1.0 or (standard_width(pw) is not None and standard_width(pw)==standard_width(cw))
        if not same or ('D' in lab and abs(lab['D']-cw)<=1.0 and abs(pw-cw)>2.5):return
        src={'field':'父体详情.dimensions','text':text,'scope':'parent','asin':self.row.get('核验父ASIN')}
        for key,ax in ((HEADERS[10],'D'),(HEADERS[11],'H')):
            if self.tags[key] is not None or ax not in lab or not 1<lab[ax]<150:continue
            ev=self.ev(src,lab[ax],text,'父体代表变体同宽度尺寸补充',{'ruleID':'DIM-PARENT-SAME-WIDTH','parentWidth':pw})
            self.tags[key]=lab[ax];self.evidence[key].update({'status':'parent_fill','selected':[ev]})

    def snap_width(self):
        w=self.tags.get(HEADERS[9])
        if not self.std_width or w is None:return
        sw=standard_width(w)
        ev=self.evidence[HEADERS[9]]
        if sw is None:
            ev['nonStandardWidth']=True;return
        if abs(sw-w)>1e-9:
            ev.update({'rawValue':w,'standardWidthRule':'DIM-STD-WIDTH'})
            self.tags[HEADERS[9]]=sw
            self.notes.append('D9宽实际%s按标准宽度归为%s'%(w,sw))

    def included(self,key,kind):
        c=[]
        word=kind
        for s in self.sources:
            t=s['text']
            separate=match(r'\b'+word+r's?\s+(?:is\s+)?sold separately\b',t)
            no=match(r'\b(?:no|without)\s+(?:a\s+)?'+word+r's?\b|\b'+word+r's?\s+(?:is\s+)?not included\b|does not include\s+(?:a\s+)?'+word,t)
            yes=match(r'\b'+word+r's?\s+(?:is\s+)?included\b|\bwith\s+(?:(?:matte|black|white|chrome|brushed|gold|nickel)\s+){0,3}'+word+r'\b(?![- ]?(?:finish|polish|like|holes?)\b)|\b1\s*[x×]\s*'+word+r'\b',t)
            chosen=('单卖',separate) if separate else ('无',no) if no else ('含',yes) if yes else None
            if chosen:
                label,m=chosen;c.append(self.ev(s,label,t[max(0,m.start()-30):m.end()+60]))
            else:
                hit=self.listed_component(s,word)
                if hit:c.append(self.ev(s,hit[0],hit[1],hit[2]))
        self.set(key,c)

    def listed_component(self,s,word):
        """List wording v2 missed: "faucets and mirror are not included",
        "excluding faucets", "mirror, faucet, and drain are sold separately",
        "includes faucet, drain", or a child title naming the part."""
        # The part itself, not "faucet hole", "faucet-ready", "mirror finish".
        noun=r'\b'+word+r's?\b(?![- ]?(?:holes?|mount(?:ing)?\s+holes?|deck|spout|cut[ -]?outs?|openings?|hole\s+size|finish|polish|like|compatible|ready)\b)'
        gap=r'(?P<gap>[\w\s,&/()\'"″”-]{0,70}?)'
        # A negation reaches back over a list of accessories only ("faucet and
        # drain are not included"), not over "6 Drawers, Mirror Not Included".
        accessory=r'^(?:[\s,&/()-]|\b(?:and|or|the|a|an|are|is|any|all|mirrors?|faucets?|drains?|pop[ -]?up|p[ -]?trap|backsplash|hardware|counter\s*tops?|tops?|sinks?|basins?|water|supply|lines?|assembly|components?|accessories|glue|lights?|lighting|plumbing|fixtures?|hot|cold|parts|kits?|mount(?:ing)?|sets?|decor|shown|pictured|in|picture|images?)\b)*$'
        neg=r'(?:(?:are|is)\s+)?not\s+(?:be\s+)?included|\bnot\s+includ(?:e|ed|ing)\b|(?:are|is)\s+excluded'
        sep=r'(?:are\s+|is\s+)?(?:sold|purchased|available)\s+separately|sold\s+individually'
        intro=r'\b(?:includes?|including|included\s*:|comes?\s+with|equipped\s+with|packages?\s+(?:includes?|contains?)|package\s+contents?\s*:|in\s+the\s+box\s*:|complete\s+with)\b'
        for_ctx=r'(?:\bfor|\bfits?|compatible\s+with|accommodates?|suitable\s+for|drilled\s+for|\bmatch(?:es)?)\s+(?:an?\s+|the\s+|your\s+)?(?:[\w"”″.-]+\s+){0,3}$'
        for clause in re.split(r'(?<=[.;!?])\s+|\n|\s*\|\|\s*',s['text']):
            for m in re.finditer(noun,clause,re.I):
                after=clause[m.end():];before=clause[max(0,m.start()-90):m.start()]
                q=clause[max(0,m.start()-60):m.end()+70]
                f_sep=match(r'^'+gap+r'(?:'+sep+r')',after)
                if f_sep and match(accessory,f_sep.group('gap')):return '单卖',q,'列表式单卖文本'
                f_neg=match(r'^\s*\(\s*not\s+included\s*\)',after) or match(r'^'+gap+r'(?:'+neg+r')',after)
                if f_neg and 'gap' in f_neg.re.groupindex and not match(accessory,f_neg.group('gap')):f_neg=None
                b_neg=match(r'(?:excluding|excludes?|does\s*n[o\']t\s+(?:come\s+with|include)|\bnot\s+include)\s+'+gap+r'$|\bwithout\s+(?:an?\s+|the\s+)?(?:[\w-]+\s+){0,2}$',before)
                if b_neg and b_neg.group('gap') is not None and not match(accessory,b_neg.group('gap')):b_neg=None
                b_inc=match(intro+gap+r'$',before)
                if b_inc and (match(r'\bnot\b|\bno\b|without|exclud',b_inc.group('gap')) or match(r'(?:\bnot|n\'t|\bno)\s*$',before[:b_inc.start()])):b_inc=None
                if b_inc and match(for_ctx,before):b_inc=None
                if (f_neg or b_neg) and b_inc:
                    # Both an inclusion intro and a negation reach the noun: nearer wins.
                    dn=min(len(x.group(0)) for x in (f_neg,b_neg) if x);di=len(b_inc.group('gap'))
                    return ('无' if dn<di else '含'),q,'列表式包含/排除文本（就近判断）'
                if f_neg or b_neg:return '无',q,'列表式排除文本'
                if b_inc:return '含',q,'列表式包含文本'
                # "Single Hole Faucet", "3-Hole Faucet", "8\" Widespread Faucet" describe drilling.
                if s['field']=='商品标题' and s['scope']=='child' and not match(for_ctx,before) and not match(r'(?:\bholes?|widespread|center[ -]?set|centre[ -]?set)[ -]*$',before,):
                    return '含',q,'子体标题列出部件'
        return None

    def run(self):
        self.structure();self.colors();self.materials();self.dimensions();self.parent_dimensions();self.snap_width();self.included(HEADERS[12],'mirror');self.included(HEADERS[13],'faucet')
        # User 2026-10-27 defaults: no explicit form -> 落地式; no assembled/pre-assembled -> 拆装;
        # no "double" -> 单盆 (double only plausible at width >= 48in).
        if self.accessory_default:
            for h,val,rule in ((HEADERS[0],'落地式','FORM-DEFAULT-FREESTANDING'),(HEADERS[1],'拆装','ASSEMBLY-DEFAULT-RTA'),(HEADERS[2],'单盆','BASIN-DEFAULT-SINGLE'),(HEADERS[3],'台下盆','TOPFORM-DEFAULT-UNDERMOUNT')):
                if self.tags.get(h)==UNKNOWN:
                    self.tags[h]=val;self.evidence[h]={'status':'business_default','selected':[],'ruleID':rule,'basisType':'business_default','note':'文本未明确，按用户规则默认'}
            width=self.tags.get(HEADERS[9])
            if self.tags.get(HEADERS[2],'').startswith('双盆') and width is not None and width<48:
                self.conflicts.append(HEADERS[2]+'：文本写双盆但宽度%s<48in，待核验'%width)
            dflt=[h for h in HEADERS[:4] if self.evidence[h].get('status')=='business_default']
            if dflt:self.notes.append('按用户规则默认：'+'、'.join('%s=%s'%(h,self.tags[h]) for h in dflt))
        if self.accessory_default:
            for h in (HEADERS[12],HEADERS[13]):
                if self.tags.get(h)==UNKNOWN:
                    self.tags[h]='无';self.evidence[h]={'status':'business_default','selected':[],'ruleID':'ACC-DEFAULT-NONE','basisType':'business_default','note':'文本未明确with/included，按用户规则默认无'}
            if any(self.evidence[h].get('status')=='business_default' for h in (HEADERS[12],HEADERS[13])):
                self.notes.append('镜子/龙头未明确提及，按用户规则默认无：'+'、'.join(h for h in (HEADERS[12],HEADERS[13]) if self.evidence[h].get('status')=='business_default'))
        for h in HEADERS[:14]:
            related=[s for s in self.conflicts if s.startswith(h)]
            if related and h in self.evidence:
                self.evidence[h]['status']='conflict';self.evidence[h]['conflicts']=related
        unknown=[h for h in HEADERS[:14] if self.tags.get(h) in (None,UNKNOWN,'待图片核验')]
        parent=[h for h in HEADERS[:14] if self.evidence.get(h,{}).get('status') in ('parent_candidate','parent_fill')]
        if self.conflicts:state='存在冲突待核验'
        elif unknown or (parent and not self.parent_fill):state='部分信息不足'
        else:state='文本证据可用'
        notes=[]
        if parent:notes.append(('父体信息补充：' if self.parent_fill else '父体候选：')+'、'.join(parent))
        if unknown:notes.append('缺少充分文本证据：'+'、'.join(unknown))
        notes.extend(uniq(self.conflicts+self.notes))
        if self.tags[HEADERS[4]]=='待图片核验':notes.append('元素图片尚未人工核验')
        else:notes.append('元素取文本线索，未作图片独立核验')
        self.tags[HEADERS[14]]=state;self.tags[HEADERS[15]]='；'.join(notes) or '标签取自当前文本快照'
        return {h:self.tags.get(h) for h in HEADERS},self.evidence,uniq(self.conflicts)

# Per-field feasibility: can the current data sources tag this field for this row?
FEASIBILITY={
    'A':'可打标：子体文本证据',
    'A2':'可打标：按已确认业务规则归类/推导',
    'A3':'可打标：子体缺失，按用户规则用父体信息补充',
    'B':'仅父体候选：需子体证据确认',
    'C':'有冲突：需人工核验',
    'D':'现有数据可补：需确认新规则后启用',
    'E':'现阶段不行：缺子体详情，需补采asin_detail',
    'F':'现阶段不行：文本无线索，需看图核验',
    'G':'现阶段不行：子体文本未写，需说明书/厂家/人工',
}
VISUAL={'D1产品形态','D3盆数','D4台面形态','D5元素','D6柜体颜色'}

def feasibility(field,ev,has_child_text):
    status=(ev or {}).get('status','missing')
    if status in ('text_supported','derived'):return 'A'
    if status in ('business_mapping','business_inference','business_assumption','order_inference','business_default'):return 'A2'
    if status=='parent_fill':return 'A3'
    if status=='parent_candidate':return 'B'
    if (ev or {}).get('swapCorrectedCandidate') and status=='conflict':return 'D'
    if status=='conflict':return 'C'
    if (ev or {}).get('orderInferenceCandidate'):return 'D'
    if field in VISUAL:return 'F'
    return 'G' if has_child_text else 'E'

def apply_solid_wood_price_rule(target_rows,matrix,evidence_rows):
    """User 2026-10-27: a bare 'solid wood' / 'solid wood frame' claim is only
    believed for an assembled vanity priced well above same-width MDF ones
    (>= SOLID_WOOD_PRICE_RATIO x the MDF median). Otherwise it is the usual
    MDF cabinet with a solid-wood frame. Applied per row (price is per row)."""
    import statistics
    D7,D2,W=HEADERS[6],HEADERS[1],HEADERS[9]
    def price(r):
        try:return float(r.get('商品价格'))
        except (TypeError,ValueError):return None
    ref={}
    for a,m,tags,e,feas,src,r,idx in target_rows:
        if tags[D7]=='MDF' and tags[W] is not None and price(r):ref.setdefault(tags[W],[]).append(price(r))
    med={w:statistics.median(v) for w,v in ref.items() if len(v)>=10}
    for a,m,tags,e,feas,src,r,idx in target_rows:
        cur=tags[D7]
        if cur not in ('实木','实木框架'):continue
        pr=price(r);w=tags[W];asm=tags[D2]
        ratio=(pr/med[w]) if (pr and w in med) else None
        expensive=ratio is not None and ratio>=SOLID_WOOD_PRICE_RATIO
        if asm=='整装' and expensive:new='实木' if cur=='实木' else '实木框架+实木';why='整装且价格≥同宽MDF中位%.1f倍'%SOLID_WOOD_PRICE_RATIO
        elif asm=='整装' and ratio is None and pr is not None:
            if pr>=SOLID_WOOD_PRICE_FLOOR:new=cur;why='整装、无同宽参照、价格≥$%d'%SOLID_WOOD_PRICE_FLOOR
            else:new='实木框架+MDF';why='整装、无同宽参照、价格<$%d，按实木框架+MDF'%SOLID_WOOD_PRICE_FLOOR
        elif asm=='整装' and pr is None:new=cur;why='整装但无价格，保留文本标签'
        else:new='实木框架+MDF';why='拆装或价格未达同宽MDF中位%.1f倍，按实木框架+MDF'%SOLID_WOOD_PRICE_RATIO
        base=e.get(D7,{})
        newev=dict(base);newev.update({'status':'business_mapping' if new!=cur else base.get('status'),'ruleID':'CAB-SOLIDWOOD-PRICE','basisType':'business_mapping','textLabel':cur,'assembly':asm,'price':pr,'width':w,'sameWidthMDFMedian':med.get(w),'priceRatio':round(ratio,2) if ratio else None,'decision':why})
        matrix[idx][6]=new
        ev=evidence_rows[idx];ev['tags']=dict(ev['tags']);ev['tags'][D7]=new
        ev['fields']=dict(ev['fields']);ev['fields'][D7]=newev
        ev['feasibility']=dict(ev['feasibility']);ev['feasibility'][D7]=feasibility(D7,newev,True) if new!=cur else ev['feasibility'][D7]
        note='；D7实木复核：'+why+('（%s→%s）'%(cur,new) if new!=cur else '')
        matrix[idx][15]=(matrix[idx][15] or '')+note;ev['tags'][HEADERS[15]]=matrix[idx][15]
    # Summary counts use per-row tags: refresh from matrix.
    for i,(a,m,tags,e,feas,src,r,idx) in enumerate(target_rows):
        if tags[D7] in ('实木','实木框架'):
            t2=dict(tags);t2[D7]=matrix[idx][6];e2=dict(e);e2[D7]=evidence_rows[idx]['fields'][D7];f2=dict(feas);f2[D7]=evidence_rows[idx]['feasibility'][D7]
            target_rows[i]=(a,m,t2,e2,f2,src,r,idx)

def load_export_rows(path):
    rows={}
    if path and Path(path).exists():
        for r in load(path):rows.setdefault(r['asin'],[]).append(r)
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data-root',required=True,help='项目规范化数据目录（含sales_payload.json等）')
    ap.add_argument('--out-dir',required=True)
    ap.add_argument('--export-rows',help='卖家精灵导出逐行JSON（asin/month/attributes/features）；默认<data-root>/input_rows.json')
    # 2026-10-27 user confirmed: dimension rules, standard widths, parent fill all on by default.
    ap.add_argument('--no-dim-rules',action='store_true',help='关闭DIM-DWH-ORDER与DIM-DW-SWAP')
    ap.add_argument('--no-parent-fill',action='store_true',help='子体缺失时不用父体值填，只标（父体候选）')
    ap.add_argument('--no-std-width',action='store_true',help='宽度保留实际值，不归标准宽度')
    ap.add_argument('--no-accessory-default',action='store_true',help='镜子/龙头未提及时保留信息不足，不默认无')
    ap.add_argument('--no-price-rules',action='store_true',help='关闭实木/实木框架的整装+价格复核（CAB-SOLIDWOOD-PRICE）')
    args=ap.parse_args()
    root=Path(args.data_root);out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    p=load(root/'sales_payload.json');details=load(root/'collected_details.json')
    excluded=load(root/'step1_macro_audit.json')['confirmedNonTargetProducts']
    fp={(r['targetMonth'],r['childASIN']):r for r in load(root/'feature_field_provenance.json')}
    exports=load_export_rows(args.export_rows or root/'input_rows.json')
    matrix=[];evidence_rows=[];states=Counter();snapshots={};target_rows=[]
    for i,r in enumerate(p['detailRows'],2):
        a=r['子ASIN'];month=r['目标月份']
        if not r.get('_eligible') or a in excluded:
            state='不纳入浴室柜分析' if a in excluded or r.get('_outside_input_scope') else '目标月归属待核验'
            values=[None]*14+[state,excluded.get(a) or '保留原始记录，未对未核验目标月候选强行打标']
            e={};conflicts=[];feas={};sourcesUsed={}
        else:
            textkey=hashlib.sha256(json.dumps({h:r.get(h) for h in ['子ASIN','SKU属性','商品标题','商品尺寸','五点描述','五点来源','五点来源ASIN','核验父ASIN']},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            if textkey not in snapshots:
                t=Tagger(r,details,fp.get((month,a)),exports.get(a),not args.no_dim_rules,not args.no_parent_fill,not args.no_std_width,not args.no_accessory_default)
                res=t.run();child_text=t.has_child_detail or t.has_export
                snapshots[textkey]=res+({h:feasibility(h,res[1].get(h),child_text) for h in HEADERS[:14]},{'childDetail':t.has_child_detail,'sellerSpriteExport':t.has_export,'parentFeatures':r.get('五点来源')=='父体详情填充'})
            tags,e,conflicts,feas,sourcesUsed=snapshots[textkey];values=[tags[h] for h in HEADERS];target_rows.append((a,month,tags,e,feas,sourcesUsed,r,len(matrix)))
        matrix.append(values);states[values[-2]]+=1
        evidence_rows.append({'excelRow':i,'marketplace':r['站点'],'month':month,'childASIN':a,'verifiedParentASIN':r.get('核验父ASIN'),'includeInBathroomAnalysis':bool(r.get('_eligible')) and a not in excluded,'tags':dict(zip(HEADERS,values)),'fields':e,'feasibility':feas,'textSources':sourcesUsed,'conflicts':conflicts,'originalRecordIDs':r.get('关联原始记录ID'),'featureSource':r.get('五点来源'),'featureSourceASIN':r.get('五点来源ASIN')})
    if not args.no_price_rules:apply_solid_wood_price_rule(target_rows,matrix,evidence_rows)
    months=sorted({x[1] for x in target_rows})
    summary={'ruleVersion':VERSION,'dimensionRulesEnabled':not args.no_dim_rules,'parentFill':not args.no_parent_fill,'standardWidth':not args.no_std_width,'accessoryDefaultNone':not args.no_accessory_default,'solidWoodPriceRule':not args.no_price_rules,'allRowsRetained':len(matrix),'taggedTargetRows':len(target_rows),'uniqueTargetASINs':len({x[0] for x in target_rows}),'distinctTextSnapshots':len(snapshots),'rowStates':dict(states),'dimensions':{},'feasibilityLegend':FEASIBILITY,'feasibility':{},'textSourceCoverage':{},'newAPICalls':0,'imagesIndependentlyReviewed':0,'imageNote':'本轮是已有文本证据打标，元素待图片核验/文本线索均明确标注，不宣称已看图','monthly':[]}
    for h in HEADERS[:14]:
        vals=[x[2][h] for x in target_rows]
        present=sum(v not in (None,UNKNOWN,'待图片核验') for v in vals)
        summary['dimensions'][h]={'textOrCandidatePresentRows':present,'insufficientRows':sum(v in (None,UNKNOWN,'待图片核验') for v in vals),'parentCandidateRows':sum(x[3].get(h,{}).get('status') in ('parent_candidate','parent_fill') for x in target_rows),'fieldEvidenceStates':dict(Counter(x[3].get(h,{}).get('status','component_specific') for x in target_rows)),'distribution':dict(Counter(str(v) if v is not None else '空白' for v in vals))}
        rows_by=Counter(x[4][h] for x in target_rows)
        asins_by={k:len({x[0] for x in target_rows if x[4][h]==k}) for k in rows_by}
        summary['feasibility'][h]={'rows':{k:rows_by.get(k,0) for k in FEASIBILITY},'uniqueASINs':{k:asins_by.get(k,0) for k in FEASIBILITY}}
    for k in ('childDetail','sellerSpriteExport','parentFeatures'):
        summary['textSourceCoverage'][k]={'rows':sum(x[5][k] for x in target_rows),'uniqueASINs':len({x[0] for x in target_rows if x[5][k]})}
    none=[x for x in target_rows if not (x[5]['childDetail'] or x[5]['sellerSpriteExport'])]
    summary['textSourceCoverage']['noChildDetailOrExport']={'rows':len(none),'uniqueASINs':len({x[0] for x in none})}
    for m in months:
        rr=[x[2] for x in target_rows if x[1]==m]
        summary['monthly'].append({'month':m,'targetRows':len(rr),'states':dict(Counter(t[HEADERS[14]] for t in rr))})
    # Work queues for what the current data cannot answer.
    recollect=sorted({x[0] for x in none})
    image_queue={}
    for a,m,t,e,feas,src,r,_i in target_rows:
        fields=[h for h in HEADERS[:14] if feas[h]=='F']
        if fields:
            q=image_queue.setdefault(a,{'childASIN':a,'mainImage':r.get('主图链接'),'productURL':r.get('商品链接'),'months':[],'fields':[]})
            q['months']=sorted(set(q['months'])|{m});q['fields']=[h for h in HEADERS[:14] if h in set(q['fields'])|set(fields)]
    queues={'recollectChildDetailASINs':recollect,'imageReviewQueue':list(image_queue.values())}
    for name,value in [('tagging_matrix.json',{'headers':HEADERS,'matrix':matrix}),('tagging_evidence.json',{'schemaVersion':VERSION,'snapshotWarning':'商品属性为当前证据快照，不是历史月末；父体候选不得当已确认子体属性','feasibilityLegend':FEASIBILITY,'rows':evidence_rows}),('tagging_summary.json',summary),('tagging_work_queues.json',queues)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('dimensions','feasibility','feasibilityLegend')},ensure_ascii=False))

if __name__=='__main__':main()
