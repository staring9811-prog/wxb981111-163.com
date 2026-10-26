/* 品类机会判定台 · 原型共用交互（无依赖，离线可用） */
(function () {
  'use strict';

  var doc = document;
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || doc).querySelectorAll(sel)); };

  function store(key, value) {
    try {
      if (value === undefined) return window.localStorage.getItem(key);
      window.localStorage.setItem(key, value);
    } catch (e) { return null; }
    return null;
  }

  /* ── 侧栏收起 ── */
  var app = doc.querySelector('.app');
  if (app && store('oppo.sidebar') === 'collapsed') app.classList.add('is-collapsed');
  $$('[data-collapse-sidebar]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!app) return;
      var collapsed = app.classList.toggle('is-collapsed');
      btn.setAttribute('aria-expanded', String(!collapsed));
      store('oppo.sidebar', collapsed ? 'collapsed' : 'expanded');
    });
  });

  /* ── 整行跳转 ── */
  function isInteractive(el) {
    return !!el.closest('a, button, input, select, textarea, label, [data-no-row]');
  }
  $$('tr[data-href]').forEach(function (tr) {
    if (!tr.hasAttribute('tabindex')) tr.setAttribute('tabindex', '0');
    tr.addEventListener('click', function (e) {
      if (isInteractive(e.target)) return;
      window.location.href = tr.getAttribute('data-href');
    });
    tr.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && e.target === tr) window.location.href = tr.getAttribute('data-href');
    });
  });

  /* ── 抽屉与弹窗 ── */
  var scrim = doc.createElement('div');
  scrim.className = 'scrim';
  doc.body.appendChild(scrim);
  var openStack = [];

  function focusFirst(panel) {
    var target = panel.querySelector('[autofocus], input:not([type=hidden]):not([disabled]), select, textarea, button:not([disabled]), a[href]');
    if (target) target.focus({ preventScroll: true });
  }
  function openOverlay(panel, opener) {
    if (!panel || panel.classList.contains('is-open')) return;
    panel.classList.add('is-open');
    panel.setAttribute('aria-hidden', 'false');
    scrim.classList.add('is-open');
    openStack.push({ panel: panel, opener: opener || doc.activeElement });
    window.setTimeout(function () { focusFirst(panel); }, 30);
  }
  function closeOverlay(panel) {
    if (!panel) return;
    var href = panel.getAttribute('data-close-href');
    if (href) { window.location.href = href; return; }
    panel.classList.remove('is-open');
    panel.setAttribute('aria-hidden', 'true');
    var idx = -1;
    openStack.forEach(function (item, i) { if (item.panel === panel) idx = i; });
    var entry = idx >= 0 ? openStack.splice(idx, 1)[0] : null;
    if (!openStack.length) scrim.classList.remove('is-open');
    if (entry && entry.opener && entry.opener.focus) entry.opener.focus({ preventScroll: true });
  }
  window.oppoOpen = function (sel) { openOverlay(doc.querySelector(sel)); };
  window.oppoClose = function (sel) { closeOverlay(doc.querySelector(sel)); };

  $$('[data-open]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      openOverlay(doc.querySelector(btn.getAttribute('data-open')), btn);
    });
  });
  doc.addEventListener('click', function (e) {
    var closer = e.target.closest('[data-close]');
    if (!closer) return;
    e.preventDefault();
    closeOverlay(closer.closest('.drawer, .modal'));
  });
  scrim.addEventListener('click', function () {
    var top = openStack[openStack.length - 1];
    if (top) closeOverlay(top.panel);
  });
  $$('.modal').forEach(function (modal) {
    modal.addEventListener('click', function (e) { if (e.target === modal) closeOverlay(modal); });
  });
  $$('[data-open-on-load]').forEach(function (panel) { openOverlay(panel); });

  /* ── 页内标签页 ── */
  $$('[role="tablist"]').forEach(function (list) {
    var tabs = $$('[role="tab"][aria-controls]', list);
    tabs.forEach(function (tab) {
      tab.addEventListener('click', function (e) {
        e.preventDefault();
        tabs.forEach(function (t) {
          var on = t === tab;
          t.setAttribute('aria-selected', String(on));
          var panel = doc.getElementById(t.getAttribute('aria-controls'));
          if (panel) panel.hidden = !on;
        });
      });
    });
  });

  /* ── 筛选标签 ── */
  function applyFilters(scope) {
    var target = doc.querySelector(scope.getAttribute('data-filter-scope'));
    if (!target) return;
    var active = {};
    $$('.chip[data-filter][aria-pressed="true"]', scope).forEach(function (chip) {
      var parts = chip.getAttribute('data-filter').split(':');
      if (parts[1] !== 'all') (active[parts[0]] = active[parts[0]] || []).push(parts[1]);
    });
    var shown = 0;
    $$('tbody tr', target).forEach(function (tr) {
      if (tr.classList.contains('table__divider')) return;
      var ok = Object.keys(active).every(function (group) {
        var own = (tr.getAttribute('data-' + group) || '').split(' ');
        return active[group].some(function (v) { return own.indexOf(v) >= 0; });
      });
      tr.hidden = !ok;
      if (ok) shown += 1;
    });
    $$('[data-filter-count]', scope.parentNode).forEach(function (el) { el.textContent = String(shown); });
  }
  $$('[data-filter-scope]').forEach(function (scope) {
    $$('.chip[data-filter]', scope).forEach(function (chip) {
      chip.addEventListener('click', function () {
        var group = chip.getAttribute('data-filter').split(':')[0];
        var multi = chip.hasAttribute('data-multi');
        if (!multi) {
          $$('.chip[data-filter^="' + group + ':"]', scope).forEach(function (c) { c.setAttribute('aria-pressed', 'false'); });
          chip.setAttribute('aria-pressed', 'true');
        } else {
          chip.setAttribute('aria-pressed', String(chip.getAttribute('aria-pressed') !== 'true'));
        }
        applyFilters(scope);
      });
    });
  });

  /* ── 勾选与批量操作条 ── */
  function syncBatch(tableSel) {
    var table = doc.querySelector(tableSel);
    if (!table) return;
    var checks = $$('input[data-row-check]', table);
    var picked = checks.filter(function (c) { return c.checked; });
    checks.forEach(function (c) { var tr = c.closest('tr'); if (tr) tr.classList.toggle('is-selected', c.checked); });
    $$('[data-batchbar="' + tableSel + '"]').forEach(function (bar) {
      bar.hidden = picked.length === 0;
      $$('[data-batch-count]', bar).forEach(function (el) { el.textContent = String(picked.length); });
    });
    $$('[data-select-all="' + tableSel + '"]').forEach(function (all) {
      all.checked = picked.length > 0 && picked.length === checks.length;
      all.indeterminate = picked.length > 0 && picked.length < checks.length;
    });
  }
  $$('[data-select-all]').forEach(function (all) {
    var sel = all.getAttribute('data-select-all');
    all.addEventListener('change', function () {
      $$('input[data-row-check]', doc.querySelector(sel)).forEach(function (c) {
        if (!c.closest('tr').hidden) c.checked = all.checked;
      });
      syncBatch(sel);
    });
  });
  $$('input[data-row-check]').forEach(function (c) {
    c.addEventListener('change', function () {
      var table = c.closest('table');
      if (table && table.id) syncBatch('#' + table.id);
    });
  });
  $$('[data-batch-clear]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var sel = btn.getAttribute('data-batch-clear');
      $$('input[data-row-check]', doc.querySelector(sel)).forEach(function (c) { c.checked = false; });
      syncBatch(sel);
    });
  });

  /* ── 证据小标签浮层 ── */
  var pop = doc.createElement('div');
  pop.className = 'popover';
  pop.setAttribute('role', 'dialog');
  doc.body.appendChild(pop);
  var popOwner = null;
  function closePop() { pop.classList.remove('is-open'); popOwner = null; }
  function openPop(btn) {
    while (pop.firstChild) pop.removeChild(pop.firstChild);
    var title = doc.createElement('div');
    title.className = 'popover__title';
    title.textContent = btn.getAttribute('data-pop-title') || btn.textContent.trim();
    pop.appendChild(title);
    var dl = doc.createElement('dl');
    (btn.getAttribute('data-pop') || '').split(';').forEach(function (pair) {
      if (!pair.trim()) return;
      var i = pair.indexOf('=');
      var dt = doc.createElement('dt');
      var dd = doc.createElement('dd');
      dt.textContent = pair.slice(0, i).trim();
      dd.textContent = pair.slice(i + 1).trim();
      dl.appendChild(dt);
      dl.appendChild(dd);
    });
    pop.appendChild(dl);
    var r = btn.getBoundingClientRect();
    pop.style.left = Math.max(8, Math.min(r.left + window.scrollX, window.scrollX + doc.documentElement.clientWidth - 372)) + 'px';
    pop.style.top = (r.bottom + window.scrollY + 6) + 'px';
    pop.classList.add('is-open');
    popOwner = btn;
  }
  doc.addEventListener('click', function (e) {
    var btn = e.target.closest('button.etag[data-pop]');
    if (btn) {
      e.preventDefault();
      if (popOwner === btn) closePop(); else openPop(btn);
      return;
    }
    if (!e.target.closest('.popover')) closePop();
  });

  /* ── 图表与说明提示 ── */
  var tip = doc.createElement('div');
  tip.className = 'tip';
  tip.setAttribute('role', 'tooltip');
  doc.body.appendChild(tip);
  function showTip(el, x, y) {
    while (tip.firstChild) tip.removeChild(tip.firstChild);
    var lines = (el.getAttribute('data-tip') || '').split('|');
    lines.forEach(function (line, i) {
      var node = doc.createElement(i === 0 ? 'strong' : 'div');
      node.textContent = line;
      tip.appendChild(node);
    });
    var left = Math.min(x + 14, doc.documentElement.clientWidth - 280);
    tip.style.left = left + 'px';
    tip.style.top = (y + 16) + 'px';
    tip.classList.add('is-on');
  }
  function hideTip() { tip.classList.remove('is-on'); }
  $$('[data-tip]').forEach(function (el) {
    el.addEventListener('pointermove', function (e) { showTip(el, e.clientX, e.clientY); });
    el.addEventListener('pointerleave', hideTip);
    el.addEventListener('focus', function () {
      var r = el.getBoundingClientRect();
      showTip(el, r.left, r.bottom - 8);
    });
    el.addEventListener('blur', hideTip);
  });

  /* ── 轻提示 ── */
  var host = doc.createElement('div');
  host.className = 'toast-host';
  host.setAttribute('aria-live', 'polite');
  doc.body.appendChild(host);
  function toast(msg) {
    var t = doc.createElement('div');
    t.className = 'toast';
    t.setAttribute('role', 'status');
    t.textContent = msg;
    host.appendChild(t);
    window.requestAnimationFrame(function () { t.classList.add('is-on'); });
    window.setTimeout(function () {
      t.classList.remove('is-on');
      window.setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 400);
    }, 3000);
  }
  window.oppoToast = toast;
  $$('[data-toast]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (btn.getAttribute('aria-disabled') === 'true' || btn.disabled) return;
      toast(btn.getAttribute('data-toast'));
    });
  });

  /* ── 模拟长任务（原型反馈） ── */
  $$('[data-simulate]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (btn.classList.contains('is-loading') || btn.getAttribute('aria-disabled') === 'true') return;
      var label = btn.querySelector('span');
      var original = label ? label.textContent : '';
      btn.classList.add('is-loading');
      if (label) label.textContent = btn.getAttribute('data-loading-text') || '运行中…';
      window.setTimeout(function () {
        btn.classList.remove('is-loading');
        if (label) label.textContent = original;
        toast(btn.getAttribute('data-simulate'));
      }, 1600);
    });
  });

  /* ── 次要列开关 ── */
  $$('[data-cols-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var wrap = doc.querySelector(btn.getAttribute('data-cols-toggle'));
      if (!wrap) return;
      var on = wrap.classList.toggle('show-all');
      btn.setAttribute('aria-pressed', String(on));
    });
  });

  /* ── 口径切换（历史 / 截面） ── */
  function applyMode(mode) {
    doc.body.setAttribute('data-mode', mode);
    $$('.seg__opt[data-mode]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-mode') === mode)); });
    $$('[data-mode-only]').forEach(function (el) { el.hidden = el.getAttribute('data-mode-only') !== mode; });
  }
  if (doc.body.hasAttribute('data-mode')) applyMode(doc.body.getAttribute('data-mode'));
  $$('.seg__opt[data-mode]').forEach(function (b) {
    b.addEventListener('click', function () { applyMode(b.getAttribute('data-mode')); });
  });

  /* ── 表头排序 ── */
  $$('.th-sort').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var th = btn.closest('th');
      var table = btn.closest('table');
      var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
      var dir = btn.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
      $$('.th-sort', table).forEach(function (b) { b.removeAttribute('aria-sort'); });
      btn.setAttribute('aria-sort', dir);
      var body = table.tBodies[0];
      var rows = $$('tr', body).filter(function (tr) { return !tr.classList.contains('table__divider') && !tr.hasAttribute('data-pin-bottom'); });
      var pinned = $$('tr.table__divider, tr[data-pin-bottom]', body);
      rows.sort(function (a, b) {
        var ca = a.children[idx], cb = b.children[idx];
        var va = ca ? (ca.getAttribute('data-sort') || ca.textContent.trim()) : '';
        var vb = cb ? (cb.getAttribute('data-sort') || cb.textContent.trim()) : '';
        var na = parseFloat(va.replace(/[^0-9.\-]/g, '')), nb = parseFloat(vb.replace(/[^0-9.\-]/g, ''));
        var cmp = (!isNaN(na) && !isNaN(nb)) ? na - nb : va.localeCompare(vb, 'zh-CN');
        return dir === 'ascending' ? cmp : -cmp;
      });
      rows.concat(pinned).forEach(function (tr) { body.appendChild(tr); });
    });
  });

  /* ── 离开拦截（有未保存修改时） ── */
  var dirty = false;
  $$('form[data-guard] input, form[data-guard] select, form[data-guard] textarea').forEach(function (el) {
    el.addEventListener('input', function () {
      dirty = true;
      $$('[data-dirty-hint]').forEach(function (h) { h.hidden = false; });
    });
  });
  window.addEventListener('beforeunload', function (e) {
    if (!dirty) return;
    e.preventDefault();
    e.returnValue = '';
  });
  $$('[data-save]').forEach(function (btn) { btn.addEventListener('click', function () { dirty = false; }); });

  /* ── Esc 关闭 ── */
  doc.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (pop.classList.contains('is-open')) { closePop(); return; }
    var top = openStack[openStack.length - 1];
    if (top) closeOverlay(top.panel);
  });
})();
