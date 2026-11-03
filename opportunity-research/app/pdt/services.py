"""外部服务入口。业务代码只通过 `client(name)` 取客户端，测试用 `set_fake(name, obj)` 替换为假服务。

密钥从 Secret 表解密读取，绝不写日志、不回传页面（NFR-008）。
各客户端的具体实现放在 pdt/clients/ 下，由对应模块提供：
- sellersprite: test(), product_month(month, page) -> (rows, cost_calls), reviews(asin, stars, limit)
- brightdata / apify: test() 以及评论 VP 追踪器 reviewkit 所需调用
- llm: test(), complete(prompt, images=None) -> (text, usage_usd)
"""
from sqlalchemy import select

from .db import session
from .models import Secret, Setting, now
from .security import decrypt, encrypt, mask

_fakes: dict[str, object] = {}


class NotConnected(Exception):
    def __init__(self, name):
        super().__init__(f"{name} 未连接：请在设置页填写密钥")


def set_fake(name: str, obj):
    _fakes[name] = obj


def clear_fakes():
    _fakes.clear()


def get_setting(key: str, default=None):
    with session() as s:
        r = s.get(Setting, key)
        return r.value if r else default


def put_setting(key: str, value):
    with session() as s:
        r = s.get(Setting, key)
        if r:
            r.value = value
        else:
            s.add(Setting(key=key, value=value))


def llm_slot() -> str:
    """当前所选大模型提供方对应的密钥槽位（AC-F16-04）。"""
    return "llm_" + (get_setting("llm", {}) or {}).get("provider", "claude")


def secret(slot: str) -> str | None:
    with session() as s:
        r = s.get(Secret, slot)
        return decrypt(r.enc_value) if r else None


def save_secret(slot: str, value: str):
    with session() as s:
        r = s.get(Secret, slot)
        if r:
            r.enc_value, r.last4, r.updated_at = encrypt(value), mask(value), now()
            r.test_status, r.test_msg, r.tested_at = "", "", None
        else:
            s.add(Secret(slot=slot, enc_value=encrypt(value), last4=mask(value)))


def delete_secret(slot: str):
    with session() as s:
        r = s.get(Secret, slot)
        if r:
            s.delete(r)


def connected(name: str) -> bool:
    slot = llm_slot() if name == "llm" else name
    with session() as s:
        return s.scalar(select(Secret.slot).where(Secret.slot == slot)) is not None


def client(name: str):
    """name ∈ sellersprite / brightdata / apify / llm。未配置密钥时抛 NotConnected，不发起调用（AC-F16-03）。"""
    if name in _fakes:
        if not connected(name):
            raise NotConnected(name)
        return _fakes[name]
    slot = llm_slot() if name == "llm" else name
    key = secret(slot)
    if not key:
        raise NotConnected(name)
    from . import clients
    return clients.make(slot, key, get_setting("llm", {}) or {})
