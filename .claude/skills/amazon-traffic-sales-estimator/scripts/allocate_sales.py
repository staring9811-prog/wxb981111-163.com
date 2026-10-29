"""Conservative cross-category monthly traffic-keyword allocation."""
import argparse
import csv
import json
import math
from pathlib import Path

def valid_number(value, integer=False):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 and (not integer or int(value) == value)

def allocate_strict_group(group):
    children = group.get('children') or []
    reasons = []
    month = group.get('month')
    if not month or group.get('parent_sales_month') != month:
        reasons.append('month_mismatch')
    if group.get('children_complete') is not True or not valid_number(group.get('expected_child_count'),True) or group.get('expected_child_count') != len(children) or not children:
        reasons.append('incomplete_variations')
    if group.get('relationship_conflict'):
        reasons.append('relationship_conflict')
    if group.get('keyword_scope') != 'child' or group.get('parent_sales_scope') != 'parent':
        reasons.append('unverified_metric_scope')
    if not valid_number(group.get('parent_monthly_sales')):
        reasons.append('missing_parent_sales')
    ids = [c.get('child_asin') for c in children]
    if not all(ids) or len(set(ids)) != len(ids):
        reasons.append('duplicate_or_missing_child')
    if any(c.get('query_success') is not True or not valid_number(c.get('keyword_count'), True) for c in children):
        reasons.append('missing_keyword_count')
    if any(c.get('month') != month for c in children):
        reasons.append('child_month_mismatch')
    denom = sum(c['keyword_count'] for c in children) if children and all(valid_number(c.get('keyword_count'), True) for c in children) else None
    if denom == 0:
        reasons.append('zero_denominator')
    rows = []
    for child in children:
        share = child['keyword_count'] / denom if not reasons else None
        rows.append(dict(parent_asin=group.get('parent_asin'), marketplace=group.get('marketplace'), month=month,
                         child_asin=child.get('child_asin'), keyword_count=child.get('keyword_count'), parent_keyword_sum=denom,
                         parent_monthly_sales=group.get('parent_monthly_sales'), share=share,
                         estimated_child_sales=share * group['parent_monthly_sales'] if share is not None else None,
                         status='ok' if not reasons else '|'.join(reasons),
                         estimate_label='按流量词数分摊的估算月销量'))
    if not reasons:
        assert math.isclose(sum(r['share'] for r in rows), 1, abs_tol=1e-12)
        assert math.isclose(sum(r['estimated_child_sales'] for r in rows), group['parent_monthly_sales'], rel_tol=1e-12, abs_tol=1e-9)
    return rows, dict(parent_asin=group.get('parent_asin'), month=month, keyword_sum=denom, child_count=len(children),
                      parent_monthly_sales=group.get('parent_monthly_sales'), status='ok' if not reasons else '|'.join(reasons))

