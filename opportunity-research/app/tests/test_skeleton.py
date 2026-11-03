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


def test_sidebar_fixed_height_nav_scrolls(wen):
    """DESIGN-02：侧栏固定视口高度，品牌区与"收起侧栏"不被压缩，菜单区单独滚动（pdt.css 在 app.css 之后引入）。"""
    html = wen.get("/").text
    head = html.split("</head>")[0]
    assert head.index("/static/app.css") < head.index("/static/pdt.css")
    css = wen.get("/static/pdt.css").text
    side = css.split(".sidebar {", 1)[1].split("}", 1)[0]
    assert "position: fixed" in side and "height: 100vh" in side and "overflow: hidden" in side
    assert ".sidebar__brand, .sidebar__foot { flex: none; }" in css
    nav = css.split(".sidebar .nav {", 1)[1].split("}", 1)[0]
    assert "min-height: 0" in nav and "overflow-y: auto" in nav
