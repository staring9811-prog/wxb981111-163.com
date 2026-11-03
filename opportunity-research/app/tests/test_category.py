"""品类配置（PAGE-F27-01）：FLOW-23 中配置查看、保存前对比、生成新参数版本部分；AC-F27-02 只有浴室柜。"""
import json

from conftest import login_as, make_user
from pdt import catconfig


def _cfg_from_page(html):
    return json.loads(html.split('<script type="application/json" id="cfg-json">')[1].split("</script>")[0])


def test_flow23_view_defaults_only_bathroom_vanity(wen):
    """FLOW-23：页面只有浴室柜、无新建品类入口；分框默认 尺寸段 × 拆装 × 形态；默认系数 50 / 20，成功线 HD 250 / Lowe's 150 / Wayfair 120。"""
    html = wen.get("/settings/category").text
    assert "品类配置 · 浴室柜" in html and "第一版只开浴室柜一个品类" in html
    assert "新建品类" not in html and "切换品类" not in html
    for tab in ("分框与属性", "打标规则", "渠道参数", "参数版本"):
        assert tab in html
    cfg = _cfg_from_page(html)
    assert [d["dim"] for d in cfg["frame_dims"]] == ["尺寸段", "拆装", "形态"]
    assert cfg["frame_dims"][2]["values"] == ["落地式", "悬浮式"]
    assert [a["attr"] for a in cfg["scan_attrs"]] == ["台面材质", "元素", "主色", "柜体材质"]
    assert cfg["low_conf_threshold"] == 0.75
    for ch, units in (("homedepot", 250), ("lowes", 150), ("wayfair", 120)):
        assert cfg["channels"][ch]["vp_coef"] == 50 and cfg["channels"][ch]["nonvp_coef"] == 20
        assert cfg["channels"][ch]["success"]["units"] == units
    assert 'value="250"' in html and 'value="150"' in html and 'value="120"' in html
    assert "当前在用：参数 v1" in html


def test_flow23_preview_then_save_new_version(wen):
    """FLOW-23：阈值改 0.8、Lowe's 非 VP 系数 20→25、成功线 150→160；先显示前后对比（不落库），填说明后生成 v2，之后读取到新值并在页面注明版本。"""
    cfg = _cfg_from_page(wen.get("/settings/category").text)
    cfg["low_conf_threshold"] = 0.8
    cfg["channels"]["lowes"]["nonvp_coef"] = 25
    cfg["channels"]["lowes"]["success"]["units"] = 160
    data = json.dumps(cfg, ensure_ascii=False)

    p = wen.post("/settings/category/preview", data={"data": data}).json()
    assert p["version"] == 1 and p["next_version"] == 2
    got = {c["label"]: (c["old"], c["new"]) for c in p["changes"]}
    assert got == {"低置信度阈值": ("0.75", "0.8"), "Lowe's 非 VP 系数": ("20", "25"), "Lowe's 成功线 · 估算月销": ("150", "160")}
    assert catconfig.current()[0] == 1  # 预览不生成版本

    r = wen.post("/settings/category", data={"data": data, "note": ""}, follow_redirects=True)
    assert "请填写修改说明" in r.text and catconfig.current()[0] == 1

    r = wen.post("/settings/category", data={"data": data, "note": "按 11 月 Lowe's 前 50 名中位数调高", "tab": "ver"}, follow_redirects=True)
    assert "已保存参数 v2" in r.text
    v, cur = catconfig.current()
    assert v == 2 and cur["low_conf_threshold"] == 0.8
    assert cur["channels"]["lowes"]["nonvp_coef"] == 25 and cur["channels"]["lowes"]["success"]["units"] == 160
    assert cur["channels"]["homedepot"]["nonvp_coef"] == 20
    html = wen.get("/settings/category?tab=ver").text
    assert "当前在用：参数 v2" in html and "按 11 月 Lowe&#39;s 前 50 名中位数调高" in html
    assert "Lowe&#39;s 非 VP 系数：20 → 25" in html and "已被 v2 替代" in html

    r = wen.post("/settings/category", data={"data": data, "note": "重复保存"}, follow_redirects=True)
    assert "没有修改" in r.text and catconfig.current()[0] == 2


