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

VERSION='bathroom-vanity-tagger-20261029-v12.2'
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
# v12.2: inch marks sellers use: " ″ ” “ '' ’’, inch/inches, in/in., 28-inch, 36in.
INCH=r'(?:\s*(?:["″”“]|\'\'|’’)|\s*-?\s*inch(?:es)?\b|\s*-?\s*in\b\.?)'
VANITY_NOUN=r'\b(?:vanit(?:y|ies)|cabinets?)\b'
# Words that make a colour belong to the sink/top/hardware, not the cabinet ("Blue Boat Glass Sink").
COLOR_COMPONENT=r'\b(?:sinks?|basins?|bowls?|boat|vessel|counter\s*tops?|tops?|faucets?|handles?|knobs?|pulls?|hardware|shell|leaf|round|square|rectangle|rectangular|curved|oval|quartz|granite|backsplash)\b'
# A specific shade and its generic family are not a conflict (SKU Brown vs title Walnut).
COLOR_FAMILY={'胡桃木色':'棕色','深咖啡色':'棕色','藏青色':'蓝色','灰蓝色':'蓝色','灰绿色':'绿色'}
# User 2026-10-29: Farmhouse means visible farmhouse trim (X / cross / barn door), not the style word;
# a title that only says "Farmhouse Bathroom Vanity" is left to image review.
FARMHOUSE_VISIBLE=r'\bx[ -]?(?:design|shaped?|pattern|style|trim|brace)\b|\bcross[ -]?(?:buck|bar|brace|trim|design)\b|\bbarn[ -]?(?:style\s+)?doors?\b'
# User 2026-10-29: a vanity sold with a side cabinet is sized by its total width.
SIDE_CABINET=r'\bside\s+(?:storage\s+)?(?:cabinet|tower)s?\b'
STYLE_WORDS=r'(?:modern|contemporary|scandinavian|minimalist|traditional|rustic|coastal|industrial|transitional|boho|bohemian|mid[ -]century|cottage|vintage|classic|nordic|japandi)'
# v12.2 D3/D4/D8 wording. Title/SKU-only no-sink products: storage cabinets around a
# pedestal sink, base cabinets and vanities sold without a top (images: no basin).
NO_SINK_TITLE=(r'\bvanity\s+only\b|\bsinks?\s+compatible\s*\(\s*not\s+included\s*\)'
    r'|\bpedestal\s+sink\s+storage\s+cabinet\b|\bunder[ -]?(?:bathroom\s+)?sink\s+(?:bathroom\s+)?(?:storage\s+)?(?:cabinet|storage|organizer)\b'
    r'|\b(?:sink\s+|kitchen\s+)?base\s+cabinet\b|\bvanity\s+base\b|\b(?:vanity|cabinet)\s+without\s+(?:a\s+)?(?:counter\s*)?top\b')
SINK_PRESENT=(r'\bwith\s+(?:\w+\s+){0,3}?(?:sinks?|basins?)\b|\bsink\s+(?:combo|set)\b'
    r'|\b(?:vessel|ceramic|porcelain|resin|glass|integrated|undermount)\s+(?:\w+\s+){0,2}?(?:sinks?|basins?)\b')
# A one-piece sink/top cannot be undermounted; "integrated undermount sink" is excluded.
ONE_PIECE=(r'\bintegra(?:ted|tion|l)\s+(?:(?!under)\w+\s+){0,2}?(?:sinks?|basins?|bowls?|counter\s*-?tops?|tops?\b(?!\s*(?:drawer|handle)))'
    r'|\bone[ -]piece\s+(?:\w+\s+){0,2}?(?:sinks?|basins?|bowls?|counter\s*-?tops?|tops?)\b|\ball[ -]in[ -]one\s+(?:\w+\s+){0,2}?(?:sinks?|basins?)\b')
# Vessel wording, incl. boat sinks and "countertop sink"; "<x> sink top" is a vessel or a
# one-piece sink-top, both 台上盆 (user 2026-10-27: 一体盆归台上盆). "vanity sink top" is a top product.
# User 2026-10-29: words naming a top material; when the child text has none, a known ceramic/resin sink
# is read as a one-piece sink-top (M-INTEGRATED-INFER), and a vessel sink sits on a wood/faux-marble panel (M-VESSEL-TOP-WOOD).
TOP_MATERIAL_WORD=(r'\b(?:quartz|marble|granite|sintered|stone|calacatta|carrara|terrazzo|solid\s+surface|cultured)\b'
    r'|\b(?:wood(?:en)?|oak|walnut|bamboo|teak|mdf|plywood|glass|tempered\s+glass)\s+(?:counter\s*)?tops?\b')
VESSEL=(r'\bvessel\s+(?:\w+\s+){0,2}?(?:sinks?|basins?|bowls?)\b|\babove[ -]counter\s+(?:sink|basin)\b'
    r'|\bboat\s+(?:\w+\s+){0,2}?(?:sinks?|basins?)\b|\bcounter\s*-?top\s+(?:vessel\s+)?(?:sinks?|basins?)\b'
    r'|(?<!vanity )\b(?:sinks?|basins?)\s+tops?\b(?!\s*(?:drawer|mount))')
# v12.2 (audit 2026-10-29): a title selling a vanity/cabinet with its own sink, or a kitchen base cabinet,
# only names "pedestal sink" as a use keyword -- same logic as the Standing Pedestal Cabinet exception.
PEDESTAL_NOT_PRODUCT=r'\b(?:vanity|cabinet)\s+(?:combo\s+|set\s+)?(?:with|w/|and|&)\s+(?:[\w-]+\s+){0,3}(?:sinks?|basins?)\b|\bkitchen\s+(?:base\s+|sink\s+base\s+)?cabinets?\b'
FLOAT_FORM=r'\b(?:floating|wall[ -]mount(?:ed)?|wall[ -]hung)\b'
FLOOR_FORM=r'\b(?:freestanding|free[ -]standing|floor[ -]mount(?:ed)?|floor[ -]?standing)\b'
# "wall mount" that names a mirror/faucet/anti-tip hardware, or a comparison ("unlike wall-mounted vanities"), is not the vanity's form.
FORM_NOT_AFTER=r'^[\s-]*(?:(?:led|lighted|matching|medicine)\s+)?(?:mirrors?|medicine|faucets?|taps?|hardware|kits?|brackets?|anchors?|straps?|shel(?:f|ves)|towel|lights?|anti[ -]?tip)\b'
FORM_NOT_BEFORE=r'\b(?:unlike|than|instead of|compared (?:to|with)|anti[ -]?tip(?:ping)?|optional|no need (?:to|for))\s+(?:[\w-]+\s+){0,2}$'
CORNER_FORM=r'\bcorner\s+(?:bathroom\s+)?(?:vanity|cabinet|sink)\b'
# User 2026-10-29: a cabinet sold as "wall-mounted or freestanding" is its own form, 两用 (FORM-DUAL).
DUAL_FORM=r'\b(?:wall[ -]?mount(?:ed|able)?|wall[ -]hung|floating)\s*(?:or|/|&|and)\s*(?:free[ -]?standing|floor[ -]?standing|floor[ -]mount(?:ed)?)\b|\b(?:free[ -]?standing|floor[ -]?standing|floor[ -]mount(?:ed)?)\s*(?:or|/|&|and)\s*(?:wall[ -]?mount(?:ed|able)?|wall[ -]hung|floating)\b'
# User 2026-10-29: an under-sink storage cabinet sold without its own sink and not named a bathroom vanity, or a
# U-shaped one, is a pedestal sink storage cabinet -> 柱状盆 (FORM-PEDESTAL-STORAGE).
UNDER_SINK_STORAGE=r'\bunder[ -]?sink\s+(?:[\w-]+\s+){0,2}?(?:cabinet|cupboard|organizer|storage)\b'
U_SHAPE=r'\bU[ -]?shaped?\b'
SELLS_VANITY_OR_SINK=r'\bbathroom\s+vanit(?:y|ies)\b|\bwith\s+(?:[\w-]+\s+){0,3}(?:sinks?|basins?)\b'
# Assembly wording (v12.2): hyphenated "fully-assembled", "comes 100% assembled"; RTA phrases only add evidence to the 拆装 default.
PARTIAL_ASSEMBLY=r'\b(?:partially|partly)\s+(?:pre[ -]?)?assembled\b|\bsome\s+(?:of\s+(?:its|the)\s+)?components?\s+(?:are\s+|come\s+)?pre[ -]?assembled'
NO_ASSEMBLY=r'\bno assembly(?: required| needed)?\b|assembly required\s*[:=]?\s*(?:no|false)\b|\b(?:fully|pre)[ -]?\s*assembled\b|\b(?:comes|arrives|ships|shipped|delivered)\s+(?:[\w%-]+\s+){0,2}assembled\b|\balready\s+assembled\b'
NEGATED=r"\b(?:not|isn't|is not|doesn't|does not|don't|do not|aren't|are not|never)\s+(?:[\w-]+\s+){0,2}$"
RTA_ASSEMBLY=r'(?<!no )\b(?:self[ -])?assembly required\b|assembly required\s*[:=]?\s*(?:yes|true)\b|\bready[ -]to[ -]assemble\b|\bRTA\b|\b(?:easy|quick) assembly\b|\bself[ -]assembl(?:y|e)\b|\brequires?\s+(?:[\w-]+\s+){0,2}assembly\b|\b(?:easy|simple|quick)\s+to\s+assemble\b|\bhassle[ -]free\s+assembly\b|\bnumbered\s+(?:parts|panels)\b'

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
    
