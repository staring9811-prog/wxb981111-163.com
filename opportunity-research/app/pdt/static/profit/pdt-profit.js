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
  function linkIndex() {
    var n = PDT.linkProduct, i = products.findIndex(function (p) { return p.name === n; });
    return i >= 0 ? i : 0;
  }
  PDT.result = result;
  /* 保存方案时：方案已关联决策卡则带上回写结果（卡片随方案更新） */
  PDT.extra = function (it) {
    var cid = (it && it.card_id) || (PDT.card && PDT.card.id);
    if (!cid || PDT.readonly) return {};
    return { card_id: cid, result: result(linkIndex()) };
  };
  PDT.onSaved = function (it) { PDT.planId = it.id; PDT.savedAt = it.savedAt; showSaved(); var n = document.querySelector('[data-plan-name]'); if (n) n.textContent = it.name; };
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
          if (el.closest('#chanBar') || el.id === 'detailChan') return;
          el.disabled = true;
        });
      };
      render = function () { orig(); lock(); };
      lock();
    }
    var btn = document.getElementById('btnWriteback');
    if (!btn) return;
    var sel = document.getElementById('wbProduct');
    function fill() {
      var R = result(+sel.value);
      document.getElementById('wbRows').innerHTML = R ? R.rows.map(function (x) {
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
    document.getElementById('wbOk').addEventListener('click', function () {
      var ok = this; ok.disabled = true;
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
