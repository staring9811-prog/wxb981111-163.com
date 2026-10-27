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
    for t_ in bad:print('FAIL',t_)
    print('selftest: %d failure(s)'%len(bad))
    raise SystemExit(1 if bad else 0)

if __name__=='__main__':main()
