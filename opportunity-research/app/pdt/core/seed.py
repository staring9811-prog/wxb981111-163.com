"""第二轮数据导入（回归基准，供 wen 首次使用与回归测试）。

读本机 ../input/data_v2（不入库）：
- 统一打标/统一打标_分析用.pkl：2024-10 至 2026-09 每月 × 子体，含 v12.2 打标与看图元素（第二轮全部计算的输入）；
- 子体流量词/子体销量预估_2024-10至2025-12.csv：定主尺寸段用的子体销量；
- keywords_20261028（尺寸词）与 关键词_属性/汇总.csv（属性词）：第九版 x3 搜索同比；
- 可选：渠道VP/浴室柜_2026_渠道VP_20261103.xlsx（其他渠道）、待核_卖家精灵导出_标为2026-10_实为9月（演示“疑似月份错误”）。
每月建一个已并入批次（来源 v2），逐行保存当月标签（打标结果按“子体 × 月”是证据快照，不能用最后一个月覆盖）。
命令行：python tools_import_v2.py [--channels] [--suspect] [--no-compute]
"""
import argparse
import glob
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func, insert, select

from ..config import PROJECT_DIR
from ..db import init_db, session
from ..models import Batch, Product, Snapshot, Tag, now
from ..models_data import SearchVolume
from . import families as fm
from . import verify as vf

D2 = PROJECT_DIR / 'input' / 'data_v2'
PKL = D2 / '统一打标' / '统一打标_分析用.pkl'
CHILD = D2 / '子体流量词' / '子体销量预估_2024-10至2025-12.csv'
KW = D2 / 'keywords_20261028'
ATTR_KW = D2 / '关键词_属性' / '汇总.csv'
VP_XLSX = D2 / '渠道VP' / '浴室柜_2026_渠道VP_20261103.xlsx'
SUSPECT = D2 / '待核_卖家精灵导出_标为2026-10_实为9月' / '2026-10_full_data.csv'
SOURCE_NAME = {'卖家精灵MCP': '卖家精灵导出', '2026 月度表': '卖家精灵导出（2026 月度表）', '2026 v11 表': 'v11 表导入'}

# 第二轮 两层识别.py 的属性关键词 → 维度取值
KMAP = {'resin top bathroom vanity': ('台面', '树脂一体'), 'marble top bathroom vanity': ('台面', '石材台面'), 'quartz top bathroom vanity': ('台面', '石材台面'),
        'stone top bathroom vanity': ('台面', '石材台面'), 'bathroom vanity with ceramic sink': ('台面', '陶瓷一体'), 'wood top bathroom vanity': ('台面', '木板台面'),
        'bathroom vanity without top': ('台面', '不含台面'), 'bathroom vanity cabinet only': ('台面', '不含盆'),
        'fluted bathroom vanity': ('元素', '竖棱'), 'reeded bathroom vanity': ('元素', '竖棱'), 'shaker bathroom vanity': ('元素', '夏克式'),
        'farmhouse bathroom vanity': ('元素', '农场风装饰饰条'), 'barn door bathroom vanity': ('元素', '农场风装饰饰条'), 'slatted bathroom vanity': ('元素', '木条格栅'),
        'rattan bathroom vanity': ('元素', 'rattan'), 'glass door bathroom vanity': ('元素', '玻璃门'), 'rustic bathroom vanity': ('元素', 'rustic'),
        'vintage bathroom vanity': ('元素', '夏克式+复古立柱'),
        'black bathroom vanity': ('主色', '黑'), 'white bathroom vanity': ('主色', '白'), 'gray bathroom vanity': ('主色', '灰'), 'grey bathroom vanity': ('主色', '灰'),
        'wood bathroom vanity': ('主色', '原木'), 'oak bathroom vanity': ('主色', '原木'), 'natural wood bathroom vanity': ('主色', '原木'), 'walnut bathroom vanity': ('主色', '深木'),
        'green bathroom vanity': ('主色', '绿'), 'blue bathroom vanity': ('主色', '蓝'),
        'floating bathroom vanity': ('形态', '悬浮式'), 'wall mounted bathroom vanity': ('形态', '悬浮式'), 'freestanding bathroom vanity': ('形态', '落地式'),
        'pedestal sink': ('形态', '柱状盆'), 'corner bathroom vanity': ('形态', '转角式')}


def available() -> bool:
    return PKL.exists()


def _norm(v):
    return '' if v is None or (isinstance(v, float) and np.isnan(v)) or str(v) in fm.RAW_UNK else str(v)


