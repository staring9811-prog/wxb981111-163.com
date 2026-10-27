/* 数据准备组页面脚本：数据包选择与上传、字段约定的行内编辑与分页、品类配置草稿、运行记录月份切换。 */
(function () {
  'use strict';
  var doc = document;
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || doc).querySelectorAll(sel)); };
  function post(url, data) { return window.oppoPost(url, data); }
  function toast(msg) { if (window.oppoToast) window.oppoToast(msg); }

  /* ── 数据包：选择 zip / 文件夹 / 本机路径，或拖入 ── */
  var drop = doc.querySelector('[data-stage-form]');
  if (drop) {
    var status = drop.querySelector('[data-stage-status]');
    var pathErr = drop.querySelector('[data-error-for="path"]');
    var busy = false;
    function setStatus(text) { if (status) { status.textContent = text; status.hidden = !text; } }
    function send(fd) {
      if (busy) return;
      busy = true;
      if (pathErr) pathErr.textContent = '';
      setStatus('正在读取清单文件…');
      drop.classList.add('is-loading');
      post('/packages/stage', fd).then(function (res) {
        busy = false;
        drop.classList.remove('is-loading');
        if (res.ok) { location.href = res.redirect; return; }
        setStatus('');
        var msg = (res.fields && res.fields.path) || res.error || '没有读取到数据包';
        if (pathErr) pathErr.textContent = msg; else toast(msg);
      }).catch(function () { busy = false; setStatus(''); toast('请求没有完成，请检查本机服务是否在运行'); });
    }
    function sendFiles(list) {
      var fd = new FormData();
      list.forEach(function (it) {
        fd.append('files', it.file, it.file.name);
        if (it.rel) fd.append('paths', it.rel);
      });
      send(fd);
    }
    drop.addEventListener('submit', function (e) {
      e.preventDefault();
      var v = (drop.querySelector('[name="path"]') || {}).value || '';
      var fd = new FormData();
      fd.append('path', v);
      send(fd);
    });
    var zip = drop.querySelector('[data-stage-zip]');
    if (zip) zip.addEventListener('change', function () {
      if (zip.files.length) sendFiles([{ file: zip.files[0] }]);
    });
    var folder = drop.querySelector('[data-stage-folder]');
    if (folder) folder.addEventListener('change', function () {
      var list = Array.prototype.slice.call(folder.files).map(function (f) { return { file: f, rel: f.webkitRelativePath || f.name }; });
      if (list.length) sendFiles(list);
    });
    ['dragenter', 'dragover'].forEach(function (ev) {
      drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('is-drag'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      drop.addEventListener(ev, function () { drop.classList.remove('is-drag'); });
    });
    function readEntry(entry, prefix, out) {
      return new Promise(function (resolve) {
        if (entry.isFile) {
          entry.file(function (f) { out.push({ file: f, rel: prefix + f.name }); resolve(); }, function () { resolve(); });
        } else if (entry.isDirectory) {
          var reader = entry.createReader();
          var all = [];
          (function readBatch() {
            reader.readEntries(function (ents) {
              if (!ents.length) {
                Promise.all(all.map(function (en) { return readEntry(en, prefix + entry.name + '/', out); })).then(resolve);
                return;
              }
              all = all.concat(Array.prototype.slice.call(ents));
              readBatch();
            }, function () { resolve(); });
          })();
        } else { resolve(); }
      });
    }
    drop.addEventListener('drop', function (e) {
      e.preventDefault();
      var items = e.dataTransfer && e.dataTransfer.items ? Array.prototype.slice.call(e.dataTransfer.items) : [];
      var entries = items.map(function (it) { return it.webkitGetAsEntry ? it.webkitGetAsEntry() : null; }).filter(Boolean);
      if (entries.length === 1 && entries[0].isDirectory) {
        var out = [];
        readEntry(entries[0], '', out).then(function () { if (out.length) sendFiles(out); });
        return;
      }
      var files = e.dataTransfer ? Array.prototype.slice.call(e.dataTransfer.files) : [];
      var z = files.filter(function (f) { return /\.zip$/i.test(f.name); });
      if (z.length) sendFiles([{ file: z[0] }]);
      else toast('请拖入 zip 文件或数据包文件夹');
    });
  }
  var importForm = doc.getElementById('import-form');
  if (importForm) importForm.addEventListener('submit', function () {
    var btn = importForm.querySelector('[data-import-submit]');
    if (btn) { btn.classList.add('is-loading'); btn.setAttribute('aria-disabled', 'true'); var s = btn.querySelector('span'); if (s) s.textContent = '导入中…'; }
    var st = doc.querySelector('[data-import-status]');
    if (st) { st.hidden = false; st.textContent = '正在复制文件、计算指纹并逐文件校验，完成后自动进入校验报告。可以离开本页，任务在后台继续。'; }
  });
  var focusPanel = doc.querySelector('#import-panel.is-focus');
  if (focusPanel) focusPanel.scrollIntoView({ block: 'start' });

  /* ── 通用：行内展开（data-expand 控制相邻编辑行） ── */
  doc.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-expand]');
    if (!btn) return;
    var row = doc.getElementById(btn.getAttribute('data-expand'));
    if (!row) return;
    var open = row.hasAttribute('data-collapsed');
    row.toggleAttribute('data-collapsed', !open);
    btn.setAttribute('aria-expanded', String(open));
    var use = btn.querySelector('use');
    if (use) use.setAttribute('href', open ? '#ph-caret-up' : '#ph-pencil-simple');
  });

  /* ── 字段约定：快照时只能选"回测不用"；搜索与分页 ── */
  $$('form[data-field-form]').forEach(function (form) {
    var timing = form.querySelector('[name="timing"]');
    function sync() {
      var snap = timing && timing.value === '快照';
      form.querySelectorAll('[name="usage"]').forEach(function (r) {
        var lock = snap && r.value !== '回测不用';
        r.disabled = lock;
        var label = r.closest('.choice');
        if (label) { label.style.opacity = lock ? '0.45' : ''; label.style.cursor = lock ? 'not-allowed' : ''; }
        if (snap && r.value === '回测不用') r.checked = true;
      });
      var d = form.querySelector('[data-snap-date]');
      if (d) d.hidden = !snap;
    }
    if (timing) { timing.addEventListener('change', sync); sync(); }
  });
  var table = doc.getElementById('field-table');
  doc.addEventListener('click', function (e) {
    if (!e.target.closest('[data-open="#batch-modal"]') || !table) return;
    var n = table.querySelectorAll('input[data-row-check]:checked').length;
    $$('#batch-modal [data-batch-count]').forEach(function (el) { el.textContent = String(n); });
  });
  if (table) {
    var PAGE = 50;
    var page = 1;
    var search = doc.querySelector('[data-field-search]');
    var pager = doc.querySelector('[data-pager]');
    function mainRows() { return $$('tbody tr[data-field-row]', table); }
    function apply() {
      var q = search ? search.value.trim().toLowerCase() : '';
      var shown = [];
      mainRows().forEach(function (tr) {
        var hitQ = !q || (tr.getAttribute('data-text') || '').toLowerCase().indexOf(q) >= 0;
        tr.toggleAttribute('data-search-hidden', !hitQ);
        var edit = doc.getElementById(tr.getAttribute('data-edit-id'));
        if (edit) edit.toggleAttribute('data-search-hidden', !hitQ);
        if (hitQ && !tr.hidden) shown.push(tr);
      });
      var pages = Math.max(1, Math.ceil(shown.length / PAGE));
      if (page > pages) page = pages;
      mainRows().forEach(function (tr) {
        var idx = shown.indexOf(tr);
        var off = idx < 0 || idx < (page - 1) * PAGE || idx >= page * PAGE;
        tr.toggleAttribute('data-page-hidden', off && idx >= 0);
        var edit = doc.getElementById(tr.getAttribute('data-edit-id'));
        if (edit) edit.toggleAttribute('data-page-hidden', off);
      });
      if (pager) {
        var info = pager.querySelector('[data-pager-info]');
        if (info) info.textContent = '共 ' + shown.length + ' 个字段 · 每页 ' + PAGE + ' 个';
        var box = pager.querySelector('[data-pager-pages]');
        if (box) {
          while (box.firstChild) box.removeChild(box.firstChild);
          function mk(label, p, cur, aria) {
            var b = doc.createElement('button');
            b.className = 'pager__btn';
            b.type = 'button';
            b.textContent = label;
            if (aria) b.setAttribute('aria-label', aria);
            if (cur) b.setAttribute('aria-current', 'page');
            if (p < 1 || p > pages) b.disabled = true;
            b.addEventListener('click', function () { page = p; apply(); table.scrollIntoView({ block: 'start' }); });
            box.appendChild(b);
          }
          mk('‹', page - 1, false, '上一页');
          for (var i = 1; i <= pages; i++) mk(String(i), i, i === page);
          mk('›', page + 1, false, '下一页');
        }
      }
    }
    if (search) search.addEventListener('input', function () { page = 1; apply(); });
    $$('.chip[data-filter]').forEach(function (c) { c.addEventListener('click', function () { page = 1; window.setTimeout(apply, 0); }); });
    apply();
  }

  /* ── 品类配置：自动存草稿、标记已修改、保存前校验 ── */
  var cfg = doc.getElementById('cfg-form');
  if (cfg) {
    var timer = null;
    var cat = cfg.getAttribute('data-category');
    function val(el) { return el.type === 'checkbox' ? String(el.checked) : el.value.trim(); }
    var curNo = cfg.getAttribute('data-cur-no');
    var PENCIL = '<svg class="icon" aria-hidden="true"><use href="#ph-pencil-simple"/></svg>';
    function wasText(el) {
      var w = el.getAttribute('data-was');
      if (el.type === 'checkbox') return w === 'true' ? '可回填' : '不回填';
      if (el.tagName === 'SELECT') {
        for (var i = 0; i < el.options.length; i++) if (el.options[i].value === w) return el.options[i].textContent.trim();
      }
      if (!w) return '空';
      var u = el.getAttribute('data-unit');
      return u ? w + (u === '%' ? u : ' ' + u) : w;
    }
    function badge() {
      var b = doc.createElement('span');
      b.className = 'badge was-badge';
      b.innerHTML = PENCIL + '已修改';
      return b;
    }
    /* 改过的项：标签旁“已修改”，下方注明当前版本的取值（如“v1 为 4 个月”）；表格单元格把两者放在输入框下方 */
    function mark(el, changed) {
      var f = el.closest('.field, td');
      if (!f) return;
      f.classList.toggle('is-modified', changed);
      var note = f.querySelector(':scope > .was-note');
      var lb = f.matches('.field') ? f.querySelector(':scope > .field__label') : null;
      var old = lb && lb.querySelector('.was-badge');
      if (!changed || !curNo) {
        if (note) note.remove();
        if (old) old.remove();
        return;
      }
      if (!note) {
        note = doc.createElement('span');
        note.className = 'field__hint was-note';
        var err = f.querySelector(':scope > .field-error');
        if (lb) f.insertBefore(note, err ? err.nextSibling : el.nextSibling);
        else f.appendChild(note);
      }
      note.textContent = 'v' + curNo + ' 为 ' + wasText(el) + (lb ? '。' : '');
      if (lb) { if (!old) lb.appendChild(badge()); } else note.insertBefore(badge(), note.firstChild);
    }
    function marks() {
      var n = 0;
      $$('[data-was]', cfg).forEach(function (el) {
        var changed = !el.disabled && val(el) !== el.getAttribute('data-was');
        if (changed) n += 1;
        mark(el, changed);
      });
      var b = doc.getElementById('draft-banner');
      if (b && n > 0) b.hidden = false;
      return n;
    }
    function clearErrors() {
      $$('[data-error-for]', cfg).forEach(function (s) { s.textContent = ''; });
      $$('.is-invalid', cfg).forEach(function (el) { el.classList.remove('is-invalid'); el.removeAttribute('aria-invalid'); });
    }
    function showErrors(fields) {
      var first = null;
      Object.keys(fields || {}).forEach(function (k) {
        var slot = cfg.querySelector('[data-error-for="' + k + '"]');
        if (slot) slot.textContent = fields[k];
        var input = cfg.querySelector('[name="' + k + '"]');
        if (input) { input.classList.add('is-invalid'); input.setAttribute('aria-invalid', 'true'); if (!first) first = input; }
      });
      return first;
    }
    function saveDraft() {
      return post('/settings/category/draft?category=' + cat, new FormData(cfg)).then(function (res) {
        clearErrors();
        if (res.fields) showErrors(res.fields);
        var at = doc.querySelector('[data-draft-at]');
        if (at && res.updated_at) at.textContent = res.updated_at;
        var b = doc.getElementById('draft-banner');
        if (b && typeof res.n_changes === 'number') {
          b.hidden = res.n_changes === 0;
          var t = b.querySelector('[data-draft-count]');
          if (t) t.textContent = String(res.n_changes);
        }
        return res;
      });
    }
    /* 细分维度：勾选后该行的分档才可填写并参与保存 */
    $$('[data-segdim]', cfg).forEach(function (box) {
      box.addEventListener('change', function () {
        var row = box.closest('tr');
        var bins = row && row.querySelector('input[name^="bins."]');
        if (bins) { bins.disabled = !box.checked; if (box.checked) bins.focus(); }
        if (row) row.classList.toggle('is-off', !box.checked);
      });
    });
    cfg.addEventListener('input', function () {
      marks();
      window.clearTimeout(timer);
      timer = window.setTimeout(saveDraft, 500);
    });
    cfg.addEventListener('change', function () { marks(); window.clearTimeout(timer); timer = window.setTimeout(saveDraft, 200); });
    cfg.addEventListener('submit', function (e) { e.preventDefault(); });
    $$('[data-cfg-review]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        if (btn.getAttribute('aria-disabled') === 'true') return;
        window.clearTimeout(timer);
        post('/settings/category/preview?category=' + cat, new FormData(cfg)).then(function (res) {
          clearErrors();
          if (!res.ok) {
            var first = showErrors(res.fields);
            if (first) first.focus(); else toast(res.error || '有配置项不合法');
            return;
          }
          var diff = doc.getElementById('save-diff');
          var none = doc.getElementById('save-none');
          var confirm = doc.getElementById('save-confirm');
          while (diff.firstChild) diff.removeChild(diff.firstChild);
          (res.diff || []).forEach(function (d) {
            ['diff__key', 'diff__old', 'diff__new'].forEach(function (cls, i) {
              var s = doc.createElement('span');
              s.className = cls;
              s.textContent = d[i];
              diff.appendChild(s);
            });
          });
          none.hidden = (res.diff || []).length > 0;
          if (res.missing && res.missing.length) {
            none.hidden = false;
            none.textContent = '还缺：' + res.missing.join('、') + '，全部填完才能保存。';
          }
          confirm.disabled = !res.can_save;
          window.oppoOpen('#save-modal');
        });
      });
    });
    marks();
  }

  /* ── 运行记录：选择月份 ── */
  $$('select[data-nav-select]').forEach(function (sel) {
    sel.addEventListener('change', function () { location.href = sel.value; });
  });
})();
