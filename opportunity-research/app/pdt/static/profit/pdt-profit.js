/* 利润测算并入判定台的衔接（PAGE-F24-01）：从决策卡带入尺寸与拟定售价（AC-F24-03）、保存并回写决策卡（AC-F24-04）、只读角色。
   计算一律调用 engine.js（原利润测算台逐字移植的函数：calcProduct / chanList / chanVal / seaIdx）。本文件在 engine.js 之前加载。 */
(function () {
  'use strict';
  var PDT = window.PDT || (window.PDT = {});
  function ls(k) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; } }

  /* ── 从决策卡带入（在 engine.js 读取初始方案之前完成） ── */
  if (PDT.card && !PDT.init) {
    var c = PDT.card, name = c.size + ' ' + c.value + '（决策卡）';
    var prods = ls('pc_products') || [];
    var hit = prods.filter(function (p) { return p.name === name; })[0];
    if (hit) { if (c.price) hit.price = c.price; }
    else {
      prods.unshift({ id: Math.random().toString(36).slice(2, 9), name: name, desc: c.name, supplier: '', category: '家具', peak: '非旺季',
        price: c.price || '', cost: '', costCur: 'USD', adj: 0, prices: {}, pkgs: [{ l: '', w: '', h: '', kg: '' }] });
    }
    PDT.init = { params: ls('pc_params'), products: prods };
    PDT.linkProduct = name;
  }

  /* ── 回写结果：所选产品在当前海运方案下各渠道的售价、单件利润、利润率、保本价 ── */
  function amzBreakeven(p, k, si) {
    // Amazon 没有现成的保本价公式：用原工具的 calcProduct 对售价二分，求利润 = 0 的售价
    var lo = 0, hi = Math.max(50, (+p.price || 100) * 5);
    var f = function (x) { var q = JSON.parse(JSON.stringify(p)); q.price = x; return calcProduct(q).sc[si][k]; };
    if (!(f(hi) > 0)) return null;
    for (var i = 0; i < 60; i++) { var m = (lo + hi) / 2; if (f(m) > 0) hi = m; else lo = m; }
    return Math.round(hi * 100) / 100;
  }
  function result(pi) {
    var p = products[pi]; if (!p) return null;
    var r = calcProduct(p), si = seaIdx();
    var rows = chanList().map(function (ch) {
      var v = chanVal(r, ch, si);
      if (ch.amz) return { channel: ch.name, price: r.price > 0 ? r.price : null, profit: v.ok ? v.profit : null, margin: v.ok ? v.profit / r.price : null, breakeven: v.ok ? amzBreakeven(p, ch.amz, si) : null };
      var x = r.plat[ch.plat];
      if (x.noPrice) return { channel: ch.name, price: null, profit: null, margin: null, breakeven: null };
      var s = x.sc[si];
      return { channel: ch.name, price: x.promo, profit: s.promo.profit, margin: s.promo.margin, breakeven: s.breakeven };
    });
    return { product: p.name, sea: P.sea[si].name, rows: rows };
  }
  /* ── 回写前必填：与服务端 routes_tools.writeback_missing 同一口径 ── */
  function pos(v) { var n = parseFloat(v); return isFinite(n) && n > 0; }
  function missingFields(p) {
    var out = [];
    if (!p) return out;
    if (!pos(p.cost) && !pos(p.costRmb)) out.push('出厂价 / 采购成本');
    if (!(p.pkgs || []).some(function (g) { return g && pos(g.l) && pos(g.w) && pos(g.h); })) out.push('尺寸（包裹长宽高）');
    if (!pos(p.price)) out.push('售价');
    return out;
  }
  /* 不能回写的原因：缺必填，或算出的保本价无效（≤ 0）；返回空串表示可以回写 */
  function blockReason(pi, R) {
    var miss = missingFields(products[pi]);
    if (miss.length) return '请补全：' + miss.join('、');
    if (!R) return '没有产品可以回写';
    var bad = R.rows.filter(function (x) { return x.breakeven != null && !(x.breakeven > 0); }).map(function (x) { return x.channel; });
    if (bad.length) return bad.join('、') + ' 的保本价无效（≤ $0），请检查成本与尺寸';
    if (!R.rows.some(function (x) { return x.price > 0 && x.profit != null; })) return '没有任何渠道算出利润';
    return '';
  }
  PDT.missingFields = missingFields;
  function linkIndex() {
    var n = PDT.linkProduct, i = products.findIndex(function (p) { return p.name === n; });
    return i >= 0 ? i : 0;
  }
  PDT.result = result;
  /* 保存方案时：方案已关联决策卡则带上回写结果（卡片随方案更新） */
  PDT.extra = function (it) {
    var cid = (it && it.card_id) || (PDT.card && PDT.card.id);
    if (!cid || PDT.readonly) return {};
    var i = linkIndex(), R = result(i);
    if (blockReason(i, R)) return {};  // 缺必填时只保存方案，不改卡片上的数字
    return { card_id: cid, result: R };
  };
  /* 当前版本变了（打开、保存回当前版本、另存为新版本、改名、删除）：engine.js 的 setCur 已同步 PDT.planId，这里更新页头的方案名与保存时间 */
  PDT.onCur = function (c, it) {
    var n = document.querySelector('[data-plan-name]'); if (n && c) n.textContent = c.name;
    if (it && it.savedAt) { PDT.savedAt = it.savedAt; showSaved(); }
  };
  PDT.onOpened = function (it) { if (it.result && it.result.product) PDT.linkProduct = it.result.product; };

  function money(v) { return v == null || !isFinite(v) ? '—' : (v < 0 ? '−' : '') + '$' + Math.abs(v).toFixed(2); }
  function showSaved() {
    var el = document.querySelector('[data-saved]'); if (!el || !PDT.savedAt) return;
    var d = new Date(PDT.savedAt), t = (d.getMonth() + 1 + '').padStart(2, '0') + '-' + (d.getDate() + '').padStart(2, '0') + ' ' + (d.getHours() + '').padStart(2, '0') + ':' + (d.getMinutes() + '').padStart(2, '0');
    el.innerHTML = '<svg class="icon"><use href="#ph-check-circle"/></svg>已保存到系统 · <span class="num">' + t + '</span>';
  }

  PDT.boot = function () {
    showSaved();
    if (PDT.readonly) {
      document.body.setAttribute('data-ro', '1');
      var orig = render;
      var lock = function () {
        document.querySelectorAll('#pc-root input, #pc-root textarea, #pc-root select').forEach(function (el) {
          // 只读也能切换查看方式：渠道勾选、明细渠道、旺季 / 海运对比、FOB vs 国内、报价对比指标与选中版本
          if (el.closest('#chanBar') || ['detailChan', 'scenChan', 'domChan', 'cmpFob', 'cmpDom', 'qMetric'].indexOf(el.id) >= 0 || el.dataset.qsel !== undefined) return;
          el.disabled = true;
        });
      };
      render = function () { orig(); lock(); };
      var origVars = renderVars;  // 变量抽屉单独重画变量面板，同样锁上
      renderVars = function () { origVars(); lock(); };
      lock();
    }
    var btn = document.getElementById('btnWriteback');
    if (!btn) return;
    var sel = document.getElementById('wbProduct');
    var ok = document.getElementById('wbOk'), warn = document.getElementById('wbMissing');
    function fill() {
      var R = result(+sel.value), why = blockReason(+sel.value, R);
      ok.disabled = !!why;
      warn.hidden = !why;
      warn.querySelector('[data-why]').textContent = why;
      document.getElementById('wbTable').hidden = !!why;  // 缺必填时不给利润预览，避免把错误数字当结果
      document.getElementById('wbRows').innerHTML = R && !why ? R.rows.map(function (x) {
        return '<tr><td>' + x.channel + '</td><td class="t-num">' + money(x.price) + '</td><td class="t-num">' + money(x.profit) + '</td><td class="t-num">' +
          (x.margin == null ? '—' : (x.margin * 100).toFixed(1) + '%') + '</td><td class="t-num">' + money(x.breakeven) + '</td></tr>';
      }).join('') : '';
    }
    btn.addEventListener('click', function () {
      if (!products.length) { toast('没有产品可以保存'); return; }
      sel.innerHTML = products.map(function (p, i) { return '<option value="' + i + '">' + esc(p.name) + '</option>'; }).join('');
      sel.value = String(linkIndex());
      document.getElementById('wbName').value = PDT.planName || defaultName();
      fill();
      window.oppoOpen('#dlgWriteback');
    });
    sel.addEventListener('change', fill);
    ok.addEventListener('click', function () {
      if (blockReason(+sel.value, result(+sel.value))) return;
      ok.disabled = true;
      PDT.linkProduct = products[+sel.value].name;
      var body = { name: document.getElementById('wbName').value.trim() || defaultName(), products: JSON.parse(JSON.stringify(products)),
        params: JSON.parse(JSON.stringify(P)), card_id: PDT.card.id, result: result(+sel.value) };
      var url = PDT.planId ? '/tools/profit/plans/' + PDT.planId : '/tools/profit/plans';
      fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json' }, body: JSON.stringify(body) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || r.status); return j; }); })
        .then(function () { location.href = '/cards/' + PDT.card.id + '?msg=' + encodeURIComponent('已保存方案并回写“钱”一节') + '#s8'; })
        .catch(function (e) { ok.disabled = false; toast('保存失败，当前编辑不丢：' + e.message); });
    });
  };
})();
