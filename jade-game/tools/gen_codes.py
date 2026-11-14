#!/usr/bin/env python3
"""生成激活码。明文写到指定的私有文件（不要提交到仓库），哈希追加到 licenses.js。
用法：python3 tools/gen_codes.py 100 /path/to/private/codes.txt
游戏里只保存哈希，看不到明文；每个码可以重复使用（不绑定设备），发现外泄就从 licenses.js 里删掉对应哈希再发版。"""
import sys, secrets, hashlib, json, re, pathlib
n = int(sys.argv[1]); out = pathlib.Path(sys.argv[2]); here = pathlib.Path(__file__).resolve().parent.parent
ALPHA = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
lic = here / 'licenses.js'; cur = []
if lic.exists():
    m = re.search(r'\[(.*)\]', lic.read_text(encoding='utf-8'), re.S)
    if m and m.group(1).strip(): cur = json.loads('[' + m.group(1) + ']')
codes = []
for _ in range(n):
    c = ''.join(secrets.choice(ALPHA) for _ in range(16)); codes.append('-'.join(c[i:i + 4] for i in range(0, 16, 4)))
    cur.append(hashlib.sha256(('jade:' + c).encode()).hexdigest())
with out.open('a', encoding='utf-8') as f: f.write('\n'.join(codes) + '\n')
lic.write_text('/* 激活码的 SHA-256 哈希，由 tools/gen_codes.py 维护。这里没有明文。 */\nwindow.JADE_LICENSES = ' + json.dumps(cur, indent=0) + ';\n', encoding='utf-8')
print(f'{n} 个新码已写入 {out}；licenses.js 现有 {len(cur)} 个哈希')
