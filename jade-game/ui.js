/* 翡翠博弈 · 界面与三维工作台 */
(function () {
'use strict';
const C = window.Core, $ = s => document.querySelector(s), fmt = C.fmt;
const SAVE_KEY = 'jade-bargain-web-v1';
const canvas = $('#gl'), gl = canvas.getContext('webgl2', { antialias: false, preserveDrawingBuffer: true });
if (!gl) { $('#hint').textContent = '这台设备的浏览器不支持 WebGL2，无法显示三维原石。'; return; }

/* ---------- GL ---------- */
function sh(type, src) { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; }
const prog = gl.createProgram(); gl.attachShader(prog, sh(gl.VERTEX_SHADER, window.JADE_VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, window.JADE_FS)); gl.linkProgram(prog);
if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
gl.useProgram(prog);
const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
const loc = gl.getAttribLocation(prog, 'aPos'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
const U = {}; const u = n => U[n] || (U[n] = gl.getUniformLocation(prog, n));
function tex3d(unit) { const t = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_3D, t); for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_3D, p, gl.LINEAR); for (const p of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R]) gl.texParameteri(gl.TEXTURE_3D, p, gl.CLAMP_TO_EDGE); return t; }
const tGeom = tex3d(0), tMat = tex3d(1);
gl.uniform1i(u('uGeom'), 0); gl.uniform1i(u('uMat'), 1);
gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
let loaded = null;
function upload(vol) {
  if (loaded === vol) return; loaded = vol;
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_3D, tGeom); gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGBA16F, vol.nx, vol.ny, vol.nz, 0, gl.RGBA, gl.FLOAT, vol.geom);
  gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_3D, tMat); gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGBA8, vol.nx, vol.ny, vol.nz, 0, gl.RGBA, gl.UNSIGNED_BYTE, vol.mat);
}
function uploadBox(vol, b) {
  const w = b[1] - b[0] + 1, h = b[3] - b[2] + 1, d = b[5] - b[4] + 1, tmp = new Float32Array(w * h * d * 4); let o = 0;
  for (let k = b[4]; k <= b[5]; k++) for (let j = b[2]; j <= b[3]; j++) { const s = (b[0] + vol.nx * (j + vol.ny * k)) * 4; tmp.set(vol.geom.subarray(s, s + w * 4), o); o += w * 4; }
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_3D, tGeom); gl.texSubImage3D(gl.TEXTURE_3D, 0, b[0], b[2], b[4], w, h, d, gl.RGBA, gl.FLOAT, tmp);
}

/* ---------- 状态 ---------- */
let W = null;
const V = { mode: null, rec: null, piece: null, e: null, tool: 'rotate', burr: '中磨头', torch: { on: false, p: null, n: null, rake: false }, room: true, lens: null, cutT: 12, cutBottom: false, section: 0, msg: '' };
const cam = { yaw: 0.6, pitch: 0.35, dist: 300, ty: 0 };
const Q = { scale: 1, fast: 0.45, K: 12, tuned: false };
let tab = 'market', thumbs = new Map(), qcache = new Map();
const WHOLE = { id: -1, yLo: -1e4, yHi: 1e4 };

function save() { try { localStorage.setItem(SAVE_KEY, C.serialize(W)); } catch (e) { /* 存不了也能继续玩 */ } }
function load() { try { const s = localStorage.getItem(SAVE_KEY); if (s) { const w = JSON.parse(s); if (w && w.v === 1) return w; } } catch (e) { } return null; }