# D7 wording (v12.2). Solid wood incl. "solid hardwood", "solid wooden", "solid-wood".
CAB_SOLID=r'\bsolid[ -](?:hard\s*)?wood(?:en)?\b|\bsolid\s+(?:american\s+)?(?:white\s+|red\s+)?(?:oak|pine|rubber\s*wood|birch|poplar)\b'
CAB_SOLID_FRAME=r'\bsolid[ -](?:hard\s*)?wood(?:en)?\s+frame\b'
# engineered/composite/manufactured wood is the generic class: MDF only when no board type is named.
CAB_GENERIC=r'\b(?:engineered|composite|manufactured)\s+wood\b'
CAB_MDF=r'\bmdf\b|medium[ -]density\s+fib(?:er|re)board|\bdensity\s+board\b|\bfib(?:er|re)\s*board\b'
CAB_WOOD_WORDS=r'(?:mdf|medium[ -]density\s+fib(?:er|re)board|density\s+board|fib(?:er|re)\s*board|(?:engineered|composite|manufactured)\s+wood|plywood|particle\s*-?\s*board|chip\s*board|solid[ -](?:hard\s*)?wood(?:en)?|hard\s*wood|wood|bamboo)'
# Competitor or negated mention, incl. the 2nd item of a list: "than MDF or particle board",
# "we avoid using MDF or particle board", "no MDF or particleboard", "warp like solid wood".
CAB_CMP=(r'(?:\bthan|\bunlike|\bcompar(?:ed|ing)\s+(?:to|with)|\bin\s+comparison\s+(?:to|with)|\binstead\s+of|\bsuperior\s+to|\bvs\.?|\bversus'
         r'|\bavoid(?:s|ing)?(?:\s+using)?|\bnever\s+uses?|\bfree\s+(?:of|from)|\bno|\bnot|\bwithout|\b(?:look|feel|warp|crack|split|swell|sag|peel)s?\s+like)'
         r'(?:\s*(?:[,/&+]|\b(?:or|and|nor|the|a|an|any|other|traditional|standard|ordinary|regular|conventional|common|typical|cheap(?:er)?|low[- ]quality|inferior|flimsy|normal|basic|using|made\s+(?:of|from|with)|cabinets?|vanities|furniture|products?|materials?|boards?|panels?)\b|'+CAB_WOOD_WORDS+r'\b))*\s*$')