def allocate_verified_group(group):
    """Versioned business rules; interval constraints require verified windows."""
    children = group.get('children') or []
    month = group.get('month')
    sales = group.get('parent_monthly_sales')
    reasons = []
    if not month or group.get('parent_sales_month') != month:
        reasons.append('month_mismatch')
    if group.get('relationship_verified_target_month') is not True:
        reasons.append('unverified_historical_relationship')
    if group.get('relationship_conflict'):
        reasons.append('relationship_conflict')
    if group.get('children_complete') is not True or not children:
        reasons.append('unverified_returned_list_coverage')
    if group.get('eligible', True) is not True:
        reasons.append('outside_source_month_parent_pool')
    if group.get('keyword_scope') != 'child':
        reasons.append('unverified_keyword_scope')
    if group.get('parent_sales_scope') not in ('parent', 'proxy'):
        reasons.append('unverified_sales_scope')
    if group.get('parent_sales_scope') == 'proxy' and not group.get('proxy_authorized'):
        reasons.append('unauthorized_proxy')
    if not valid_number(sales):
        reasons.append('missing_parent_sales')
    ids = [c.get('child_asin') for c in children]
    if not all(ids) or len(set(ids)) != len(ids):
        reasons.append('duplicate_or_missing_child')
    if any(c.get('month') != month for c in children):
        reasons.append('child_month_mismatch')
    counts, missing = [], []
    minimum = group.get('keyword_minimum', 1)
    for c in children:
        ok = c.get('query_success') is True and valid_number(c.get('keyword_count'), True)
        missing.append(not ok)
        if not ok and not group.get('missing_keywords_as_zero'):
            reasons.append('missing_keyword_count')
        k = c['keyword_count'] if ok else 0
        counts.append(k if k >= minimum else 0)
    denominator = sum(counts)
    single = (len(children) == 1 and group.get('single_child_verified') is True)
    if denominator == 0 and not single:
        reasons.append('zero_denominator')
    ready = not reasons
    shares = ([1.0] if ready and single and denominator == 0 else
              [k / denominator for k in counts] if ready else [None] * len(children))
    base = [s * sales if s is not None else None for s in shares]
    final = list(base)
    kinds = ['single_child_fallback' if ready and single and denominator == 0 else 'traffic' for _ in children]
    legacy = []
    for i, c in enumerate(children):
        original = c.get('raw_child_monthly_sales')
        trigger = (base[i] is not None and valid_number(original) and original > 0 and sales > 4.5 * original)
        legacy.append(1.5 * original if trigger else base[i])
        if trigger and group.get('legacy_correction_enabled'):
            final[i] = legacy[i]
            kinds[i] = 'legacy_4_5_then_1_5'
    hard = [c.get('interval_window_verified') is True and valid_number(c.get('interval_lower'))
            for c in children]
    if ready and group.get('use_hard_intervals') and any(hard):
        if group.get('parent_sales_scope') != 'parent' or group.get('legacy_correction_enabled'):
            reasons.append('incompatible_constraint_scope')
        else:
            lower = [c['interval_lower'] if h else 0.0 for c, h in zip(children, hard)]
            upper = [c.get('interval_upper') if h and valid_number(c.get('interval_upper')) else math.inf
                     for c, h in zip(children, hard)]
            if any(u < l for l, u in zip(lower, upper)) or sum(lower) > sales + 1e-9 or sum(upper) < sales - 1e-9:
                reasons.append('infeasible_sales_intervals')
            elif sales == 0:
                final = [0.0] * len(children)
            else:
                weights = [max(q, sales * 1e-12) for q in base]
                def bounded(scale):
                    return [min(u, max(l, w * scale)) for l, u, w in zip(lower, upper, weights)]
                lo, hi = 0.0, 1.0
                for _ in range(180):
                    if sum(bounded(hi)) >= sales - 1e-10:
                        break
                    hi *= 2
                for _ in range(180):
                    mid = (lo + hi) / 2
                    if sum(bounded(mid)) < sales:
                        lo = mid
                    else:
                        hi = mid
                final = bounded((lo + hi) / 2)
                kinds = ['verified_interval_allocation'] * len(children)
                if not math.isclose(sum(final), sales, rel_tol=1e-10, abs_tol=1e-8):
                    reasons.append('allocation_not_converged')
    if reasons:
        shares, final = [None] * len(children), [None] * len(children)
    bsr_flags = [False] * len(children)
    ranked = [i for i, c in enumerate(children)
              if c.get('bsr_month') == month and c.get('bsr_node') == group.get('bsr_node')
              and valid_number(c.get('bsr')) and c['bsr'] > 0 and final[i] is not None]
    if len(ranked) >= 2:
        values = [children[i]['bsr'] for i in ranked]
        if max(values) - min(values) >= 50:
            bsr_order = {v: i + 1 for i, v in enumerate(sorted(set(values)))}
            sales_order = {v: i + 1 for i, v in enumerate(sorted({final[i] for i in ranked}, reverse=True))}
            limit = max(len(bsr_order) / 2, 2)
            for i in ranked:
                bsr_flags[i] = abs(bsr_order[children[i]['bsr']] - sales_order[final[i]]) > limit
    rows = []
    for i, c in enumerate(children):
        soft = False
        if final[i] is not None and not hard[i] and valid_number(c.get('interval_lower')):
            soft = final[i] < c['interval_lower']
            if valid_number(c.get('interval_upper')):
                soft = soft or final[i] > c['interval_upper']
        rows.append(dict(parent_asin=group.get('parent_asin'), marketplace=group.get('marketplace'), month=month,
                         child_asin=c['child_asin'], keyword_count=c.get('keyword_count'), effective_keyword_count=counts[i],
                         parent_keyword_sum=denominator, parent_monthly_sales=sales, share=shares[i],
                         base_estimated_child_sales=base[i], estimated_child_sales=final[i],
                         legacy_estimated_child_sales=legacy[i], rule_applied=kinds[i], missing_keyword_as_zero=missing[i],
                         bsr_check=bsr_flags[i], soft_interval_conflict=soft,
                         status='ok' if not reasons else '|'.join(dict.fromkeys(reasons)),
                         estimate_label='按流量词数分摊的估算月销量'))
    if not reasons and not group.get('legacy_correction_enabled'):
        assert math.isclose(sum(r['estimated_child_sales'] for r in rows), sales, rel_tol=1e-10, abs_tol=1e-8)
    return rows, dict(parent_asin=group.get('parent_asin'), month=month, keyword_sum=denominator,
                      child_count=len(children), parent_monthly_sales=sales,
                      status='ok' if not reasons else '|'.join(dict.fromkeys(reasons)),
                      rule_version=group.get('rule_version'))

def allocate_group(group):
    if group.get('rule_version') == 'verified-20261021':
        return allocate_verified_group(group)
    return allocate_strict_group(group)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    groups = json.loads(Path(args.input).read_text(encoding='utf-8'))
    if len({(g.get('marketplace'), g.get('parent_asin'), g.get('month')) for g in groups}) != len(groups):
        raise ValueError('duplicate_parent_group')
    rows, parents = [], []
    for group in groups:
        detail, parent = allocate_group(group)
        rows.extend(detail)
        parents.append(parent)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (('child_sales_detail', rows), ('parent_sales_summary', parents)):
        (out / (name + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        if data:
            with (out / (name + '.csv')).open('w', encoding='utf-8-sig', newline='') as f:
                w = csv.DictWriter(f, fieldnames=list(data[0]))
                w.writeheader()
                w.writerows(data)
    print(json.dumps({'parents': len(parents), 'children': len(rows), 'calculable_parents': sum(p['status']=='ok' for p in parents)}))

if __name__ == '__main__':
    main()