def test_flow23_validation(wen):
    """FLOW-23 / AC-F27-02：系数填负数、阈值越界、改品类都被拦截，版本不变。"""
    base = _cfg_from_page(wen.get("/settings/category").text)
    for mutate, word in ((lambda c: c["channels"]["wayfair"].__setitem__("vp_coef", -5), "请填正数"),
                         (lambda c: c.__setitem__("low_conf_threshold", 0.99), "0.50–0.95"),
                         (lambda c: c.__setitem__("category", "马桶"), "只开浴室柜")):
        c = json.loads(json.dumps(base))
        mutate(c)
        r = wen.post("/settings/category/preview", data={"data": json.dumps(c, ensure_ascii=False)})
        assert r.status_code == 400 and word in r.json()["detail"]
        r = wen.post("/settings/category", data={"data": json.dumps(c, ensure_ascii=False), "note": "测试"}, follow_redirects=True)
        assert word in r.text
    assert catconfig.current()[0] == 1


def test_category_operator_only(app_env, client):
    """RULE-01（品类配置）：只读与审批者打开或保存品类配置都被拒绝。"""
    make_user("lixiaomei", "李晓梅", "readonly")
    make_user("zhoujianguo", "周建国", "approver")
    for u in ("lixiaomei", "zhoujianguo"):
        from fastapi.testclient import TestClient
        c = login_as(TestClient(app_env), u, "密码-123456")
        assert c.get("/settings/category").status_code == 403
        r = c.post("/settings/category", data={"data": "{}", "note": "越权"}, headers={"accept": "application/json"})
        assert r.status_code == 403 and r.json()["detail"] == "无权限"
    assert catconfig.current()[0] == 1


def test_tag_rules_tab_chinese_summary(wen):
    """DESIGN-18（补）：“打标规则”页签按业务标签（尺寸段、拆装、形态、台面材质、元素、主色、柜体材质）分行显示中文摘要，
    不出现内部字段名与 \\uXXXX 转义；“编辑”抽屉里的 JSON 中文正常显示。"""
    import re
    html = wen.get("/settings/category", params={"tab": "tag"}).text
    body = html.split("<h2 class=\"panel__title\">打标规则</h2>")[1].split("</table>")[0]
    tags = re.findall(r'<tr><td class="cell-title">([^<]+)</td>', body)
    assert tags == ["尺寸段", "拆装", "形态", "台面材质", "元素", "主色", "柜体材质"]
    for raw in ("color_map", "vision_prompt", "element_map", "size_bands", "rule_version", "\\u"):
        assert raw not in body, raw
    assert "27–33 英寸 → 30″" in body and "Fluted / Reeded → 竖棱" in body and "胡桃木色 / 深咖啡色 / 棕色 → 深木" in body
    assert "树脂 / Cultured Marble → 树脂一体" in body
    drawer = html.split('id="dwRules"')[1].split("</textarea>")[0]
    assert "\\u" not in drawer
    v, cfg = catconfig.current()
    if cfg.get("tag_rules"):
        assert "夏克式" in drawer
    # 保存过带中文的打标规则后，编辑框里中文原样显示
    cfg["tag_rules"] = dict(cfg.get("tag_rules") or {}, color_map={"白色": "白", "胡桃木色": "深木"})
    catconfig.save(cfg, None)
    drawer = wen.get("/settings/category", params={"tab": "tag"}).text.split('id="dwRules"')[1].split("</textarea>")[0]
    assert '&#34;胡桃木色&#34;: &#34;深木&#34;' in drawer and "\\u" not in drawer
