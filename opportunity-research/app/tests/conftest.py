"""测试公共夹具：每个测试独立数据目录、同步执行任务、假外部服务。"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PDT_SYNC_JOBS"] = "1"


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PDT_DATA", str(tmp_path))
    monkeypatch.setenv("PDT_INIT_PASSWORD", "wen-初始-密码")
    from pdt import db, services
    db.reset_engine()
    services.clear_fakes()
    from pdt.main import create_app
    app = create_app()
    yield app
    services.clear_fakes()
    db.reset_engine()


@pytest.fixture()
def client(app_env):
    from fastapi.testclient import TestClient
    return TestClient(app_env)


def login_as(client, username="wen", password="wen-初始-密码"):
    r = client.post("/login", data={"account": username, "password": password}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return client


def make_user(username, name, role, password="密码-123456"):
    from pdt.db import session
    from pdt.models import User
    from pdt.security import hash_pw
    with session() as s:
        s.add(User(username=username, name=name, role=role, pw_hash=hash_pw(password)))
    return password


@pytest.fixture()
def wen(client):
    return login_as(client)
