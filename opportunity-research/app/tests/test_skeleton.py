from conftest import login_as, make_user


def test_unauthenticated_redirect(client):
    for p in ["/", "/scan", "/cards", "/ledger"]:
        r = client.get(p, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_login_and_home(wen):
    r = wen.get("/")
    assert r.status_code == 200 and "工作台" in r.text and 'name="page-id" content="PAGE-F15-02"' in r.text


def test_wrong_password(client):
    r = client.post("/login", data={"account": "wen", "password": "错的"})
    assert r.status_code == 401 and "账号或密码不正确" in r.text


def test_readonly_cannot_post(client):
    make_user("lixiaomei", "李晓梅", "readonly")
    login_as(client, "lixiaomei", "密码-123456")
    r = client.post("/cards", data={}, headers={"accept": "application/json"})
    assert r.status_code == 403 and r.json()["detail"] == "无权限"
    r = client.get("/")
    assert "设置" not in r.text.split('<nav class="nav">')[1].split("</nav>")[0]