def rows_from_pkl() -> pd.DataFrame:
    A = pd.read_pickle(PKL).reset_index(drop=True)
    child = pd.to_numeric(A['子体月销（2026 原流程估算）'], errors='coerce')
    if CHILD.exists():
        c = pd.read_csv(CHILD, encoding='utf-8-sig', dtype=str)
        c['v'] = pd.to_numeric(c['子体月销预估'], errors='coerce')
        v = A[['月份', '子ASIN']].merge(c[['月', '子ASIN', 'v']].rename(columns={'月': '月份'}), on=['月份', '子ASIN'], how='left')['v'].values
        child = np.where(pd.notna(v), v, child)
    A['_child'] = child
    A['_el'] = A['元素（看图）'].map(lambda e: '|'.join(x for x in fm.img_el(e) if x not in ('fluted', 'reeded')))
    A['_cab'] = A.get('D7柜体材质（价格复核前）', A['D7柜体材质']).map(fm.cab)
    return A


def row_tags(r) -> dict:
    cab = r['_cab']
    col = fm.color(r['D6柜体颜色'])
    return {'尺寸段': fm.band(r['D9宽(in)']) or '', '装': '整装' if r['D2安装方式'] == '整装' else '拆装',
            '形态': _norm(r['形态（怎么装）']) or '落地式', '台面材质': _norm(r['D8台面材质']), '台盆材质': _norm(r['D8台盆材质']),
            '元素': r['_el'], '主色': '' if col == '未知' else col, '柜体材质': '' if cab == '未知' else cab}


def import_keywords() -> int:
    if not KW.exists():
        return 0
    tag = pd.read_csv(KW / '数据' / '01_关键词词库' / 'tables' / 'keywords_tagged.csv')
    wmap = dict(zip(tag['关键词'], tag['宽度（英寸）'].map(fm.band)))
    out = []
    for f in sorted(glob.glob(str(KW / '数据' / '02_Amazon历史趋势' / 'raw' / '*.json'))):
        j = json.load(open(f, encoding='utf-8'))
        val = wmap.get(j['keyword'])
        if not isinstance(val, str) or not val:
            continue
        for r in json.loads(j['response']['content'][0]['text'])['data']:
            yy, mm = re.match(r'(\d{4})年(\d{2})月', r['time']).groups()
            out.append(dict(dim='尺寸', value=val, source='amazon', keyword=j['keyword'], month=f'{yy}-{mm}', volume=r['search']))
    if ATTR_KW.exists():
        at = pd.read_csv(ATTR_KW, encoding='utf-8-sig')
        at = at[at['关键词'].isin(KMAP)]
        for r in at.itertuples():
            v = pd.to_numeric(r.值, errors='coerce')
            out.append(dict(dim=KMAP[r.关键词][0], value=KMAP[r.关键词][1], source=r.来源, keyword=r.关键词, month=r.月, volume=None if pd.isna(v) else float(v)))
    with session() as s:
        s.query(SearchVolume).delete()
        s.execute(insert(SearchVolume), out)
    return len(out)


def import_amazon(log=print, until: str | None = None) -> dict:
    A = rows_from_pkl()
    if until:  # 只导到某月（回归测试固定在第二轮的 2024-10 至 2026-09；统一打标表 2026-11-04 起并入了 2026-10）
        A = A[A['月份'].astype(str) <= until].reset_index(drop=True)
    log(f'读入 {len(A):,} 行（{A["月份"].min()} 至 {A["月份"].max()}）')
    tags_rows = [row_tags(r) for _, r in A.iterrows()]
    A['_tags'] = tags_rows
    with session() as s:
        if s.scalar(select(func.count()).select_from(Batch).where(Batch.channel == 'amazon', Batch.source == 'v2')):
            raise RuntimeError('第二轮数据已导入过；如需重导请换一个空的数据目录')
    # 商品：取最后一个月的行
    last = A.sort_values('月份').drop_duplicates('子ASIN', keep='last')
    with session() as s:
        have = {p for (p,) in s.execute(select(Product.item_id).where(Product.channel == 'amazon'))}
        prods = [dict(channel='amazon', item_id=r['子ASIN'], parent=_norm(r['父体字段']), family_key=_norm(r['家族键']), brand=_norm(r['品牌']),
                      title=_norm(r['标题']), image_url=_norm(r['主图500']), link=_norm(r['商品链接']), listed_at=_norm(r['上架日期'])[:10], excluded=False)
                 for _, r in last.iterrows() if r['子ASIN'] not in have]
        if prods:
            s.execute(insert(Product), prods)
    from .tagging import img_key
    with session() as s:
        tags = []
        for _, r in last.iterrows():
            t = r['_tags']
            grp = img_key(_norm(r['主图500']))
            for k, v in t.items():
                if k == '元素':
                    c = (0.95 if r['元素来源（看图）'] == 'wen 复核' else 0.85) if v else 0.0
                    src = 'vision'
                else:
                    c, src = (0.9 if v else 0.0), 'rule'
                tags.append(dict(channel='amazon', item_id=r['子ASIN'], tag=k, value=v, auto_value=v, confidence=c, source=src, status='auto',
                                 candidates=[], img_group=grp, month='', config_version=1))  # 历史导入，不算“本批新子体”
        s.execute(insert(Tag), tags)
    # 每月一个已并入批次 + 快照（按原表行顺序写入，保证与第二轮逐行一致）
    stat = {}
    prev = None
    for month, g in A.groupby('月份', sort=True):
        src = g['数据来源批次'].mode().iloc[0]
        cur = pd.DataFrame(dict(item_id=g['子ASIN'].values, family_key=g['家族键'].values, rank=g['小类BSR'].values,
                                units=pd.to_numeric(g['子体月销（家族均分）'], errors='coerce').values, in_scope=g['纳入浴室柜分析'].values))
        cur = cur[cur['in_scope']]
        cur.attrs['month'] = month
        tmap = {i: t for i, t, ok in zip(g['子ASIN'], g['_tags'], g['纳入浴室柜分析']) if ok}
        checks = vf.run(month, cur, prev, tmap, {})
        fc = next((i for i in checks['items'] if i['key'] == 'family_consistency'), None)
        star = src == '2026 v11 表'
        reason = ''
        if star:
            reason = f"数据来源切换（v11 表），家族键月间一致率 {fc['value'] if fc else '—'}"
        with session() as s:
            b = Batch(channel='amazon', month=month, source='v2', file_path=str(PKL), status='merged', checks=dict(checks, source=SOURCE_NAME.get(src, src)),
                      anomaly_reason=reason, star=star, rows=int(len(g)), merged_at=now())
            s.add(b)
            s.flush()
            bid = b.id
            snaps = []
            nz = lambda x: None if x is None or pd.isna(x) else float(x)
            for _, r in g.iterrows():
                raw = dict(family_key=r['家族键'], listed_at=_norm(r['上架日期'])[:10], in_scope=bool(r['纳入浴室柜分析']), fam_units=nz(r['家族月销']),
                           child_units=nz(r['_child']), brand=_norm(r['品牌']), source=src, tags=r['_tags'], sku=_norm(r['SKU']), dimension=_norm(r['尺寸文本']))
                u = nz(r['子体月销（家族均分）'])
                snaps.append(dict(batch_id=bid, channel='amazon', month=month, item_id=r['子ASIN'], price=nz(r['价格']), units=u,
                                  revenue=None if u is None or pd.isna(r['价格']) else u * float(r['价格']), rank=nz(r['小类BSR']), rating=nz(r['评分']),
                                  ratings_count=nz(r['评分数']), raw=raw))
            s.execute(insert(Snapshot), snaps)
        stat[month] = dict(rows=int(len(g)), star=star, status=checks['status'])
        prev = cur
        log(f'{month}：{len(g):,} 行' + ('（带 *）' if star else ''))
    return stat


