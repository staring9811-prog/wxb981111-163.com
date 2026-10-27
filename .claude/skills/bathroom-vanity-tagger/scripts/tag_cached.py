"""Evidence-preserving, network-free bathroom vanity attribute tagging.

Consumes the current normalized payload and exact-ASIN detail cache. Produces
only JSON; workbook editing is separate. Parent descriptions remain candidates.
"""
import argparse,html,json,re,hashlib
from pathlib import Path
from collections import Counter

VERSION='bathroom-vanity-tagger-20261024-v2'
HEADERS=['D1产品形态','D2安装方式','D3盆数','D4台面形态','D5元素','D6柜体颜色','D7柜体材质','D8台面材质','D8台盆材质','D9宽(in)','D9深(in)','D9高(in)','D10镜子','D11龙头','打标状态','打标说明']
UNKNOWN='信息不足'
def clean(s):return re.sub(r'\s+',' ',html.unescape(str(s or ''))).strip()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def match(pattern,text):return re.search(pattern,text,re.I)
def uniq(xs):return list(dict.fromkeys(xs))

class Tagger:
    def __init__(self,row,details,feature_provenance=None):
        self.row=row;self.asin=row['子ASIN'];self.sources=[];self.notes=[];self.conflicts=[];self.tags={};self.evidence={}
        def add(field,text,scope='child',a=None):
            if clean(text):self.sources.append({'field':field,'text':clean(text),'scope':scope,'asin':a or self.asin})
        add('SKU属性',row.get('SKU属性'));add('商品标题',row.get('商品标题'))
        d=(details.get(self.asin) or {}).get('data') or {}
        if d.get('asin')!=self.asin:d={}
        ov=d.get('overviews')
        if isinstance(ov,str):
            try:ov=json.loads(ov)
            except (ValueError,TypeError):ov={}
        if isinstance(ov,dict):
            for k,v in ov.items():add('子体详情.overviews.'+k,clean(v))
        if row.get('五点来源')=='子体详情':add('五点描述',row.get('五点描述'))
        elif row.get('五点来源')=='父体详情填充':add('五点描述',row.get('五点描述'),'parent',row.get('五点来源ASIN'))
        add('商品尺寸',row.get('商品尺寸'))
        self.provenance=feature_provenance or {}
    def ev(self,source,label,quote,method='明确文本',extra=None):
        e={'label':label,'sourceField':source['field'],'sourceASIN':source['asin'],'sourceScope':source['scope'],'quote':clean(quote),'method':method}
        if source['field']=='五点描述':
            e['sourceRecordID']=self.provenance.get('sourceRecordID');e['requestTime']=self.provenance.get('requestTime')
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
        if parent:value+='（父体候选）'
        self.tags[key]=value
        self.evidence[key]={'status':'parent_candidate' if parent else 'conflict' if len(labels)>1 and not multi else 'text_supported','selected':selected,'otherParentCandidates':[e for e in candidates if e['sourceScope']=='parent'] if direct else []}
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
        self.set(HEADERS[0],self.pattern_candidates([
            ('悬浮式',r'\b(?:floating|wall[ -]mount(?:ed)?|wall[ -]hung)\b'),
            ('落地式',r'\b(?:freestanding|free[ -]standing|floor[ -]mount(?:ed)?)\b'),
            ('开放式',r'\bconsole\s+(?:vanity|sink|table)\b'),
            ('柱状盆',r'\bpedestal\s+(?:sink|basin)(?!\s+(?:storage|cabinet))\b')],lambda f:f!='商品尺寸'))
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
        c=[]
        for s in self.sources:
            t=s['text']
            no=match(r'\b(?:without|no) (?:a )?(?:sink|basin)\b|\b(?:sink|basin) (?:is )?(?:not included|sold separately)\b|\b(?:cabinet|vanity base) only\b',t)
            double=match(r'\b(?:double|dual|two|2)[ -]+(?:sink|basin|bowl)s?\b|\bsize\s*:[^|]*\bdual\b',t)
            single=match(r'\b(?:single|one|1)[ -]+(?:(?:oval|round|rectangular|white|black|ceramic|porcelain|resin|undermount)\s+){0,3}(?:sink|basin|bowl)\b|\bsize\s*:[^|]*\bsingle\b',t)
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
        else:self.set(HEADERS[2],c)
        if self.tags[HEADERS[2]]=='无盆':
            self.tags[HEADERS[3]]='不适用（无盆）';self.evidence[HEADERS[3]]={'status':'derived','basis':HEADERS[2]}
        else:self.set(HEADERS[3],self.pattern_candidates([
            ('台上盆',r'\bvessel\s+(?:sink|basin)|\babove[ -]counter\s+(?:sink|basin)\b'),
            ('台下盆',r'\bunder[ -]?(?:mount|counter)(?:ed)?\b'),
            ('一体盆',r'\bintegrat(?:ed|ion)\s+(?:sink|basin|countertop)|one[ -]piece\s+(?:sink|basin|countertop)'),
            ('嵌入盆',r'\bdrop[ -]in\s+(?:sink|basin)|\btop[ -]mount(?:ed)?\s+(?:sink|basin)')]))
        self.set(HEADERS[4],self.pattern_candidates([
            ('Fluted',r'\bfluted\b'),('Reeded',r'\breeded\b'),('Shaker',r'\bshaker\b|\brecessed panel\b'),
            ('Barn Door',r'\bbarn[ -]door\b'),('Farmhouse',r'\bfarmhouse\b|\bx[ -]design\b'),
            ('Slatted',r'\bslatted\b|\blouvered\b'),('Glass Door',r'\b(?:glass|glazed)\s+(?:cabinet\s+)?doors?\b'),
            ('Rattan',r'\b(?:rattan|wicker|cane)\b')],lambda f:f in ('商品标题','SKU属性','五点描述') or 'style' in f.lower()),multi=True,default='待图片核验')

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
        pats=[('MDF',r'\bmdf\b|medium[ -]density\s+fib(?:er|re)board'),('胶合板',r'\bplywood\b'),('刨花板',r'\bparticle\s*board\b|\bchipboard\b'),('实木',r'\bsolid\s+(?:wood|oak|pine|rubberwood|birch|poplar)\b'),('工程木材（未细分）',r'\bengineered\s+wood\b|\bcomposite\s+wood\b'),('人造大理石',r'\b(?:cultured|engineered|synthetic)\s+marble\b'),('人造石（未细分）',r'\bengineered\s+stone\b'),('石英石',r'\b(?:engineered\s+)?quartz(?:\s+stone)?\b'),('岩板',r'\bsintered\s+stone\b'),('大理石（天然性未核实）',r'\bmarble\b'),('陶瓷',r'\bceramic\b|\bporcelain\b'),('树脂',r'\bresin\b'),('亚克力',r'\bacrylic\b'),('SMC',r'\bsmc\b|sheet\s+moulding\s+compound|sheet\s+molding\s+compound'),('花岗岩',r'\bgranite\b'),('玻璃',r'\b(?:tempered\s+)?glass\b'),('不锈钢',r'\bstainless\s+steel\b'),('竹材',r'\bbamboo\b')]
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
        if '实木框架（其余未说明）' in self.tags[HEADERS[6]] and 'MDF' in self.tags[HEADERS[6]]:
            self.tags[HEADERS[6]]=self.tags[HEADERS[6]].replace('实木框架（其余未说明）','实木框架')
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
            ('实木',r'\bsolid\s+wood\b')]
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
                    if role=='sink' and raw=='实木':continue
                    label=raw;method='部件绑定文本';rule='M-DIRECT'
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
        for role,key in keys.items():
            es=buckets[role]
            self.set(key,es)
            ev=self.evidence[key]
            if ev['status']=='text_supported' and any(e.get('basisType')=='business_mapping' for e in ev.get('selected',[])):ev['status']='business_mapping'
        # Explicitly absent components override inferred combinations.
        no_top=self.pattern_candidates([('不适用（不含台面）',r'\bwithout\s+(?:a\s+)?(?:top|countertop)\b|\b(?:top|countertop)\s+(?:is\s+)?(?:not included|sold separately)\b')])
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
                self.tags[HEADERS[8]]='陶瓷盆'+('（父体候选）' if scope=='parent' else '')
                self.evidence[HEADERS[8]]={'status':'parent_candidate' if scope=='parent' else 'business_assumption','selected':[ev]}
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
            for m in re.finditer(r'(?<![\d.])(\d{1,3}(?:\.\d+)?)\s*(?:["″]|inches|inch|\bin\b|cm)?\s*([WDH])(?=\s|[x×,;)]|$)',t,re.I):
                v=float(m.group(1))*factor;axis=m.group(2).upper()
                if 1<v<150:dims[axis].append((v,s,self.ev(s,v,m.group(0),'方向标记尺寸')))
            if s['field']=='SKU属性':
                m=match(r'(?:size|pattern name)\s*:\s*([^|]+)',t)
                if m and not match(r'\b(?:depth|deep|height|tall)\b|\d\s*["″]?\s*[DH]\b',m.group(1)):
                    mm=match(r'^\s*(\d{1,3}(?:\.\d+)?)\s*(?:inch(?:es)?|["″]|\bin\b|cm)(?!\s*(?:deep|depth))',m.group(1))
                    if mm:
                        v=float(mm.group(1))*factor
                        if 5<v<150:dims['W'].insert(0,(v,s,self.ev(s,v,m.group(0),'SKU名义宽度')))
                    elif match(r'^\s*\d{1,3}(?:\.\d+)?\s*$',m.group(1)):
                        v=float(m.group(1))
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
        for axis,key in zip(('W','D','H'),HEADERS[9:12]):
            values=dims[axis]
            if axis=='W':values.sort(key=lambda x:0 if x[1]['field']=='SKU属性' else 1)
            if values:
                value=values[0][0];self.tags[key]=round(value,3);self.evidence[key]={'status':'text_supported','selected':[values[0][2]],'otherCandidates':[v[2] for v in values[1:]]}
                if any(abs(v[0]-value)>2.5 for v in values[1:]):self.conflicts.append(key+'尺寸来源差异超过2.5in，保留首选值待核验')
            else:self.tags[key]=None;self.evidence[key]={'status':'missing','candidates':[]}

    def included(self,key,kind):
        c=[]
        for s in self.sources:
            t=s['text'];word=kind
            separate=match(r'\b'+word+r's?\s+(?:is\s+)?sold separately\b',t)
            no=match(r'\b(?:no|without)\s+(?:a\s+)?'+word+r's?\b|\b'+word+r's?\s+(?:is\s+)?not included\b|does not include\s+(?:a\s+)?'+word,t)
            yes=match(r'\b'+word+r's?\s+(?:is\s+)?included\b|\bwith\s+(?:(?:matte|black|white|chrome|brushed|gold|nickel)\s+){0,3}'+word+r'\b|\b1\s*[x×]\s*'+word+r'\b',t)
            chosen=('单卖',separate) if separate else ('无',no) if no else ('含',yes) if yes else None
            if chosen:
                label,m=chosen;c.append(self.ev(s,label,t[max(0,m.start()-30):m.end()+60]))
        self.set(key,c)
    def run(self):
        self.structure();self.colors();self.materials();self.dimensions();self.included(HEADERS[12],'mirror');self.included(HEADERS[13],'faucet')
        for h in HEADERS[:14]:
            related=[s for s in self.conflicts if s.startswith(h)]
            if related and h in self.evidence:
                self.evidence[h]['status']='conflict';self.evidence[h]['conflicts']=related
        unknown=[h for h in HEADERS[:14] if self.tags.get(h) in (None,UNKNOWN,'待图片核验')]
        parent=[h for h in HEADERS[:14] if '父体候选' in str(self.tags.get(h,''))]
        if self.conflicts:state='存在冲突待核验'
        elif unknown or parent:state='部分信息不足'
        else:state='文本证据可用'
        notes=[]
        if parent:notes.append('父体候选：'+'、'.join(parent))
        if unknown:notes.append('缺少充分文本证据：'+'、'.join(unknown))
        notes.extend(uniq(self.conflicts+self.notes))
        if self.tags[HEADERS[4]]=='待图片核验':notes.append('元素图片尚未人工核验')
        else:notes.append('元素取文本线索，未作图片独立核验')
        self.tags[HEADERS[14]]=state;self.tags[HEADERS[15]]='；'.join(notes) or '标签取自当前文本快照'
        return {h:self.tags.get(h) for h in HEADERS},self.evidence,uniq(self.conflicts)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',required=True);ap.add_argument('--out-dir',required=True);args=ap.parse_args()
    root=Path(args.data_root);out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    p=load(root/'sales_payload.json');details=load(root/'collected_details.json')
    excluded=load(root/'step1_macro_audit.json')['confirmedNonTargetProducts']
    fp={(r['targetMonth'],r['childASIN']):r for r in load(root/'feature_field_provenance.json')}
    matrix=[];evidence_rows=[];states=Counter();snapshots={};target_rows=[]
    for i,r in enumerate(p['detailRows'],2):
        a=r['子ASIN'];month=r['目标月份']
        if not r.get('_eligible') or a in excluded:
            state='不纳入浴室柜分析' if a in excluded or r.get('_outside_input_scope') else '目标月归属待核验'
            values=[None]*14+[state,excluded.get(a) or '保留原始记录，未对未核验目标月候选强行打标']
            e={};conflicts=[]
        else:
            textkey=hashlib.sha256(json.dumps({h:r.get(h) for h in ['子ASIN','SKU属性','商品标题','商品尺寸','五点描述','五点来源','五点来源ASIN']},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            if textkey not in snapshots:
                snapshots[textkey]=Tagger(r,details,fp.get((month,a))).run()
            tags,e,conflicts=snapshots[textkey];values=[tags[h] for h in HEADERS];target_rows.append((a,month,tags,e))
        matrix.append(values);states[values[-2]]+=1
        evidence_rows.append({'excelRow':i,'marketplace':r['站点'],'month':month,'childASIN':a,'verifiedParentASIN':r.get('核验父ASIN'),'includeInBathroomAnalysis':bool(r.get('_eligible')) and a not in excluded,'tags':dict(zip(HEADERS,values)),'fields':e,'conflicts':conflicts,'originalRecordIDs':r.get('关联原始记录ID'),'featureSource':r.get('五点来源'),'featureSourceASIN':r.get('五点来源ASIN')})
    summary={'ruleVersion':VERSION,'allRowsRetained':len(matrix),'taggedTargetRows':len(target_rows),'uniqueTargetASINs':len({a for a,m,t,e in target_rows}),'distinctTextSnapshots':len(snapshots),'rowStates':dict(states),'dimensions':{},'newAPICalls':0,'imagesIndependentlyReviewed':0,'imageNote':'本轮是已有文本证据打标，元素待图片核验/文本线索均明确标注，不宣称已看图','monthly':[]}
    for h in HEADERS[:14]:
        vals=[t[h] for a,m,t,e in target_rows]
        present=sum(v not in (None,UNKNOWN,'待图片核验') for v in vals)
        summary['dimensions'][h]={'textOrCandidatePresentRows':present,'insufficientRows':sum(v in (None,UNKNOWN,'待图片核验') for v in vals),'parentCandidateRows':sum('父体候选' in str(v) for v in vals),'fieldEvidenceStates':dict(Counter(e.get(h,{}).get('status','component_specific') for a,m,t,e in target_rows)),'distribution':dict(Counter(str(v) if v is not None else '空白' for v in vals))}
    for m in ['202606','202607','202608','202609']:
        rr=[t for a,mm,t,e in target_rows if mm==m]
        summary['monthly'].append({'month':m,'targetRows':len(rr),'states':dict(Counter(t[HEADERS[14]] for t in rr))})
    for name,value in [('tagging_matrix.json',{'headers':HEADERS,'matrix':matrix}),('tagging_evidence.json',{'schemaVersion':VERSION,'snapshotWarning':'商品属性为当前证据快照，不是历史月末；父体候选不得当已确认子体属性','rows':evidence_rows}),('tagging_summary.json',summary)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='dimensions'},ensure_ascii=False))

if __name__=='__main__':main()