# "where particle board warps and sags", "MDF-free".
CAB_CMP_AFTER=r'^(?:[ -]free\b(?![ -]*stand)|\s+(?:that\s+|which\s+)?(?:can\s+|may\s+|will\s+|tends?\s+to\s+|often\s+|easily\s+)?(?:warps?|sags?|swells?|cracks?|peels?|deteriorates?|rots?|crumbles?)(?![\w-]))'
# Up to two words between the material and a part noun, not crossing a list or the cabinet itself.
CAB_PART_GAP=r'\s+(?:(?!(?:and|or|with|for|in|of|plus|frame|cabinet|vanity|body|construction|base)\b)[a-z][\w-]*\s+){0,2}?'
# Solid wood that only describes a part, a surface or a board type (实木颗粒板 / 多层实木板).
CAB_SOLID_PART=r'^'+CAB_PART_GAP+r'(?:legs?|feet|foot|handles?|knobs?|trim|edges?|accents?|pulls?|mirrors?|drawers?|drawer\s+box(?:es)?)\b'
CAB_SOLID_SURFACE=r'^\s+(?:laminate|veneer|grain|look|texture|pattern|effect|print|paper|film)\b'
CAB_SOLID_BOARD=r'^\s+(?:composite\s+)?(?:multi[ -]?layers?\s+)?(?:particle\s*-?\s*board|chip\s*board|plywood)\b'
CAB_MULTILAYER=r'multi[ -]?layers?\s+$'
# Export keys that name another part ("Top Material", "Sink Material", "Handle Material").
CAB_PART_FIELD=r'^(?:top|counter\s*top|countertop|sink|basin|bowl|handle|hardware|knob|pull|leg|feet|mirror|faucet|drain)s?\b'

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
                # "Assembly Required: No" carries its meaning in the key; keep the key in the text for those.
                seen.add((k,v));add('卖家精灵导出.详细参数.'+k,k+': '+v if match(r'assembl',k) else v,exportMonth=x.get('month'),exportFile=x.get('sourceFile'),exportRow=x.get('sourceRow'))
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
    def pattern_candidates(self,patterns,fields=None,skip=None):
        out=[]
        for s in self.sources:
            if fields and not fields(s['field']):continue
            for label,pat in patterns:
                for m in re.finditer(pat,s['text'],re.I):
                    prefix=s['text'][max(0,m.start()-30):m.start()].lower()
                    if re.search(r'\b(?:not|no|without)\s+(?:a\s+)?$',prefix):continue
                    if skip and skip(label,s['text'],m):continue
                    out.append(self.ev(s,label,s['text'][max(0,m.start()-35):min(len(s['text']),m.end()+55)]));break
        return out
    @staticmethod
    def not_form(label,text,m):
        if label!='悬浮式':return False
        return bool(match(FORM_NOT_AFTER,text[m.end():m.end()+30]) or match(FORM_NOT_BEFORE,text[max(0,m.start()-40):m.start()]))
    def structure(self):
        c=self.pattern_candidates([
            ('悬浮式',FLOAT_FORM),
            ('落地式',FLOOR_FORM),
            ('开放式',r'\bconsole\s+(?:vanity|sink|table)\b'),
            ('转角式',CORNER_FORM),
            ('柱状盆',PEDESTAL_FORM)],lambda f:f!='商品尺寸',skip=self.not_form)
        title=' '.join(s['text'] for s in self.sources if s['field'] in ('商品标题','SKU属性'))
        # A vanity sold with its own sink, or a kitchen base cabinet, only uses "pedestal sink" as a keyword (v12.2).
        if match(PEDESTAL_NOT_PRODUCT,title):c=[e for e in c if e['label']!='柱状盆']
        # Title/SKU naming a pedestal sink outranks floating/freestanding words (FORM-PEDESTAL-PRIORITY);
        # a corner vanity is 转角式 even when it is also wall-mounted or freestanding (FORM-CORNER-PRIORITY, user 2026-10-29).
        ped=[e for e in c if e['label']=='柱状盆' and e['sourceField'] in ('商品标题','SKU属性')]
        cor=[e for e in c if e['label']=='转角式' and e['sourceField'] in ('商品标题','SKU属性')]
        store=[]
        if not ped:
            for s in self.sources:
                if s['field']!='商品标题':continue
                m=match(UNDER_SINK_STORAGE,s['text'])
                if m and (match(U_SHAPE,s['text']) or not match(SELLS_VANITY_OR_SINK,s['text'])):store=[self.ev(s,'柱状盆',s['text'][max(0,m.start()-60):m.end()+60])];break
        dual=[]
        if not (ped or store or cor):
            for s in self.sources:
                if s['field'] not in ('商品标题','SKU属性'):continue
                m=match(DUAL_FORM,s['text'])
                if m:dual=[self.ev(s,'两用',s['text'][max(0,m.start()-35):m.end()+35])];break
        self.set(HEADERS[0],ped or store or cor or dual or c)
        if ped:self.evidence[HEADERS[0]].update({'ruleID':'FORM-PEDESTAL-PRIORITY','note':'标题/SKU写明立柱盆，形态统一为柱状盆（用户2026-10-28）'})
        elif store:self.evidence[HEADERS[0]].update({'ruleID':'FORM-PEDESTAL-STORAGE','note':'标题写 under sink 储物柜、不含盆也不是 bathroom vanity，或写 U 形，按立柱盆储物柜算柱状盆（用户2026-10-29）'})
        elif cor:self.evidence[HEADERS[0]].update({'ruleID':'FORM-CORNER-PRIORITY','note':'标题/SKU写明转角柜，形态统一为转角式（用户2026-10-29）'})
        elif dual:self.evidence[HEADERS[0]].update({'ruleID':'FORM-DUAL','note':'标题/SKU写可壁挂也可落地，形态单列两用（用户2026-10-29）'})
        c=[]
        for s in self.sources:
            text=s['text']
            # Negative and partial-assembly wording must be read before bare assembly.
            if match(PARTIAL_ASSEMBLY,text):
                c.append(self.ev(s,'部分预装',text[:350]));continue
            no=match(NO_ASSEMBLY,text)
            # "not pre-assembled" is a ready-to-assemble statement.
            if no and match(NEGATED,text[max(0,no.start()-30):no.start()]):
                c.append(self.ev(s,'拆装',text[max(0,no.start()-40):no.end()+60]));continue
            yes=match(RTA_ASSEMBLY,text)
            if no:c.append(self.ev(s,'整装',text[max(0,no.start()-25):no.end()+60]))
            elif yes:c.append(self.ev(s,'拆装',text[max(0,yes.start()-25):yes.end()+60]))
        self.set(HEADERS[1],c)
        c=[];vanity_terms=[]
        for s in self.sources:
            t=s['text']
            no=match(r'\b(?:without|no) (?:a )?(?:sink|basin)\b|\b(?:sink|basin) (?:is )?(?:not included|sold separately)\b|\b(?:cabinet|vanity base) only\b',t)
            # "top with double sinks (not included)"; not "faucet suitable for the sink (not included)".
            if not no:no=match(r'(?<!for the )(?<!for your )(?<!for a )\b(?:sinks?|basins?)\s*\(\s*not\s+included\s*\)|\b(?:sinks|basins)\s+(?:are\s+)?(?:not included|sold separately)\b',t)
            if not no and s['field'] in ('商品标题','SKU属性') and not match(SINK_PRESENT,t):no=match(NO_SINK_TITLE,t)
            # Explicit count words only; adjectives such as "vessel"/"boat" may sit between.
            adj=r'(?:(?:oval|round|rectangular|rectangle|square|white|black|gr[ae]y|ceramic|porcelain|resin|smc|stone|marble|glass|undermount|undercounter|vessel|boat|integrated|drop[ -]in)\s+){0,3}'
            # Plural nouns after a count may carry free modifiers ("Two Bathroom Frosted Glass
            # Vessel Sinks", "2 Faceted Ceramic Basins"), but not doors/drawers/options lists.
            free=r'(?:(?!(?:doors?|drawers?|shel(?:f|ves)|cabinets?|faucets?|handles?|holes?|tiers?|tone|towels?|vanit(?:y|ies)|types?|kinds?|styles?|options?|colou?rs?|sizes?|materials?|choices?|different|sets?|with|for|or|of)\b)[\w-]+[ -]+){0,5}?'
            # "Size: ... Dual/Double/Single" is SKU wording; in bullets "Sink Size:" would reach any later word.
            # "Size: 48" Single Cabinet" names the cabinet, not the sink count.
            sku_size=s['field']=='SKU属性'
            double=match(r'\b(?:double|dual|two|2)[ -]+'+adj+r'(?:sink|basin|bowl)s?\b|\b(?:double|dual|two|2)[ -]+'+free+r'(?:sinks|basins|bowls)\b',t) or (sku_size and match(r'\bsize\s*:[^|]*\b(?:dual|double)\b(?!\s+(?:cabinet|door|drawer))',t))
            single=match(r'\b(?:single|one|1)[ -]+'+adj+r'(?:sink|basin|bowl)\b',t) or (sku_size and match(r'\bsize\s*:[^|]*\bsingle\b(?!\s+(?:cabinet|door|drawer))',t))
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
        # Child SKU basin count is more specific than broad title variants,
        # but an explicit child "no sink" outranks a SKU count word.
        sku=[e for e in c if e['sourceField']=='SKU属性']
        nosink=[e for e in c if e['label']=='无盆' and e['sourceScope']=='child']
        overridden=bool(nosink and any(e['label']!='无盆' for e in sku))
        if overridden:
            self.notes.append('D3：子体文本明确不含盆，优先于SKU盆数写法');sku=nosink
        if sku:
            for e in c:
                if e['sourceScope']=='child' and e['label']!=sku[0]['label'] and not (overridden and e['sourceField']=='SKU属性'):self.conflicts.append('D3盆数：SKU与其他文本不一致')
            self.set(HEADERS[2],sku)
        else:self.set(HEADERS[2],c or [e for e in vanity_terms if len({x['label'] for x in vanity_terms})==1])
        if self.tags[HEADERS[2]]=='无盆':
            self.tags[HEADERS[3]]='无盆';self.evidence[HEADERS[3]]={'status':'derived','basis':HEADERS[2]}
        else:
            c=self.pattern_candidates([
                ('台上盆',VESSEL),
                # Drawer "under-mount slides" are hardware, not a sink position.
                ('台下盆',r'\bunder[ -]?(?:mount|counter)(?:ed)?\b(?!\s+(?:(?:soft[ -]close|full[ -]extension|drawer|hidden|concealed)\s+)*(?:slides?|rails?|glides?|runners?|tracks?)\b)'),
                ('台上盆',ONE_PIECE),
                # User 2026-10-29: 台盆位置只有无盆 / 台上盆 / 台下盆三种；drop-in 盆沿压在台面上，归台上盆。
                ('台上盆',r'\bdrop[ -]?in\s+(?:\w+\s+){0,3}?(?:sinks?|basins?)\b|\btop[ -]?mount(?:ed)?\s+(?:\w+\s+){0,3}?(?:sinks?|basins?)\b')])
            # Images (2026-10-29): budget combos call one-piece sink-tops "undermount";
            # a one-piece/sink-top statement in the same scope wins over that word.
            for scope in ('child','parent'):
                up=[e for e in c if e['sourceScope']==scope and e['label']=='台上盆' and match(ONE_PIECE+r'|(?<!vanity )\b(?:sinks?|basins?)\s+tops?\b',e['quote'])]
                if up and any(e['sourceScope']==scope and e['label']=='台下盆' for e in c):
                    c=[e for e in c if not (e['sourceScope']==scope and e['label']=='台下盆')]
                    self.notes.append('D4：一体盆/台上盆写法与undermount并存，按台上盆')
            self.set(HEADERS[3],c)
        # v12.2: plural/variant spellings (Barn Doors, barn-style doors, glassed doors, louvre);
        # export keys "Door & hardware" / "Door & drawer features" also carry door style.
        elem_fields=lambda f:f in ('商品标题','SKU属性','五点描述','卖家精灵导出.亮点') or any(k in f.lower() for k in ('style','door'))
        # "farmhouse" listed among decor styles it matches ("match with contemporary, farmhouse,
        # Scandinavian ... styles") describes the room, not this cabinet.
        self.set(HEADERS[4],self.pattern_candidates([
            ('Fluted',r'\bfluted\b'),('Reeded',r'\breeded\b'),('Shaker',r'\bshaker\b|\brecessed panel\b'),
            ('Barn Door',r'\bbarn[ -]?(?:style\s+)?doors?\b'),('Farmhouse',FARMHOUSE_VISIBLE),
            ('Slatted',r'\bslatted\b|\blouv(?:er|re)(?:ed|d)?\b'),('Glass Door',r'\b(?:glass(?:ed)?|glazed)\s+(?:cabinet\s+)?doors?\b'),
            ('Rattan',r'\b(?:rattan|wicker|cane)\b')],elem_fields,skip=lambda label,t,m:label=='Farmhouse' and self.style_list(t,m.start(),m.end())),multi=True,default='待图片核验')


    @staticmethod
    def style_list(text,a,b):
        """True when text[a:b] sits in a list of decor styles the product is said to match."""
        sep=r'\s*(?:,|/|\bor\b|\band\b)\s*'
        listed=re.search(STYLE_WORDS+sep+r'(?:and\s+|or\s+)?(?:even\s+)?$',text[max(0,a-70):a],re.I) or re.search(r'^'+sep+r'(?:and\s+|or\s+)?(?:even\s+)?'+STYLE_WORDS,text[b:b+50],re.I)
        cue=re.search(r'\b(?:match(?:es|ing)?|complement(?:s|ing)?|suit(?:s|able)?|fits?|blend(?:s|ing)?|perfect\s+for|ideal\s+for|such\s+as|any|various|d[ée]cors?|styles)\b',text[max(0,a-90):b+70],re.I)
        return bool(listed and cue)

    def colors(self):
        # v12.2: "White Oak" is a wood species (原木色), not a white+oak combination.
        patterns=[('原木色',r'white[ -]oak'),('灰绿色',r'gray[ -]green|grey[ -]green'),('灰蓝色',r'blue[ -]gr[ae]y|gr[ae]y[ -]blue'),('藏青色',r'navy(?: blue)?'),('胡桃木色',r'(?:dark )?walnut'),('深咖啡色',r'espresso|dark brown|coffee'),('白色',r'(?:milky |off[ -]|matte |pure )?white|cream|ivory'),('黑色',r'(?:matte |jet )?black|tuxedo'),('灰色',r'gr[ae]y|driftwood'),('原木色',r'natur(?:al|e)(?: oak| wood)?|(?:light )?oak|wood color'),('米色',r'beige'),('棕色',r'brown'),('蓝色',r'blue'),('绿色',r'green|sage|mint|eucalyptus'),('粉色',r'pink|blush|rose pink'),('黄色',r'yellow|mustard'),('红色',r'red|burgundy|coral|rust red')]
        def found(t):
            hits=[]
            occupied=[]
            for label,pat in patterns:
                for m in re.finditer(r'(?<![a-z])(?:'+pat+r')(?![a-z])',t,re.I):
                    if any(m.start()<b and a<m.end() for a,b in occupied):continue
                    occupied.append(m.span());hits.append((m.start(),m.end(),label))
            return sorted(hits)
        def bound(t,b):
            # Colour directly naming a sink/top/hardware part ("White Resin Sink", "Matte Black
            # Faucet"); "White Single Sink Vanity" and "Bathroom Sink Cabinet" name the cabinet.
            after=t[b:b+70]
            if match(r'^[ -]+(?:single|double|dual|two|one)[ -]+(?:sinks?|basins?)\b',after):return False
            return bool(match(r'^(?:\s+(?!(?:with|and|or|for|in|w)\b)[\w.\'"″]+(?:-[\w.\'"″]+)*){0,3}?\s+(?:sinks?|basins?|bowls?|vessel|counter\s*tops?|tops?|faucets?|handles?|knobs?|pulls?|hardware|backsplash|quartz|granite|stone)\b(?!\s+(?:cabinet|vanit|base))',after))
        def cab_colors(value):
            # 'Walnut / White Sink', 'Natural Oak W/ Black Sink', 'Vanity With Blue Boat Glass Sink':
            # colours in the part that names the sink/top/hardware are not the cabinet's.
            parts=[p for p in re.split(r'\bw/o\s*|\s*/\s*|\bw/\s*|\s+(?:with(?:out)?|no)\s+|\s*[()]\s*|\s*\+\s*|\s+&\s+|\s*-\s+|,\s*',value,flags=re.I) if p.strip()]
            cab=[p for p in parts if not match(COLOR_COMPONENT,p)]
            return uniq(h[2] for p in cab for h in found(p)),[p for p in parts if match(COLOR_COMPONENT,p) and found(p)]
        same=lambda a,b:a==b or COLOR_FAMILY.get(a,a)==COLOR_FAMILY.get(b,b)
        candidates=[];sku_values=[]
        for s in self.sources:
            if s['field']!='SKU属性':continue
            m=match(r'colou?r\s*:\s*([^|]+)',s['text'])
            if m:
                sku_values,comp=cab_colors(m.group(1))
                if comp:self.notes.append('D6：SKU颜色“%s”写的是盆/台面/五金，不作柜体色'%m.group(1).strip())
                if len(sku_values)==1:candidates.append(self.ev(s,sku_values[0],m.group(0),'SKU明确颜色'))
                elif len(sku_values)>1:self.notes.append('SKU含组合色；先区分柜体/盆/五金，不按词序取色')
            sz=match(r'size\s*:\s*([^|]+)',s['text'])
            if sz and not candidates:
                # UEV/eclife put the cabinet colour in Size ('Size: 24" Black') and the sink in Color.
                hh=uniq(h[2] for h in found(sz.group(1)) if not bound(sz.group(1),h[1]))
                if len(hh)==1 and (not sku_values or hh[0] in sku_values):candidates.append(self.ev(s,hh[0],sz.group(0),'SKU尺寸字段柜体颜色'))
        explicit=[]
        for s in self.sources:
            if s['field']=='SKU属性':continue
            t=s['text'];hits=found(t)
            for k,(a,b,label) in enumerate(hits):
                if bound(t,b):continue
                # Two-tone or compound names ("Black and Natural Mixed", "Natural Brown"):
                # one word of the pair is not the cabinet colour.
                pair=[h for h in (hits[k-1] if k else None,hits[k+1] if k+1<len(hits) else None) if h and match(r'^\s*(?:&|and|/|\+)\s*$',t[min(b,h[1]):max(a,h[0])]) and not same(h[2],label)]
                if pair:continue
                nxt=hits[k+1][0]-b if k+1<len(hits) else 999
                tail=re.sub(r'\d+(?:\.\d+)?'+INCH,' N',t[b:b+80]);before=t[max(0,a-45):a]
                # Cabinet noun after ≤4 modifiers ("White Small Vanity", "Grey Wall Mounted Modern
                # Vanity", "Espresso 42 in Bathroom Sink Cabinet"), "cabinet is/in/of <colour>",
                # "Vanity Set in White Finish". "cabinet with <colour> ..." is another part.
                noun=match(r'^(?:[ -]+(?!(?:with|and|or|for|in|w)\b)[\w.\'"″-]+){0,4}?[ -]+(?:cabinet|vanity base|vanit(?:y|ies))(?![ -]+(?:sink|top)\b)\b',tail)
                # Another colour word before the noun owns it ("Natural Brown Vanity" -> Brown).
                # "... in Oak White" is a two-tone name; word order does not pick the cabinet colour.
                lead=not match(r'^\s*$',t[b:b+nxt]) if nxt<999 else True
                if (noun and nxt>=noun.end()) or lead and (match(r'\b(?:cabinet|cabinet finish|cabinet colou?r|cabinet body)\s*(?:is|in|:|of)?\s*$',before) or match(r'\b(?:vanit(?:y|ies)(?:\s+(?:set|base|cabinet))?|cabinets?)\s+in\s+$',before)):
                    explicit.append(self.ev(s,label,t[max(0,a-35):b+70],'明确柜体颜色上下文'))
            if s['field']=='商品标题':
                tail=match(r'(?:,|\(|\bin)\s*([^,()]{1,35})\)?\s*$',t)
                if tail:
                    hh=found(tail.group(1))
                    # ", White Sink Top with 3 Holes" / ", Red&Black Boat Glass Sink" describe the sink.
                    if len(uniq(h[2] for h in hh))==1 and not any(bound(tail.group(1),h[1]) for h in hh) and not match(r'\b(?:sinks?|basins?|bowls?|boat|vessel)\b',tail.group(1)):explicit.append(self.ev(s,hh[0][2],tail.group(0),'标题末尾颜色，需与SKU核对'))
            if s['field'].lower().endswith('.color') or s['field'].lower().endswith('.colour'):
                hh,_=cab_colors(t)
                if len(hh)==1:explicit.append(self.ev(s,hh[0],t,'ASIN匹配详情颜色'))
        # A title-end finish word ("..., Matte Black") is usually the hardware once the SKU or
        # the title names the cabinet colour elsewhere.
        ctx=[e for e in explicit if e['sourceScope']=='child' and e['method']=='明确柜体颜色上下文']
        finish=lambda e:e['method']=='标题末尾颜色，需与SKU核对' and match(r'^\W*(?:in\s+)?(?:matte|brushed|satin|polished)\s',e['quote'])
        if candidates:
            for e in explicit:
                if e['sourceScope']=='child' and not same(e['label'],candidates[0]['label']) and not finish(e):self.conflicts.append('D6柜体颜色：SKU与标题/参数柜体颜色不一致')
            self.set(HEADERS[5],candidates)
        else:
            if len(sku_values)>1:explicit=[e for e in explicit if e['label'] in sku_values or e['sourceScope']=='parent']
            # Cabinet context > title end > export Color (a later snapshot); weaker child
            # sources that disagree stay out of the selection.
            rank={'明确柜体颜色上下文':0,'标题末尾颜色，需与SKU核对':1,'ASIN匹配详情颜色':2}
            child=[e for e in explicit if e['sourceScope']=='child' and not (finish(e) and ctx)]
            if child:
                best=min(rank[e['method']] for e in child)
                explicit=[e for e in child if rank[e['method']]==best]
                if all(same(e['label'],explicit[0]['label']) for e in explicit):explicit=[e for e in explicit if e['label']==explicit[0]['label']]
            self.set(HEADERS[5],explicit)
            if len(sku_values)>1 and self.tags[HEADERS[5]]==UNKNOWN:self.notes.append('D6组合色未取得明确柜体归属')

    def materials(self):
        pats=[('MDF',CAB_MDF),('工程木材（未细分）',CAB_GENERIC),('胶合板',r'\bplywood\b'),('刨花板',r'\bparticle\s*-?\s*board\b|\bchip\s*board\b'),('实木',CAB_SOLID),('人造大理石',r'\b(?:cultured|engineered|synthetic)\s+marble\b'),('人造石（未细分）',r'\bengineered\s+stone\b'),('石英石',r'\b(?:engineered\s+)?quartz(?:\s+stone)?\b'),('岩板',r'\bsintered\s+stone\b'),('大理石（天然性未核实）',r'\bmarble\b'),('陶瓷',r'\bceramic\b|\bporcelain\b'),('树脂',r'\bresin\b'),('亚克力',r'\bacrylic\b'),('SMC',r'\bsmc\b|sheet\s+moulding\s+compound|sheet\s+molding\s+compound'),('花岗岩',r'\bgranite\b'),('玻璃',r'\b(?:tempered\s+)?glass\b'),('不锈钢',r'\bstainless\s+steel\b'),('竹材',r'\bbamboo\b')]
        wood={'MDF','胶合板','刨花板','实木','工程木材（未细分）','竹材'}
        roles={'cabinet':r'\bcabinet(?:ry)?\b|\bvanity\s+(?:base|body|frame)\b|\bwood\s+frame\b|\bdoors?\b','top':r'\bcounter\s*top\b|\bvanity\s+top\b|\btable\s*top\b','sink':r'\bsinks?\b|\bbasins?\b|\bbowls?\b','hardware':r'\bhinges?\b|\bhandles?\b|\bfaucets?\b|\bdrains?\b|\bknobs?\b'}
        buckets={k:[] for k in ('cabinet','top','sink')}
        for s in self.sources:
            if s['field'] in ('SKU属性','商品尺寸'):continue
            if s['field'].startswith('卖家精灵导出.详细参数.') and match(CAB_PART_FIELD,s['field'].split('.',2)[2]):continue
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
                        if label in wood and (match(CAB_CMP,clause[max(0,m.start()-80):m.start()]) or match(CAB_CMP_AFTER,clause[m.end():])):
                            self.notes.append('D7：对比/否定句中的材料不计入柜体');continue
                        # "solid wood legs / feet / handles / drawers" describe a part, not the cabinet.
                        if label=='实木' and match(CAB_SOLID_PART,clause[m.end():]):
                            self.notes.append('D7：solid wood仅指腿/脚/把手/抽屉等部件，不作柜体材质');continue
                        if label=='实木' and (match(CAB_SOLID_SURFACE,clause[m.end():]) or match(CAB_SOLID_BOARD,clause[m.end():])):continue
                        hits.append((m.start(),m.end(),'胶合板' if label=='实木' and match(CAB_MULTILAYER,clause[max(0,m.start()-15):m.start()]) else label))
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
                        local_top=match(re.escape(clause[a:b])+CAB_PART_GAP+r'(?:vanity\s+)?(?:counter\s*tops?|tops?|table\s*tops?)\b',clause)
                        if local_top:role='top'
                        elif role in ('top','sink','hardware'):role=None
                    if not role and label in wood:
                        if 'material' in s['field'].lower() or match(r'vanit(?:y|ies)|cabinet',s['text']):role='cabinet'
                    if role=='hardware':continue
                    if role=='cabinet' and label not in wood:
                        # A generic ceramic/resin/metal mention near a cabinet noun
                        # is insufficient to assert the cabinet's construction.
                        if not match(r'(?:cabinet|body|frame).{0,18}(?:made|constructed|crafted).{0,10}'+re.escape(clause[a:b]),clause) and not match(re.escape(clause[a:b])+r'\s+cabinet\b(?!\s+(?:doors?|drawers?|handles?|knobs?|pulls?|legs?|feet|panels?)\b)',clause):continue
                    if role in buckets:
                        lab=label
                        if label=='实木' and match(CAB_SOLID_FRAME,clause):lab='实木框架（其余未说明）'
                        if label=='大理石（天然性未核实）' and match(r'\bnatural\s+marble\b',clause):lab='天然大理石'
                        buckets[role].append(self.ev(s,lab,clause[max(0,a-65):min(len(clause),b+90)],'部件绑定文本'))
        def reduced(es):
            direct=[e for e in es if e['sourceScope']=='child'];selected=direct or es
            labels={e['label'] for e in selected}
            if labels & {'MDF','胶合板','刨花板'}:selected=[e for e in selected if e['label']!='工程木材（未细分）']
            # User 2026-10-27: engineered/composite wood alone is MDF.
            return [dict(e,label='MDF') if e['label']=='工程木材（未细分）' else e for e in selected]
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
        # "countertop sink(s)" is a sink (vessel or one-piece), "vanity sink top(s)" a top product.
        rolepat=r'\b(?P<sink2>counter\s*-?tops?\s+(?:vessel\s+)?(?:sinks?|basins?))\b|\b(?P<top>vanity\s+sink\s+tops?|counter\s*-?tops?|vanity\s+tops?|table\s*tops?|tops?)\b|\b(?P<sink>sinks?|basins?|bowls?)\b|\b(?P<other>cabinets?|doors?|frames?|faucets?|handles?|drains?|hinges?)\b'
        explicit=('石英石','岩板','Cultured Marble','SMC','亚克力','树脂','陶瓷')
        marble_branch=('engineered marble','marble','Carrara / Calacatta')
        buckets={'top':[],'sink':[]}
        all_evidence=[]
        for source in self.sources:
            if source['field']=='商品尺寸':continue
            # Bracketed bullet heading is a mixed-material list, not a component assertion.
            text=re.sub(r'[【\[][^】\]]*(?:&| and )[^】\]]*[】\]]',' ',source['text'],flags=re.I)
            # SKU "Key: value | Key: value" items are separate clauses.
            for clause in re.split(r'(?<=[;!?])\s+|(?<=\.)\s+(?=[A-Z])|\s*\|\|\s*|\s+\|\s+|,\s*',text):
                hits=[];occupied=[]
                for raw,pat in pats:
                    for m in re.finditer(pat,clause,re.I):
                        if any(m.start()<b and a<m.end() for a,b in occupied):continue
                        occupied.append(m.span());hits.append((m.start(),m.end(),raw,m.group()))
                hits.sort()
                anchors=[]
                for m in re.finditer(rolepat,clause,re.I):
                    if m.group('sink') and match(r'^\s*(?:shape|style)\b',clause[m.end():]):continue
                    role='top' if m.group('top') else 'sink' if (m.group('sink') or m.group('sink2')) else 'other'
                    # "Bathroom Sink Vanity" names the vanity; "Ceramic Sink Vanity" still names the sink material.
                    if role=='sink' and match(r'^\s+(?:cabinet|vanity)\b',clause[m.end():]) and not any(d<=m.start() and not clause[d:m.start()].strip() for c,d,lab,o in hits):role='other'
                    anchors.append((m.start(),m.end(),role))
                for a,b,raw,original in hits:
                    prefix=clause[max(0,a-40):a]
                    # Negation and comparison ("lighter than ceramic sinks", "compared to traditional ceramic").
                    if match(r'\b(?:not(?: made of)?|without|no|unlike|instead\s+of|than|compared\s+(?:to|with)|versus|vs\.?|replac(?:e|es|ing))\s+(?:(?:the|traditional|ordinary|conventional|regular|common|standard|typical|other|cheap|fragile|heavy|easily|breakable)\s+){0,3}$|\b(?:not(?: made of)?|without|no)\s*$',prefix):continue
                    if raw in marble_branch and match(r'\b(?:faux|imitation|fake|simulated)[ -]+$',clause[max(0,a-15):a]):continue
                    # "glass or ceramic countertop sinks" lists options, not this product's material.
                    if any(d<=a and match(r'^\s*(?:or|and/or|/)\s*$',clause[d:a]) for c,d,lab,o in hits):continue
                    if raw=='marble' and match(r'^\s*[- ]?(?:look|pattern(?:ed)?|textured?|grain|like|effect|finish|print(?:ed)?|veneer|laminate|design)\b',clause[b:]):continue
                    if raw in ('木板','stone') and role_hint_sink(clause,b):continue
                    # Carrara/Calacatta next to an explicit non-marble material is a design name.
                    if raw=='Carrara / Calacatta' and any(c>=b and c-b<32 and lab not in ('Carrara / Calacatta','marble','engineered marble') for c,d,lab,o in hits):continue
                    forward=[x for x in anchors if x[0]>=b]
                    backward=[x for x in anchors if x[1]<=a]
                    role=None
                    if forward:
                        x,y,r=forward[0];gap=clause[b:x]
                        # "Sintered Stone Artificial Marble ... Top": a marble-branch name right after an
                        # explicit material is a pattern name, not another component material.
                        end=b
                        if raw in explicit:
                            for c,d,lab,o in hits:
                                if c>=end and lab in marble_branch and not clause[end:c].strip(' -'):end=d
                        othermaterial=any(c>=end and d<=x for c,d,lab,o in hits)
                        # A material before its component noun, without crossing another part.
                        if r!='other' and len(gap)<=55 and not othermaterial and not match(r'[:;&]|\b(?:and|with|for|includes?|features?)\b',clause[end:x]):role=r
                    if role is None and backward:
                        x,y,r=backward[-1];gap=clause[y:a]
                        # A noun followed by an explicit material predicate or field value; up to three
                        # describing words may follow ("is crafted from high-hardness SMC",
                        # "sink with overflow is made of engineered stone").
                        if r!='other' and len(gap)<=65 and match(r'^\s*(?:with\s+\w+\s+)?(?:(?:material|construction)\s*[:=]?|(?:(?:is|are)\s+)?(?:made|constructed|crafted|manufactured|molded|moulded|formed)(?:\s+from|\s+of|\s+with)?|[:=])\s*(?:an?\s+|the\s+)?(?:[\w-]+\s+){0,3}$',gap) and not any(c>=y and d<=a for c,d,lab,o in hits):role=r
                    if role is None:
                        field=source['field'].lower()
                        if match(r'(?:countertop|top)[ _-]*material',field) and not anchors:role='top'
                        elif match(r'(?:sink|basin)[ _-]*material',field) and not anchors:role='sink'
                        # SKU "Style: Carrara Quartz" / "Pattern Name: White Marble" names the top.
                        # A bare "Style: Black Marble" may be a basin pattern: plain marble needs a top cue.
                        elif source['field']=='SKU属性' and not anchors and raw in ('石英石','岩板','Cultured Marble','engineered marble','engineered stone','marble','Carrara / Calacatta','花岗岩') and match(r'^\s*(?:style|pattern\s+name|top|counter\s*top)\s*:',clause) and (raw!='marble' or match(r'\bcarrara|\bcalacatta|\bitalian|\d(?:\.\d+)?\s*(?:"|”|inch|in\b)',clause)):role='top'
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
        # User 2026-10-24 rule 6: an explicit Quartz/Sintered Stone/resin/Cultured Marble top makes
        # a Carrara/marble name in the same source text a pattern name, not a second material.
        for src_key in {(e['sourceField'],e['sourceASIN']) for e in buckets['top'] if e.get('materialSubtype') in ('石英石','岩板','Cultured Marble','SMC','亚克力','树脂')}:
            buckets['top']=[e for e in buckets['top'] if not ((e['sourceField'],e['sourceASIN'])==src_key and e.get('materialSubtype') in marble_branch)]
        # "Boat Marble Sink" next to "Boat Marble Ceramic Sink": with an explicit child sink material,
        # a marble name on the sink is a pattern name.
        if any(e['sourceScope']=='child' and e.get('materialSubtype') in ('陶瓷','玻璃','SMC','亚克力','树脂','Cultured Marble') for e in buckets['sink']):
            buckets['sink']=[e for e in buckets['sink'] if e.get('materialSubtype') not in marble_branch]
        for role,key in keys.items():
            es=buckets[role]
            self.set(key,es)
            ev=self.evidence[key]
            if ev['status']=='text_supported' and any(e.get('basisType')=='business_mapping' for e in ev.get('selected',[])):ev['status']='business_mapping'
        # User 2026-10-27: "marble texture/look top" with no real stone word in the
        # child's own text is a wood (board) top.
        if self.tags[HEADERS[7]]==UNKNOWN:
            child_text=' || '.join(x['text'] for x in self.sources if x['scope']=='child' and x['field'] not in ('商品尺寸',))
            # "Faux Marble Top" is the faux wording itself, not a stone word.
            stone=match(r'\b(?:quartz|sintered|granite|stone|cultured|engineered\s+marble|(?<!faux )(?<!fake )(?<!imitation )(?<!simulated )marble\s+(?:counter\s*top|top)|calacatta|carrara)\b',child_text)
            faux=[]
            for x in self.sources:
                if x['scope']!='child':continue
                m=match(r'\b(?:faux|fake|imitation|simulated)[ -]+marble(?:[ -]+\w+){0,2}?\s+(?:counter\s*tops?|table\s*tops?|tops?)\b|\b(?:faux[ -]?)?marble[ -]?(?:textured?|look|pattern(?:ed)?|grain|like|effect|finish|print(?:ed)?|veneer|laminate)(?:[ -]+\w+){0,2}?\s+(?:counter\s*tops?|table\s*tops?|tops?)\b',x['text'])
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
                if subtype not in ('Cultured Marble','SMC','亚克力','树脂','陶瓷'):continue
                # Ceramic only top->sink here; sink->top stays with M-SINK-TOP-ONEPIECE below.
                if subtype=='陶瓷' and role!='sink':continue
                src=next((s for s in self.sources if s['field']==ev['sourceField'] and s['asin']==ev['sourceASIN']),None)
                if not src:continue
                mold=match(r'one[ -]piece.{0,70}(?:sink|basin|bowl|countertop)|(?:sink|basin|countertop).{0,70}one[ -]piece|(?:molded|moulded|cast).{0,50}(?:integral|integrated).{0,30}(?:sink|basin|bowl)|(?:sink|basin).{0,35}(?:same material|seamless one[ -]piece)',src['text'])
                # User 2026-10-27 (R1/R2/R6) accepts integrated sink wording as one-piece for sink->top;
                # the same wording now also gives top->sink.
                if not mold and role=='sink':mold=match(ONE_PIECE,src['text'])
                if not mold:continue
                label={'Cultured Marble':'Cultured Marble','陶瓷':'陶瓷'}.get(subtype,'树脂')+('盆' if role=='sink' else '')
                candidates.append(self.ev(src,label,mold.group(),'同材一体结构推导',{'basisType':'business_inference','basisField':otherkey,'basisMaterialEvidence':ev,'ruleID':'M-SAME-PIECE'}))
            if candidates:
                self.set(key,candidates)
                if self.evidence[key]['status']=='text_supported':self.evidence[key]['status']='business_inference'
        # User 2026-10-27 (R1/R2/R6): a one-piece sink-top is the sink's material.
        # A child one-piece statement also replaces a parent-filled top (parent bullets may
        # describe another variant). Vessel/boat/glass "sink top" is a bowl on a top, not one piece.
        top_parent=self.evidence[HEADERS[7]].get('status') in ('parent_fill','parent_candidate')
        if (self.tags[HEADERS[7]]==UNKNOWN or top_parent) and self.tags[HEADERS[8]] not in (UNKNOWN,'不适用（不含盆）'):
            sink_ev=self.evidence[HEADERS[8]].get('selected') or []
            base=next((e for e in sink_ev if e.get('materialSubtype') and e.get('materialSubtype')!='玻璃'),None)
            child_text=' || '.join(x['text'] for x in self.sources if x['scope']=='child' and x['field']!='商品尺寸')
            vessel=match(r'\bvessel\b|\bboat\s+(?:\w+\s+){0,2}?(?:sinks?|basins?)\b|\babove[ -]counter\b',child_text)
            onepiece=None
            for x in self.sources:
                if x['field']=='商品尺寸':continue
                # "<ceramic/resin> sink top" and "ceramic countertop sink" count only when the child
                # text has no vessel/boat wording; explicit integrated/one-piece wording always counts.
                m=match(r'\b(?:sink|basin)\s+(?:and|&|/)\s+(?:counter\s*)?top\s+(?:in\s+)?one\b|\bseamless(?:ly)?\s+(?:\w+\s+){0,3}?(?:sink|basin)\s+(?:and|&)\s+(?:counter\s*)?top\b|'+ONE_PIECE,x['text'])
                if not m and not vessel:m=match(r'\b(?:ceramic|porcelain|vitreous\s+china|resin|smc|acrylic|cultured\s+marble)\s+(?:(?!vessel|boat)\w+\s+){0,3}?(?:sink|basin)s?\s+tops?\b|\b(?:ceramic|porcelain|resin|smc|acrylic)\s+counter\s*-?top\s+(?:sink|basin)\b(?!s)',x['text'])
                if m:onepiece=(x,m);break
            if top_parent and not (onepiece and onepiece[0]['scope']=='child' and base and base['sourceScope']=='child'):onepiece=None;base=None
            if base and onepiece:
                src,m=onepiece
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
                # "Undermount Single Sink Bathroom Vanity", "Right Rectangular Sink" also state a basin.
                m=match(r'\bwith\s+(?:(?:an?|single|double|white|black|integrated|undermount|vessel|ceramic|porcelain|resin)\s+){0,5}(?:sink|basin)\b|\b(?:sink|basin)\s+(?:is\s+)?included\b|\b(?:single|double|dual|two|undermount(?:ed)?|under[ -]mount|undercounter|rectangular|rectangle|oval|round|square|center|left|right|offset)\s+(?:\w+\s+){0,2}?(?:sinks?|basins?)\b(?!\s+(?:is\s+|are\s+)?(?:not included|sold separately))',src['text'])
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
        dims={a:[] for a in ('W','D','H')};self.weak_dh=set()
        # v12.2: basin / drawer / package / mirror sizes are parts, not the cabinet.
        part_dim=lambda t,a:bool(match(r'(?<!with )\b(?:basin|sink|bowl|drawers?|mirror|package|box|carton|shel(?:f|ves)|opening|interior|faucet)s?\s*(?:size|dimensions?|measures?)?\s*[:：]\s*[^:|;]*$',t[max(0,a-60):a]) or match(r'^[^|;]{0,40}?\bper\s+package\b',t[a:a+60]))
        for s in self.sources:
            if s['scope']!='child':continue
            if s['field'] not in ('SKU属性','商品标题','商品尺寸') and not any(x in s['field'].lower() for x in ('dimension','size')):continue
            if any(x in s['field'].lower() for x in ('package','drawer','basin','sink','mirror','shelf')):continue
            t=s['text'];cm=bool(match(r'\bcm\b',t)) and not match(r'inch|\bin\b|["″]',t)
            factor=1/2.54 if cm else 1
            for m in re.finditer(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(["″”]|\'\'|’’|inches|inch|\bin\b|cm)?\s*([WDH])(?=\s|[x×,;)]|$)',t,re.I):
                v=float(m.group(1))*factor;axis=m.group(3).upper()
                if part_dim(t,m.start()):continue
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
                    mm=match(r'^\s*(\d{1,3}(?:\.\d+)?)(?:'+INCH+r'|\s*cm\b)(?!\s*(?:deep|depth))',size)
                    wd=match(r'^\s*(\d{2}(?:\.\d+)?)\s*[x×*]\s*(\d{2}(?:\.\d+)?)\b(?!\s*[x×*])',size)
                    if mm:
                        v=float(mm.group(1))*factor
                        if 5<v<150:dims['W'].insert(0,(v,s,self.ev(s,v,m.group(0),'SKU名义宽度')))
                    elif wd and 12<=float(wd.group(2))<=30:
                        # Design House 'Size: 36 x 21' is width x depth.
                        v=float(wd.group(1))
                        if 5<v<150:dims['W'].insert(0,(v,s,self.ev(s,v,m.group(0),'SKU尺寸W×D取首值')))
                    elif match(r'^\s*\d{1,3}(?:\.\d+)?\s*$',size):
                        v=float(size)
                        # Bare SKU size is only usable when the child title
                        # independently spells out the same vanity width.
                        title=clean(self.row.get('商品标题'))
                        if 5<v<150 and match(r'(?<![\d.])'+re.escape(str(int(v)) if v.is_integer() else str(v))+INCH+r'\s*(?:wide\s+)?(?:[a-z &()/-]{0,50}?)'+VANITY_NOUN,title):
                            dims['W'].insert(0,(v,s,self.ev(s,v,m.group(0),'SKU裸尺寸与子体标题同值相互支持')))
                if not any(x[1] is s for x in dims['W']):
                    # Width written in another SKU attribute ('Style: 30" Rustic', 'Color: Grey 36inch').
                    for part in t.split('|'):
                        k,_,val=part.partition(':')
                        if match(r'size|pattern name',k):continue
                        mm=match(r'(?<![\d.])(?<![x×*])(?<![x×*]\s)(\d{2}(?:\.\d+)?)'+INCH+r'(?![ -]*(?:edge|thick|holes?|faucets?|drawers?|deep|depth|height|tall|[DH]\b|[x×*]))',val)
                        if mm and 12<=float(mm.group(1))<=96:
                            v=float(mm.group(1));dims['W'].append((v,s,self.ev(s,v,part.strip(),'SKU其他属性写明宽度')));break
            if s['field']=='商品标题':
                tw=[]
                # 'for 25-in. x 19-in. Vanity Top' / 'fits 36" vanity' name another product's size.
                for_ctx=lambda a:match(r'\b(?:for|fits?|compatible\s+with|accommodates?)\s+(?:an?\s+|the\s+|most\s+)?$',t[max(0,a-25):a])
                for mm in re.finditer(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)'+INCH+r'\s*(?:wide\s+)?(?:[a-z &()/-]{0,50}?)'+VANITY_NOUN,t,re.I):
                    # In '31"x 22" Vanity Top' the number next to the noun is the depth.
                    # Size lists ('24"/30'/36" Width') name the family, not this child.
                    if match(r'\d(?:'+INCH+r')?\s*[WD]?\s*[x×*/]\s*$|\d\s*[\'"″”]\s*/\s*$',t[max(0,mm.start()-16):mm.start()]) or match(r'^\d{1,3}(?:\.\d+)?'+INCH+r'\s*[DH]\b',mm.group(0)) or match(r'^\s*/\s*\d',t[mm.end(1):mm.end(1)+6]) or match(r'^'+INCH+r'\s*/\s*\d',t[mm.end(1):mm.end(1)+8]) or match(r'\b(?:depth|height|faucet|mirror)\b',mm.group(0)) or match(r'^\d{1,3}(?:\.\d+)?'+INCH+r'\s*(?:tall|high(?!\s+gloss)|deep)\b',mm.group(0)) or for_ctx(mm.start()):continue
                    tw.append((mm.start(),float(mm.group(1)),mm.group(0)));break
                mm=match(r'(?<![\d.])(\d{2}(?:\.\d+)?)(?:'+INCH+r')?\s*[x×*]\s*(\d{2}(?:\.\d+)?)'+INCH+r'(?:[a-z &()/-]{0,50}?)'+VANITY_NOUN,t)
                if mm and 12<=float(mm.group(2))<=30 and not for_ctx(mm.start()):tw.append((mm.start(),float(mm.group(1)),mm.group(0)))
                # Number after the noun: 'Bathroom Vanity 55" Inch', 'Vanity with Sink 30 inch', 'Bathroom Vanity, 36"'.
                mm=match(r'\bvanit(?:y|ies)\b(?:\s+(?:set|cabinet|combo|base))?(?:\s+with\s+(?:a\s+)?(?:single\s+|double\s+)?sinks?)?\s*[,:-]?\s*(\d{2}(?:\.\d+)?)'+INCH+r'(?!\s*(?:[x×*]|[DH]\b))(?!\s*(?:(?!with\b)[a-z]+\s+)?(?:mirror|faucet|sink|basin|bowl|top|countertop|deep|depth|height|tall|high)\b)',t)
                if mm:tw.append((mm.start(1),float(mm.group(1)),mm.group(0)))
                if tw:
                    _,v,q=min(tw)
                    if 5<v<150:dims['W'].append((v,s,self.ev(s,v,q,'子体标题浴室柜宽度上下文')))
        dims['W'].sort(key=lambda x:0 if x[1]['field']=='SKU属性' else 1)
        # Sellers sometimes swap D/W labels ('30"D x 18.3"W', '31.89"D x 18.74"W' for a 30in):
        # a source whose W disagrees with the chosen width while its larger D is near that
        # width. Its W is not a width conflict; its D is handled below.
        swapped=[];mismatched=[]
        if dims['W']:
            width=dims['W'][0][0]
            for s in {id(x[1]):x[1] for x in dims['D']}.values():
                own_w=[v for v,s2,e in dims['W'] if s2 is s];own_d=[v for v,s2,e in dims['D'] if s2 is s]
                if own_w and own_d and own_w[0]<own_d[0] and abs(own_d[0]-width)<=2.5 and (abs(own_w[0]-width)>2.5 or (abs(own_d[0]-width)<=1.0 and own_d[0]-own_w[0]>1.0)):swapped.append(s)
            # A labelled source whose own W is another size (2026 export of a sibling
            # variant) is the last choice for depth/height.
            for s in {id(x[1]):x[1] for x in dims['D']+dims['H']}.values():
                own_w=[v for v,s2,e in dims['W'] if s2 is s]
                if own_w and abs(own_w[0]-width)>2.5 and not any(s is x for x in swapped):mismatched.append(s)
        # Prefer a depth from a source whose labels are consistent.
        dims['D'].sort(key=lambda x:2 if any(x[1] is s for s in mismatched) else 1 if any(x[1] is s for s in swapped) else 0)
        dims['H'].sort(key=lambda x:1 if any(x[1] is s for s in mismatched) else 0)
        # Corner vanities list the side length as W ('22" Corner' = 16"D x 16"W).
        corner=bool(match(r'\bcorner\b',clean(self.row.get('商品标题'))))
        for axis,key in zip(('W','D','H'),HEADERS[9:12]):
            values=dims[axis]
            if values:
                value=values[0][0];self.tags[key]=round(value,3);self.evidence[key]={'status':'text_supported','selected':[values[0][2]],'otherCandidates':[v[2] for v in values[1:]]}
                if any(abs(v[0]-value)>2.5 and not (axis in ('W','D') and any(v[1] is s for s in swapped)) and not (axis=='W' and corner and v[1]['field']!='SKU属性' and v[1]['field']!='商品标题') for v in values[1:]):self.conflicts.append(key+'尺寸来源差异超过2.5in，保留首选值待核验')
                if axis in ('D','H') and any(values[0][1] is s for s in mismatched):self.weak_dh.add(key)
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
        # v12.2: depth/height taken from a source whose own W is another size count as missing here.
        weak=getattr(self,'weak_dh',set())
        s=next((x for x in self.sources if x['field']=='商品尺寸' and x['scope']=='child'),None)
        m=s and match(r'^\s*(\d{1,3}(?:\.\d+)?)\s*[x×]\s*(\d{1,3}(?:\.\d+)?)\s*[x×]\s*(\d{1,3}(?:\.\d+)?)\s*(inches|inch|in|cm)?\s*$',s['text'])
        if not m:return
        f=1/2.54 if (m.group(4) or '').lower()=='cm' else 1
        a,b,c=(float(m.group(i))*f for i in (1,2,3))
        title=clean(self.row.get('商品标题'))
        widest=max([v for v in (a,b) if 12<=v<=96],default=None)
        # User 2026-10-29: no text width -> the cabinet width from the product dimension (larger of the first two values <= 84).
        if width is None and widest is not None and widest<=84:
            ev=self.ev(s,round(widest,3),s['text'],'文字没写宽度，用商品尺寸前两维中较大且≤84的值',{'ruleID':'DIM-WIDTH-FROM-DIMENSION','basisType':'order_inference'})
            self.tags[HEADERS[9]]=width=round(widest,3);self.evidence[HEADERS[9]]={'status':'order_inference','selected':[ev]}
            self.notes.append('D9宽：文字没写，按商品尺寸推断为%s'%width)
        # User 2026-10-29: a vanity with a side cabinet is sized by its total width (product dimension).
        elif width is not None and widest is not None and match(SIDE_CABINET,title) and widest>=width+3:
            ev=self.ev(s,round(widest,3),s['text'],'带侧柜按总宽（商品尺寸）',{'ruleID':'DIM-SIDE-CABINET-TOTAL','basisType':'business_mapping','titleWidth':width})
            self.evidence[HEADERS[9]].update({'status':'business_mapping','selected':[ev],'replacedTitleWidth':width})
            self.tags[HEADERS[9]]=width=round(widest,3)
            self.notes.append('D9宽：带侧柜，按总宽%s（标题主柜宽另见证据）'%width)
        if width is None or all(self.tags[k] is not None and k not in weak for k in HEADERS[10:12]):return
        if abs(b-width)<=1.0:order=((HEADERS[10],a),(HEADERS[11],c));how=('DIM-DWH-ORDER','无方向商品尺寸按D×W×H顺序推断（中间值与已选宽度一致）')
        # User 2026-10-29: W×D×H order when the first value is the width and the second is a plausible, smaller depth.
        elif abs(a-width)<=1.0 and b<=26 and b<a:order=((HEADERS[10],b),(HEADERS[11],c));how=('DIM-WDH-ORDER','无方向商品尺寸按W×D×H顺序推断（首值与已选宽度一致）')
        else:return
        for key,v in order:
            if (self.tags[key] is not None and key not in weak) or not 1<v<150:continue
            ev=self.ev(s,round(v,3),s['text'],how[1],{'ruleID':how[0],'basisType':'order_inference','crossCheckWidth':width})
            self.evidence[key]['orderInferenceCandidate']=ev
            if self.enable_dim_rules:
                if key in weak:
                    self.evidence[key]['replacedSelected']=self.evidence[key].get('selected')
                    self.notes.append(key+'：原首选来源标W与已选宽度不符，改用商品尺寸D×W×H')
                self.tags[key]=round(v,3);self.evidence[key].update({'status':'order_inference','selected':[ev]})
        if self.enable_dim_rules and any(self.evidence[k].get('status')=='order_inference' for k in HEADERS[10:12]):
            self.notes.append('D9深/高按无方向商品尺寸%s顺序推断，宽度已交叉核对'%('D×W×H' if how[0]=='DIM-DWH-ORDER' else 'W×D×H'))

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
        # A one-piece sink-top found for D8 (same material, molded/integrated) fixes D4:
        # user 2026-10-27, 一体盆归台上盆. Ceramic/resin top with the same sink material is one piece.
        top_ev=self.evidence.get(HEADERS[7],{});sel=top_ev.get('selected') or [{}]
        # Same ceramic/resin top and sink from the child's own text are one piece even when the
        # title says "undermount" (images 2026-10-29: Yaheetech, IRONCK, eclife are one-piece tops).
        same=self.tags.get(HEADERS[7]) in ('陶瓷','树脂') and self.tags.get(HEADERS[8])==self.tags.get(HEADERS[7])+'盆'
        same_child=same and all(e.get('sourceScope')=='child' for k in (HEADERS[7],HEADERS[8]) for e in self.evidence[k].get('selected',[]))
        undermount=self.tags.get(HEADERS[3])=='台下盆' and self.evidence[HEADERS[3]].get('status') in ('text_supported','parent_fill','conflict')
        if (self.tags.get(HEADERS[3])==UNKNOWN and (sel[0].get('ruleID') in ('M-SINK-TOP-ONEPIECE','M-SAME-PIECE') or same)) or (undermount and same_child):
            self.notes.append(('D4：文本写undermount，但台面与盆同为%s，'%self.tags[HEADERS[7]] if undermount else 'D4：台面与盆同材一体，')+'按一体盆归台上盆')
            self.tags[HEADERS[3]]='台上盆';self.evidence[HEADERS[3]]={'status':'business_inference','selected':[],'ruleID':'TOPFORM-ONEPIECE','basisField':HEADERS[7],'note':'台面与盆同材一体，按用户规则一体盆归台上盆'}
        # User 2026-10-29: sink material known (ceramic/resin), no top-material word in the child text, no vessel/boat/countertop
        # sink and no stone top -> one-piece sink-top: top = sink material, D4 = 台上盆 (images: such vanities are one-piece).
        # A vessel sink with no top-material word sits on the cabinet's wood or faux-marble panel -> 木板.
        child_text=' || '.join(x['text'] for x in self.sources if x['scope']=='child' and x['field']!='商品尺寸')
        d4ev=self.evidence.get(HEADERS[3],{})
        vessel=self.tags.get(HEADERS[3])=='台上盆' and any(match(VESSEL,e.get('quote','')) for e in d4ev.get('selected',[]))
        sink=self.tags.get(HEADERS[8])
        if self.tags.get(HEADERS[7])==UNKNOWN and not match(TOP_MATERIAL_WORD,child_text):
            if vessel:
                self.tags[HEADERS[7]]='木板';self.evidence[HEADERS[7]]={'status':'business_inference','selected':[],'ruleID':'M-VESSEL-TOP-WOOD','basisField':HEADERS[3],'note':'台上盆且文字没写台面材质，按柜体自带木板/仿大理石纹面板算木板（用户2026-10-29）'}
                self.notes.append('D8台面：台上盆且没写台面材质，推断为木板')
            elif sink in ('陶瓷盆','树脂盆','Cultured Marble盆') and (self.tags.get(HEADERS[3])==UNKNOWN or d4ev.get('ruleID')=='TOPFORM-ONEPIECE' or (self.tags.get(HEADERS[3])=='台上盆' and not vessel)):
                self.tags[HEADERS[7]]=sink[:-1];self.evidence[HEADERS[7]]={'status':'business_inference','selected':[],'ruleID':'M-INTEGRATED-INFER','basisField':HEADERS[8],'note':'盆材已知、文字没写台面材质，按一体盆台推断台面=盆材（用户2026-10-29）'}
                self.notes.append('D8台面：盆材已知、没写台面，按一体盆台推断为%s'%sink[:-1])
                if self.tags.get(HEADERS[3])==UNKNOWN:
                    self.tags[HEADERS[3]]='台上盆';self.evidence[HEADERS[3]]={'status':'business_inference','selected':[],'ruleID':'TOPFORM-INTEGRATED-INFER','basisField':HEADERS[8],'note':'一体盆台推断，一体盆归台上盆（用户2026-10-27/29）'}
        # A child text without a top ("vanity top not included") and without any sink wording is a base cabinet.
        if self.tags.get(HEADERS[7])=='不适用（不含台面）' and self.tags.get(HEADERS[2])==UNKNOWN and self.tags.get(HEADERS[8])==UNKNOWN:
            self.tags[HEADERS[2]]='无盆';self.evidence[HEADERS[2]]={'status':'derived','basis':HEADERS[7],'ruleID':'BASIN-NO-TOP'}
            self.tags[HEADERS[3]]='无盆';self.evidence[HEADERS[3]]={'status':'derived','basis':HEADERS[2]}
            self.tags[HEADERS[8]]='不适用（不含盆）';self.evidence[HEADERS[8]]={'status':'derived','basis':HEADERS[2]}
            self.notes.append('D3：不含台面且未提盆，按不含盆')
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
    if status in ('parent_fill','family_fill'):return 'A3'
    if status=='parent_candidate':return 'B'
    if (ev or {}).get('swapCorrectedCandidate') and status=='conflict':return 'D'
    if status=='conflict':return 'C'
    if (ev or {}).get('orderInferenceCandidate'):return 'D'
    if field in VISUAL:return 'F'
    return 'G' if has_child_text else 'E'

def apply_family_assembly_fill(target_rows,matrix,evidence_rows):
    """User 2026-10-27: one listing is essentially all 整装 or all 拆装. A row whose D2 is only the 拆装
    default takes the text-backed value of the same child ASIN (another snapshot) or, failing that, of
    its verified parent family when that family's text-backed rows agree (FAMILY-ASSEMBLY-FILL, v12.2)."""
    D2=HEADERS[1];by_asin={};by_fam={}
    for a,m,tags,e,feas,src,r,idx in target_rows:
        if e.get(D2,{}).get('status') in ('text_supported','parent_fill'):
            by_asin.setdefault(a,set()).add(tags[D2]);by_fam.setdefault(r.get('核验父ASIN') or a,set()).add(tags[D2])
    for i,(a,m,tags,e,feas,src,r,idx) in enumerate(target_rows):
        if e.get(D2,{}).get('status')!='business_default':continue
        fam=r.get('核验父ASIN') or a
        if len(by_asin.get(a,()))==1:got,how=next(iter(by_asin[a])),'同子体其他快照文本'
        elif len(by_fam.get(fam,()))==1:got,how=next(iter(by_fam[fam])),'同家族其他子体文本'
        else:continue
        newev={'status':'family_fill','selected':[],'ruleID':'FAMILY-ASSEMBLY-FILL','basis':how,'familyKey':fam,'note':'一个链接基本只有整装或拆装一种（用户2026-10-27），取'+how}
        matrix[idx][1]=got
        ev=evidence_rows[idx];ev['tags']=dict(ev['tags']);ev['tags'][D2]=got
        ev['fields']=dict(ev['fields']);ev['fields'][D2]=newev
        ev['feasibility']=dict(ev['feasibility']);ev['feasibility'][D2]=feasibility(D2,newev,True)
        matrix[idx][15]=(matrix[idx][15] or '')+'；D2按%s补充为%s（替代默认拆装）'%(how,got);ev['tags'][HEADERS[15]]=matrix[idx][15]
        t2=dict(tags);t2[D2]=got;e2=dict(e);e2[D2]=newev;f2=dict(feas);f2[D2]=ev['feasibility'][D2]
        target_rows[i]=(a,m,t2,e2,f2,src,r,idx)

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
        if asm=='整装' and expensive:new='实木';why='整装且价格≥同宽MDF中位%.1f倍'%SOLID_WOOD_PRICE_RATIO
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
    ap.add_argument('--no-family-fill',action='store_true',help='安装方式默认拆装时不取同子体/同家族文本（FAMILY-ASSEMBLY-FILL）')
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
    # Family fill runs first: the solid-wood price rule reads D2.
    if not args.no_family_fill:apply_family_assembly_fill(target_rows,matrix,evidence_rows)
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
    # Pre-review text labels of D7 (CAB-SOLIDWOOD-PRICE uses price, so price analyses must use the text label; v12.2).
    review=[{'row':i,'textLabel':ev['fields'][HEADERS[6]].get('textLabel'),'final':ev['tags'][HEADERS[6]]} for i,ev in enumerate(evidence_rows) if (ev.get('fields') or {}).get(HEADERS[6],{}).get('ruleID')=='CAB-SOLIDWOOD-PRICE']
    for name,value in [('tagging_matrix.json',{'headers':HEADERS,'matrix':matrix}),('tagging_d7_text_labels.json',review),('tagging_evidence.json',{'schemaVersion':VERSION,'snapshotWarning':'商品属性为当前证据快照，不是历史月末；父体候选不得当已确认子体属性','feasibilityLegend':FEASIBILITY,'rows':evidence_rows}),('tagging_summary.json',summary),('tagging_work_queues.json',queues)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('dimensions','feasibility','feasibilityLegend')},ensure_ascii=False))

if __name__=='__main__':main()
