"""自动检查立项 / 发布文件的 A 类验收项（见 验收标准.md）。

用法：python check_doc.py <文件.docx> lixiang|fabu [--channels 4] [--renders 2] [--skus 8]
输出每项 PASS / FAIL 和原因；全部通过时退出码 0。
"""
import argparse, re, sys
from docx import Document
from docx.oxml.ns import qn

AI_WORDS = ['一页看完', '赋能', '抓手', '闭环', '痛点直击', '极致', '全方位', '助力']
EMOJI = re.compile('[\U0001F300-\U0001FAFF☀-➿⭐✅❌]')


def load(path):
    d = Document(path)
    paras = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    heads = []
    for p in d.paragraphs:
        try:
            sn = p.style.name or ''
        except Exception:
            sn = ''
        t = p.text.strip()
        if sn.startswith('Heading') and t:
            heads.append((sn, t))
        elif t and len(t) <= 40:  # 飞书等导出的文件没有标题样式，按编号识别
            if re.match(r'^[一二三四五六七八九十]+、', t): heads.append(('Heading 1', t))
            elif re.match(r'^\d+\.\d+\s', t): heads.append(('Heading 3', t))
            elif re.match(r'^\d+\.\s', t) or re.search(r'（我们[:：]', t): heads.append(('Heading 2', t))
    tables = []
    for t in d.tables:
        rows = [[c.text.strip() for c in r.cells] for r in t.rows]
        tables.append(rows)
    imgs = len(d.element.body.findall('.//' + qn('w:drawing')))
    full = '\n'.join(paras + ['\n'.join(' | '.join(r) for r in t) for t in tables])
    return paras, heads, tables, imgs, full


def h1(heads):
    return [t for s, t in heads if s == 'Heading 1']


def has_h1(heads, *keys):
    return all(any(k in t for t in h1(heads)) for k in keys)


def run(path, mode, channels, renders, skus):
    paras, heads, tables, imgs, full = load(path)
    hdr = lambda t: ' '.join(t[0]) if t else ''
    comp = [t for t in tables if '和我们比' in hdr(t)]
    R = []
    ok = lambda k, c, why='': R.append((k, bool(c), why))
    if mode == 'lixiang':
        ok('L1', has_h1(heads, '需求分析', '差异化', '产品定义', '产品落地价格'), str(h1(heads)))
        ok('L2', all(k in full for k in ('机会点', '危机点', '两大方向')))
        bad = [k for k in ('销量预估', '第三个月', '直接竞对：', '核心结论') if k in full]
        ok('L3', not bad, '出现：' + '、'.join(bad))
        ok('L4', re.search(r'要[^\n]{1,24}?、\s*要[^\n]{1,24}?、\s*要', full) and '外观设计理念' in full and '使用性设计理念' in full)
        sec = full.split('产品落地价格', 1)[-1]
        ok('L5', re.search(r'利润率\s*[\d.]+\s*[–-]\s*[\d.]+\s*%', sec) and any('利润率' in hdr(t) and '促销价' in hdr(t) for t in tables))
        ok('L6', imgs >= channels + renders, f'图片 {imgs} 张，需要 ≥ {channels + renders}')
        ok('L7', len(comp) >= 3, f'竞品表 {len(comp)} 张')
        ok('L8', any('推荐率' in hdr(t) or '星' in hdr(t) for t in tables) and any('原话' in hdr(t) or '原文' in hdr(t) for t in tables))
    else:
        cover = '\n'.join(paras[:40] + ['\n'.join(' | '.join(r) for r in t) for t in tables[:3]])
        ok('R1', '核心结论' in cover and re.search(r'第三个月[^\n]*件', cover), '')
        need = ['需求分析', '差异化', '规格', '竞对', '利润', '销量预估', '风险']
        miss = [k for k in need if not any(k in t for t in h1(heads))]
        ok('R2', not miss, '缺：' + '、'.join(miss))
        miss3 = [k for k in ('结构', '材质', '包装', '出厂价') if not any(k in t for s, t in heads)]
        ok('R3', not miss3 and '待补' in full, '缺：' + '、'.join(miss3))
        price_t = [t for t in tables if '尺寸' in hdr(t) and ('Amazon' in hdr(t) or 'Lowe' in hdr(t))]
        prof_t = [t for t in tables if ('SKU' in hdr(t) or '出厂价' in hdr(t)) and len(t) - 1 >= skus]
        ok('R4', price_t and prof_t, f'售价表 {len(price_t)}，SKU 利润表 {len(prof_t)}')
        n4 = len(re.findall(r'直接竞对：', full))
        fmt = re.findall(r'直接竞对：[^\n]*\n[^\n]*价格[^\n]*月销[^\n]*评分[^\n]*\n配置：[^\n]*\n估算：', full)
        ok('R5', n4 >= channels and len(fmt) >= 1, f'直接竞对 {n4} 处，标准 4 行格式 {len(fmt)} 处')
        h2s = [t for s, t in heads if s in ('Heading 2', 'Heading 3')]
        ok('R6', sum(1 for t in h2s if '我们：' in t or '我们:' in t) >= channels, str([t for t in h2s if '我们' in t]))
        ok('R7', len(comp) >= 1 and imgs >= 1, f'竞品表 {len(comp)}，图片 {imgs}')
    bad = [w for w in AI_WORDS if w in full]
    ok('C1', not bad, '出现：' + '、'.join(bad))
    em = EMOJI.findall(full)
    ok('C2', not em, '出现：' + ''.join(set(em)))
    ok('C4', '数据来源' in full or '数据：' in full)
    for k, v, why in R:
        print(f'{k}  {"PASS" if v else "FAIL"}  {why if not v else ""}')
    print(f'通过 {sum(v for _, v, _ in R)}/{len(R)}')
    return all(v for _, v, _ in R)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('docx'); ap.add_argument('mode', choices=['lixiang', 'fabu'])
    ap.add_argument('--channels', type=int, default=4); ap.add_argument('--renders', type=int, default=2)
    ap.add_argument('--skus', type=int, default=8)
    a = ap.parse_args()
    sys.exit(0 if run(a.docx, a.mode, a.channels, a.renders, a.skus) else 1)
