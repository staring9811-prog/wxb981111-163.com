"""Amazon 月度数据进入（F17）：卖家精灵接口拉取（费用闸门任务 amazon_pull，按页分片、断点续拉）、手动上传、建批次、核对、并入 / 放弃。

原始文件与每月并入版本都保留（NFR-012）：上传文件、每页拉取结果存 data/raw/amazon/<月份>/；批次与快照不删，
同月再次并入时旧批次标为 superseded（可回看），分析只用 merged 批次。
"""
import html
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func, insert, select

from .. import catconfig, costgate, services
from ..config import data_dir
from ..db import session
from ..models import Batch, Job, Product, Snapshot, Tag, now
from ..models_data import DataNote
from . import families as fm
from . import verify as vf

VANITY_NODE = '6810202011'  # 亚马逊 Bathroom Vanities 小类节点
PAGE_SIZE = 100

# 规范列 → 可接受的表头（卖家精灵接口 JSON/CSV、卖家精灵网页“类目选品”导出、第二轮已打标表）
ALIASES = {
    'item_id': ['asin', 'ASIN', '子ASIN', '子 ASIN'],
    'parent': ['parent', '父ASIN', '核验父ASIN', '父体', '父体字段'],
    'brand': ['brand', '品牌'],
    'title': ['title', '商品标题', '标题'],
    'price': ['price', '价格($)', '价格', '商品价格'],
    'units': ['units', '月销量', '父体月销量', '家族月销', '父体月销量预测'],
    'rank': ['rank', '小类排名', '小类BSR', '目标月校验小类BSR'],
    'rating': ['rating', '评分', '商品评分'],
    'ratings_count': ['ratings', '评分数', '评分数量'],
    'listed_at': ['availableDate', '上架时间', '上架日期'],
    'variations': ['variations', '变体数'],
    'image_url': ['imageUrl', '商品主图', '主图链接', '主图500'],
    'link': ['link', '商品详情页链接', '商品链接'],
    'sku': ['sku', 'SKU', 'SKU属性'],
    'dimension': ['dimension', '商品尺寸'],
    'features': ['features', '五点描述', '详细参数'],
    'purchase_date': ['amzUnitDate', '上月购买标日期', '上月购买标（MCP）日期'],
    'subcategories': ['subcategories', '子类目列表'],
    'month': ['月份', '目标月份'],
}
REQUIRED = [('item_id', 'ASIN'), ('units', '月销量'), ('rank', '小类排名'), ('price', '价格')]
TAG_COLS = ['D1产品形态', 'D2安装方式', 'D5元素', 'D6柜体颜色', 'D7柜体材质', 'D8台面材质', 'D8台盆材质', 'D9宽(in)']


class FileFormatError(ValueError):
    pass


