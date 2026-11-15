"""分析组测试的公共夹具：第二轮数据导入（每次测试会话只导一次，之后每个测试复制一份数据库）、假卖家精灵 / 大模型、合成月度数据。"""
import json
import os
import shutil
from datetime import datetime, timezone

import pandas as pd
import pytest

from conftest import login_as

_BASE = {}
PW = 'wen-初始-密码'

BRANDS = ['Yaheetech', 'ARIEL', 'eclife', 'WOODBRIDGE', 'Kohler', 'Home Decorators Collection', 'Glacier Bay', 'VEVOR', 'HOMCOM', 'Wade Logan']
STYLES = [('Shaker', '30 Inch White Shaker Bathroom Vanity with Ceramic Sink Countertop', 30),
          ('Fluted', '36 Inch Fluted Bathroom Vanity with Resin Sink Top, Natural Oak, Freestanding', 36),
          ('', '24 Inch Wall Mounted Floating Bathroom Vanity with Sink, Black', 24),
          ('Barn Door', '48 Inch Farmhouse Bathroom Vanity with Barn Doors and Carrara Marble Top', 48),
          ('Glass Door', '30" Bathroom Vanity with Glass Doors and Undermount Sink, Grey', 30)]


def seed_available():
    from pdt.core import seed
    return seed.available()


def _base(tmp_path_factory):
    if 'p' in _BASE:
        return _BASE['p']
    from pdt import db, services
    old = {k: os.environ.get(k) for k in ('PDT_DATA', 'PDT_INIT_PASSWORD')}
    d = tmp_path_factory.mktemp('v2base')
    os.environ['PDT_DATA'], os.environ['PDT_INIT_PASSWORD'] = str(d), PW
    db.reset_engine()
    services.clear_fakes()
    from pdt.core import panel, seed
    panel.clear_cache()
    seed.run(channels=True, suspect=False, compute=True, log=lambda m: None, until='2026-09')  # 期望值来自第二轮（数据到 2026-09）
    from pdt.main import create_app
    create_app()  # 建初始操作者 wen
    from sqlalchemy import text
    with db.engine().connect() as c:
        c.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
    db.reset_engine()
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _BASE['p'] = d
    return d


@pytest.fixture()
def v2(tmp_path, tmp_path_factory, monkeypatch):
    """已导入第二轮数据（2024-10 至 2026-09 + 其他渠道样本 + 预计算扫描与评分）的已登录操作者客户端。原始数据缺失时跳过。"""
    if not seed_available():
        pytest.skip('本机没有 ../input/data_v2/统一打标/统一打标_分析用.pkl（原始数据不入库），跳过回归测试')
    base = _base(tmp_path_factory)
    shutil.copy(base / 'pdt.sqlite3', tmp_path / 'pdt.sqlite3')
    monkeypatch.setenv('PDT_DATA', str(tmp_path))
    monkeypatch.setenv('PDT_INIT_PASSWORD', PW)
    from pdt import db, services
    from pdt.core import panel
    db.reset_engine()
    services.clear_fakes()
    panel.clear_cache()
    from fastapi.testclient import TestClient
    from pdt.main import create_app
    c = TestClient(create_app())
    login_as(c)
    yield c
    services.clear_fakes()
    db.reset_engine()


def ms_ts(s):
    return int(datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() * 1000)


def api_rows(month: str, n: int = 230, rank_shift: int = 0, units_scale: float = 1.0, purchase_day: str | None = None) -> list[dict]:
    """卖家精灵接口格式（asin / parent / brand / units / subcategories …）的一个月合成数据。"""
    rows = []
    for i in range(n):
        st, title, w = STYLES[i % len(STYLES)]
        fam = i // 3
        asin = f'B0SYN{i:05d}'
        rows.append(dict(asin=asin, parent=f'B0FAM{fam:05d}', brand=BRANDS[fam % len(BRANDS)], title=f'{BRANDS[fam % len(BRANDS)]} {title}',
                         price=199.99 + (i % 7) * 40, units=int((300 - (i % 97) * 2) * units_scale), variations=3,
                         subcategories=json.dumps([{'code': '6810202011', 'rank': i + 1 + rank_shift, 'label': 'Bathroom Vanities'}]),
                         rating=4.0 + (i % 9) / 10, ratings=120 + i, availableDate=ms_ts('2025-06-15' if i % 4 else '2026-05-02'),
                         imageUrl=f'https://m.media-amazon.com/images/I/IMG{fam:05d}._AC_US200_.jpg', sku=f'Color: White | Size: {w} Inch',
                         dimension=f'18.5 x {w} x 34 inches', amzUnitDate=ms_ts(purchase_day or f'{month}-17')))
    return rows


class FakeSellerSprite:
    """假卖家精灵：按页返回，记录每次调用；fail_at 页抛网络错误（模拟中断）。"""

    def __init__(self, month_rows: dict, page_size=100, fail_at=None):
        self.month_rows, self.page_size, self.fail_at, self.calls = month_rows, page_size, fail_at, []

    def test(self):
        return True

    def product_month(self, month, page):
        self.calls.append((month, page))
        if self.fail_at and page == self.fail_at:
            self.fail_at = None
            raise ConnectionError('网络超时')
        rows = self.month_rows.get(month, [])
        return rows[(page - 1) * self.page_size: page * self.page_size], 1


class FakeLLM:
    def __init__(self, element='竖棱', conf=0.82):
        self.element, self.conf, self.calls = element, conf, []

    def test(self):
        return True

    def complete(self, prompt, images=None):
        self.calls.append((prompt, images))
        return json.dumps({'element': self.element, 'confidence': self.conf, 'alternatives': [{'element': '木条格栅', 'confidence': 0.12}]}, ensure_ascii=False), 0.006


def export_xlsx(path, month, n=60, rank_shift=0, units_scale=1.0, family_suffix='', tagged=True):
    """卖家精灵网页“类目选品”导出格式（中文表头），带 D1–D9 打标列（已打标表）。"""
    rows = []
    for r in api_rows(month, n, rank_shift, units_scale):
        st, title, w = next(s for s in STYLES if s[1] in r['title'])
        d = {'ASIN': r['asin'], 'SKU': r['sku'], '品牌': r['brand'], '商品标题': r['title'], '商品详情页链接': f"https://www.amazon.com/dp/{r['asin']}",
             '商品主图': r['imageUrl'], '父ASIN': r['parent'] + family_suffix, '小类BSR': json.loads(r['subcategories'])[0]['rank'], '月销量': r['units'],
             '变体数': 3, '价格($)': r['price'], '评分数': r['ratings'], '评分': r['rating'], '上架时间': '2025-06-15', '商品尺寸': r['dimension'], '月份': month}
        if tagged:
            d.update({'D1产品形态': '悬浮式' if 'Floating' in title else '落地式', 'D2安装方式': '拆装', 'D5元素': st or '待图片核验', 'D6柜体颜色': '白色',
                      'D7柜体材质': 'MDF', 'D8台面材质': '陶瓷', 'D8台盆材质': '陶瓷盆', 'D9宽(in)': w})
        rows.append(d)
    pd.DataFrame(rows).to_excel(path, index=False, sheet_name='Competitor-US')
    return path


def set_secret(name):
    from pdt import services
    services.save_secret(name if name != 'llm' else services.llm_slot(), 'sk-测试密钥-0000-1234')
