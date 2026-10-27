/* PAGE scripts owned by the products group: 新品与 SPU 筛选、合并建议（批量确认、修改、拆分）、信号页细分详情抽屉。 */
(function () {
  'use strict';
  var doc = document;
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || doc).querySelectorAll(sel)); };

  /* 下拉筛选：变更后提交所在表单 */
  $$('select[data-b-autosubmit]').forEach(function (sel) {
    sel.addEventListener('change', function () { if (sel.form) sel.form.submit(); });
  });
  /* 下拉跳转：data-b-nav="/signals?month=" */
  $$('select[data-b-nav]').forEach(function (sel) {
    sel.addEventListener('change', function () { location.href = sel.getAttribute('data-b-nav') + encodeURIComponent(sel.value); });
  });

  /* 表内搜索：按行 data-search 过滤（同一建议的主行与对照行同进同出） */
  $$('input[data-b-search]').forEach(function (input) {
    var table = doc.querySelector(input.getAttribute('data-b-search'));
    if (!table) return;
    input.addEventListener('input', function () {
      var q = input.value.trim().toLowerCase();
      $$('tbody > tr[data-search]', table).forEach(function (tr) {
        var hit = !q || tr.getAttribute('data-search').indexOf(q) >= 0;
        tr.classList.toggle('b-search-hidden', !hit);
      });
    });
  });

  /* 合并建议：批量确认表单带上勾选的建议 */
  $$('form[data-b-batch]').forEach(function (form) {
    var table = doc.querySelector(form.getAttribute('data-b-batch'));
    function picked() {
      return $$('input[data-row-check]', table).filter(function (c) { return c.checked && !c.closest('tr').hidden; });
    }
    form.addEventListener('submit', function () {
      $$('input[name="ids"]', form).forEach(function (el) { el.remove(); });
      picked().forEach(function (c) {
        var h = doc.createElement('input');
        h.type = 'hidden'; h.name = 'ids'; h.value = c.value;
        form.appendChild(h);
      });
    }, true);
    var modal = form.closest('.modal');
    $$('[data-open="#' + (modal ? modal.id : '') + '"]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        $$('[data-batch-count]', form).forEach(function (el) { el.textContent = String(picked().length); });
      });
    });
  });

  /* 合并建议：修改 / 拆分弹窗按所点行填充 */
  $$('[data-merge-code]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var modal = doc.querySelector(btn.getAttribute('data-open'));
      if (!modal) return;
      var code = btn.getAttribute('data-merge-code');
      var parents = btn.getAttribute('data-merge-parents').split(' ').filter(Boolean);
      var form = modal.querySelector('form[data-b-action]');
      if (form) form.setAttribute('action', form.getAttribute('data-b-action').replace('{code}', encodeURIComponent(code)));
      $$('[data-fill="code"]', modal).forEach(function (el) { el.textContent = code; });
      $$('[data-fill="kids"]', modal).forEach(function (el) { el.textContent = btn.getAttribute('data-merge-kids'); });
      $$('[data-fill="parents"]', modal).forEach(function (el) { el.textContent = parents.join('、'); });
      $$('[data-fill="parent-count"]', modal).forEach(function (el) { el.textContent = String(parents.length); });
      $$('[data-fill="parent-checks"]', modal).forEach(function (box) {
        while (box.firstChild) box.removeChild(box.firstChild);
        parents.forEach(function (asin) {
          var label = doc.createElement('label');
          var input = doc.createElement('input');
          var text = doc.createElement('span');
          label.className = 'check';
          input.type = 'checkbox'; input.name = 'keep'; input.value = asin; input.checked = true;
          text.className = 'mono'; text.textContent = asin;
          label.appendChild(input); label.appendChild(text);
          box.appendChild(label);
        });
      });
      $$('input[name="add"]', modal).forEach(function (el) { el.value = ''; });
    });
  });

  /* 信号页：点细分行在本页打开细分详情抽屉，关闭后回到原位置 */
  var slot = doc.getElementById('seg-drawer-slot');
  var sigTable = doc.getElementById('sig-table');
  var tipEl = null;
  function tip() { return tipEl || (tipEl = doc.querySelector('body > .tip')); }
  function bindTips(root) {
    $$('[data-tip]', root).forEach(function (el) {
      function show(x, y) {
        var t = tip();
        if (!t) return;
        while (t.firstChild) t.removeChild(t.firstChild);
        (el.getAttribute('data-tip') || '').split('|').forEach(function (line, i) {
          var n = doc.createElement(i === 0 ? 'strong' : 'div');
          n.textContent = line;
          t.appendChild(n);
        });
        t.style.left = Math.min(x + 14, doc.documentElement.clientWidth - 280) + 'px';
        t.style.top = (y + 16) + 'px';
        t.classList.add('is-on');
      }
      function hide() { var t = tip(); if (t) t.classList.remove('is-on'); }
      el.addEventListener('pointermove', function (e) { show(e.clientX, e.clientY); });
      el.addEventListener('pointerleave', hide);
      el.addEventListener('focus', function () { var r = el.getBoundingClientRect(); show(r.left, r.bottom - 8); });
      el.addEventListener('blur', hide);
    });
  }
  function watchClose(drawer) {
    if (!drawer || !window.MutationObserver) return;
    var mo = new MutationObserver(function () {
      if (drawer.classList.contains('is-open')) return;
      var u = new URL(location.href);
      if (u.searchParams.has('segment')) {
        u.searchParams.delete('segment');
        history.replaceState(null, '', u.pathname + (u.search ? u.search : ''));
      }
      $$('#sig-table tr.is-selected').forEach(function (tr) { tr.classList.remove('is-selected'); });
    });
    mo.observe(drawer, { attributes: true, attributeFilter: ['class'] });
  }
  watchClose(doc.getElementById('seg-drawer'));
  function openSegment(tr) {
    var url = tr.getAttribute('data-href');
    $$('#sig-table tr.is-selected').forEach(function (x) { x.classList.remove('is-selected'); });
    tr.classList.add('is-selected');
    fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.text(); }).then(function (html) {
      var parsed = new DOMParser().parseFromString(html, 'text/html');
      var fresh = parsed.getElementById('seg-drawer');
      if (!fresh) { location.href = url; return; }
      var old = doc.getElementById('seg-drawer');
      if (old && old.classList.contains('is-open') && window.oppoClose) window.oppoClose('#seg-drawer');
      if (old) old.remove();
      var node = doc.importNode(fresh, true);
      node.removeAttribute('data-open-on-load');
      slot.appendChild(node);
      bindTips(node);
      watchClose(node);
      history.pushState(null, '', url);
      if (window.oppoOpen) window.oppoOpen('#seg-drawer');
    }).catch(function () { location.href = url; });
  }
  if (sigTable && slot) {
    doc.addEventListener('click', function (e) {
      var tr = e.target.closest('#sig-table tbody tr[data-segment]');
      if (!tr) return;
      if (e.target.closest('button, .etag, input, select')) return;
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      openSegment(tr);
    }, true);
    doc.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      var tr = e.target.closest && e.target.closest('#sig-table tbody tr[data-segment]');
      if (!tr || e.target !== tr) return;
      e.preventDefault();
      e.stopPropagation();
      openSegment(tr);
    }, true);
    window.addEventListener('popstate', function () { location.reload(); });
  }
})();