def raw_dir(month: str) -> Path:
    d = data_dir() / 'raw' / 'amazon' / month
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ms_date(v):
    """毫秒时间戳 / 日期文本 → YYYY-MM-DD。"""
    if v is None or (isinstance(v, float) and np.isnan(v)) or v == '' or v == -1:
        return ''
    try:
        x = float(v)
        if x > 1e11:
            return datetime.fromtimestamp(x / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
    except (TypeError, ValueError):
        pass
    d = pd.to_datetime(str(v), errors='coerce')
    return '' if pd.isna(d) else d.strftime('%Y-%m-%d')


def _sub_rank(v):
    """卖家精灵 subcategories → 浴室柜小类排名。"""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except json.JSONDecodeError:
            return np.nan
    for x in v or []:
        if str(x.get('code')) == VANITY_NODE:
            return x.get('rank')
    return np.nan


def normalize(df: pd.DataFrame, source_name: str = '') -> pd.DataFrame:
    """任意支持的表头 → 规范列；缺必需列时抛 FileFormatError（指出列名）。"""
    cols = {}
    for canon, al in ALIASES.items():
        for a in al:
            if a in df.columns:
                cols[canon] = a
                break
    if 'rank' not in cols and 'subcategories' in cols:
        df = df.assign(_rank=df[cols['subcategories']].map(_sub_rank))
        cols['rank'] = '_rank'
    miss = [label for k, label in REQUIRED if k not in cols]
    if miss:
        raise FileFormatError(f"{source_name or '文件'}缺少“{'”“'.join(miss)}”列（第 1 行表头）。请用卖家精灵“类目选品”导出同格式文件（勾选全部字段）后重新上传。")
    out = pd.DataFrame({k: df[c].values for k, c in cols.items() if k != 'subcategories'})
    out['item_id'] = out['item_id'].astype(str).str.strip()
    out = out[out['item_id'].str.match(r'^[A-Z0-9]{10}$', na=False)].copy()
    out['parent'] = out.get('parent', pd.Series('', index=out.index)).fillna('').astype(str).str.strip()
    out['family_key'] = np.where(out['parent'].isin(['', 'nan', 'None']), out['item_id'], out['parent'])
    for k in ('price', 'units', 'rank', 'rating', 'ratings_count', 'variations'):
        out[k] = pd.to_numeric(out.get(k, np.nan), errors='coerce')
    out.loc[out['rank'] < 0, 'rank'] = np.nan
    out.loc[out['price'] < 0, 'price'] = np.nan
    for k in ('listed_at', 'purchase_date'):
        out[k] = out[k].map(_ms_date) if k in out else ''
    for k in ('brand', 'title', 'image_url', 'link', 'sku', 'dimension', 'features'):
        out[k] = out[k].fillna('').astype(str) if k in out else ''
    out['link'] = [l or f'https://www.amazon.com/dp/{a}' for l, a in zip(out['link'], out['item_id'])]
    out['title'] = out['title'].map(html.unescape)
    # 已打标表：带 D1–D9 / 看图元素时直接作为该行标签
    if any(c in df.columns for c in TAG_COLS):
        src = df.loc[out.index]
        out['tags'] = [file_tags(r) for _, r in src.iterrows()]
    out = out.drop_duplicates('item_id').reset_index(drop=True)
    return out


def file_tags(r) -> dict:
    g = r.get
    el = g('元素（看图）')
    if isinstance(el, str) and el:
        e = '|'.join(x for x in fm.img_el(el) if x not in ('fluted', 'reeded'))
    else:
        from .tagging import DEFAULT_TAG_RULES
        em = DEFAULT_TAG_RULES['element_map']
        e = '|'.join(dict.fromkeys(em[x] for x in str(g('D5元素') or '').split('；') if x in em))
    norm = lambda v: '' if v is None or (isinstance(v, float) and np.isnan(v)) or str(v) in fm.RAW_UNK else str(v)
    color = fm.color(g('D6柜体颜色'))
    cabv = fm.cab(g('D7柜体材质（价格复核前）') if g('D7柜体材质（价格复核前）') is not None else g('D7柜体材质'))
    return {'尺寸段': fm.band(g('D9宽(in)')) or '', '装': '整装' if g('D2安装方式') == '整装' else '拆装',
            '形态': norm(g('形态（怎么装）')) or norm(g('D1产品形态')) or '落地式', '台面材质': norm(g('D8台面材质')), '台盆材质': norm(g('D8台盆材质')),
            '元素': e, '主色': '' if color == '未知' else color, '柜体材质': '' if cabv == '未知' else cabv}


def read_file(path: Path) -> pd.DataFrame:
    name = path.name
    if path.suffix.lower() == '.csv':
        df = pd.read_csv(path, dtype={'asin': str, 'parent': str}, encoding='utf-8-sig')
    elif path.suffix.lower() == '.json':
        j = json.loads(path.read_text(encoding='utf-8'))
        rows = j.get('items') if isinstance(j, dict) else j
        df = pd.DataFrame(rows)
    elif path.suffix.lower() in ('.xlsx', '.xlsm'):
        xl = pd.ExcelFile(path)
        sheet = next((s for s in xl.sheet_names if any(k in s for k in ('Competitor', 'Product', '明细', 'Sheet'))), xl.sheet_names[0])
        df = xl.parse(sheet)
    else:
        raise FileFormatError(f'{name} 不是 .xlsx / .csv / .json 文件')
    return normalize(df, name)


# ---------------- 批次 ----------------
def prev_merged_month(month: str, channel='amazon'):
    with session() as s:
        return s.scalar(select(func.max(Batch.month)).where(Batch.channel == channel, Batch.status == 'merged', Batch.month < month))


def month_frame(month: str, channel='amazon', batch_id: int | None = None) -> pd.DataFrame:
    """某月（已并入版本，或指定批次）的商品行：item_id, family_key, rank, units。"""
    with session() as s:
        if batch_id is None:
            batch_id = s.scalar(select(Batch.id).where(Batch.channel == channel, Batch.month == month, Batch.status == 'merged').order_by(Batch.id.desc()))
        if batch_id is None:
            return pd.DataFrame(columns=['item_id', 'family_key', 'rank', 'units'])
        rows = [(sn.item_id, (sn.raw or {}).get('family_key') or sn.item_id, sn.rank, sn.units, (sn.raw or {}).get('purchase_date', ''), (sn.raw or {}).get('in_scope', True))
                for sn in s.scalars(select(Snapshot).where(Snapshot.batch_id == batch_id))]
    df = pd.DataFrame(rows, columns=['item_id', 'family_key', 'rank', 'units', 'purchase_date', 'in_scope'])
    df = df[df['in_scope'] != False]  # noqa: E712
    df.attrs['month'] = month
    return df


def current_tags(items, channel='amazon', batch_id=None) -> dict:
    """覆盖率用：确认值 > 本批行内标签 > 当前自动值。"""
    out = {}
    with session() as s:
        for t in s.scalars(select(Tag).where(Tag.channel == channel, Tag.item_id.in_(list(items)))):
            out.setdefault(t.item_id, {})[t.tag] = (t.value, t.status)
        rowtags = {}
        if batch_id is not None:
            for sn in s.scalars(select(Snapshot).where(Snapshot.batch_id == batch_id)):
                if (sn.raw or {}).get('tags'):
                    rowtags[sn.item_id] = sn.raw['tags']
    res = {}
    for i in items:
        d = {k: v for k, (v, st) in out.get(i, {}).items()}
        for k, v in (rowtags.get(i) or {}).items():
            if out.get(i, {}).get(k, ('', ''))[1] != 'confirmed':
                d[k] = v
        res[i] = d
    return res


def create_batch(month: str, df: pd.DataFrame, source: str, file_path: str = '', job_id: int | None = None, channel='amazon') -> int:
    """建批次 → 写商品与快照（未并入）→ 新商品规则打标 → 核对。返回批次 ID。"""
    fam_n = df.groupby('family_key')['item_id'].transform('nunique')
    df = df.assign(c=df['units'] / fam_n)
    with session() as s:
        b = Batch(channel=channel, month=month, source=source, file_path=str(file_path), status='checking', rows=int(len(df)), job_id=job_id)
        s.add(b)
        s.flush()
        bid = b.id
        have = {p.item_id: p for p in s.scalars(select(Product).where(Product.channel == channel, Product.item_id.in_(list(df['item_id']))))}
        for r in df.itertuples():
            p = have.get(r.item_id)
            if p is None:
                p = Product(channel=channel, item_id=r.item_id)
                s.add(p)
            for k in ('parent', 'family_key', 'brand', 'title', 'image_url', 'link', 'listed_at'):
                v = getattr(r, k, '')
                if isinstance(v, str) and v and v not in ('nan', 'None'):
                    setattr(p, k, v[:10] if k == 'listed_at' else v)
        snaps = []
        for r in df.to_dict('records'):
            raw = dict(family_key=r['family_key'], listed_at=r.get('listed_at', ''), fam_units=None if pd.isna(r['units']) else float(r['units']),
                       child_units=None, purchase_date=r.get('purchase_date', ''), sku=r.get('sku', ''), dimension=r.get('dimension', ''),
                       features=str(r.get('features', ''))[:4000], variations=None if pd.isna(r.get('variations')) else float(r['variations']),
                       title=r.get('title', ''), brand=r.get('brand', ''), source=source, in_scope=True)
            if isinstance(r.get('tags'), dict):
                raw['tags'] = r['tags']
            nz = lambda x: None if x is None or pd.isna(x) else float(x)
            snaps.append(dict(batch_id=bid, channel=channel, month=month, item_id=r['item_id'], price=nz(r['price']), units=nz(r['c']),
                              revenue=nz(r['c'] * r['price']) if not pd.isna(r['price']) and not pd.isna(r['c']) else None,
                              rank=nz(r['rank']), rating=nz(r.get('rating')), ratings_count=nz(r.get('ratings_count')), raw=raw))
        s.execute(insert(Snapshot), snaps)
    # 新商品规则打标（免费、本地），覆盖率核对用
    from . import tagging
    new_items = [i for i in df['item_id'] if i not in have]
    if new_items:
        tagging.tag_products(channel, new_items, month)
    recheck(bid)
    return bid


def recheck(batch_id: int) -> dict:
    with session() as s:
        b = s.get(Batch, batch_id)
        month, channel = b.month, b.channel
    cur = month_frame(month, channel, batch_id)
    pm = prev_merged_month(month, channel)
    prev = month_frame(pm, channel) if pm else None
    cfg = catconfig.current()[1].get('verify') or {}
    prev_cov = vf.coverage(list(dict.fromkeys(prev['item_id'])), current_tags(prev['item_id'], channel)) if prev is not None and not prev.empty else None
    checks = vf.run(month, cur, prev, current_tags(cur['item_id'], channel, batch_id), cfg, prev_cov)
    with session() as s:
        b = s.get(Batch, batch_id)
        if b.status in ('checking', 'ok', 'anomaly', 'suspect_month'):
            b.status = checks['status']
        b.checks = checks
        b.anomaly_reason = checks['reason']
    return checks


def recheck_stuck() -> list[int]:
    """启动时补做核对：建批次后进程中断（核对没跑完）的批次会一直停在“核对中”，与其他页面显示不一致。
    启动时没有在跑的任务，凡仍是 checking 的批次都重新核对一次，状态落到疑似 / 异常 / 通过。"""
    with session() as s:
        ids = list(s.scalars(select(Batch.id).where(Batch.status == 'checking')))
        # 未并入的批次若还是旧覆盖率规则（每项 ≥ 95%）的核对结果，按当前规则重核（DEC-102 wen 2026-11-03 调整）；已并入的历史批次保留当时记录
        for b in s.scalars(select(Batch).where(Batch.channel == 'amazon', Batch.status.in_(['anomaly', 'ok', 'suspect_month']))):
            tc = next((i for i in (b.checks or {}).get('items', []) if i.get('key') == 'tag_coverage'), None)
            if tc is not None and 'drop' not in tc and b.id not in ids:
                ids.append(b.id)
    for bid in ids:
        recheck(bid)
    return ids


def merge(batch_id: int, user_id: int | None, note: str = '', confirm_anomaly: bool = False) -> tuple[bool, str]:
    """并入。疑似月份错误不能并入；异常需确认，并入后带 * 与原因（AC-F17-05）。"""
    with session() as s:
        b = s.get(Batch, batch_id)
        if b is None:
            return False, '批次不存在'
        if b.status == 'suspect_month':
            return False, f'{b.month} 疑似月份错误，不能并入；请重新拉取或手动上传'
        if b.status == 'anomaly' and not confirm_anomaly:
            return False, '核对有异常，需确认后才能并入'
        if b.status not in ('ok', 'anomaly'):
            return False, f'批次状态为 {b.status}，不能并入'
        if b.status == 'anomaly':
            b.star = True
            b.anomaly_reason = (b.anomaly_reason or '') + (f'；说明：{note}' if note else '')
        for old in s.scalars(select(Batch).where(Batch.channel == b.channel, Batch.month == b.month, Batch.status == 'merged', Batch.id != b.id)):
            old.status = 'superseded'
        b.status, b.merged_at, b.merged_by = 'merged', now(), user_id
        s.add(DataNote(batch_id=b.id, user_id=user_id, kind='anomaly_confirm' if b.star else 'merge', text=note or ''))
        ch, month = b.channel, b.month
    from . import panel, pipeline
    panel.clear_cache()
    pipeline.after_merge(ch, month)
    return True, f'{month}{"*" if b.star else ""} 已并入，已对新商品规则打标，去打标确认'


def reject(batch_id: int, user_id: int | None, note: str = '') -> bool:
    with session() as s:
        b = s.get(Batch, batch_id)
        if b is None or b.status == 'merged':
            return False
        b.status = 'rejected'
        s.add(DataNote(batch_id=b.id, user_id=user_id, kind='reject', text=note or ''))
        return True


def save_upload(month: str, filename: str, content: bytes) -> Path:
    safe = re.sub(r'[^\w.\-（）()]+', '_', filename)[-120:] or 'upload.xlsx'
    p = raw_dir(month) / f"{datetime.now():%Y%m%d%H%M%S}_{safe}"
    p.write_bytes(content)
    return p


def upload(month: str, filename: str, content: bytes) -> int:
    p = save_upload(month, filename, content)
    df = read_file(p)
    if 'month' in df and df['month'].astype(str).str.len().gt(0).any():
        df = df.drop(columns=['month'])
    return create_batch(month, df, 'upload', str(p))


# ---------------- 卖家精灵拉取（费用闸门任务） ----------------
def _round(month: str) -> int:
    """第几轮拉取：已经由拉取建成的批次数 + 1。已并入月份再次拉取会开新一轮（新批次，旧版本保留）。"""
    with session() as s:
        return (s.scalar(select(func.count()).select_from(Batch).where(Batch.channel == 'amazon', Batch.month == month, Batch.source == 'api')) or 0) + 1


def _pull_est(params):
    month = params.get('month')
    services.client('sellersprite')  # 未连接即抛 NotConnected，不发起调用（AC-F16-03）
    with session() as s:
        n = s.scalar(select(Batch.rows).where(Batch.channel == 'amazon', Batch.status == 'merged').order_by(Batch.month.desc()).limit(1)) or 2900
    pages = math.ceil(n / PAGE_SIZE) + 1
    r = _round(month)
    done = 0
    with session() as s:
        from ..models import Shard
        done = s.scalar(select(func.count()).select_from(Shard).where(Shard.kind == 'amazon_pull', Shard.month == month, Shard.key.like(f'r{r}-%'))) or 0
    left = max(1, pages - done)
    return dict(service='sellersprite', calls=left, usd_lo=round(left * 0.01, 2), usd_hi=round(left * 0.012, 2), minutes=round(max(1, left * 0.15), 1),
                note=f'约 {n:,} 个 ASIN，每页 {PAGE_SIZE} 个' + (f'；已拉 {done} 页，只拉缺的部分' if done else ''))


def _duplicate(ctx) -> bool:
    """同一月份同时只运行一个拉取任务：本任务创建时另一任务仍在进行（或在本任务之后才结束）即视为重复发起。"""
    with session() as s:
        me = s.get(Job, ctx.id)
        for j in s.scalars(select(Job).where(Job.kind == 'amazon_pull', Job.month == ctx.month, Job.id != ctx.id, Job.id < ctx.id)):
            if j.status in ('running', 'queued') or (j.status == 'done' and j.finished_at and j.finished_at > me.created_at and (j.progress or {}).get('batch_id')):
                return True
    return False


def _pull_run(ctx):
    month = ctx.month
    if _duplicate(ctx):
        ctx.progress(duplicate=True, note='同一月份已有拉取任务，本次未重复调用')
        return
    client = services.client('sellersprite')
    r = _round(month)
    seg = dict(start=now().strftime('%m-%d %H:%M'), pages=0, rows=0, calls=0, usd=0.0, end='', reason='')
    segs = list((ctx.job.progress or {}).get('segments') or [])
    rows_all, page = [], 1
    try:
        while True:
            key = f'r{r}-p{page}'
            path = raw_dir(month) / f'pull_r{r}_p{page}.json'
            if ctx.shard_done(key) and path.exists():
                rows = json.loads(path.read_text(encoding='utf-8'))
            else:
                ctx.allow('sellersprite', qty=1, amount=0.01)
                rows, calls = client.product_month(month, page)
                calls = calls or 1
                ctx.charge('sellersprite', qty=calls, amount=0.01 * calls, task=f'拉取 Amazon {month} 第 {page} 页')
                path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
                ctx.mark_shard(key, str(path))
                seg['pages'] += 1
                seg['rows'] += len(rows)
                seg['calls'] += calls
                seg['usd'] += 0.01 * calls
            rows_all += rows
            ctx.progress(fetched=len(rows_all), page=page, step='拉取商品月度字段', segments=segs + [seg], round=r)
            if not rows:
                break
            page += 1
        seg['end'], seg['reason'] = now().strftime('%H:%M'), '完成'
    except costgate.CapReached:
        seg['end'], seg['reason'] = now().strftime('%H:%M'), '已达上限'
        ctx.progress(segments=segs + [seg])
        raise
    except costgate.Paused:
        seg['end'], seg['reason'] = now().strftime('%H:%M'), '已暂停'
        ctx.progress(segments=segs + [seg])
        if _job_progress(ctx.id).get('abandoned'):
            _set_aside(month, r, ctx.id)
        raise
    except Exception as e:
        seg['end'], seg['reason'] = now().strftime('%H:%M'), f'中断（{type(e).__name__}: {e}）'
        ctx.progress(segments=segs + [seg])
        raise
    if _job_progress(ctx.id).get('abandoned'):  # 拉完最后一页前刚点了“放弃本批”：不建批次、不并入
        _set_aside(month, r, ctx.id)
        raise costgate.Paused()
    df = normalize(pd.DataFrame(rows_all), f'卖家精灵接口 {month}')
    full = raw_dir(month) / f'pull_r{r}_全部.json'
    full.write_text(json.dumps(rows_all, ensure_ascii=False), encoding='utf-8')
    ctx.progress(step='核对', segments=segs + [seg])
    bid = create_batch(month, df, 'api', str(full), job_id=ctx.id)
    ctx.progress(batch_id=bid, step='核对完成')


costgate.register('amazon_pull', '拉取 Amazon 月度数据', _pull_est, _pull_run)


def _job_progress(job_id: int) -> dict:
    with session() as s:
        j = s.get(Job, job_id)
        return dict(j.progress or {}) if j else {}


def _set_aside(month: str, r: int, job_id: int) -> str:
    """放弃本批后，把本轮已拉分片挪到原始文件目录下的“放弃_任务号”子目录（文件保留、不并入），
    并让分片记录失效，下次拉取同月从头开始，不会误用放弃的分片。返回子目录名。"""
    from ..models import Shard
    sub = raw_dir(month) / f'放弃_任务{job_id}_{now():%Y%m%d%H%M}'
    sub.mkdir(parents=True, exist_ok=True)
    for f in raw_dir(month).glob(f'pull_r{r}_p*.json'):
        f.rename(sub / f.name)
    with session() as s:
        for sh in s.scalars(select(Shard).where(Shard.kind == 'amazon_pull', Shard.month == month, Shard.key.like(f'r{r}-%'))):
            sh.key = f'放弃{job_id}-{sh.key}'
            if sh.payload_path:
                sh.payload_path = str(sub / Path(sh.payload_path).name)
    return sub.name


def abandon_pull(job_id: int, user_id: int | None) -> tuple[bool, str]:
    """“放弃本批”（拉取中 / 已暂停 / 已达上限 / 中断，PAGE-F17-01）：任务记为已取消，已拉分片保留在原始文件目录但不并入。
    运行中的任务先请求暂停，停下后由费用闸门记为已取消；同月之前暂停未续完的拉取任务一并取消。"""
    with session() as s:
        j = s.get(Job, job_id)
        if j is None or j.kind != 'amazon_pull':
            return False, '任务不存在'
        if j.status not in ('running', 'queued', 'paused', 'stopped_cap', 'failed') or (j.progress or {}).get('batch_id'):
            return False, '该任务已结束，不能放弃'
        month, fetched = j.month, (j.progress or {}).get('fetched') or 0
        note = f'已放弃本批：已拉 {fetched:,} 个 ASIN 的分片保留在原始文件目录，不并入分析'
        running = j.status in ('running', 'queued')
        for o in s.scalars(select(Job).where(Job.kind == 'amazon_pull', Job.month == month, Job.status.in_(['paused', 'stopped_cap', 'failed']))):
            if not (o.progress or {}).get('batch_id'):
                o.status, o.error, o.finished_at = 'cancelled', note, now()
                o.progress = dict(o.progress or {}, abandoned=True, abandon_note=note, abandoned_by=user_id)
        if running:
            j.progress = dict(j.progress or {}, abandoned=True, abandon_note=note, abandoned_by=user_id, pause_requested=True)
            return True, f'已请求放弃 {month} 本批：当前页拉完即停止，已拉分片保留在原始文件目录，不并入分析'
    sub = _set_aside(month, _round(month), job_id)
    return True, f'{note}（{raw_dir(month).relative_to(data_dir())}/{sub}）'


def pull_segments(month: str) -> list[dict]:
    """同月本轮各次拉取记录（第 1 次 / 续拉），供页面显示。已放弃的拉取不算本轮。"""
    out = []
    with session() as s:
        for j in s.scalars(select(Job).where(Job.kind == 'amazon_pull', Job.month == month).order_by(Job.id)):
            if (j.progress or {}).get('abandoned'):
                continue
            for sg in (j.progress or {}).get('segments') or []:
                out.append(dict(sg, job_id=j.id, status=j.status))
    return out


def start_pull(month: str, user_id: int | None) -> Job:
    """API-F17-01：发起拉取（估算）。同月已有未确认或进行中的任务时返回该任务，不另建（RULE-04）。"""
    with session() as s:
        j = s.scalar(select(Job).where(Job.kind == 'amazon_pull', Job.month == month, Job.status.in_(['estimated', 'queued', 'running'])).order_by(Job.id.desc()))
        if j is not None:
            s.expunge(j)
            return j
    return costgate.estimate('amazon_pull', {}, user_id, month=month)
