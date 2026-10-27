/* 台账、策略库与备份页面的交互（只调用本机接口）。 */
(function () {
  'use strict';
  var doc = document;
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || doc).querySelectorAll(sel)); };

  function here() {
    return (location.pathname + location.search).replace(/([?&])(toast|export|done)=[^&]*/g, '$1').replace(/[?&]+$/, '').replace(/\?&/, '?');
  }

  /* ── 记录立项决定弹窗（PAGE-F10-02） ── */
  var dm = doc.querySelector('[data-decision-modal]');
  function showTab(name) {
    if (!dm) return;
    $$('[data-dtab]', dm).forEach(function (t) {
      var on = t.getAttribute('data-dtab') === name;
      t.setAttribute('aria-selected', String(on));
      var p = doc.getElementById(t.getAttribute('aria-controls'));
      if (p) p.hidden = !on;
    });
    $$('[data-submit-for]', dm).forEach(function (b) {
      if ($$('[data-dtab]', dm).length) b.hidden = b.getAttribute('data-submit-for') !== name;
    });
  }
  function showCtx(key) {
    if (!dm) return;
    $$('[data-ctx-for]', dm).forEach(function (el) { el.hidden = el.getAttribute('data-ctx-for') !== (key || ''); });
  }
  if (dm) {
    $$('[data-next]', dm).forEach(function (i) { i.value = here(); });
    $$('[data-dtab]', dm).forEach(function (t) {
      t.addEventListener('click', function () { showTab(t.getAttribute('data-dtab')); });
    });
    var sel = dm.querySelector('[data-seg-select]');
    if (sel) {
      sel.addEventListener('change', function () { showCtx(sel.value); });
      showCtx(sel.value);
    }
    $$('[data-decision]', dm).forEach(function (r) {
      r.addEventListener('change', function () {
        var go = dm.querySelector('[data-decision]:checked');
        $$('[data-go-only]', dm).forEach(function (el) { el.hidden = !go || go.value !== '立项'; });
      });
    });
    if (dm.getAttribute('data-start-tab')) showTab(dm.getAttribute('data-start-tab'));
    doc.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-open="#decision-modal"]');
      if (!btn) return;
      showTab(btn.getAttribute('data-tab') || 'decide');
      var seg = btn.getAttribute('data-segment');
      $$('[data-next]', dm).forEach(function (i) { i.value = here(); });
      if (seg !== null) {
        $$('select[name="segment_key"]', dm).forEach(function (s) { s.value = seg; });
        showCtx(seg);
      } else if (btn.hasAttribute('data-tab')) {
        $$('select[name="segment_key"]', dm).forEach(function (s) { if (!dm.querySelector('[data-close-href]')) s.value = ''; });
        showCtx(sel ? sel.value : '');
      }
    }, true);
  }

  /* ── 录入自家上架数据（PAGE-F10-06）：上架月改变时更新列头与可填月份 ── */
  var lmodal = doc.querySelector('[data-launch-modal]');
  if (lmodal) {
    var cur = lmodal.getAttribute('data-current');
    var monthInput = lmodal.querySelector('[data-launch-month]');
    var addMonths = function (m, n) {
      var y = +m.slice(0, 4), mo = +m.slice(5, 7) - 1 + n;
      y += Math.floor(mo / 12); mo = ((mo % 12) + 12) % 12;
      return y + '-' + String(mo + 1).padStart(2, '0');
    };
    var syncMonths = function () {
      var v = (monthInput.value || '').trim();
      var ok = /^\d{4}-(0[1-9]|1[0-2])$/.test(v);
      for (var i = 1; i <= 6; i++) {
        var mm = ok ? addMonths(v, i - 1) : '';
        var lab = lmodal.querySelector('[data-month-label="' + i + '"]');
        if (lab) lab.textContent = mm || '—';
        $$('input[data-age="' + i + '"]', lmodal).forEach(function (inp) { inp.disabled = !!(mm && cur && mm > cur); });
      }
    };
    monthInput.addEventListener('input', syncMonths);
    syncMonths();
  }

  /* ── 规则编辑抽屉（PAGE-F11-02） ── */
  var drawer = doc.querySelector('[data-rule-drawer]');
  if (drawer) {
    var list = drawer.querySelector('#cond-list');
    var tpl = drawer.querySelector('#cond-tpl');
    var hint = drawer.querySelector('#reset-hint');
    var values = {};
    try { values = JSON.parse(drawer.querySelector('#rule-values').textContent || '{}'); } catch (err) { values = {}; }
    var SIG_OPS = [['>=', '≥'], ['>', '>'], ['<=', '≤'], ['<', '<']];
    var DIM_OPS = [['=', '='], ['!=', '≠']];
    var relabel = function () {
      var rows = $$('[data-cond]', list);
      rows.forEach(function (row, i) {
        row.querySelector('[data-join]').textContent = i === 0 ? '当' : '且';
        row.querySelector('[data-remove]').disabled = rows.length === 1;
        var err = row.querySelector('.cond-row__error');
        if (err) err.setAttribute('data-error-for', 'cond_' + (i + 1));
        $$('select, input', row).forEach(function (el) {
          var al = el.getAttribute('aria-label') || '';
          el.setAttribute('aria-label', '条件 ' + (i + 1) + ' · ' + al.replace(/^条件 \d+ · /, ''));
        });
      });
    };
    var fillOps = function (sel, ops, keep) {
      var prev = keep ? sel.value : '';
      while (sel.firstChild) sel.removeChild(sel.firstChild);
      ops.forEach(function (o) {
        var opt = doc.createElement('option');
        opt.value = o[0]; opt.textContent = o[1];
        sel.appendChild(opt);
      });
      if (prev && ops.some(function (o) { return o[0] === prev; })) sel.value = prev;
    };
    var setField = function (row) {
      var f = row.querySelector('[data-cond-field]').value || '';
      var kind = f.split(':')[0];
      var op = row.querySelector('[data-cond-op]');
      var slot = row.querySelector('[data-cond-value-slot]');
      var old = slot.querySelector('[name="cond_value"]');
      var label = old ? old.getAttribute('aria-label') : '值';
      fillOps(op, kind === 'signal' ? SIG_OPS : DIM_OPS, true);
      var el;
      if (kind === 'dim' || kind === 'attr') {
        el = doc.createElement('select');
        el.className = 'select';
        (values[f] || []).forEach(function (v) {
          var o = doc.createElement('option'); o.textContent = v; o.value = v; el.appendChild(o);
        });
        if (old && old.tagName === 'SELECT' && (values[f] || []).indexOf(old.value) >= 0) el.value = old.value;
      } else {
        el = doc.createElement('input');
        el.className = 'input input--num';
        el.placeholder = '如 +15%';
        if (old && old.tagName === 'INPUT') el.value = old.value;
      }
      el.name = 'cond_value';
      el.setAttribute('aria-label', label);
      slot.replaceChild(el, old);
    };
    var sig = function () {
      var rows = $$('[data-cond]', list).map(function (row) {
        return $$('select, input', row).map(function (el) { return el.value; }).join('|');
      });
      var act = drawer.querySelector('input[name="action"]:checked');
      return rows.join('&') + '#' + (act ? act.value : '');
    };
    var base = sig();
    var changed = function () {
      if (hint) hint.hidden = sig() === base;
      $$('[data-dirty-hint]', drawer).forEach(function (h) { h.hidden = false; });
    };
    list.addEventListener('change', function (e) {
      if (e.target.matches('[data-cond-field]')) setField(e.target.closest('[data-cond]'));
      changed();
    });
    list.addEventListener('input', changed);
    $$('input[name="action"]', drawer).forEach(function (r) { r.addEventListener('change', changed); });
    drawer.querySelector('#cond-add').addEventListener('click', function () {
      list.appendChild(tpl.content.cloneNode(true));
      relabel();
      changed();
      var rows = $$('[data-cond]', list);
      rows[rows.length - 1].querySelector('select').focus();
    });
    list.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-remove]');
      if (!btn || btn.disabled) return;
      btn.closest('[data-cond]').remove();
      relabel();
      changed();
    });
    relabel();
  }

  /* ── 表内搜索（策略库） ── */
  $$('[data-table-search]').forEach(function (inp) {
    var table = doc.querySelector(inp.getAttribute('data-table-search'));
    inp.addEventListener('input', function () {
      var q = inp.value.trim().toLowerCase();
      $$('tbody tr', table).forEach(function (tr) {
        var text = (tr.getAttribute('data-search') || tr.textContent).toLowerCase();
        tr.classList.toggle('is-search-hidden', !!q && text.indexOf(q) < 0);
      });
      syncEmpty(table);
    });
  });

  /* ── 筛选无结果时的空状态与"清除筛选" ── */
  function syncEmpty(table) {
    if (!table) return;
    var wrap = table.parentNode;
    var empty = wrap.querySelector('[data-filter-empty]');
    var visible = $$('tbody tr', table).filter(function (tr) { return !tr.hidden && !tr.classList.contains('is-search-hidden'); });
    if (empty) empty.hidden = visible.length > 0;
    var scope = doc.querySelector('[data-filter-scope="#' + table.id + '"]');
    if (scope) $$('[data-filter-count]', scope).forEach(function (el) { el.textContent = String(visible.length); });
  }
  $$('[data-filter-scope]').forEach(function (scope) {
    var table = doc.querySelector(scope.getAttribute('data-filter-scope'));
    $$('.chip[data-filter]', scope).forEach(function (chip) {
      chip.addEventListener('click', function () { window.setTimeout(function () { syncEmpty(table); }, 0); });
    });
  });
  $$('[data-filter-clear]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var sel = btn.getAttribute('data-filter-clear');
      var scope = doc.querySelector('[data-filter-scope="' + sel + '"]');
      if (!scope) return;
      $$('.chip[data-filter$=":all"]', scope).forEach(function (c) { c.click(); });
      $$('[data-table-search]', scope).forEach(function (i) { i.value = ''; i.dispatchEvent(new Event('input')); });
    });
  });

  /* ── 备份目录：检测能否写入 ── */
  var check = doc.querySelector('[data-dir-check]');
  if (check) {
    check.addEventListener('click', function () {
      var form = check.closest('form');
      var out = form.querySelector('[data-dir-result]');
      var err = form.querySelector('[data-error-for="directory"]');
      var label = check.querySelector('span');
      var original = label.textContent;
      label.textContent = '检测中…';
      check.disabled = true;
      window.oppoPost('/settings/backup/check', { directory: form.querySelector('[name="directory"]').value }).then(function (res) {
        label.textContent = original;
        check.disabled = false;
        while (out.firstChild) out.removeChild(out.firstChild);
        err.textContent = '';
        if (res.ok) {
          var b = doc.createElement('span');
          b.className = 'badge badge--ok';
          b.textContent = res.message;
          out.appendChild(b);
          out.appendChild(doc.createTextNode(' 可用空间 ' + res.free + ' · 检测于 ' + res.checked_at));
        } else {
          err.textContent = (res.fields && res.fields.directory) || res.error;
        }
      });
    });
  }

  /* ── 恢复：确认后按钮显示"恢复中…"，失败时恢复可点 ── */
  $$('[data-restore-confirm]').forEach(function (btn) {
    var form = doc.getElementById(btn.getAttribute('form'));
    var label = btn.querySelector('span');
    form.addEventListener('submit', function () {
      if (btn.disabled) return;
      btn.disabled = true;
      btn.classList.add('is-loading');
      label.textContent = '恢复中…';
    });
    var errBox = form.querySelector('[data-form-error]');
    new MutationObserver(function () {
      if (!errBox.hidden) { btn.disabled = false; btn.classList.remove('is-loading'); label.textContent = '确认恢复'; }
    }).observe(errBox, { attributes: true, attributeFilter: ['hidden'] });
  });
})();
