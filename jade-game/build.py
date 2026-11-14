#!/usr/bin/env python3
"""由 index.html 生成可直接双击打开的 play.html。
每次发版：改 version.json 的 version（+1）和 notes，运行本脚本，再提交。
play.html 打开时会到 GitHub 读 version.json；线上版本号更大时，直接加载线上的页面和脚本运行，并提示本地需要 git pull。"""
import json, re, pathlib
here = pathlib.Path(__file__).parent
ver = json.loads((here / 'version.json').read_text(encoding='utf-8'))
body = (here / 'index.html').read_text(encoding='utf-8')
body = re.sub(r'<script src="[^"]+"></script>\s*', '', body)
body = re.sub(r'<title>.*?</title>\s*', '', body, count=1)
loader = r'''
<script>
(function () {
  var LOCAL = __VER__, FILES = ['config.js', 'licenses.js', 'core.js', 'shader.js', 'ui.js'];
  var BASES = ['https://raw.githubusercontent.com/staring9811-prog/wxb981111-163.com/claude/pensive-volta-k3p8sy/jade-game/', 'https://raw.githubusercontent.com/staring9811-prog/wxb981111-163.com/main/jade-game/'];
  function bar(text, kind) { var b = document.getElementById('upd'); b.textContent = text; b.className = kind || ''; b.hidden = false; var x = document.createElement('button'); x.textContent = '知道了'; x.onclick = function () { b.hidden = true; }; b.appendChild(x); }
  function runLocal() { (function next(i) { if (i >= FILES.length) return; var s = document.createElement('script'); s.src = FILES[i]; s.onload = function () { next(i + 1); }; s.onerror = function () { bar('找不到 ' + FILES[i] + '。请确认 play.html 和它在同一个文件夹里。', 'bad'); }; document.body.appendChild(s); })(0); }
  function get(url) { return fetch(url + '?t=' + Date.now(), { cache: 'no-store' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); }); }
  function check() {
    return Promise.all(BASES.map(function (b) { return get(b + 'version.json').then(function (t) { var v = JSON.parse(t); v.base = b; return v; }).catch(function () { return null; }); }))
      .then(function (vs) { vs = vs.filter(Boolean).sort(function (a, b) { return b.version - a.version; }); if (!vs.length) throw new Error('offline'); return vs[0]; });
  }
  var timer = new Promise(function (_, rej) { setTimeout(function () { rej(new Error('timeout')); }, 6000); });
  Promise.race([check(), timer]).then(function (remote) {
    if (!(remote.version > LOCAL)) { runLocal(); document.getElementById('ver').textContent = 'v' + LOCAL + ' 已是最新'; return; }
    return Promise.all([get(remote.base + 'index.html')].concat(FILES.map(function (f) { return get(remote.base + f); }))).then(function (parts) {
      document.getElementById('root').innerHTML = parts[0].replace(/<script[^>]*><\/script>/g, '').replace(/<title>[\s\S]*?<\/title>/, '');
      for (var i = 1; i < parts.length; i++) { var s = document.createElement('script'); s.text = parts[i] + '\n//# sourceURL=remote-' + FILES[i - 1]; document.body.appendChild(s); }
      document.getElementById('ver').textContent = 'v' + remote.version + '（线上）';
      bar('已自动加载线上最新版 v' + remote.version + '（本地文件是 v' + LOCAL + '）：' + (remote.notes || '') + '。在这个文件夹执行 git pull 可把本地文件也更新。', 'ok');
    });
  }).catch(function () { runLocal(); document.getElementById('ver').textContent = 'v' + LOCAL + '（未能联网检查更新）'; });
})();
</script>'''.replace('__VER__', str(ver['version']))
html = f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>翡翠博弈</title>
<style>
html, body {{ margin: 0; height: 100%; }}
#root {{ height: 100%; }}
#upd {{ position: fixed; left: 50%; top: 8px; transform: translateX(-50%); z-index: 50; max-width: min(92vw, 720px); background: #2b3f33; color: #ebe4d8; border: 1px solid #3f6a55; border-radius: 6px; padding: 8px 12px; font: 13px/1.5 system-ui, "Microsoft YaHei", sans-serif; display: flex; gap: 10px; align-items: center; }}
#upd.bad {{ background: #4a2a24; border-color: #8a4a3c; }}
#upd button {{ flex: none; }}
#ver {{ position: fixed; right: 8px; bottom: 4px; z-index: 40; font: 11px system-ui, sans-serif; color: #6f675c; pointer-events: none; }}
</style>
</head>
<body>
<div id="root">
{body}
</div>
<div id="upd" hidden></div>
<div id="ver">v{ver['version']}</div>
{loader}
</body>
</html>
'''
(here / 'play.html').write_text(html, encoding='utf-8')
print('play.html built, version', ver['version'])

# 对外售卖的发布包：python3 build.py --dist  →  dist/ 整个文件夹传到任何静态网站主机即可。
# 不带联网更新（更新就是重新上传），打开激活码校验。
import sys, shutil
if '--dist' in sys.argv:
    dist = here / 'dist'; shutil.rmtree(dist, ignore_errors=True); dist.mkdir()
    page = (here / 'index.html').read_text(encoding='utf-8')
    page = re.sub(r'<title>.*?</title>\s*', '', page, count=1)
    page = re.sub(r'<script src="([^"]+)"></script>', lambda m: f'<script src="{m.group(1)}?v={ver["version"]}"></script>', page)
    (dist / 'index.html').write_text(f'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#0e0c0a">
<title>翡翠博弈</title>
<style>html, body {{ margin: 0; height: 100%; }}</style>
</head>
<body>
{page}
</body>
</html>
''', encoding='utf-8')
    for f in ['core.js', 'shader.js', 'ui.js', 'licenses.js']: shutil.copy(here / f, dist / f)
    cfg = (here / 'config.js').read_text(encoding='utf-8').replace('license: false', 'license: true')
    (dist / 'config.js').write_text(cfg, encoding='utf-8')
    print('dist/ built with license check ON')