def run(channels=False, suspect=False, compute=True, log=print, until: str | None = None) -> dict:
    init_db()
    out = dict(amazon=import_amazon(log, until), keywords=import_keywords())
    log(f"搜索量 {out['keywords']:,} 行")
    if channels and VP_XLSX.exists():
        from . import channels as chm
        out['channels'] = chm.import_excel(VP_XLSX, 'upload')
        log(f"其他渠道：{out['channels']}")
    if compute:
        from . import panel, pipeline
        panel.clear_cache()
        if channels:
            for ch in ('homedepot', 'lowes', 'wayfair'):
                pipeline.rescan(ch)
        log('重算评分与回测（含 Amazon 机会扫描预计算）…')
        out['run_id'] = pipeline.rescore(None)
    if suspect and SUSPECT.exists():
        from . import ingest
        df = ingest.read_file(SUSPECT)
        out['suspect_batch'] = ingest.create_batch('2026-10', df, 'upload', str(SUSPECT))
        log(f"已导入待核 2026-10 文件为批次 #{out['suspect_batch']}（核对：疑似月份错误）")
    return out


def main():
    ap = argparse.ArgumentParser(description='导入第二轮数据（2024-10 至 2026-09，含已打标结果）')
    ap.add_argument('--channels', action='store_true', help='同时导入其他渠道 VP 样本')
    ap.add_argument('--suspect', action='store_true', help='再导入“标为 2026-10 实为 9 月”的待核文件（演示疑似月份错误）')
    ap.add_argument('--no-compute', action='store_true', help='只导数据，不预计算扫描与评分')
    ap.add_argument('--channel-history', metavar='渠道', choices=['homedepot'],
                    help='只导入该渠道的历史回补缓存（../input/data_v2/渠道历史/<渠道>/）并按评论日期重建 2024-01 起的月度历史，免得重新采集')
    a = ap.parse_args()
    if a.channel_history:
        from . import backfill
        init_db()
        st = backfill.import_cache(a.channel_history, log=print)
        print(f"重建完成：{st['start']} 至 {st['end']}，{st['pages_listed']} 个在榜商品页 / {st['pages_all']} 个有评论商品页，"
              f"{st['families']} 个评论家族，评论 {st['reviews_all']:,} 条（{st['start']} 起 {st['reviews_window']:,} 条），截断 {st['truncated_pages']} 个商品页")
        return
    if not available():
        raise SystemExit(f'找不到 {PKL}（原始数据不入库，只在 wen 本机）')
    run(a.channels, a.suspect, not a.no_compute)


if __name__ == '__main__':
    main()