/* ---------- 相机与渲染 ---------- */
function camBasis() {
  const cp = Math.cos(cam.pitch), pos = [cam.dist * cp * Math.sin(cam.yaw), cam.ty + cam.dist * Math.sin(cam.pitch), cam.dist * cp * Math.cos(cam.yaw)];
  const f = [-pos[0], cam.ty - pos[1], -pos[2]], fl = Math.hypot(f[0], f[1], f[2]); f[0] /= fl; f[1] /= fl; f[2] /= fl;
  let r = [f[2] * -1, 0, f[0]]; r = [-f[2], 0, f[0]]; const rl = Math.hypot(r[0], r[2]) || 1; r[0] /= rl; r[2] /= rl;
  const up = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]];
  return { pos, f, r, up };
}
const TANF = Math.tan(0.30);
function rayAt(cx, cy) {
  const rect = canvas.getBoundingClientRect(), b = camBasis();
  const uu = ((cx - rect.left) - rect.width / 2) / (rect.height / 2) * TANF, vv = -((cy - rect.top) - rect.height / 2) / (rect.height / 2) * TANF;
  const d = [b.r[0] * uu + b.up[0] * vv + b.f[0], b.r[1] * uu + b.up[1] * vv + b.f[1], b.r[2] * uu + b.up[2] * vv + b.f[2]], l = Math.hypot(d[0], d[1], d[2]);
  return { ro: b.pos, rd: [d[0] / l, d[1] / l, d[2] / l] };
}
function curPiece() { return V.mode === 'review' ? { yLo: -1e4, yHi: V.section } : (V.piece || WHOLE); }
let pending = false, fullTimer = 0;
function invalidate(fast) { clearTimeout(fullTimer); if (fast) fullTimer = setTimeout(() => invalidate(false), 170); if (pending) { pendingFast = pendingFast && fast; return; } pending = true; pendingFast = !!fast; requestAnimationFrame(() => { pending = false; render(pendingFast ? Q.fast : 1); }); }
let pendingFast = false;
function render(scale, forceSize) {
  if (!V.e) { gl.viewport(0, 0, canvas.width, canvas.height); gl.clearColor(0.03, 0.027, 0.024, 1); gl.clear(gl.COLOR_BUFFER_BIT); return; }
  const rect = canvas.getBoundingClientRect(), pr = Math.min(window.devicePixelRatio || 1, 1.5) * Q.scale * scale;
  const w = forceSize || Math.max(2, Math.round(rect.width * pr)), h = forceSize || Math.max(2, Math.round(rect.height * pr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  const t0 = performance.now();
  gl.viewport(0, 0, w, h);
  const { st, vol } = V.e, b = camBasis(), pc = curPiece();
  upload(vol);
  gl.uniform2f(u('uRes'), w, h); gl.uniform3fv(u('uCamPos'), b.pos);
  gl.uniformMatrix3fv(u('uCamRot'), false, [b.r[0], b.r[1], b.r[2], b.up[0], b.up[1], b.up[2], -b.f[0], -b.f[1], -b.f[2]]);
  gl.uniform1f(u('uTan'), TANF); gl.uniform3f(u('uBox'), vol.hx, vol.hy, vol.hz);
  gl.uniform2f(u('uClip'), pc.yLo, pc.yHi); gl.uniform1f(u('uPristine'), V.mode === 'review' ? 1 : 0);
  const sk = st.skin, H = C.HUES[st.hue];
  gl.uniform3fv(u('uSkinCol'), sk.col); gl.uniform1f(u('uSkinSig'), sk.sig); gl.uniform1f(u('uSkinGrain'), sk.grain); gl.uniform1f(u('uSkinRel'), C.ORIGINS[st.origin].rel); gl.uniform1f(u('uWeather'), sk.weather); gl.uniform1f(u('uPhase'), sk.phase);
  gl.uniform3fv(u('uBodyCol'), C.BODIES[st.body]); gl.uniform3fv(u('uBandCol'), H.band); gl.uniform3fv(u('uHueAbs'), H.abs); gl.uniform3fv(u('uFogCol'), st.fog.col); gl.uniform1f(u('uFogT'), st.fog.t);
  const A = new Float32Array(24), B = new Float32Array(24), Cc = new Float32Array(24), Tt = new Float32Array(18);
  st.cracks.forEach((c, i) => { A.set([c.c[0], c.c[1], c.c[2], c.R], i * 4); B.set([c.n[0], c.n[1], c.n[2], c.open], i * 4); Cc.set([c.warp, c.freq, c.phase, c.skinVis], i * 4); Tt.set(c.t1, i * 3); });
  gl.uniform1i(u('uNCr'), st.cracks.length); gl.uniform4fv(u('uCrA'), A); gl.uniform4fv(u('uCrB'), B); gl.uniform4fv(u('uCrC'), Cc); gl.uniform3fv(u('uCrT'), Tt);
  const T = V.torch; let amb = V.room ? 1 : 0.06;
  if (T.on && T.p) {
    const p = T.p, n = T.n, skinT = C.sampleG(vol, 2, p[0], p[1], p[2]), depth0 = -C.sampleG(vol, 0, p[0], p[1], p[2]);
    const onFlesh = depth0 > skinT - 0.2, inset = onFlesh ? 0.6 : skinT - Math.max(0, depth0) + 0.6;
    const entry = onFlesh ? 1 : Math.max(0.02, Math.exp(-sk.sig * Math.max(0, skinT - Math.max(0, depth0))));
    let tan = [b.r[0] - n[0] * (b.r[0] * n[0] + b.r[1] * n[1] + b.r[2] * n[2]), b.r[1] - n[1] * (b.r[0] * n[0] + b.r[1] * n[1] + b.r[2] * n[2]), b.r[2] - n[2] * (b.r[0] * n[0] + b.r[1] * n[1] + b.r[2] * n[2])];
    const tl = Math.hypot(tan[0], tan[1], tan[2]) || 1; tan = tan.map(v => v / tl);
    const dir = T.rake ? [-n[0] * 0.35 + tan[0] * 0.94, -n[1] * 0.35 + tan[1] * 0.94, -n[2] * 0.35 + tan[2] * 0.94] : [-n[0], -n[1], -n[2]];
    gl.uniform4f(u('uTorch'), p[0] - n[0] * inset, p[1] - n[1] * inset, p[2] - n[2] * inset, 34 * entry * (T.rake ? 0.45 : 1));
    gl.uniform3fv(u('uTorchDir'), dir); gl.uniform3fv(u('uTorchSurf'), p);
    if (T.rake) { gl.uniform3f(u('uRakePos'), p[0] + n[0] * 9 - tan[0] * 22, p[1] + n[1] * 9 - tan[1] * 22, p[2] + n[2] * 9 - tan[2] * 22); gl.uniform1f(u('uRakeFall'), 1600); gl.uniform1f(u('uRakeI'), 3.2); }
    else { gl.uniform3f(u('uRakePos'), p[0] + n[0] * 3, p[1] + n[1] * 3, p[2] + n[2] * 3); gl.uniform1f(u('uRakeFall'), 40); gl.uniform1f(u('uRakeI'), 0.6); }
  } else gl.uniform4f(u('uTorch'), 0, 0, 0, 0);
  gl.uniform1f(u('uSpread'), 260); gl.uniform1f(u('uAmbient'), amb);
  if (V.lens && !forceSize) { const R = Math.min(w, h) * 0.2; gl.uniform4f(u('uLens'), (V.lens.x - rect.left) / rect.width * w, (1 - (V.lens.y - rect.top) / rect.height) * h, R, 3.2); } else gl.uniform4f(u('uLens'), 0, 0, 0, 1);
  let cutY = -1e5;
  if (V.tool === 'slice' && V.mode === 'own' && !forceSize) { const ext = C.extentY(vol, pc); cutY = V.cutBottom ? ext[0] + V.cutT : ext[1] - V.cutT; }
  gl.uniform1f(u('uCutY'), cutY); gl.uniform1i(u('uK'), scale < 1 ? 8 : Q.K);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  if (scale === 1 && !forceSize && !Q.tuned) { const px = new Uint8Array(4); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); const ms = performance.now() - t0; if (ms > 350 && Q.scale > 0.45) { Q.scale *= 0.7; invalidate(false); } else Q.tuned = true; }
}
function thumb(s, piece) {
  const e = C.getVol(s), key = s.id + ':' + piece.id + ':' + e.vol.ver + ':' + piece.yLo + ':' + piece.yHi;
  if (thumbs.has(key)) return thumbs.get(key);
  if (!V.e || V.e.vol !== e.vol) return '';
  const keep = { cam: Object.assign({}, cam), piece: V.piece, torch: V.torch.on, room: V.room, lens: V.lens, mode: V.mode };
  const ext = C.extentY(e.vol, piece);
  V.piece = piece; V.mode = 'own'; V.torch.on = false; V.room = true; V.lens = null; cam.yaw = 0; cam.pitch = 1.5607; cam.ty = (ext[0] + ext[1]) / 2; cam.dist = Math.max(e.vol.hx, e.vol.hz) * 3.6;
  render(1, 128); const url = canvas.toDataURL('image/jpeg', 0.8);
  Object.assign(cam, keep.cam); V.piece = keep.piece; V.torch.on = keep.torch; V.room = keep.room; V.lens = keep.lens; V.mode = keep.mode;
  thumbs.set(key, url); return url;
}

/* ---------- 选择 ---------- */
function frame() { const { vol } = V.e, ext = C.extentY(vol, curPiece()); cam.ty = V.mode === 'review' ? 0 : (ext[0] + ext[1]) / 2; cam.dist = Math.max(vol.hx, vol.hz, (ext[1] - ext[0]) / 2) * 4.3; }
function view(mode, rec, piece) {
  V.mode = mode; V.rec = rec; V.piece = piece; V.e = rec ? C.getVol(rec) : null; V.torch.p = null; V.torch.on = false; V.lens = null; V.msg = '';
  if (V.e) { if (mode === 'review') V.section = V.e.vol.hy; frame(); }
  if (mode !== 'own' && (V.tool === 'grind' || V.tool === 'slice')) V.tool = 'rotate';
  renderAll();
}
function getQuotes(s, p) { const e = C.getVol(s), key = s.id + ':' + p.id + ':' + e.vol.ver + ':' + W.day + ':' + p.yLo + ':' + p.yHi; let q = qcache.get(key); if (!q) { q = C.quotes(W, s, p); qcache.set(key, q); } return q; }
function bookOf(s) { let v = s.proceeds, all = true; for (const p of s.pieces) if (!p.sold) { const e = C.volCache.get(s.seed); if (!e) { all = false; continue; } v += getQuotes(s, p).best; } return { v, all }; }

/* ---------- 面板 ---------- */
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
function pct(a, b) { const r = (a / b - 1) * 100; return `<span class="${r >= 0 ? 'up' : 'down'}">${r >= 0 ? '+' : ''}${r.toFixed(0)}%</span>`; }
function renderTop() {
  const recv = W.recv.reduce((a, r) => a + r.amt, 0);
  let inv = 0; for (const s of W.stones) if (!s.closed) { for (const p of s.pieces) if (!p.sold) inv += (s.last[p.id] || {}).best || 0; }
  $('#stats').innerHTML = `<div><span>第</span><b>${W.day}</b><span>天</span></div><div><span>现金</span><b>${fmt(W.cash)}</b></div><div><span>应收</span><b>${fmt(recv)}</b></div><div><span>存货报价</span><b>${fmt(inv)}</b></div>`;
}
function renderSide() {
  document.querySelectorAll('#tabs button').forEach(b => b.setAttribute('aria-selected', b.dataset.tab === tab));
  const el = $('#panel'); let h = '';
  if (tab === 'market') {
    h += `<p class="note">今日货源。先转着看、打灯看，再决定出不出价。不买也是一种选择。</p>`;
    W.market.forEach((L, i) => {
      const sel = V.mode === 'market' && V.rec === L;
      h += `<article class="card ${sel ? 'sel' : ''} ${L.sold ? 'gone' : ''}" data-act="listing" data-i="${i}"><div class="row"><b>${L.origin} · ${L.info.skin}</b><span class="price">${L.sold ? '已买' : fmt(L.ask)}</span></div>
      <div class="row dim"><span>${(L.info.weight / 1000).toFixed(2)} kg · ${L.info.dims.join('×')} mm</span><span>${L.channel}</span></div>
      <div class="row dim"><span class="tag ${L.info.window ? 'w' : ''}">${L.info.window ? '卖家已开窗' : '全蒙头'}</span></div>`;
      if (sel && !L.sold) h += `<div class="bargain"><label for="offer">出价（元）</label><div class="row"><input id="offer" type="number" inputmode="numeric" min="0" step="100" value="${V.offer || Math.round(L.ask * 0.7 / 100) * 100}"><button data-act="offer">还价</button><button data-act="take" class="pri">照价买 ${fmt(L.ask)}</button></div>${V.msg ? `<p class="say">${esc(V.msg)}</p>` : ''}</div>`;
      h += `</article>`;
    });
  } else if (tab === 'mine') {
    const open = W.stones.filter(s => !s.closed);
    if (!open.length) h += `<p class="note">还没有存货。到「货源」里挑一块买下，就能在这里开窗、切片和询价。</p>`;
    for (const s of open) {
      const act = V.mode === 'own' && V.rec === s, bk = bookOf(s);
      h += `<article class="card ${act ? 'sel' : ''}"><div class="row"><b>#${s.id} ${s.origin} · ${s.info.skin}</b><span class="dim">第 ${s.buyDay} 天买入</span></div>
      <div class="row dim"><span>买入 ${fmt(s.buyPrice)} · 加工 ${fmt(s.costs)} · 已回款 ${fmt(s.proceeds)}</span></div>
      ${bk.all ? `<div class="row"><span>账面（回款＋当前最高报价）${fmt(bk.v)}</span><span>${pct(bk.v, s.buyPrice)}</span></div>` : ''}<div class="pieces">`;
      for (const p of s.pieces) { const t = thumb(s, p); h += `<button class="pc ${act && V.piece === p ? 'on' : ''} ${p.sold ? 'sold' : ''}" data-act="piece" data-s="${s.id}" data-p="${p.id}" ${p.sold ? 'disabled' : ''}>${t ? `<img src="${t}" alt="">` : '<i></i>'}<span>${p.name}${p.sold ? ' 已售' : ''}</span></button>`; }
      h += `</div>`;
      if (act && V.piece && !V.piece.sold) {
        const q = getQuotes(s, V.piece), last = s.last[V.piece.id], stt = q.stats;
        h += `<div class="quotes"><div class="row dim"><span>${V.piece.name} · ${Math.round(stt.weight)} g · 厚 ${stt.thickness.toFixed(0)} mm${stt.bracelets ? ` · 可见手镯位 ${stt.bracelets}` : ''}</span></div>`;
        if (last && last.prev != null && last.prev !== q.best) h += `<p class="delta">较上次报价 ${pct(q.best, Math.max(1, last.prev))}${last.why && last.why.length ? '：' + esc(last.why.join('；')) : ''}</p>`;
        for (const o of q.list) h += `<div class="row q"><span><b>${o.buyer}</b> <i>${esc(o.note)}</i></span>${o.price ? `<button data-act="sell" data-b="${o.buyer}">${fmt(o.price)} 卖</button>` : '<span class="dim">不收</span>'}</div>`;
        h += `<p class="note">报价只在今天有效。账面开涨不是现金到账。</p></div>`;
      }
      h += `</article>`;
    }
  } else {
    const recv = W.recv.map(r => `<div class="row dim"><span>${r.from} 货款</span><span>第 ${r.day} 天到账 ${fmt(r.amt)}</span></div>`).join('');
    h += `<article class="card"><div class="row"><b>资金</b><span>现金 ${fmt(W.cash)}</span></div>${recv || '<div class="row dim"><span>没有在途货款</span></div>'}<div class="row dim"><span>每天铺面与生活开销 ${C.ECON.daily}</span></div></article>`;
    for (const s of W.stones.filter(s => s.closed).reverse()) {
      const r = s.review, net = s.proceeds - s.buyPrice - s.costs;
      h += `<article class="card ${V.mode === 'review' && V.rec === s ? 'sel' : ''}"><div class="row"><b>复盘 #${s.id} ${s.origin} · ${s.info.skin}</b><span class="${net >= 0 ? 'up' : 'down'}">${net >= 0 ? '+' : ''}${fmt(net)}</span></div>
      <div class="row dim"><span>买入 ${fmt(s.buyPrice)} · 加工 ${fmt(s.costs)} · 回款 ${fmt(s.proceeds)} · 持有 ${s.closeDay - s.buyDay} 天</span></div>
      <div class="row dim"><span>买入当天原样转手最高 ${fmt(s.flip)}；途中账面最高 ${fmt(s.best)}</span></div>
      <div class="row dim"><span>真相：${r.water}，${r.feats.length ? r.hue + '（' + r.feats.join('、') + '）' : '基本无色'}，${r.cracks} 条裂；完全看清时的出材潜力约 ${fmt(r.truth)}</span></div>
      <div class="row"><span class="dim">一次赚钱不等于判断正确，亏了也不一定是决策错。</span><button data-act="review" data-s="${s.id}">看剖面</button></div></article>`;
    }
    h += `<article class="card"><b>流水</b>${W.log.slice(-40).reverse().map(l => `<div class="row dim"><span>第 ${l.day} 天 ${esc(l.t)}</span><span>${l.amt ? (l.amt > 0 ? '+' : '') + fmt(l.amt) : ''}</span></div>`).join('')}</article>`;
  }
  el.innerHTML = h;
}
const HINTS = {
  rotate: '拖动转石头，滚轮或双指缩放。右键拖动在任何工具下都能转。',
  torch: '点或拖到石头上压灯，灯会留在原处；转到别的角度看光从哪里透出来。',
  loupe: '移动放大镜看皮壳颗粒、松花、细裂和玉肉晶粒。可以和手电一起用。',
  grind: '在石头上拖动磨皮开窗。同一处来回磨会越磨越深，磨掉的料回不来。',
  slice: '橙线是下一刀的位置。从顶面往下切指定厚度，切下的片单独成为一件货。',
};
function renderTools() {
  const own = V.mode === 'own' && V.piece && !V.piece.sold;
  document.querySelectorAll('#tools button[data-tool]').forEach(b => { b.setAttribute('aria-pressed', b.dataset.tool === V.tool); b.disabled = (b.dataset.tool === 'grind' || b.dataset.tool === 'slice') && !own; });
  let o = '';
  if (V.mode === 'review') o += `<label for="sec">剖面高度</label><input id="sec" type="range" min="${(-V.e.vol.hy).toFixed(0)}" max="${V.e.vol.hy.toFixed(0)}" step="0.5" value="${V.section}"><span class="dim">复盘：这是石头原本的内部</span>`;
  else if (V.tool === 'torch') o += `<button data-act="rake" aria-pressed="${V.torch.rake}">斜照</button><button data-act="toff" ${V.torch.on ? '' : 'disabled'}>关灯</button>`;
  else if (V.tool === 'grind') o += Object.keys(C.TOOLS).map(k => `<button data-act="burr" data-k="${k}" aria-pressed="${V.burr === k}">${k}</button>`).join('');
  else if (V.tool === 'slice' && own) {
    const ext = C.extentY(V.e.vol, V.piece), T = ext[1] - ext[0], max = Math.max(3, Math.min(40, Math.floor(T - 3 - C.ECON.kerf)));
    if (V.cutT > max) V.cutT = max;
    o += `<label for="cutT">厚度 <b id="cutV">${V.cutT}</b> mm</label><input id="cutT" type="range" min="3" max="${max}" step="1" value="${V.cutT}"><button data-act="flip">${V.cutBottom ? '从底面切' : '从顶面切'}</button><button data-act="cut" class="pri" ${T < 7.5 ? 'disabled' : ''}>下刀</button><span class="dim">已推进 ${(V.e.vol.hy * 2 - T).toFixed(0)} mm · 剩余厚 ${T.toFixed(0)} mm</span>`;
  }
  o += `<button data-act="room" aria-pressed="${V.room}">室内灯</button>`;
  $('#opts').innerHTML = o;
  let t = V.e ? HINTS[V.tool] : '从右侧「货源」里点一块石头开始看料。';
  if (V.mode === 'review') t = '复盘剖面：拖动滑块看这块石头原本的内部结构。';
  $('#hint').textContent = V.note || t;
  $('#title').textContent = V.rec ? (V.mode === 'market' ? `${V.rec.origin} · ${V.rec.info.skin}` : `#${V.rec.id} ${V.rec.origin} · ${V.rec.info.skin}${V.mode === 'own' && V.piece ? ' · ' + V.piece.name : ''}${V.mode === 'review' ? ' · 复盘' : ''}`) : '';
}
function renderAll() { renderTop(); renderSide(); renderTools(); invalidate(false); $('#over').hidden = !W.over; }
function refreshQuote(s, p, record) {
  const prev = s.last[p.id]; qcache.clear();
  const q = getQuotes(s, p); s.last[p.id] = { best: q.best, stats: q.stats, prev: prev ? prev.best : null, why: prev ? C.explain(prev.stats, q.stats) : [] };
  if (record) { const bk = bookOf(s); if (bk.all && bk.v > s.best) s.best = bk.v; }
}

/* ---------- 交互 ---------- */
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-act],[data-tab],[data-tool]'); if (!b) return;
  if (b.dataset.tab) { tab = b.dataset.tab; renderSide(); return; }
  if (b.dataset.tool) { V.tool = b.dataset.tool; V.lens = null; V.note = ''; renderTools(); invalidate(false); return; }
  const a = b.dataset.act;
  if (a === 'listing') { if (ev.target.closest('.bargain')) return; const L = W.market[+b.dataset.i]; V.offer = 0; if (V.rec !== L) view('market', L, null); }
  else if (a === 'offer' || a === 'take') {
    const L = V.rec, offer = a === 'take' ? L.ask : +($('#offer').value || 0); V.offer = offer;
    const r = C.negotiate(W, L, offer); V.msg = r.msg;
    if (r.res === 'deal') { const s = C.buy(W, L, r.price); s.last[0] = { best: s.flip, stats: C.quotes(W, s, s.pieces[0]).stats, prev: null, why: [] }; tab = 'mine'; save(); view('own', s, s.pieces[0]); V.note = `成交 ${fmt(r.price)}。现在可以开窗、切片，或直接询价转手。`; renderTools(); return; }
    save(); renderSide();
  }
  else if (a === 'piece') { const s = W.stones.find(x => x.id === +b.dataset.s), p = s.pieces.find(x => x.id === +b.dataset.p); view('own', s, p); if (!s.last[p.id]) refreshQuote(s, p); renderAll(); }
  else if (a === 'sell') { const s = V.rec, p = V.piece, q = getQuotes(s, p).list.find(o => o.buyer === b.dataset.b); C.sell(W, s, p, q); qcache.clear(); save(); const next = s.pieces.find(x => !x.sold); if (s.closed) { tab = 'ledger'; view('review', s, null); } else view('own', s, next); }
  else if (a === 'review') { view('review', W.stones.find(x => x.id === +b.dataset.s), null); }
  else if (a === 'rake') { V.torch.rake = !V.torch.rake; renderTools(); invalidate(false); }
  else if (a === 'toff') { V.torch.on = false; renderTools(); invalidate(false); }
  else if (a === 'room') { V.room = !V.room; renderTools(); invalidate(false); }
  else if (a === 'burr') { V.burr = b.dataset.k; renderTools(); }
  else if (a === 'flip') { V.cutBottom = !V.cutBottom; renderTools(); invalidate(false); }
  else if (a === 'cut') {
    const s = V.rec, p = V.piece, r = C.cut(W, s, p, V.cutT, V.cutBottom);
    if (!r.ok) { V.note = r.msg; renderTools(); return; }
    refreshQuote(s, p, false); refreshQuote(s, r.piece, true); V.note = `切下 ${r.piece.name}，切工 ${fmt(r.cost)}。片料已放到右侧，可单独查看和出售。`;
    tab = 'mine'; save(); frame(); renderAll();
  }
  else if (a === 'next') { const n = C.nextDay(W); qcache.clear(); for (const s of W.stones) if (!s.closed) for (const p of s.pieces) if (!p.sold && C.volCache.get(s.seed)) refreshQuote(s, p, true); save(); tab = 'market'; view(null, null, null); V.note = `第 ${W.day} 天。${n.join('，')}。货源已更新，昨天的报价作废。`; renderTools(); }
  else if (a === 'restart') { $('#confirm').hidden = false; }
  else if (a === 'no') { $('#confirm').hidden = true; }
  else if (a === 'yes') { $('#confirm').hidden = true; C.volCache.clear(); thumbs.clear(); qcache.clear(); loaded = null; W = C.newWorld((Date.now() ^ (Math.random() * 1e9)) >>> 0); save(); tab = 'market'; view(null, null, null); }
  else if (a === 'help') { $('#help').hidden = !$('#help').hidden; }
});
document.addEventListener('input', ev => {
  if (ev.target.id === 'cutT') { V.cutT = +ev.target.value; $('#cutV').textContent = V.cutT; invalidate(true); }
  if (ev.target.id === 'sec') { V.section = +ev.target.value; invalidate(true); }
});
const ptrs = new Map(); let drag = null, lastCarve = null, strokeCost = 0;
function torchAt(ev) { const r = rayAt(ev.clientX, ev.clientY), h = C.pick(V.e.vol, curPiece(), r.ro, r.rd, V.mode === 'review'); if (h) { V.torch.on = true; V.torch.p = h.p; V.torch.n = h.n; } return h; }
function carveAt(ev) {
  const r = rayAt(ev.clientX, ev.clientY), h = C.pick(V.e.vol, V.piece, r.ro, r.rd); if (!h) return;
  if (lastCarve && Math.hypot(h.p[0] - lastCarve[0], h.p[1] - lastCarve[1], h.p[2] - lastCarve[2]) < 1.2) return;
  lastCarve = h.p; const res = C.grind(W, V.rec, V.piece, h.p, h.n, V.burr); strokeCost += res.removed * C.ECON.grind;
  uploadBox(V.e.vol, res.box); invalidate(true);
}
canvas.addEventListener('contextmenu', e => e.preventDefault());
canvas.addEventListener('pointerdown', ev => {
  if (!V.e) return; canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]);
  if (ptrs.size === 2) { const a = [...ptrs.values()]; drag = { kind: 'pinch', d: Math.hypot(a[0][0] - a[1][0], a[0][1] - a[1][1]), x: (a[0][0] + a[1][0]) / 2, y: (a[0][1] + a[1][1]) / 2 }; return; }
  const orbit = ev.button === 2 || V.tool === 'rotate' || V.tool === 'slice' || ev.shiftKey || (V.tool === 'grind' && V.mode !== 'own');
  if (orbit) drag = { kind: 'orbit', x: ev.clientX, y: ev.clientY };
  else if (V.tool === 'torch') { drag = { kind: 'torch' }; torchAt(ev); renderTools(); invalidate(true); }
  else if (V.tool === 'loupe') { drag = { kind: 'loupe' }; V.lens = { x: ev.clientX, y: ev.clientY }; invalidate(true); }
  else if (V.tool === 'grind') { drag = { kind: 'grind' }; lastCarve = null; strokeCost = 0; carveAt(ev); }
});
canvas.addEventListener('pointermove', ev => {
  if (!V.e) return;
  if (ptrs.has(ev.pointerId)) ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]);
  if (!drag) { if (V.tool === 'loupe' && ev.pointerType === 'mouse') { V.lens = { x: ev.clientX, y: ev.clientY }; invalidate(true); } return; }
  if (drag.kind === 'pinch' && ptrs.size === 2) { const a = [...ptrs.values()], d = Math.hypot(a[0][0] - a[1][0], a[0][1] - a[1][1]), x = (a[0][0] + a[1][0]) / 2, y = (a[0][1] + a[1][1]) / 2; cam.dist = Math.min(1500, Math.max(40, cam.dist * drag.d / Math.max(1, d))); cam.yaw -= (x - drag.x) * 0.008; cam.pitch = Math.max(-1.5, Math.min(1.5, cam.pitch + (y - drag.y) * 0.008)); drag.d = d; drag.x = x; drag.y = y; invalidate(true); }
  else if (drag.kind === 'orbit') { cam.yaw -= (ev.clientX - drag.x) * 0.008; cam.pitch = Math.max(-1.5, Math.min(1.5, cam.pitch + (ev.clientY - drag.y) * 0.008)); drag.x = ev.clientX; drag.y = ev.clientY; invalidate(true); }
  else if (drag.kind === 'torch') { torchAt(ev); invalidate(true); }
  else if (drag.kind === 'loupe') { V.lens = { x: ev.clientX, y: ev.clientY }; invalidate(true); }
  else if (drag.kind === 'grind') carveAt(ev);
});
function endPtr(ev) {
  ptrs.delete(ev.pointerId); if (!drag) return;
  if (drag.kind === 'grind') { const s = V.rec, p = V.piece; refreshQuote(s, p, true); V.note = `本次打磨花费 ${Math.max(1, Math.round(strokeCost))} 元。`; save(); renderAll(); }
  if (drag.kind === 'loupe' && ev.pointerType !== 'mouse') { V.lens = null; invalidate(false); }
  if (drag.kind === 'pinch' && ptrs.size) return;
  drag = null;
}
canvas.addEventListener('pointerup', endPtr); canvas.addEventListener('pointercancel', endPtr);
canvas.addEventListener('pointerleave', () => { if (V.lens && !drag) { V.lens = null; invalidate(false); } });
canvas.addEventListener('wheel', ev => { if (!V.e) return; ev.preventDefault(); cam.dist = Math.min(1500, Math.max(40, cam.dist * Math.exp(ev.deltaY * 0.0012))); invalidate(true); }, { passive: false });
new ResizeObserver(() => invalidate(false)).observe(canvas);

/* ---------- 启动 ---------- */
W = load() || C.newWorld((Date.now() ^ 0x5f3759df) >>> 0);
window.JadeDebug = { V, cam, Q, render, invalidate, view, world: () => W, setWorld: w => { W = w; } };
if (!W.market.length) C.genMarket(W);
view('market', W.market.find(L => !L.sold) || null, null);
})();
