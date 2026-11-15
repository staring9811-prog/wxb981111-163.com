/* CMP-F16-01 费用评估确认弹窗：先估算再确认（AC-F16-07）。 */
(function () {
  var modal = document.getElementById('cmp-f16-01');
  if (!modal) return;
  var job = null;
  function q(k) { return modal.querySelector('[data-cost="' + k + '"]'); }
  function fmt(n) { return Number(n || 0).toLocaleString('en-US', { maximumFractionDigits: 2 }); }
  function post(url, data) {
    var fd = new FormData(); Object.keys(data || {}).forEach(function (k) { fd.append(k, data[k]); });
    return fetch(url, { method: 'POST', body: fd, headers: { accept: 'application/json' } }).then(function (r) { return r.json().then(function (j) { j._status = r.status; return j; }); });
  }
  function show(j) {
    job = j; var e = j.estimate || {};
    q('label').textContent = (j.label || '') + (j.month ? ' · ' + j.month : '');
    q('calls').textContent = fmt(e.calls) + ' 次';
    q('usd').textContent = '$' + fmt(e.usd_lo) + '–' + fmt(e.usd_hi);
    q('minutes').textContent = fmt(e.minutes) + ' 分钟';
    q('note').textContent = e.note || '';
    q('usage').innerHTML = (j.usage || []).map(function (u) {
      var used = u.unit === 'usd' ? '$' + fmt(u.spent_usd) : fmt(u.spent_qty) + ' 次';
      var cap = u.cap == null ? '未设上限' : (u.unit === 'usd' ? '$' + fmt(u.cap) : fmt(u.cap) + ' 次');
      return '<dt>' + u.name + ' 本月额度</dt><dd class="num">已用 ' + used + ' / ' + cap + '</dd>';
    }).join('');
    var w = (e.warnings || []);
    q('warn').hidden = !w.length; q('warntext').textContent = w.join('；');
    q('error').hidden = true;
    // 没有要采的内容（估算 nothing = true）：说明写在调用量下方，禁用“确认并开始”
    var ok = modal.querySelector('[data-cost-ok]'); ok.disabled = !!e.nothing; ok.title = e.nothing ? '没有需要采集的商品页' : '';
    window.oppoOpen ? window.oppoOpen('#cmp-f16-01') : modal.setAttribute('aria-hidden', 'false');
  }
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest('[data-cost-kind]');
    if (!b) return;
    ev.preventDefault();
    post('/jobs/estimate', { kind: b.dataset.costKind, month: b.dataset.costMonth || '', target: b.dataset.costTarget || '', params: b.dataset.costParams || '{}' })
      .then(function (j) {
        if (j._status >= 400) { window.oppoToast ? window.oppoToast(j.error || j.detail || '估算失败') : alert(j.error || j.detail); return; }
        show(j);
      });
  });
  modal.querySelector('[data-cost-ok]').addEventListener('click', function () {
    if (!job) return;
    post('/jobs/' + job.id + '/confirm', {}).then(function (j) {
      window.oppoClose ? window.oppoClose('#cmp-f16-01') : modal.setAttribute('aria-hidden', 'true');
      window.dispatchEvent(new CustomEvent('pdt:job-started', { detail: j }));
      if (window.oppoToast) window.oppoToast('已开始：' + (j.label || ''));
    });
  });
  modal.querySelector('[data-cost-cancel]').addEventListener('click', function () {
    if (job) post('/jobs/' + job.id + '/cancel', {});
    window.oppoClose ? window.oppoClose('#cmp-f16-01') : modal.setAttribute('aria-hidden', 'true');
  });
})();
