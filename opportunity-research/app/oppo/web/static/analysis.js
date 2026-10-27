/* 分析组页面脚本：导出报告弹窗（PAGE-F12-01）的三步流程与进度轮询；只调用本机接口。 */
(function () {
  'use strict';
  var doc = document;
  var modal = doc.getElementById('export-modal');
  if (!modal) return;

  var STEPS = ['confirm', 'running', 'result'];
  function step(name) {
    STEPS.forEach(function (s) {
      var panel = doc.getElementById('exp-' + s);
      if (panel) panel.hidden = s !== name;
      var tab = modal.querySelector('[data-step-tab="' + s + '"]');
      if (tab) tab.setAttribute('aria-selected', String(s === name));
    });
  }

  var ICONS = { done: 'check-circle', run: 'circle-notch', wait: 'clock', fail: 'warning-octagon' };
  function setSub(name, state, desc) {
    var li = modal.querySelector('[data-substep="' + name + '"]');
    if (!li) return;
    var svg = li.querySelector('svg.list__icon');
    if (svg) {
      svg.setAttribute('class', 'icon list__icon' + (state === 'done' ? ' list__icon--ok' : '') +
        (state === 'run' ? ' spin' : '') + (state === 'fail' ? ' list__icon--danger' : ''));
      var use = svg.querySelector('use');
      if (use) use.setAttribute('href', '#ph-' + ICONS[state]);
    }
    li.setAttribute('data-state', state);
    if (desc !== undefined) { var d = li.querySelector('[data-desc]'); if (d) d.textContent = desc; }
  }

  var startedAt = null;
  function render(st) {
    var p = Math.round((st.progress || 0) * 100);
    var secs = startedAt ? Math.round((Date.now() - startedAt) / 1000) : 0;
    var meta = modal.querySelector('[data-run-meta]');
    if (meta) meta.textContent = p + '% · 已用 ' + secs + ' 秒';
    var meter = modal.querySelector('[data-run-meter]');
    if (meter) { meter.setAttribute('aria-valuenow', String(p)); var i = meter.querySelector('i'); if (i) i.style.width = p + '%'; }
    var s = st.step || '';
    if (s.indexOf('读取快照') === 0) {
      setSub('snapshot', 'run', '进行中 · 核对内容指纹');
    } else if (s.indexOf('写入 Excel') === 0) {
      setSub('snapshot', 'done', '已完成 · 内容指纹与保存时一致');
      setSub('excel', 'run', s.replace('写入 Excel：', ''));
    } else if (s.indexOf('生成网页报告') === 0) {
      setSub('snapshot', 'done', '已完成 · 内容指纹与保存时一致');
      setSub('excel', 'done', '已完成 · 9 张工作表');
      setSub('html', 'run', '进行中');
    } else if (s.indexOf('自动备份') === 0) {
      setSub('snapshot', 'done', '已完成 · 内容指纹与保存时一致');
      setSub('excel', 'done', '已完成 · 9 张工作表');
      setSub('html', 'done', '已完成 · 单个离线文件');
      setSub('backup', 'run', '进行中');
    }
  }

  function fail(msg) {
    var box = modal.querySelector('[data-run-error]');
    var title = modal.querySelector('[data-run-title]');
    if (title) title.textContent = '导出没有完成';
    if (box) { box.hidden = false; var t = box.querySelector('[data-run-error-text]'); if (t) t.textContent = msg; }
    modal.querySelectorAll('[data-substep]').forEach(function (li) {
      if (li.getAttribute('data-state') === 'run') setSub(li.getAttribute('data-substep'), 'fail', '失败');
    });
  }

  function poll() {
    fetch('/jobs/current', { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (st) {
      if (st.running) {
        if (st.kind === 'export') render(st);
        setTimeout(poll, 600);
        return;
      }
      if (st.kind === 'export' && st.status === 'success' && st.result && st.result.export_id) {
        location.href = '/ranking?export=1&done=' + st.result.export_id;
        return;
      }
      fail(st.error || '导出没有完成');
    }).catch(function () { setTimeout(poll, 1500); });
  }

  function start() {
    var errBox = modal.querySelector('[data-export-error]');
    if (errBox) errBox.hidden = true;
    var runErr = modal.querySelector('[data-run-error]');
    if (runErr) runErr.hidden = true;
    ['snapshot', 'excel', 'html'].forEach(function (s) { setSub(s, 'wait', '等待'); });
    setSub('backup', 'wait', '等待 · 导出完成后开始');
    var title = modal.querySelector('[data-run-title]');
    if (title) title.textContent = '正在生成';
    window.oppoPost('/jobs/export', {
      month: modal.getAttribute('data-export-month') || '',
      mode: modal.getAttribute('data-export-mode') || 'history'
    }).then(function (res) {
      if (!res.ok) {
        step('confirm');
        if (errBox) { errBox.hidden = false; var t = errBox.querySelector('[data-export-error-text]'); if (t) t.textContent = res.error || '没有开始导出'; }
        return;
      }
      startedAt = Date.now();
      step('running');
      setSub('snapshot', 'run', '进行中');
      setTimeout(poll, 300);
    });
  }

  modal.addEventListener('click', function (e) {
    var b = e.target.closest('[data-export-start]');
    if (b) {
      e.preventDefault();
      if (b.getAttribute('aria-disabled') === 'true') return;
      start();
      return;
    }
    var rv = e.target.closest('[data-reveal]');
    if (rv) {
      e.preventDefault();
      window.oppoPost(rv.getAttribute('data-reveal'), {}).then(function (res) {
        if (window.oppoToast) window.oppoToast(res.ok ? (res.toast || '已打开') : (res.error || '没有打开'));
      });
      return;
    }
    var rb = e.target.closest('[data-backup-retry]');
    if (rb) {
      e.preventDefault();
      rb.disabled = true;
      window.oppoPost(rb.getAttribute('data-backup-retry'), {}).then(function (res) {
        if (res.ok && res.redirect) { location.href = res.redirect; return; }
        rb.disabled = false;
        if (window.oppoToast) window.oppoToast(res.error || '没有完成');
      });
    }
  });

  /* 打开时进入的步骤；导出进行中（例如刷新了页面）则继续显示进度 */
  var first = modal.getAttribute('data-first-step') || 'confirm';
  step(first);
  if (first === 'running') { startedAt = Date.now(); poll(); }
})();
