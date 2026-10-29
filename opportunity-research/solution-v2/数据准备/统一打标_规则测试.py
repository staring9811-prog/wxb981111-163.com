"""统一打标脚本里自带规则的用例（2026-10-29 形态结构审计的测试句，期望值按 wen 当天的决定更新）：
柜体结构（开放层板）和疑似非浴室柜。规则函数直接从 卖家精灵导出_打标.py 里取，不另抄一份。
用法：python3 -I 统一打标_规则测试.py"""
import os, re, html, json
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, '卖家精灵导出_打标.py'), encoding='utf-8').read()
ns = {}
exec('import re, html\n' + src[src.index('def suspect(t, dim=None):'):src.index('SUS = [')], ns)
exec('import re, html\n' + src[src.index('OPEN_RE = re.compile'):src.index('STRUCT_SRC = [')], ns)

def struct(text, src_, title=''):
    args = {'标题': (text, '', '', None, ''), 'SKU': ('', text, '', None, ''), '子体五点': (title, '', text, '子体详情', ''),
            '父体五点': (title, '', text, '父体详情填充', '')}.get(src_, (title, '', '', None, text))
    return '开放式' if ns['struct_of'](*args) else '待图片核验'

bad = []
cases = [json.loads(l) for l in open(os.path.join(HERE, '统一打标_规则测试.jsonl'), encoding='utf-8') if l.strip()]
for c in cases:
    got = struct(c['text'], c['source_field'], c.get('title', '')) if c['field'] == '柜体结构' else ns['suspect'](c['text'], c.get('dim'))
    if got != c['expected']: bad.append((c['field'], c['expected'], got, c['text'][:90]))
for b in bad: print('FAIL', b)
print(f'统一打标规则用例：{len(cases) - len(bad)}/{len(cases)} 通过')
