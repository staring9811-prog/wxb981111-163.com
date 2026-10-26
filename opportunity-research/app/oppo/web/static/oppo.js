/* 品类机会判定台 · 运行时：写请求带启动令牌、表单就地校验、后台任务进度（只调用本机接口）。 */
(function () {
  'use strict';
  var doc = document;
  var token = (doc.querySelector('meta[name="oppo-token"]') || {}).content || '';
  window.oppoToken = token;

  function post(url, data) {
    var body = data instanceof FormData ? data : new FormData();
    if (!(data instanceof FormData) && data) Object.keys(data).forEach(function (k) {
      var v = data[k];
      if (Array.isArray(v)) v.forEach(function (x) { body.append(k, x); }); else body.append(k, v);
    });
    return fetch(url, { method: 'POST', body: body, headers: { 'X-Oppo-Token': token }, credentials: 'same-origin' })
      .then(function (r) { return r.json().catch(function () { return { ok: false, error: '服务器返回了无法识别的内容（' + r.status + '）' }; }); });
  }
  window.oppoPost = post;

  function clearErrors(form) {
    form.querySelectorAll('[data-error-for]').forEach(function (el) { el.textContent = ''; });
    form.querySelectorAll('.is-invalid').forEach(function (el) { el.classList.remove('is-invalid'); el.removeAttribute('aria-invalid'); });
    var ge = form.querySelector('[data-form-error]');
    if (ge) { ge.hidden = true; ge.querySelector('[data-form-error-text]') ? ge.querySelector('[data-form-error-text]').textContent = '' : (ge.textContent = ''); }
  }
  function showErrors(form, res) {
    var fields = res.fields || {};
    Object.keys(fields).forEach(function (name) {
      var slot = form.querySelector('[data-error-for="' + name + '"]');
      if (slot) slot.textContent = fields[name];
      var input = form.querySelector('[name="' + name + '"]');
      if (input) { input.classList.add('is-invalid'); input.setAttribute('aria-invalid', 'true'); }
    });
    var ge = form.querySelector('[data-form-error]');
    if (ge && res.error) {
      var t = ge.querySelector('[data-form-error-text]');
      if (t) t.textContent = res.error; else ge.textContent = res.error;
      ge.hidden = false;
    } else if (res.error && !Object.keys(fields).length) {
      if (window.oppoToast) window.oppoToast(res.error);
    }
    var first = form.querySelector('.is-invalid');
    if (first) first.focus();
  }

  doc.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches('form[data-ajax]')) return;
    e.preventDefault();
    clearErrors(form);
    var fd = new FormData(form);
    if (e.submitter && e.submitter.name) fd.append(e.submitter.name, e.submitter.value);
    var btns = form.querySelectorAll('button[type="submit"]');
    btns.forEach(function (b) { b.disabled = true; });
    post(form.getAttribute('action'), fd).then(function (res) {
      btns.forEach(function (b) { b.disabled = false; });
      if (res.ok) {
        if (res.job) { watchJob(res.redirect || location.pathname + location.search); return; }
        if (res.redirect) location.href = res.redirect; else location.reload();
      } else {
        showErrors(form, res);
      }
    }).catch(function () {
      btns.forEach(function (b) { b.disabled = false; });
      showErrors(form, { error: '请求没有完成，请检查本机服务是否在运行' });
    });
  });

  /* 后台任务：按钮 data-job-start="/jobs/compute" 发起；每 2 秒轮询 /jobs/current */
  var indicator = doc.getElementById('job-indicator');
  function setIndicator(st) {
    if (!indicator) return;
    indicator.hidden = !st.running;
    if (!st.running) return;
    var lab = indicator.querySelector('[data-job-label]');
    if (lab) lab.textContent = (st.label || '任务') + ' · ' + (st.step || '运行中');
    var bar = indicator.querySelector('.job__bar > i');
    if (bar) bar.style.width = Math.round((st.progress || 0) * 100) + '%';
    doc.querySelectorAll('[data-job-step]').forEach(function (el) { el.textContent = st.step || '运行中'; });
  }
  function watchJob(next) {
    var started = Date.now();
    function tick() {
      fetch('/jobs/current', { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (st) {
        setIndicator(st);
        if (st.running) { setTimeout(tick, 2000); return; }
        var msg = st.status === 'success' ? (st.label + '完成') : ((st.label || '任务') + '失败：' + (st.error || ''));
        var url = next || (location.pathname + location.search);
        url = url.replace(/([?&])toast=[^&]*/, '$1').replace(/[?&]$/, '');
        location.href = url + (url.indexOf('?') >= 0 ? '&' : '?') + 'toast=' + encodeURIComponent(msg);
      }).catch(function () { setTimeout(tick, 3000); });
    }
    setTimeout(tick, Date.now() - started > 0 ? 500 : 500);
  }
  window.oppoWatchJob = watchJob;
  doc.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-job-start]');
    if (!btn) return;
    e.preventDefault();
    if (btn.getAttribute('aria-disabled') === 'true' || btn.disabled) return;
    btn.classList.add('is-loading');
    btn.setAttribute('aria-disabled', 'true');
    post(btn.getAttribute('data-job-start'), {}).then(function (res) {
      if (!res.ok) {
        btn.classList.remove('is-loading');
        btn.removeAttribute('aria-disabled');
        if (window.oppoToast) window.oppoToast(res.error || '没有启动');
        return;
      }
      watchJob(btn.getAttribute('data-job-next'));
    });
  });
  if (indicator && !indicator.hidden) watchJob(null);

  /* 进入页面时的轻提示 */
  var t = doc.body.getAttribute('data-toast-on-load');
  if (t && window.oppoToast) window.oppoToast(t);

  /* 普通链接式确认：data-post="/url" 直接提交（带令牌） */
  doc.addEventListener('click', function (e) {
    var el = e.target.closest('[data-post]');
    if (!el) return;
    e.preventDefault();
    var payload = {};
    Array.prototype.slice.call(el.attributes).forEach(function (a) {
      if (a.name.indexOf('data-arg-') === 0) payload[a.name.slice(9)] = a.value;
    });
    post(el.getAttribute('data-post'), payload).then(function (res) {
      if (res.ok) { if (res.job) { watchJob(res.redirect); return; } if (res.redirect) location.href = res.redirect; else location.reload(); }
      else if (window.oppoToast) window.oppoToast(res.error || '没有完成');
    });
  });
})();
