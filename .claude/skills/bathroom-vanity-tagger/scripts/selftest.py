"""Regression cases for tag_cached.py rules. Run after any rule change:

  python3 -I scripts/selftest.py
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))  # works under python -I
import tag_cached as t

def tagger(sources,row=None,**kw):
    x=t.Tagger.__new__(t.Tagger)
    x.row=row or {};x.asin='X';x.provenance={};x.tags={};x.evidence={};x.conflicts=[];x.notes=[]
    x.rejected_dims=[];x.enable_dim_rules=kw.get('enable_dim_rules',False)
    x.accessory_default=kw.get('accessory_default',False);x.parent_fill=kw.get('parent_fill',False);x.std_width=kw.get('std_width',False);x.parent_detail=kw.get('parent_detail',{})
    x.sources=[{'field':f,'text':txt,'scope':scope,'asin':'X'} for f,txt,scope in sources]
    return x

INCLUDED=[
    ('五点描述','Packages include the bathroom vanity, sink, faucet, pop-up drain, hot/ cold lines.','faucet','含'),
    ('五点描述','Includes vanity top, single sink, hardware and backsplash. Faucets and mirror are not included.','faucet','无'),
    ('五点描述','Includes vanity top, single sink, hardware and backsplash. Faucets and mirror are not included.','mirror','无'),
    ('五点描述','The countertop comes pre-drilled for a 3-hole faucet with an 8” widespread configuration.','faucet','信息不足'),
    ('五点描述','The top is pre-drilled for an 8” widespread faucet, and the sink is included.','faucet','信息不足'),
    ('五点描述','Mounts to solid walls. Faucet, and drain not included','faucet','无'),
    ('五点描述','*Please note: mirror, faucet, and drain are sold separately.','faucet','单卖'),
    ('五点描述','Sink has 1 pre-drilled hole suitable for 4-inch faucet(not included).','faucet','无'),
    ('五点描述','Easy installation (note: excluding faucets and drains.)','faucet','无'),
    ('五点描述','Water saving faucet: 1.2 gpm faucet aerator is adopted.','faucet','信息不足'),
    ('五点描述','The vanity does not include a countertop, sink, faucet or mirror.','faucet','无'),
    ('五点描述','Single hole faucet mount (not included).','faucet','无'),
    ('商品标题','36" Vanity with Sink Combo, Vessel Sink Top, Faucet & Pop Up Drain (Green Leaf)','faucet','含'),
    ('商品标题','36” Floating Vanity, Undermount Basin, 3 Faucet Hole, Soft-Close','faucet','信息不足'),
    ('商品标题','30” Floating Vanity, Undermount Basin, Single Hole Faucet, Soft-Close','faucet','信息不足'),
    ('商品标题','Cabinet, Resin Dual Sink Top, Matte Black Faucet and 6 Drawers, Mirror Not Included','faucet','含'),
    ('商品标题','Cabinet, Resin Dual Sink Top, Matte Black Faucet and 6 Drawers, Mirror Not Included','mirror','无'),
    ('商品标题','Bathroom Vanity with Mirror Finish Hardware','mirror','信息不足'),
]

def main():
    bad=[]
    for field,text,word,want in INCLUDED:
        x=tagger([(field,text,'child')]);x.included('K',word)
        if x.tags['K']!=want:bad.append(('included',word,text,want,x.tags['K']))
    # 3H is a faucet-hole code, not a 3in height.
    x=tagger([('SKU属性','Color: Light Oak - 01 | Size: 48" -3H','child')]);x.dimensions()
    if x.tags['D9高(in)'] is not None or x.tags['D9宽(in)']!=48:bad.append(('3H',x.tags))
    x=tagger([('商品尺寸','18.1"D x 30"W x 34"H','child')]);x.dimensions()
    if (x.tags['D9宽(in)'],x.tags['D9深(in)'],x.tags['D9高(in)'])!=(30,18.1,34):bad.append(('labelled',x.tags))
    # D/W swapped labels: depth blank + conflict by default, corrected when enabled.
    src=[('SKU属性','Size: 30 inch','child'),('子体详情.overviews.Product Dimensions','30"D x 18.1"W x 34"H','child')]
    x=tagger(src);x.dimensions()
    if x.tags['D9深(in)'] is not None or x.tags['D9宽(in)']!=30 or any(c.startswith('D9宽') for c in x.conflicts):bad.append(('swap-default',x.tags,x.conflicts))
    x=tagger(src,enable_dim_rules=True);x.dimensions()
    if x.tags['D9深(in)']!=18.1:bad.append(('swap-enabled',x.tags))
    # Unlabelled D×W×H only with the rule enabled and a width cross-check.
    src=[('SKU属性','Size: 36 Inch','child'),('商品尺寸','22 x 36 x 34.5 inches','child')]
    x=tagger(src);x.dimensions()
    if x.tags['D9深(in)'] is not None or not x.evidence['D9深(in)'].get('orderInferenceCandidate'):bad.append(('dwh-default',x.tags))
    x=tagger(src,enable_dim_rules=True);x.dimensions()
    if (x.tags['D9深(in)'],x.tags['D9高(in)'])!=(22,34.5):bad.append(('dwh-enabled',x.tags))
    x=tagger([('SKU属性','Size: 36 Inch','child'),('商品尺寸','36 x 22 x 34.5 inches','child')],enable_dim_rules=True);x.dimensions()
    if x.tags['D9深(in)'] is not None:bad.append(('dwh-no-crosscheck',x.tags))
    # Standard widths: 23.6 -> 24, 31.5 (tie 31/32) and 37 stay raw.
    for raw,want in ((23.6,24),(47.2,48),(29.3,30),(31.5,31.5),(37,37)):
        x=tagger([('子体详情.overviews.Product Dimensions','18"D x %s"W x 34"H'%raw,'child')],std_width=True);x.dimensions();x.snap_width()
        if x.tags['D9宽(in)']!=want:bad.append(('std-width',raw,x.tags['D9宽(in)']))
    # Parent fill: no suffix, status parent_fill; parent dims only for the same width.
    x=tagger([('五点描述','Fully assembled cabinet','parent')],parent_fill=True);x.set('K',[x.ev(x.sources[0],'整装','q')])
    if x.tags['K']!='整装' or x.evidence['K']['status']!='parent_fill':bad.append(('parent-fill',x.tags))
    for pw,want in (('47.2',18.1),('60',None)):
        x=tagger([('SKU属性','Size: 48 Inch','child')],row={'核验父ASIN':'P'},parent_fill=True,parent_detail={'dimensions':'18.1"D x %s"W x 35"H'%pw});x.dimensions();x.parent_dimensions()
        if x.tags['D9深(in)']!=want:bad.append(('parent-dims',pw,x.tags))
    # Mirror/faucet default: no mention -> 无; explicit mention still wins.
    for txt,want in (('30 Inch Bathroom Vanity with Sink, White','无'),('30 Inch Bathroom Vanity with Sink & Faucet, White','含'),('Vanity, Faucet Sold Separately','单卖')):
        x=tagger([('商品标题',txt,'child')],accessory_default=True);x.tags[t.HEADERS[4]]='待图片核验'
        for h in t.HEADERS[:14]:x.tags.setdefault(h,None)
        x.included(t.HEADERS[13],'faucet')
        if x.tags[t.HEADERS[13]]==t.UNKNOWN:x.tags[t.HEADERS[13]]='无'
        if x.tags[t.HEADERS[13]]!=want:bad.append(('acc-default',txt,x.tags[t.HEADERS[13]]))
    # Countertop rules (v6).
    def top(sources,**kw):
        x=tagger(sources,**kw)
        for h in t.HEADERS[:14]:x.tags.setdefault(h,t.UNKNOWN)
        x.tags[t.HEADERS[2]]=t.UNKNOWN;x.evidence[t.HEADERS[3]]={'status':'missing'}
        x.structure();x.surface_materials();return x
    cases=[
     ('Solid Wood Bathroom Vanity with Ceramic Sink, White',t.UNKNOWN,'陶瓷盆'),
     ('Vanity with Ceramic Vessel Sink and Multi-layer Solid Wood Countertop','木板','陶瓷盆'),
     ('24" Floating Vanity, Marble Look Wooden Tabletop, Natural','木板',t.UNKNOWN),
     ('Vanity with Marble Texture Top and 2 Drawers, Two Boat Ceramic Sinks','木板','陶瓷盆'),
     ('Vanity with Marble Texture Top, Carrara Quartz Countertop','石英石',t.UNKNOWN),
     ('Vanity with Stone Countertop and Backsplash','岗石',t.UNKNOWN),
     ('Premium Sintered Stone Top; combines a beige stone top with oak','岩板',t.UNKNOWN),
     ('Vanity with Sintered Stone Top and Ceramic Basin','岩板','陶瓷盆'),
     ('Vanity Base Only, No Top or Sink','不适用（不含台面）',None),
     ('Vanity with White Ceramic Sink Top, Black Faucet','陶瓷','陶瓷盆'),
     ('Vanity with Integrated Ceramic Sink, 2 Drawers','陶瓷','陶瓷盆'),
     ('Vanity with Blue Boat Glass Vessel Sink','信息不足','玻璃盆'),
    ]
    for title,wt,ws in cases:
        x=top([('商品标题',title,'child')],parent_fill=True)
        got=(x.tags[t.HEADERS[7]],x.tags[t.HEADERS[8]])
        if got[0]!=wt or (ws is not None and got[1]!=ws):bad.append(('top',title,got))
    for v,want in (('MDF；实木','实木框架+MDF'),('实木；胶合板；MDF；刨花板','实木框架+MDF+胶合板+刨花板'),('胶合板；MDF','MDF+胶合板'),('实木框架（其余未说明）','实木框架'),('实木','实木'),('MDF','MDF'),('MDF；实木（父体候选）','实木框架+MDF（父体候选）')):
        if t.format_cabinet(v)!=want:bad.append(('cabinet-format',v,t.format_cabinet(v)))
    # Pedestal forms (user 2026-10-28): pedestal sink / storage cabinet -> 柱状盆, outranking freestanding/wall words.
    def form(sources,**kw):
        x=tagger(sources,**kw)
        for h in t.HEADERS[:14]:x.tags.setdefault(h,t.UNKNOWN)
        x.structure();return x.tags[t.HEADERS[0]]
    for title,want in (
        ('TEENFON Pedestal Sink Storage Cabinet with 2 Doors and Drawer, Freestanding Under Sink Storage with U-Shape Cut-Out','柱状盆'),
        ('kleankin Modern Under Sink Cabinet with 2 Doors, Pedestal Under Sink Bathroom Cupboard, Wall Mounted','柱状盆'),
        ('White Ceramic Pedestal Sink, 24 inch Bathroom Pedestal Basin','柱状盆'),
        ('Under Sink Cabinet for Pedestal Sink, Bathroom Storage Organizer','柱状盆'),
        ('Farmhouse Style Standing Pedestal Cabinet with Two Blue Boat Glass Vessel Sinks, Freestanding','落地式'),
        ('30 Inch Floating Bathroom Vanity with Sink','悬浮式')):
        got=form([('商品标题',title,'child')])
        if got!=want:bad.append(('pedestal',title,got))
    # Pedestal wording only in parent bullets does not override the child's explicit form.
    got=form([('商品标题','36" Freestanding Bathroom Vanity with Sink','child'),('五点描述','A stylish upgrade from your old pedestal sink.','parent')],parent_fill=True)
    if got!='落地式':bad.append(('pedestal-bullet',got))
    # Workbook parts without an XML declaration (openpyxl output) must still be writable.
    import write_workbook as ww
    for xml,want in (('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n<worksheet xmlns="m">',''),('<worksheet xmlns="m"><sheetData/>',''),('<x:worksheet xmlns:x="m">','x:')):
        if ww.root_prefix(xml,'worksheet')!=want:bad.append(('xml-declaration',xml[:45],ww.root_prefix(xml,'worksheet')))
    for t_ in bad:print('FAIL',t_)
    print('selftest: %d failure(s)'%len(bad))
    raise SystemExit(1 if bad else 0)

if __name__=='__main__':main()
