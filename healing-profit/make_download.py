# -*- coding: utf-8 -*-
"""Offline snapshot: index.html + sprite sheets inlined, with a banner pointing to the always-current link."""
import base64, json, os, re
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
URL = "https://claude.ai/artifact/HE3ri4RHRqKR9hSs5SxiHD"
h = open("index.html", encoding="utf-8").read()
ver = re.search(r'<span class="vtag">(v\d+)</span><span>更新于 ([^（]+)', h)
sp = {k: "data:image/jpeg;base64," + base64.b64encode(open(f"sprite_{k}.jpg", "rb").read()).decode() for k in ["sauna", "tandem", "thermo"]}
banner = (f'<div style="position:sticky;top:0;z-index:20;background:#fff4c7;color:#5a4300;border-bottom:1px solid #e8a10a;'
          f'padding:8px 16px;font:13px/1.5 system-ui,sans-serif">这是 {ver.group(1)}（{ver.group(2).strip()}）的离线快照，不会自动更新。'
          f'最新版请打开：<a href="{URL}" target="_blank" rel="noopener">{URL}</a></div>')
doc = ('<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
       '<style>[hidden]{display:none!important}body{margin:0}</style>\n' + banner + h +
       '\n<script>window.MX_SPRITES=' + json.dumps(sp) + ';</script>\n</html>')
os.makedirs("download", exist_ok=True)
for f in os.listdir("download"): os.remove(os.path.join("download", f))
out = f"download/疗愈品类利润摸底_{ver.group(1)}.html"
open(out, "w", encoding="utf-8").write(doc); print(out)
