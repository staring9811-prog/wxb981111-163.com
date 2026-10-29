"""v12.2 rule cases: references/v12.2_cases.jsonl (sentences from the four 2026-10-29 audits;
expectations updated to the user's 2026-10-29 decisions).
mode=run: build one row from the sources and run Tagger.run(); mode=structure: structure() only
(no business defaults); mode=family: same-family assembly fill (FAMILY-ASSEMBLY-FILL).
usage: python3 -I scripts/case_tests.py"""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import tag_cached as T
CASES=Path(__file__).resolve().parent.parent/'references'/'v12.2_cases.jsonl'

def build(src,suite):
    row={'子ASIN':'BTEST00001','目标月份':'202601','SKU属性':'','商品标题':'Bathroom Vanity' if suite=='台面台盆' else '','商品尺寸':'','五点描述':None,'五点来源':None,'五点来源ASIN':None,'核验父ASIN':None,'商品价格':None}
    exports=[]
    for f,v in src.items():
        if f in ('商品标题','SKU属性','商品尺寸'):row[f]=v
        elif f in ('五点描述','五点描述(子体)'):row.update({'五点描述':v,'五点来源':'子体详情','五点来源ASIN':'BTEST00001'})
        elif f=='五点描述(父体)':row.update({'五点描述':v,'五点来源':'父体详情填充','五点来源ASIN':'BPARENT001'})
        elif f.startswith('卖家精灵导出.详细参数'):
            key=f[len('卖家精灵导出.详细参数'):].lstrip('.')
            exports.append({'attributes':'%s:%s'%(key,v) if key else v,'features':None,'month':'202605'})
        else:raise ValueError(f)
    return row,exports

def structure_only(field,text):
    if field.startswith('卖家精灵导出.详细参数'):
        x=T.Tagger({'子ASIN':'X','SKU属性':'','商品标题':'','五点来源':None,'核验父ASIN':None,'商品尺寸':''},{},None,[{'attributes':text,'month':'202605'}])
    else:
        x=T.Tagger.__new__(T.Tagger)
        x.row={};x.asin='X';x.provenance={};x.tags={};x.evidence={};x.conflicts=[];x.notes=[];x.rejected_dims=[]
        x.enable_dim_rules=False;x.accessory_default=False;x.parent_fill=True;x.std_width=False;x.parent_detail={}
        x.sources=[{'field':field,'text':text,'scope':'child','asin':'X'}]
    for h in T.HEADERS[:14]:x.tags.setdefault(h,T.UNKNOWN)
    x.structure();return x.tags

def family():
    D2=T.HEADERS[1]
    rows=[('A','202510',{D2:'整装',T.HEADERS[15]:''},{D2:{'status':'parent_fill'}},{D2:'A3'},{},{'核验父ASIN':'P'},0),
          ('B','202510',{D2:'拆装',T.HEADERS[15]:''},{D2:{'status':'business_default'}},{D2:'A2'},{},{'核验父ASIN':'P'},1)]
    matrix=[[None]*16,[None,'拆装']+[None]*14];ev=[{'tags':{},'fields':{},'feasibility':{}},{'tags':{},'fields':{},'feasibility':{}}]
    T.apply_family_assembly_fill(rows,matrix,ev);return matrix[1][1]

def main():
    bad=[];n=0
    for line in CASES.read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        c=json.loads(line);n+=1;f=c['field'];exp=c['expected']
        if c['mode']=='family':got=family()
        elif c['mode']=='structure':(field,text),=c['sources'].items();got=structure_only(field,text)[f]
        else:
            row,ex=build(c['sources'],c['suite']);tags,ev,conf=T.Tagger(row,{},None,ex or None).run()
            got=('有' if any(x.startswith(('D6','D9')) for x in conf) else '无') if f=='冲突标记(D6/D9)' else tags[f]
        ok=(got is not None and exp is not None and abs(float(got)-float(exp))<=0.5) if f.startswith('D9') and not (got is None or exp is None) else got==exp
        if not ok:bad.append((c['suite'],c.get('id'),f,exp,got,str(c['sources'])[:90]))
    for b in bad:print('FAIL',b)
    print('case_tests: %d/%d passed'%(n-len(bad),n))
    return 1 if bad else 0

if __name__=='__main__':sys.exit(main())
