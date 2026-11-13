/* 翡翠博弈 · 界面与三维工作台 */
(function () {
'use strict';
const C = window.Core, $ = s => document.querySelector(s), fmt = C.fmt;
const SAVE_KEY = 'jade-bargain-web-v4';
const canvas = $('#gl'), gl = canvas.getContext('webgl2', { antialias: false, preserveDrawingBuffer: true });
if (!gl) { $('#hint').textContent = '这台设备的浏览器不支持 WebGL2，无法显示三维原石。'; return; }

/* ---------- GL ---------- */
function sh(type, src) { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; }
const prog = gl.createProgram(); gl.attachShader(prog, sh(gl.VERTEX_SHADER, window.JADE_VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, window.JADE_FS)); gl.linkProgram(prog);
if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
const progT = gl.createProgram(); gl.attachShader(progT, sh(gl.VERTEX_SHADER, window.JADE_VS)); gl.attachShader(progT, sh(gl.FRAGMENT_SHADER, window.JADE_TRAY_FS)); gl.bindAttribLocation(progT, 0, 'aPos'); gl.linkProgram(progT);
if (!gl.getProgramParameter(progT, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(progT));
const UT = {}; const ut = n => UT[n] || (UT[n] = gl.getUniformLocation(progT, n));
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

/* ---------- 音效（合成，无素材） ---------- */
const Snd = (() => { let ac = null, on = true; const ctx = () => { if (!ac) try { ac = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { } return ac; };
  function noise(d, f, q, g) { const a = ctx(); if (!a || !on) return; const n = Math.floor(a.sampleRate * d), b = a.createBuffer(1, n, a.sampleRate), ch = b.getChannelData(0); for (let i = 0; i < n; i++) ch[i] = Math.random() * 2 - 1; const s = a.createBufferSource(); s.buffer = b; const bp = a.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = f; bp.Q.value = q; const gn = a.createGain(); gn.gain.setValueAtTime(0, a.currentTime); gn.gain.linearRampToValueAtTime(g, a.currentTime + 0.04); gn.gain.linearRampToValueAtTime(0, a.currentTime + d); s.connect(bp); bp.connect(gn); gn.connect(a.destination); s.start(); }
  function tone(f, d, g, type, delay) { const a = ctx(); if (!a || !on) return; const o = a.createOscillator(), gn = a.createGain(), t = a.currentTime + (delay || 0); o.type = type || 'sine'; o.frequency.value = f; gn.gain.setValueAtTime(0, t); gn.gain.linearRampToValueAtTime(g, t + 0.01); gn.gain.exponentialRampToValueAtTime(0.0001, t + d); o.connect(gn); gn.connect(a.destination); o.start(t); o.stop(t + d + 0.05); }
  return { saw() { noise(1.15, 2600, 3, 0.22); tone(170, 1.15, 0.04, 'sawtooth'); }, grind() { noise(0.12, 4300, 2, 0.06); }, coin() { tone(1320, 0.12, 0.10); tone(1760, 0.3, 0.08, 'sine', 0.08); }, win() { [523, 659, 784, 1047].forEach((f, i) => tone(f, 0.35, 0.09, 'triangle', i * 0.09)); }, lose() { tone(196, 0.5, 0.10); tone(147, 0.8, 0.10, 'sine', 0.2); }, tap() { tone(700, 0.05, 0.04); }, toggle() { on = !on; return on; } }; })();

/* ---------- 状态 ---------- */
let W = null;
const V = { mode: null, rec: null, piece: null, e: null, tool: 'rotate', burr: '中磨头', torch: { on: false, p: null, n: null, rake: false }, room: true, lens: null, cut: null, cutT: 12, section: 0, msg: '', note: '', wk: { route: 'bracelet', master: '平洲镯师', theme: '师傅定' }, ref: false, sel: null, cab: false };
const cam = { yaw: 0.6, pitch: 0.35, dist: 300, t: [0, 0, 0] };
const Q = { scale: 1, fast: 0.45, K: 16, tuned: false };
let tab = 'market', thumbs = new Map(), qcache = new Map();

function save() { try { localStorage.setItem(SAVE_KEY, C.serialize(W)); } catch (e) { /* 存不了也能继续玩 */ } }
function load() { try { const s = localStorage.getItem(SAVE_KEY); if (s) { const w = JSON.parse(s); if (w && w.v === 4) { w.market = w.markets[w.scene] || []; return w; } } } catch (e) { } return null; }

/* ---------- 相机与渲染 ---------- */
function camBasis() {
  const cp = Math.cos(cam.pitch), o = [cam.dist * cp * Math.sin(cam.yaw), cam.dist * Math.sin(cam.pitch), cam.dist * cp * Math.cos(cam.yaw)];
  const pos = [cam.t[0] + o[0], cam.t[1] + o[1], cam.t[2] + o[2]], f = [-o[0] / cam.dist, -o[1] / cam.dist, -o[2] / cam.dist];
  let r = [-f[2], 0, f[0]]; const rl = Math.hypot(r[0], r[2]) || 1; r[0] /= rl; r[2] /= rl;
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
function curPiece() { return V.mode === 'review' ? { planes: [[0, 1, 0, V.section]] } : (V.piece || C.WHOLE); }
let pending = false, pendingFast = false, fullTimer = 0;
function invalidate(fast) { clearTimeout(fullTimer); if (fast) fullTimer = setTimeout(() => invalidate(false), 170); if (pending) { pendingFast = pendingFast && fast; return; } pending = true; pendingFast = !!fast; requestAnimationFrame(() => { pending = false; render(pendingFast ? Q.fast : 1); }); }
function render(scale, forceSize) {
  if (V.mode === 'tray') return renderTray(scale);
  gl.useProgram(prog);
  if (!V.e) { gl.viewport(0, 0, canvas.width, canvas.height); gl.clearColor(0.03, 0.027, 0.024, 1); gl.clear(gl.COLOR_BUFFER_BIT); return; }
  const rect = canvas.getBoundingClientRect(), pr = Math.min(window.devicePixelRatio || 1, 2) * Q.scale * scale;
  const w = forceSize || Math.max(2, Math.round(rect.width * pr)), h = forceSize || Math.max(2, Math.round(rect.height * pr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  const t0 = performance.now();
  gl.viewport(0, 0, w, h);
  const { st, vol } = V.e, b = camBasis(), pc = curPiece();
  upload(vol);
  gl.uniform2f(u('uRes'), w, h); gl.uniform3fv(u('uCamPos'), b.pos);
  gl.uniformMatrix3fv(u('uCamRot'), false, [b.r[0], b.r[1], b.r[2], b.up[0], b.up[1], b.up[2], -b.f[0], -b.f[1], -b.f[2]]);
  gl.uniform1f(u('uTan'), TANF); gl.uniform3f(u('uBox'), vol.hx, vol.hy, vol.hz);
  const PL = new Float32Array(64); pc.planes.slice(0, 16).forEach((p, i) => PL.set(p, i * 4));
  gl.uniform1i(u('uNPl'), Math.min(16, pc.planes.length)); gl.uniform4fv(u('uPl'), PL); gl.uniform1f(u('uPristine'), V.mode === 'review' ? 1 : 0);
  const sk = st.skin, H = C.HUES[st.hue];
  gl.uniform3fv(u('uSkinCol'), sk.col); gl.uniform1f(u('uSkinSig'), sk.sig); gl.uniform1f(u('uSkinGrain'), sk.grain); gl.uniform1f(u('uSkinRel'), C.ORIGINS[st.origin].rel); gl.uniform1f(u('uWeather'), sk.weather); gl.uniform1f(u('uPhase'), sk.phase);
  gl.uniform3fv(u('uBodyCol'), C.BODIES[st.body]); gl.uniform3fv(u('uBandCol'), H.band); gl.uniform3fv(u('uHueAbs'), H.abs); gl.uniform3fv(u('uFogCol'), st.fog.col); gl.uniform1f(u('uFogT'), st.fog.t);
  const A = new Float32Array(24), B = new Float32Array(24), Cc = new Float32Array(24), Tt = new Float32Array(18);
  st.cracks.forEach((c, i) => { A.set([c.c[0], c.c[1], c.c[2], c.R], i * 4); B.set([c.n[0], c.n[1], c.n[2], c.open], i * 4); Cc.set([c.warp, c.freq, c.phase, c.skinVis], i * 4); Tt.set(c.t1, i * 3); });
  gl.uniform1i(u('uNCr'), st.cracks.length); gl.uniform4fv(u('uCrA'), A); gl.uniform4fv(u('uCrB'), B); gl.uniform4fv(u('uCrC'), Cc); gl.uniform3fv(u('uCrT'), Tt);
  const T = V.torch;
  if (T.on && T.p) {
    const p = T.p, n = T.n, skinT = C.sampleG(vol, 2, p[0], p[1], p[2]), depth0 = -C.sampleG(vol, 0, p[0], p[1], p[2]);
    const onFlesh = depth0 > skinT - 0.2, left = Math.max(0, skinT - Math.max(0, depth0)), inset = onFlesh ? 0.6 : left + 0.6, entry = onFlesh ? 1 : Math.max(0.02, Math.exp(-sk.sig * left));
    const dn = b.r[0] * n[0] + b.r[1] * n[1] + b.r[2] * n[2]; let tan = [b.r[0] - n[0] * dn, b.r[1] - n[1] * dn, b.r[2] - n[2] * dn];
    const tl = Math.hypot(tan[0], tan[1], tan[2]) || 1; tan = tan.map(v => v / tl);
    const dir = T.rake ? [-n[0] * 0.35 + tan[0] * 0.94, -n[1] * 0.35 + tan[1] * 0.94, -n[2] * 0.35 + tan[2] * 0.94] : [-n[0], -n[1], -n[2]];
    gl.uniform4f(u('uTorch'), p[0] - n[0] * inset, p[1] - n[1] * inset, p[2] - n[2] * inset, 28 * entry * (T.rake ? 0.45 : 1));
    gl.uniform3fv(u('uTorchDir'), dir); gl.uniform3fv(u('uTorchSurf'), p);
    if (T.rake) { gl.uniform3f(u('uRakePos'), p[0] + n[0] * 9 - tan[0] * 22, p[1] + n[1] * 9 - tan[1] * 22, p[2] + n[2] * 9 - tan[2] * 22); gl.uniform1f(u('uRakeFall'), 1600); gl.uniform1f(u('uRakeI'), 3.2); }
    else { gl.uniform3f(u('uRakePos'), p[0] + n[0] * 3, p[1] + n[1] * 3, p[2] + n[2] * 3); gl.uniform1f(u('uRakeFall'), 40); gl.uniform1f(u('uRakeI'), 0.6); }
    const v = [p[0] - b.pos[0], p[1] - b.pos[1], p[2] - b.pos[2]], z = v[0] * b.f[0] + v[1] * b.f[1] + v[2] * b.f[2];
    const vis = Math.max(0, -(n[0] * b.f[0] + n[1] * b.f[1] + n[2] * b.f[2]));
    gl.uniform3f(u('uGlare'), w / 2 + (v[0] * b.r[0] + v[1] * b.r[1] + v[2] * b.r[2]) / z / TANF * h / 2, h / 2 + (v[0] * b.up[0] + v[1] * b.up[1] + v[2] * b.up[2]) / z / TANF * h / 2, forceSize ? 0 : vis * (T.rake ? 0.03 : 0.06) * Math.sqrt(entry));
  } else { gl.uniform4f(u('uTorch'), 0, 0, 0, 0); gl.uniform3f(u('uGlare'), 0, 0, 0); }
  gl.uniform1f(u('uSpread'), 260); gl.uniform1f(u('uAmbient'), V.room ? 1 : 0.06);
  if (V.lens && !forceSize) { const R = Math.min(w, h) * 0.2; gl.uniform4f(u('uLens'), (V.lens.x - rect.left) / rect.width * w, (1 - (V.lens.y - rect.top) / rect.height) * h, R, 3.2); } else gl.uniform4f(u('uLens'), 0, 0, 0, 1);
  const cutOn = V.cut && V.tool === 'cut' && V.mode === 'own' && !forceSize;
  gl.uniform1f(u('uCutOn'), cutOn ? 1 : 0); if (cutOn) gl.uniform4f(u('uCut'), V.cut.n[0], V.cut.n[1], V.cut.n[2], V.cut.d);
  const SC = { '夜市地摊': [0, [0.075, 0.05, 0.03], [0.014, 0.010, 0.009], [1.0, 0.82, 0.56]], '玉石集散地': [1, [0.125, 0.115, 0.10], [0.022, 0.02, 0.018], [1.0, 0.97, 0.92]], '翡翠公盘': [2, [0.05, 0.06, 0.08], [0.008, 0.01, 0.014], [0.92, 0.97, 1.0]], '场口直采': [3, [0.3, 0.25, 0.18], [0.12, 0.10, 0.08], [1.0, 0.94, 0.84]] }[(V.rec && V.rec.scene) || W.scene] || [1, [0.115, 0.1, 0.085], [0.02, 0.018, 0.016], [1, 0.96, 0.9]];
  gl.uniform1i(u('uScene'), V.mode === 'market' ? SC[0] : 1); gl.uniform3fv(u('uBgA'), V.mode === 'market' ? SC[1] : [0.115, 0.1, 0.085]); gl.uniform3fv(u('uBgB'), V.mode === 'market' ? SC[2] : [0.02, 0.018, 0.016]); gl.uniform3fv(u('uKeyCol'), V.mode === 'market' ? SC[3] : [1, 0.96, 0.9]);
  gl.uniform1i(u('uK'), scale < 1 ? 8 : Q.K); gl.uniform1f(u('uHi'), scale < 1 ? 0 : 1);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  if (scale === 1 && !forceSize && !Q.tuned) { const px = new Uint8Array(4); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); const ms = performance.now() - t0; if (ms > 350 && Q.scale > 0.45) { Q.scale *= 0.7; invalidate(false); } else Q.tuned = true; }
}
/* ---------- 成品托盘 ---------- */
const TYPE_ID = { bracelet: 0, pendant: 1, cab: 2, bead: 3, carve: 4 };
const REF = (() => { const B = C.BODIES['白底'], H = C.HUES, it = (type, name, w, lv, hue, note) => ({ id: name, type, name, w, lv, body: B, band: H[hue].band, cot: 0.05, seed: 7, theme: '素面无事牌', note }); return [
  it('pendant', '豆种', 0.10, 0, '阳绿', '发白发闷，像瓷，看得见颗粒，几乎不反光'), it('pendant', '糯种', 0.25, 0, '阳绿', '像糯米汤，浑而细，光只进表层'), it('pendant', '糯冰种', 0.45, 0, '阳绿', '半透，边缘开始透光，有点起光'),
  it('pendant', '冰种', 0.65, 0, '阳绿', '像冰块，能看进去，反光清晰'), it('pendant', '高冰种', 0.82, 0, '阳绿', '通透，内部干净，高光锐利'), it('pendant', '玻璃种', 0.95, 0, '阳绿', '像玻璃，一眼看穿，表面起荧光'),
  it('cab', '淡绿', 0.65, 1, '淡绿', '色淡，只比无色贵一点'), it('cab', '阳绿', 0.65, 1, '阳绿', '鲜亮带黄味，贵十几倍'), it('cab', '正绿', 0.65, 1, '正绿', '浓而正，贵几十倍'), it('cab', '帝王绿', 0.65, 1, '帝王绿', '浓艳深沉，最贵'),
  it('cab', '紫罗兰', 0.65, 1, '紫罗兰', '春色，贵一两倍'), it('bracelet', '冰种飘花手镯', 0.65, 0.3, '阳绿', '色只占一段：种定底价，色定倍数'),
  Object.assign(it('pendant', '佛公牌', 0.5, 0.35, '阳绿', '浮雕题材：常年好卖，不挑料'), { theme: '观音佛公' }), Object.assign(it('pendant', '山水牌', 0.4, 0.2, '淡绿', '棉可以做成雪和云'), { theme: '山水', cot: 0.5 }), Object.assign(it('pendant', '平安扣', 0.82, 0.15, '阳绿', '交给师傅定：圆润的扣子最显水头'), { theme: '师傅定' }), Object.assign(it('carve', '佛公摆件', 0.3, 0.4, '正绿', '整块随形雕，裂和脏藏进题材里'), { theme: '观音佛公' }),
]; })();
function trayItems() { return V.ref ? REF : W.items.filter(i => i.state === (V.cab ? 'kept' : 'ready')).slice(0, 16); }
function trayLayout(items) { const n = items.length, cols = Math.max(1, Math.ceil(Math.sqrt(n * 1.5))), rows = Math.ceil(n / cols), sp = 84; return { cols, rows, sp, pos: items.map((_, i) => [((i % cols) - (cols - 1) / 2) * sp, (Math.floor(i / cols) - (rows - 1) / 2) * sp]), half: [cols * sp / 2 + 14, rows * sp / 2 + 14] }; }
function renderTray(scale) {
  gl.useProgram(progT);
  const rect = canvas.getBoundingClientRect(), pr = Math.min(window.devicePixelRatio || 1, 2) * Q.scale * scale, w = Math.max(2, Math.round(rect.width * pr)), h = Math.max(2, Math.round(rect.height * pr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  gl.viewport(0, 0, w, h);
  const items = trayItems(), lay = trayLayout(items), b = camBasis();
  gl.uniform2f(ut('uRes'), w, h); gl.uniform3fv(ut('uCamPos'), b.pos); gl.uniformMatrix3fv(ut('uCamRot'), false, [b.r[0], b.r[1], b.r[2], b.up[0], b.up[1], b.up[2], -b.f[0], -b.f[1], -b.f[2]]); gl.uniform1f(ut('uTan'), TANF); gl.uniform2f(ut('uTray'), Math.max(60, lay.half[0]), Math.max(60, lay.half[1]));
  const It = new Float32Array(64), Ic = new Float32Array(64), Ib = new Float32Array(64), Ix = new Float32Array(64);
  items.forEach((it, i) => { It.set([lay.pos[i][0], lay.pos[i][1], TYPE_ID[it.type], it.seed % 97], i * 4); Ic.set([it.band[0], it.band[1], it.band[2], it.w], i * 4); Ib.set([it.body[0], it.body[1], it.body[2], it.lv], i * 4); Ix.set([V.sel === it.id ? 1 : 0, it.cot, ({ '素面无事牌': 0, '观音佛公': 1, '山水': 2, '花鸟龙凤': 3 })[it.theme] != null ? ({ '素面无事牌': 0, '观音佛公': 1, '山水': 2, '花鸟龙凤': 3 })[it.theme] : 4, 0], i * 4); });
  gl.uniform1i(ut('uN'), items.length); gl.uniform4fv(ut('uIt'), It); gl.uniform4fv(ut('uIc'), Ic); gl.uniform4fv(ut('uIb'), Ib); gl.uniform4fv(ut('uIx'), Ix);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
}
function openTray(ref, cab) { V.mode = 'tray'; V.ref = !!ref; V.cab = !!cab; V.rec = null; V.piece = null; V.e = null; V.sel = null; V.tool = 'rotate'; const lay = trayLayout(trayItems()); cam.t = [0, 6, 0]; cam.yaw = 0.35; cam.pitch = 0.85; cam.dist = Math.max(200, Math.max(lay.half[0], lay.half[1]) * 2.5); V.note = ''; tab = 'tray'; renderAll(); }
function focusItem() { const items = trayItems(), i = items.findIndex(x => x.id === V.sel); if (i < 0) return; const lay = trayLayout(items); cam.t = [lay.pos[i][0], items[i].type === 'carve' ? 16 : 5, lay.pos[i][1]]; cam.dist = items[i].type === 'cab' ? 80 : 170; cam.pitch = Math.min(cam.pitch, 0.62); }
function pickTray(cx, cy) { const r = rayAt(cx, cy); if (r.rd[1] >= 0) return null; const t = (5 - r.ro[1]) / r.rd[1], x = r.ro[0] + r.rd[0] * t, z = r.ro[2] + r.rd[2] * t, items = trayItems(), lay = trayLayout(items); let best = null, bd = 44; items.forEach((it, i) => { const d = Math.hypot(x - lay.pos[i][0], z - lay.pos[i][1]); if (d < bd) { bd = d; best = it; } }); return best; }
function lookAlong(n) { cam.pitch = Math.max(-1.55, Math.min(1.55, Math.asin(Math.max(-1, Math.min(1, n[1]))))); cam.yaw = Math.atan2(n[0], n[2]); }
function thumb(s, piece) {
  const e = C.volCache.get(s.seed); if (!e) return '';
  const key = s.id + ':' + piece.id + ':' + e.vol.ver + ':' + piece.planes.length;
  if (thumbs.has(key)) return thumbs.get(key);
  if (!V.e || V.e.vol !== e.vol) return '';
  const keep = { cam: { yaw: cam.yaw, pitch: cam.pitch, dist: cam.dist, t: cam.t }, piece: V.piece, torch: V.torch.on, room: V.room, lens: V.lens, mode: V.mode };
  const inf = C.pieceInfo(e.vol, piece), slab = C.slabOf(piece);
  V.piece = piece; V.mode = 'own'; V.torch.on = false; V.room = true; V.lens = null; cam.t = inf.center; cam.dist = inf.radius * 3.9;
  if (slab) lookAlong(slab.n); else if (piece.planes.length) lookAlong(piece.planes[piece.planes.length - 1]); else { cam.yaw = 0.6; cam.pitch = 0.35; }
  render(1, 128); const url = canvas.toDataURL('image/jpeg', 0.8);
  Object.assign(cam, keep.cam); V.piece = keep.piece; V.torch.on = keep.torch; V.room = keep.room; V.lens = keep.lens; V.mode = keep.mode;
  thumbs.set(key, url); return url;
}

/* ---------- 选择 ---------- */
function frame() { const inf = C.pieceInfo(V.e.vol, V.mode === 'review' ? C.WHOLE : curPiece()); cam.t = inf.center; cam.dist = Math.max(60, inf.radius * 4.3); V.info = inf; }
function view(mode, rec, piece) {
  V.ref = false; if (tab === 'tray') tab = 'mine';
  V.mode = mode; V.rec = rec; V.piece = piece; V.e = rec ? C.getVol(rec) : null; V.torch.p = null; V.torch.on = false; V.lens = null; V.cut = null; V.msg = ''; V.note = '';
  if (V.e) { if (mode === 'review') V.section = V.e.vol.hy; frame(); }
  if (mode !== 'own' && (V.tool === 'grind' || V.tool === 'cut' || V.tool === 'peel')) V.tool = 'rotate';
  renderAll();
}
function getQuotes(s, p) { const e = C.getVol(s), key = s.id + ':' + p.id + ':' + e.vol.ver + ':' + W.day + ':' + p.planes.length; let q = qcache.get(key); if (!q) { q = C.quotes(W, s, p); qcache.set(key, q); } return q; }
function bookOf(s) { let v = s.proceeds, all = true; for (const p of s.pieces) if (!p.sold) { if (!C.volCache.get(s.seed)) { all = false; continue; } v += getQuotes(s, p).best; } if (W.works.some(k => k.stone === s.id)) all = false; for (const it of W.items) if (it.stone === s.id) { if (it.state === 'sold') continue; v += it.value * 0.6; } return { v, all }; }

/* ---------- 面板 ---------- */
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
function pct(a, b) { const r = (a / b - 1) * 100; return `<span class="${r >= 0 ? 'up' : 'down'}">${r >= 0 ? '+' : ''}${r.toFixed(0)}%</span>`; }
function renderTop() {
  const recv = W.recv.reduce((a, r) => a + r.amt, 0);
  let inv = 0; for (const s of W.stones) if (!s.closed) for (const p of s.pieces) if (!p.sold) inv += (s.last[p.id] || {}).best || 0;
  $('#stats').innerHTML = `<div><span>第</span><b>${W.day}</b><span>天</span></div><div><span>现金</span><b>${fmt(W.cash)}</b></div><div><span>应收</span><b>${fmt(recv)}</b></div><div><span>存货报价</span><b>${fmt(inv)}</b></div><div><span>${C.rankOf(W)} · 眼力</span><b>${W.eye}</b></div>`;
}
function betHtml(bet, full) { return `<span class="tag b">${bet.main}</span>${bet.tags.map(t => `<span class="tag">${t}</span>`).join('')}${full ? `<p class="why">${esc(bet.why)}</p>` : ''}`; }
function renderSide() {
  document.querySelectorAll('#tabs button').forEach(b => b.setAttribute('aria-selected', b.dataset.tab === tab));
  const el = $('#panel'); let h = '';
  if (tab === 'market') {
    h += `<div class="scenes">${Object.keys(C.SCENES).map(k => { const S = C.SCENES[k], ok = C.sceneOpen(W, k); return `<button data-act="scene" data-k="${k}" aria-pressed="${W.scene === k}" ${ok ? '' : 'disabled'}>${k}${ok ? '' : `<small>眼力 ${S.eye}</small>`}</button>`; }).join('')}</div><p class="note">${C.SCENES[W.scene].tip}</p>`;
    W.market.forEach((L, i) => {
      const sel = V.mode === 'market' && V.rec === L;
      h += `<article class="card ${sel ? 'sel' : ''} ${L.sold ? 'gone' : ''}" data-act="listing" data-i="${i}"><div class="row"><b>${L.origin} · ${L.info.skin}</b><span class="price">${L.sold ? '已买' : L.auction ? '底价 ' + fmt(L.floor) : fmt(L.ask)}</span></div>
      <div class="row dim"><span>${(L.info.weight / 1000).toFixed(2)} kg · ${L.info.dims.join('×')} mm</span><span>${L.channel}</span></div>
      <div class="tags"><span class="tag ${L.info.window ? 'w' : ''}">${L.info.window ? '卖家已开窗' : '全蒙头'}</span>${betHtml(L.info.bet, sel)}</div>`;
      if (L.auction && L.bid && !L.sold) h += `<div class="row"><span class="say">已投标 ${fmt(L.bid)}，收工后开标</span></div>`;
      if (sel && !L.sold && L.auction) h += `<div class="bargain"><label for="offer">暗标出价（元）。别人出多少你看不到，出高了白花钱，出低了拿不到。</label><div class="row"><input id="offer" type="number" inputmode="numeric" min="0" step="100" value="${L.bid || V.offer || L.floor}"><button data-act="bid" class="pri">${L.bid ? '改标' : '投标'}</button></div>${V.msg ? `<p class="say">${esc(V.msg)}</p>` : ''}</div>`;
      else if (sel && !L.sold) h += `<div class="bargain"><label for="offer">出价（元）</label><div class="row"><input id="offer" type="number" inputmode="numeric" min="0" step="100" value="${V.offer || Math.round(L.ask * 0.7 / 100) * 100}"><button data-act="offer">还价</button><button data-act="take" class="pri">照价买 ${fmt(L.ask)}</button></div>${V.msg ? `<p class="say">${esc(V.msg)}</p>` : ''}</div>`;
      h += `</article>`;
    });
  } else if (tab === 'mine') {
    const open = W.stones.filter(s => !s.closed), ready = W.items.filter(i => i.state === 'ready').length;
    if (!open.length && !W.works.length) h += `<p class="note">还没有存货。到「货源」里挑一块买下，就能在这里开窗、下刀、询价或送去做件。</p>`;
    for (const k of W.works) h += `<article class="card"><div class="row"><b>加工中 · ${esc(k.from)}</b><span class="dim">第 ${k.ready} 天取货</span></div><div class="row dim"><span>${esc(k.what)}，按看得见的料预计 ${k.expected} 件。开出来才知道。</span></div></article>`;
    if (ready) h += `<article class="card" data-act="tray"><div class="row"><b>成品托盘里有 ${ready} 件待售</b><span class="price">去看看</span></div></article>`;
    for (const s of open) {
      const act = V.mode === 'own' && V.rec === s, bk = bookOf(s);
      h += `<article class="card ${act ? 'sel' : ''}"><div class="row"><b>#${s.id} ${s.origin} · ${s.info.skin}</b><span class="dim">第 ${s.buyDay} 天买入</span></div>
      <div class="row dim"><span>买入 ${fmt(s.buyPrice)} · 加工 ${fmt(s.costs)} · 已回款 ${fmt(s.proceeds)}</span></div>
      ${bk.all ? `<div class="row"><span>账面（回款＋当前最高报价）${fmt(bk.v)}</span><span>${pct(bk.v, s.buyPrice)}</span></div>` : ''}<div class="pieces">`;
      if (act) { const fresh = s.pieces.length === 1 && !s.pieces[0].planes.length && !s.pieces[0].sold, g = s.guess || {}, o = (arr, cur) => arr.map(x => `<option value="${x[0]}" ${String(cur) === String(x[0]) ? 'selected' : ''}>${x[1]}</option>`).join('');
        if (fresh) h += `<div class="work"><b>判断本</b><p class="note">下刀前写下你的判断。这块料全部出手后对答案，判断得准涨眼力，眼力能进更好的场子。</p>
          <div class="row"><label for="gW">种水</label><select id="gW">${o([['', '还没想好'], [0, '豆种'], [1, '糯种'], [2, '糯冰种'], [3, '冰种'], [4, '高冰种'], [5, '玻璃种']], g.water == null ? '' : g.water)}</select></div>
          <div class="row"><label for="gC">色</label><select id="gC">${o([['none', '基本无色'], ['skin', '只有贴皮一层'], ['deep', '有色吃进去'], ['full', '满色']], g.color || 'none')}</select></div>
          <div class="row"><label for="gK">裂</label><select id="gK">${o([['few', '裂少（至多一条）'], ['many', '裂多（两条以上）']], g.crack || 'few')}</select></div></div>`;
        else if (s.guess) h += `<p class="note">判断本已封存：${C.waterName(C.GRADES[s.guess.water])}，${{ none: '基本无色', skin: '贴皮色', deep: '色吃进去', full: '满色' }[s.guess.color]}，${s.guess.crack === 'few' ? '裂少' : '裂多'}。出完货对答案。</p>`; }
      for (const p of s.pieces) { if (p.sold) continue; const t = thumb(s, p); h += `<button class="pc ${act && V.piece === p ? 'on' : ''}" data-act="piece" data-s="${s.id}" data-p="${p.id}">${t ? `<img src="${t}" alt="">` : '<i></i>'}<span>${p.name}</span></button>`; }
      h += `</div>`;
      if (act && V.piece && !V.piece.sold) {
        const q = getQuotes(s, V.piece), last = s.last[V.piece.id], stt = q.stats;
        h += `<div class="quotes"><div class="row dim"><span>${V.piece.name} · ${Math.round(stt.weight)} g${stt.isSlab ? ` · 片厚 ${stt.thickness.toFixed(0)} mm` : ''}${stt.bracelets ? ` · 可见手镯位 ${stt.bracelets}` : ''} · 看清程度 ${Math.round(stt.kAvg * 100)}%</span></div>`;
        if (last && last.prev != null && last.prev !== q.best) h += `<p class="delta">较上次报价 ${pct(q.best, Math.max(1, last.prev))}${last.why && last.why.length ? '：' + esc(last.why.join('；')) : ''}</p>`;
        for (const o of q.list) h += `<div class="row q"><span><b>${o.buyer}</b> <i>${esc(o.note)}</i></span>${o.price ? `<button data-act="sell" data-b="${o.buyer}">${fmt(o.price)} 卖</button>` : '<span class="dim">不收</span>'}</div>`;
        const K = V.wk, plan = C.workPlan(W, s, V.piece, K.route, K.master, K.theme), themed = K.route === 'pendant' || K.route === 'carve';
        const opt = (o, cur, f) => Object.keys(o).map(k => `<option value="${k}" ${k === cur ? 'selected' : ''}>${f(k)}</option>`).join('');
        h += `<div class="work"><b>送去做件</b>
          <div class="row"><label for="wkRoute">做什么</label><select id="wkRoute">${opt(C.ROUTES, K.route, k => C.ROUTES[k].name)}</select></div><p class="note">${C.ROUTES[K.route].tip}</p>
          <div class="row"><label for="wkMaster">找谁做</label><select id="wkMaster">${opt(C.MASTERS, K.master, k => k)}</select></div><p class="note">${C.MASTERS[K.master].tip}</p>
          ${themed ? `<div class="row"><label for="wkTheme">题材</label><select id="wkTheme">${opt(C.THEMES, K.theme, k => k === '师傅定' ? k : `${k}（行情${C.demandWord(C.themeDemand(W, k))}）`)}</select></div><p class="note">${C.THEMES[K.theme].tip}</p>` : ''}
          ${plan.warn.map(x => `<p class="say">${esc(x)}</p>`).join('')}
          <div class="row"><span class="dim">预计 ${plan.n} ${C.ROUTES[K.route].unit} · 工费 ${fmt(plan.fee)} · ${plan.days} 天</span><button data-act="work" class="pri" ${plan.ok ? '' : 'disabled'}>送去</button></div></div>`;
        h += `<p class="note">报价只在今天有效。账面开涨不是现金到账。</p></div>`;
      }
      h += `</article>`;
    }
  } else if (tab === 'tray') {
    const items = trayItems();
    if (V.ref) { h += `<p class="note">对照盘：上面六块素面牌从豆种到玻璃种，下面是同为冰种、不同颜色的蛋面。转动托盘，对着光看它们的差别。</p>`; for (const it of items) h += `<article class="card ${V.sel === it.id ? 'sel' : ''}" data-act="isel" data-i="${it.id}"><div class="row"><b>${it.name}</b></div><div class="row dim"><span>${it.note}</span></div></article>`; h += `<button data-act="trayback" class="pri">回到我的托盘</button>`; }
    else {
      h += `<div class="scenes"><button data-act="cab0" aria-pressed="${!V.cab}">待售托盘</button><button data-act="cab1" aria-pressed="${V.cab}">藏品柜（${W.items.filter(i => i.state === 'kept').length}）</button></div>`;
      if (!V.cab) { h += `<article class="card"><b>客户订单</b>${W.orders.map(o => `<div class="row dim"><span>${esc(C.orderText(o))}</span><span>加价 ${Math.round((o.bonus - 1) * 100)}% · 第 ${o.due} 天前</span></div>`).join('') || '<div class="row dim"><span>暂时没有订单</span></div>'}</article>`;
      for (const k of W.works) h += `<article class="card"><div class="row"><b>加工中 · ${esc(k.from)}</b><span class="dim">第 ${k.ready} 天取货</span></div><div class="row dim"><span>${esc(k.what)}</span></div></article>`; }
      if (V.cab) { if (!items.length) h += `<p class="note">藏品柜是空的。舍不得卖的成品可以收进来，随时拿出来看。</p>`; for (const it of items) h += `<article class="card ${V.sel === it.id ? 'sel' : ''}" data-act="isel" data-i="${it.id}"><div class="row"><b>${esc(it.name)}</b><span class="price">${fmt(it.value)}</span></div><div class="row dim"><span>${C.waterName(it.w)} · ${it.master} · 出自 #${it.stone}</span></div><div class="row"><button data-act="unkeep" data-i="${it.id}">拿回托盘出售</button></div></article>`; }
      else if (!items.length) h += `<p class="note">托盘是空的。把料送去做件，做好后成品会摆在这里，可以转着看，一件件卖或整盘卖。</p>`;
      else if (!V.cab) { const tot = items.reduce((a, i) => a + i.value, 0); h += `<article class="card"><div class="row"><b>整盘 ${items.length} 件</b><span>零售估值 ${fmt(tot)}</span></div><div class="row"><button data-act="iall" data-how="whole">整盘批发现结 ${fmt(tot * 0.6)}</button><button data-act="iall" data-how="retail" class="pri">整盘寄卖 ${fmt(tot * 0.95)}</button></div></article>`; }
      if (!V.cab) for (const it of items) h += `<article class="card ${V.sel === it.id ? 'sel' : ''}" data-act="isel" data-i="${it.id}"><div class="row"><b>${esc(it.name)}</b><span class="price">${fmt(it.value)}</span></div><div class="row dim"><span>${C.waterName(it.w)} · ${it.lv > 0.6 ? '色满' : it.lv > 0.25 ? '带色' : it.lv > 0.08 ? '飘色' : '无色'}${it.theme && it.theme !== '师傅定' ? ' · ' + it.theme : ''} · ${it.master} · 出自 #${it.stone}</span></div>
        <div class="row"><button data-act="isell" data-i="${it.id}" data-how="whole">批发 ${fmt(it.value * 0.6)}</button><button data-act="isell" data-i="${it.id}" data-how="retail">寄卖 ${fmt(it.value * 0.95)}（6–14 天）</button>${W.orders.filter(o => C.orderMatch(o, it)).slice(0, 1).map(o => `<button data-act="iorder" data-i="${it.id}" data-o="${o.id}" class="pri">交给${o.who} ${fmt(it.value * o.bonus)}</button>`).join('')}<button data-act="keep" data-i="${it.id}">收藏</button></div></article>`;
      h += `<button data-act="trayref">看种水与颜色对照盘</button>`;
    }
  } else {
    const recv = W.recv.map(r => `<div class="row dim"><span>${r.from}</span><span>第 ${r.day} 天到账 ${fmt(r.amt)}</span></div>`).join('');
    h += `<article class="card"><div class="row"><b>资金</b><span>现金 ${fmt(W.cash)}</span></div>${recv || '<div class="row dim"><span>没有在途货款</span></div>'}<div class="row dim"><span>每天铺面与生活开销 ${C.ECON.daily}</span></div></article>`;
    for (const s of W.stones.filter(s => s.closed).reverse()) {
      const r = s.review, net = s.proceeds - s.buyPrice - s.costs;
      h += `<article class="card ${V.mode === 'review' && V.rec === s ? 'sel' : ''}"><div class="row"><b>复盘 #${s.id} ${s.origin} · ${s.info.skin}</b><span class="${net >= 0 ? 'up' : 'down'}">${net >= 0 ? '+' : ''}${fmt(net)}</span></div>
      <div class="row dim"><span>买入 ${fmt(s.buyPrice)} · 加工 ${fmt(s.costs)} · 回款 ${fmt(s.proceeds)} · 持有 ${s.closeDay - s.buyDay} 天</span></div>
      <div class="row dim"><span>买入当天原样转手最高 ${fmt(s.flip)}；途中账面最高 ${fmt(s.best)}</span></div>
      <div class="row dim"><span>真相：${r.water}，${r.feats.length ? r.hue + '（' + r.feats.join('、') + '）' : '基本无色'}，${r.cracks} 条裂${r.shift ? '，' + r.shift : ''}；全部做成件的零售价值约 ${fmt(r.truth)}</span></div>
      ${s.guessResult ? `<div class="row"><span class="say">判断本：你写的是 ${C.waterName(C.GRADES[s.guess.water])}／${{ none: '无色', skin: '贴皮色', deep: '色吃进去', full: '满色' }[s.guess.color]}／${s.guess.crack === 'few' ? '裂少' : '裂多'}，实际 ${C.waterName(C.GRADES[s.guessResult.water])}／${{ none: '无色', skin: '贴皮色', deep: '色吃进去', full: '满色' }[s.guessResult.color]}／${s.guessResult.crack === 'few' ? '裂少' : '裂多'}。眼力 +${s.guessResult.pts}</span></div>` : ''}
      <div class="row"><span class="dim">一次赚钱不等于判断正确，亏了也不一定是决策错。</span><button data-act="review" data-s="${s.id}">看剖面</button></div></article>`;
    }
    const ach = Object.values(W.ach); h += `<article class="card"><div class="row"><b>${C.rankOf(W)}</b><span>眼力 ${W.eye}</span></div><div class="row dim"><span>${C.RANKS.map(r => `${r[1]} ${r[0]}`).join(' → ')}</span></div>${ach.length ? ach.map(a => `<div class="row"><span class="say">★ ${esc(a.name)}</span><span class="dim">第 ${a.day} 天</span></div>`).join('') : '<div class="row dim"><span>还没有成就</span></div>'}</article>`;
    h += `<article class="card"><b>流水</b>${W.log.slice(-40).reverse().map(l => `<div class="row dim"><span>第 ${l.day} 天 ${esc(l.t)}</span><span>${l.amt ? (l.amt > 0 ? '+' : '') + fmt(l.amt) : ''}</span></div>`).join('')}</article>`;
  }
  el.innerHTML = h;
}
const HINTS = {
  rotate: '拖动转石头，滚轮或双指缩放。右键拖动在任何工具下都能转。',
  torch: '点或拖到石头上压灯，灯会留在原处；转到别的角度看光从哪里透出来。',
  loupe: '移动放大镜看皮壳颗粒、松花、细裂和玉肉晶粒。可以和手电一起用。',
  grind: '在石头上拖动磨皮开窗。同一处来回磨会越磨越深，磨掉的料回不来。',
  peel: '在石头上画一个圈，圈里的皮会被整片切掉，只剥到刚露肉，不伤里面的料。圈越大切工越贵，想象空间也越少。',
  cut: '在石头上拖一条线，就是锯片走的位置；或者把想切的面转到正对自己，按厚度切一片。橙线是下刀处。',
};
function cutFromView() {
  const b = camBasis(), n = [-b.f[0], -b.f[1], -b.f[2]], inf = C.pieceInfo(V.e.vol, V.piece, n);
  V.cut = { n, d: inf.hi - V.cutT, base: inf.hi }; V.cut.pv = C.cutPreview(V.rec, V.piece, V.cut.n, V.cut.d);
}
function renderTools() {
  const own = V.mode === 'own' && V.piece && !V.piece.sold, tray = V.mode === 'tray';
  document.querySelectorAll('#tools button[data-tool]').forEach(b => { b.setAttribute('aria-pressed', b.dataset.tool === V.tool); b.disabled = ((b.dataset.tool === 'grind' || b.dataset.tool === 'cut' || b.dataset.tool === 'peel') && !own) || (tray && b.dataset.tool !== 'rotate'); });
  let o = '';
  if (V.mode === 'review') o += `<label for="sec">剖面高度</label><input id="sec" type="range" min="${(-V.e.vol.hy).toFixed(0)}" max="${V.e.vol.hy.toFixed(0)}" step="0.5" value="${V.section}"><span class="dim">复盘：这是石头原本的内部</span>`;
  else if (V.tool === 'torch') o += `<button data-act="rake" aria-pressed="${V.torch.rake}">斜照</button><button data-act="toff" ${V.torch.on ? '' : 'disabled'}>关灯</button>`;
  else if (V.tool === 'grind') o += Object.keys(C.TOOLS).map(k => `<button data-act="burr" data-k="${k}" aria-pressed="${V.burr === k}">${k}</button>`).join('');
  else if (V.tool === 'cut' && own) {
    o += `<label for="cutT">片厚 <b id="cutV">${V.cutT}</b> mm</label><input id="cutT" type="range" min="3" max="60" step="1" value="${V.cutT}"><button data-act="cview">从正对我的面切这么厚</button>`;
    if (V.cut) o += `<button data-act="cut" class="pri">下刀（切工 ${fmt(V.cut.pv.cost)}）</button><button data-act="ccancel">取消</button><span class="dim">两侧约 ${Math.round(V.cut.pv.a)} g / ${Math.round(V.cut.pv.b)} g</span>`;
  }
  o += `<button data-act="room" aria-pressed="${V.room}">室内灯</button>`;
  $('#opts').innerHTML = o;
  let t = V.e ? HINTS[V.tool] : '从右侧「货源」里点一块石头开始看料。';
  if (tray) t = V.ref ? '对照盘：拖动转托盘，点一件看说明。' : '成品托盘：拖动转着看，点一件选中，在右侧一件件卖或整盘卖。';
  if (V.mode === 'review') t = '复盘剖面：拖动滑块看这块石头原本的内部结构。';
  $('#hint').textContent = V.note || t;
  $('#title').textContent = tray ? (V.ref ? '种水与颜色对照盘' : '成品托盘') : V.rec ? (V.mode === 'market' ? `${V.rec.origin} · ${V.rec.info.skin}` : `#${V.rec.id} ${V.rec.origin} · ${V.rec.info.skin}${V.mode === 'own' && V.piece ? ' · ' + V.piece.name : ''}${V.mode === 'review' ? ' · 复盘' : ''}`) : '';
}
function renderAll() { renderTop(); renderSide(); renderTools(); invalidate(false); $('#over').hidden = !W.over; }
function refreshQuote(s, p, record) {
  const prev = s.last[p.id]; qcache.clear();
  const q = getQuotes(s, p); s.last[p.id] = { best: q.best, stats: q.stats, prev: prev ? prev.best : null, why: prev ? C.explain(prev.stats, q.stats) : [] };
  if (record) { const bk = bookOf(s); if (bk.all && bk.v > s.best) s.best = bk.v; }
}
function afterStoneChange(s) { if (s.closed) { tab = 'ledger'; view('review', s, null); } else { const next = s.pieces.find(x => !x.sold); if (next) { view('own', s, next); if (!s.last[next.id]) refreshQuote(s, next); renderAll(); } else { tab = 'mine'; view(null, null, null); } } }

/* ---------- 教程里的对照图：用游戏自己的渲染器现场拍 ---------- */
const SKIN_NOTES = { '黄砂皮': '最常见。砂粒均匀、翻砂有力的多半种老。', '白砂皮': '皮薄砂细，常出高种无色料。', '乌砂皮': '黑灰色，皮厚挡光；色料多，裂也多。', '红褐皮': '铁质重，皮下常有红雾。', '灰绿薄皮': '皮最薄，灯下最好看，里面什么样基本藏不住。', '黑乌砂': '最黑最厚，灯几乎打不进，赌性最大。', '黄红雾': '皮下有一层黄或红的雾，雾厚吃料，雾下的种通常不差。', '灰白盐砂': '砂粒像盐，手感扎，种老水好，色少。', '铁锈皮': '锈色斑驳，皮厚，底子容易偏灰。', '青灰皮': '细腻偏青，水头不错，容易带蓝灰底。', '黑蜡皮': '表面像打了蜡，光滑少砂，皮紧，裂多。', '褐黄砂': '黄砂的深色款，砂粗，种嫩的多。' };
let atlasDone = false;
function buildAtlas() {
  if (atlasDone) return; atlasDone = true;
  const keep = { mode: V.mode, rec: V.rec, piece: V.piece, e: V.e, torch: V.torch, room: V.room, lens: V.lens, cam: { yaw: cam.yaw, pitch: cam.pitch, dist: cam.dist, t: cam.t } };
  const mk = () => { const st = C.genStone(424242, '木那', '二级供应商'); st.feats = []; st.cracks = []; st.dirt = []; st.shift = null; st.wVar = 0; st.cot = 0.08; st.planes = []; st.fog = { t: 0, col: [1, 1, 1] }; st.body = '白底'; return st; };
  const shot = (st, vol, torch) => { V.mode = 'own'; V.rec = null; V.piece = C.WHOLE; V.e = { st, vol }; V.lens = null; V.room = !torch; cam.yaw = 0.5; cam.pitch = 0.3; cam.t = [0, 0, 0]; cam.dist = Math.max(vol.hx, vol.hy, vol.hz) * 3.9; V.torch = { on: false, p: null, n: null, rake: false };
    if (torch) { const b = camBasis(), h = C.pick(vol, C.WHOLE, b.pos, b.f); if (h) V.torch = { on: true, p: h.p, n: h.n, rake: false }; }
    render(1, 168); return canvas.toDataURL('image/jpeg', 0.85); };
  try {
    const st = mk(); st.w0 = 0.4; st.skin = Object.assign({}, st.skin, { t: 2 }); const vol = C.bake(st, 44); let h = '';
    for (const name in C.SKINS) { const S = C.SKINS[name]; st.skin = { name, col: S.col, grain: S.grain, sig: S.sig, weather: S.weather, t: 2, phase: 3 }; const tr = S.sig * (S.t[0] + S.t[1]) / 2;
      h += `<figure><img src="${shot(st, vol, false)}" alt="${name}"><figcaption><b>${name}</b><span>皮厚 ${S.t[0]}–${S.t[1]} mm · 透光${tr < 1.2 ? '好' : tr < 2.6 ? '一般' : '差'}</span><span>${SKIN_NOTES[name]}</span></figcaption></figure>`; }
    $('#skinAtlas').innerHTML = h; h = '';
    const notes = ['光只在灯头一小团，发白', '光晕稍大，浑而柔', '光晕明显变大，边缘柔和', '透出一大片，颜色干净', '几乎整块亮起来', '通体透亮，像灯泡'];
    C.GRADES.forEach((g, i) => { const s2 = mk(); s2.w0 = g; s2.skin = { name: '灰绿薄皮', col: C.SKINS['灰绿薄皮'].col, grain: 0.22, sig: 0.45, weather: 0.3, t: 0.7, phase: 3 }; const v2 = C.bake(s2, 40);
      h += `<figure><img src="${shot(s2, v2, true)}" alt="${C.waterName(g)}"><figcaption><b>${C.waterName(g)}</b><span>${notes[i]}</span></figcaption></figure>`; });
    $('#waterAtlas').innerHTML = h;
  } catch (e) { $('#skinAtlas').textContent = '对照图生成失败：' + e.message; }
  V.mode = keep.mode; V.rec = keep.rec; V.piece = keep.piece; V.e = keep.e; V.torch = keep.torch; V.room = keep.room; V.lens = keep.lens; Object.assign(cam, keep.cam); loaded = null; invalidate(false);
  const word = (v, a, b) => v >= b ? '高' : v >= a ? '中' : '低';
  $('#originTable').innerHTML = '<table><thead><tr><th>场口</th><th>种水</th><th>出色</th><th>裂</th><th>皮壳表现可信度</th><th>常见皮</th></tr></thead><tbody>' + Object.keys(C.ORIGINS).map(k => { const O = C.ORIGINS[k]; return `<tr><th>${k}</th><td>${word(O.w, 35, 42)}</td><td>${word(O.c, 48, 54)}</td><td>${word(O.crack, 38, 48)}</td><td>${word(O.rel * 100, 50, 65)}</td><td style="text-align:left;white-space:normal">${O.skins.slice(0, 3).join('、')}</td></tr>`; }).join('') + '</tbody></table>';
}
function showPane(k) { document.querySelectorAll('#help [data-pane]').forEach(x => x.hidden = x.dataset.pane !== k); document.querySelectorAll('#help [data-act=pane]').forEach(x => x.setAttribute('aria-pressed', x.dataset.k === k)); if (k === 'skin' || k === 'water') buildAtlas(); }

/* ---------- 说明书里的价值表：直接用内核公式算，保证和游戏一致 ---------- */
function fillManual() {
  const seeds = [['豆种', 0.10], ['糯种', 0.25], ['糯冰种', 0.45], ['冰种', 0.65], ['高冰种', 0.82], ['玻璃种', 0.95]];
  const cols = [['无色', 0, '阳绿'], ['淡绿／晴水', 0.6, '淡绿'], ['紫罗兰', 0.6, '紫罗兰'], ['阳绿一段', 0.17, '阳绿'], ['阳绿半圈', 0.6, '阳绿'], ['正绿满色', 1, '正绿'], ['帝王绿满色', 1, '帝王绿']];
  const ring = Math.PI * (36 * 36 - 28 * 28) * 9 / 1000 * C.ECON.braceletBonus * 1.1;
  let h = '<table><thead><tr><th>手镯成品</th>' + cols.map(c => `<th>${c[0]}</th>`).join('') + '</tr></thead><tbody>';
  for (const s of seeds) h += `<tr><th>${s[0]}</th>` + cols.map(c => `<td>${fmt(C.vd(s[1], c[1], 0, 0, C.HUES[c[2]].grade) * ring)}</td>`).join('') + '</tr>';
  h += '</tbody></table>';
  $('#vtable').innerHTML = h;
}

/* ---------- 交互 ---------- */
document.addEventListener('click', ev => {
  const b = ev.target.closest('[data-act],[data-tab],[data-tool]'); if (!b) return;
  if (b.dataset.tab) { if (b.dataset.tab === 'tray') { openTray(false); return; } if (V.mode === 'tray') { tab = b.dataset.tab; view(null, null, null); return; } tab = b.dataset.tab; renderSide(); return; }
  if (b.dataset.tool) { V.tool = b.dataset.tool; V.lens = null; V.cut = null; V.note = ''; renderTools(); invalidate(false); return; }
  const a = b.dataset.act;
  if (a === 'listing') { if (ev.target.closest('.bargain')) return; const L = W.market[+b.dataset.i]; V.offer = 0; if (V.rec !== L) view('market', L, null); }
  else if (a === 'offer' || a === 'take') {
    const L = V.rec, offer = a === 'take' ? L.ask : +($('#offer').value || 0); V.offer = offer;
    const r = C.negotiate(W, L, offer); V.msg = r.msg;
    if (r.res === 'deal') { Snd.coin(); const s = C.buy(W, L, r.price); tab = 'mine'; view('own', s, s.pieces[0]); refreshQuote(s, s.pieces[0], true); save(); V.note = `成交 ${fmt(r.price)}。可以直接询价转手，也可以开窗、下刀或送加工。`; renderAll(); return; }
    save(); renderSide();
  }
  else if (a === 'piece') { const s = W.stones.find(x => x.id === +b.dataset.s), p = s.pieces.find(x => x.id === +b.dataset.p); view('own', s, p); if (!s.last[p.id]) refreshQuote(s, p); renderAll(); }
  else if (a === 'sell') { const s = V.rec, p = V.piece, q = getQuotes(s, p).list.find(o => o.buyer === b.dataset.b); C.sell(W, s, p, q); Snd.coin(); qcache.clear(); save(); afterStoneChange(s); }
  else if (a === 'work') { const s = V.rec, K = V.wk, r = C.sendWork(W, s, V.piece, K.route, K.master, K.theme); if (!r.ok) { V.note = r.msg; renderTools(); return; } qcache.clear(); save(); afterStoneChange(s); V.note = `已送去，工费 ${fmt(r.fee)}，${r.days} 天后到托盘取成品。`; renderTools(); }
  else if (a === 'scene') { C.enterScene(W, b.dataset.k); save(); Snd.tap(); view('market', W.market.find(L => !L.sold) || null, null); }
  else if (a === 'bid') { const L = V.rec, r = C.placeBid(W, L, +($('#offer').value || 0)); V.msg = r.msg; if (r.ok) Snd.coin(); save(); renderTop(); renderSide(); }
  else if (a === 'cab0') openTray(false, false);
  else if (a === 'cab1') openTray(false, true);
  else if (a === 'keep') { C.keepItem(W, W.items.find(x => x.id === +b.dataset.i)); save(); openTray(false, false); }
  else if (a === 'unkeep') { W.items.find(x => x.id === +b.dataset.i).state = 'ready'; save(); openTray(false, true); }
  else if (a === 'iorder') { const it = W.items.find(x => x.id === +b.dataset.i), o = W.orders.find(x => x.id === +b.dataset.o); C.sellToOrder(W, it, o); Snd.win(); save(); openTray(false, false); }
  else if (a === 'mute') { b.textContent = Snd.toggle() ? '声音 开' : '声音 关'; }
  else if (a === 'tray') openTray(false);
  else if (a === 'trayref') openTray(true);
  else if (a === 'trayback') openTray(false);
  else if (a === 'isel') { if (ev.target.closest('button')) return; V.sel = V.ref ? b.dataset.i : +b.dataset.i; focusItem(); renderSide(); invalidate(false); }
  else if (a === 'isell') { const it = W.items.find(x => x.id === +b.dataset.i); C.sellItem(W, it, b.dataset.how); Snd.coin(); save(); const s = W.stones.find(x => x.id === it.stone); if (s && s.closed && !trayItems().length) { tab = 'ledger'; view('review', s, null); } else openTray(false); }
  else if (a === 'iall') { for (const it of trayItems()) C.sellItem(W, it, b.dataset.how); save(); tab = 'ledger'; view(null, null, null); }
  else if (a === 'review') { view('review', W.stones.find(x => x.id === +b.dataset.s), null); }
  else if (a === 'rake') { V.torch.rake = !V.torch.rake; renderTools(); invalidate(false); }
  else if (a === 'toff') { V.torch.on = false; renderTools(); invalidate(false); }
  else if (a === 'room') { V.room = !V.room; renderTools(); invalidate(false); }
  else if (a === 'burr') { V.burr = b.dataset.k; renderTools(); }
  else if (a === 'cview') { cutFromView(); V.cut.fromView = true; renderTools(); invalidate(false); }
  else if (a === 'ccancel') { V.cut = null; renderTools(); invalidate(false); }
  else if (a === 'cut') {
    const s = V.rec, p = V.piece, before = bookOf(s).v, rv = $('#reveal'), cutSpec = V.cut;
    rv.className = 'sawing'; rv.innerHTML = '<div class="blade"></div><p>下刀中…</p>'; rv.hidden = false; Snd.saw();
    setTimeout(() => {
      const r = C.cut(W, s, p, cutSpec.n, cutSpec.d);
      if (!r.ok) { rv.hidden = true; V.note = r.msg; renderTools(); return; }
      V.cut = null; refreshQuote(s, p, false); refreshQuote(s, r.piece, true); tab = 'mine'; save(); frame(); renderAll();
      const after = bookOf(s).v, d = (after / Math.max(1, before) - 1) * 100, why = (s.last[p.id].why || []).concat(s.last[r.piece.id].why || []).filter(x => !x.startsWith('重量')).slice(0, 3);
      const up = d >= 3, down = d <= -3; if (up) { Snd.win(); C.achieve(W, 'cutup', '第一刀切涨'); } else if (down) Snd.lose(); else Snd.tap();
      rv.className = up ? 'up' : down ? 'down' : 'flat';
      rv.innerHTML = `<h2>${up ? '切涨了' : down ? '切垮了' : '平开'}</h2><p class="big">${d >= 0 ? '+' : ''}${d.toFixed(0)}%</p><p>账面 ${fmt(before)} → ${fmt(after)}</p>${why.map(x => `<p class="why2">${esc(x)}</p>`).join('')}<button data-act="rvok" class="pri">继续</button>`;
      V.note = `切工 ${fmt(r.cost)}。分出的 ${r.piece.name} 在右侧，可单独查看、再切、出售或送去做件。`; renderTools();
    }, 1150);
  }
  else if (a === 'rvok') { $('#reveal').hidden = true; }
  else if (a === 'next') { const n = C.nextDay(W); qcache.clear(); for (const s of W.stones) if (!s.closed) for (const p of s.pieces) if (!p.sold && C.volCache.get(s.seed)) refreshQuote(s, p, true); save(); const fresh = W.items.some(i => i.state === 'ready'); tab = 'market'; view(null, null, null); V.note = `第 ${W.day} 天。${n.join('，')}。货源已更新，昨天的报价作废。`; renderTools(); if (fresh && n.some(x => x.includes('做好了'))) { openTray(false); V.note = n.filter(x => x.includes('做好了')).join('；'); renderTools(); } }
  else if (a === 'restart') { $('#confirm').hidden = false; }
  else if (a === 'no') { $('#confirm').hidden = true; }
  else if (a === 'yes') { $('#confirm').hidden = true; C.volCache.clear(); thumbs.clear(); qcache.clear(); loaded = null; W = C.newWorld((Date.now() ^ (Math.random() * 1e9)) >>> 0); save(); tab = 'market'; view(null, null, null); }
  else if (a === 'help') { $('#help').hidden = !$('#help').hidden; if (!$('#help').hidden) showPane('play'); }
  else if (a === 'pane') showPane(b.dataset.k);
  else if (a === 'gotoref') { $('#help').hidden = true; openTray(true); }
});
document.addEventListener('input', ev => {
  if (ev.target.id === 'cutT') { V.cutT = +ev.target.value; $('#cutV').textContent = V.cutT; if (V.cut && V.cut.fromView) { V.cut.d = V.cut.base - V.cutT; V.cut.pv = C.cutPreview(V.rec, V.piece, V.cut.n, V.cut.d); renderTools(); } invalidate(true); }
  if (ev.target.id === 'gW' || ev.target.id === 'gC' || ev.target.id === 'gK') { const s = V.rec, w = $('#gW').value; s.guess = w === '' ? null : { water: +w, color: $('#gC').value, crack: $('#gK').value }; save(); }
  if (ev.target.id === 'wkRoute' || ev.target.id === 'wkMaster' || ev.target.id === 'wkTheme') { V.wk[{ wkRoute: 'route', wkMaster: 'master', wkTheme: 'theme' }[ev.target.id]] = ev.target.value; renderSide(); }
  if (ev.target.id === 'sec') { V.section = +ev.target.value; invalidate(true); }
});
const ptrs = new Map(); let drag = null, lastCarve = null, strokeCost = 0; const lineEl = $('#cutline');
function torchAt(ev) { const r = rayAt(ev.clientX, ev.clientY), h = C.pick(V.e.vol, curPiece(), r.ro, r.rd, V.mode === 'review'); if (h) { V.torch.on = true; V.torch.p = h.p; V.torch.n = h.n; } return h; }
function carveAt(ev) {
  const r = rayAt(ev.clientX, ev.clientY), h = C.pick(V.e.vol, V.piece, r.ro, r.rd); if (!h) return;
  if (lastCarve && Math.hypot(h.p[0] - lastCarve[0], h.p[1] - lastCarve[1], h.p[2] - lastCarve[2]) < 1.2) return;
  lastCarve = h.p; Snd.grind(); const res = C.grind(W, V.rec, V.piece, h.p, h.n, V.burr); strokeCost += res.removed * C.ECON.grind;
  uploadBox(V.e.vol, res.box); invalidate(true);
}
function showLine(d) { const r = canvas.getBoundingClientRect(); lineEl.hidden = !d; if (d) { lineEl.setAttribute('x1', d.x0 - r.left); lineEl.setAttribute('y1', d.y0 - r.top); lineEl.setAttribute('x2', d.x - r.left); lineEl.setAttribute('y2', d.y - r.top); } }
function showLasso(pts) { const el = $('#lasso'), r = canvas.getBoundingClientRect(); el.hidden = !pts; if (pts) el.setAttribute('points', pts.map(p => (p[0] - r.left) + ',' + (p[1] - r.top)).join(' ')); }
function doPeel(pts) {
  if (pts.length < 6) return;
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9; for (const p of pts) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); }
  if (x1 - x0 < 12 || y1 - y0 < 12) return;
  const inside = (x, y) => { let c = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const a = pts[i], b = pts[j]; if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) c = !c; } return c; };
  const step = Math.max(5, Math.sqrt((x1 - x0) * (y1 - y0) / 900)), hits = [];
  for (let y = y0; y <= y1; y += step) for (let x = x0; x <= x1; x += step) if (inside(x, y)) { const r = rayAt(x, y), h = C.pick(V.e.vol, V.piece, r.ro, r.rd); if (h && !h.flat) hits.push(h); }
  let cost = 0, n = 0; for (const h of hits) { const res = C.peelAt(W, V.rec, V.piece, h.p, h.n); if (res) { cost += res.cost; n++; } }
  if (!n) { V.note = '圈里没有可切的皮。'; renderTools(); return; }
  loaded = null; Snd.saw(); refreshQuote(V.rec, V.piece, true); save(); V.note = `切皮完成，花费 ${Math.max(1, Math.round(cost))} 元。`; renderAll();
}
canvas.addEventListener('contextmenu', e => e.preventDefault());
canvas.addEventListener('pointerdown', ev => {
  if (V.mode === 'tray') { canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]); drag = { kind: 'orbit', x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY, tray: true }; return; }
  if (!V.e) return; canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]);
  if (ptrs.size === 2) { showLine(null); const a = [...ptrs.values()]; drag = { kind: 'pinch', d: Math.hypot(a[0][0] - a[1][0], a[0][1] - a[1][1]), x: (a[0][0] + a[1][0]) / 2, y: (a[0][1] + a[1][1]) / 2 }; return; }
  const own = V.mode === 'own' && V.piece && !V.piece.sold;
  const orbit = ev.button === 2 || V.tool === 'rotate' || ev.shiftKey || ((V.tool === 'grind' || V.tool === 'cut' || V.tool === 'peel') && !own);
  if (orbit) drag = { kind: 'orbit', x: ev.clientX, y: ev.clientY };
  else if (V.tool === 'torch') { drag = { kind: 'torch' }; torchAt(ev); renderTools(); invalidate(true); }
  else if (V.tool === 'loupe') { drag = { kind: 'loupe' }; V.lens = { x: ev.clientX, y: ev.clientY }; invalidate(true); }
  else if (V.tool === 'grind') { drag = { kind: 'grind' }; lastCarve = null; strokeCost = 0; carveAt(ev); }
  else if (V.tool === 'peel') { drag = { kind: 'lasso', pts: [[ev.clientX, ev.clientY]] }; }
  else if (V.tool === 'cut') { drag = { kind: 'line', x0: ev.clientX, y0: ev.clientY, x: ev.clientX, y: ev.clientY }; }
});
canvas.addEventListener('pointermove', ev => {
  if (!V.e && V.mode !== 'tray') return;
  if (ptrs.has(ev.pointerId)) ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]);
  if (!drag) { if (V.tool === 'loupe' && ev.pointerType === 'mouse') { V.lens = { x: ev.clientX, y: ev.clientY }; invalidate(true); } return; }
  if (drag.kind === 'pinch' && ptrs.size === 2) { const a = [...ptrs.values()], d = Math.hypot(a[0][0] - a[1][0], a[0][1] - a[1][1]), x = (a[0][0] + a[1][0]) / 2, y = (a[0][1] + a[1][1]) / 2; cam.dist = Math.min(1500, Math.max(40, cam.dist * drag.d / Math.max(1, d))); cam.yaw -= (x - drag.x) * 0.008; cam.pitch = Math.max(-1.5, Math.min(1.5, cam.pitch + (y - drag.y) * 0.008)); drag.d = d; drag.x = x; drag.y = y; invalidate(true); }
  else if (drag.kind === 'orbit') { cam.yaw -= (ev.clientX - drag.x) * 0.008; cam.pitch = Math.max(V.mode === 'tray' ? 0.12 : -1.5, Math.min(1.5, cam.pitch + (ev.clientY - drag.y) * 0.008)); drag.x = ev.clientX; drag.y = ev.clientY; if (V.cut && V.cut.fromView) { V.cut = null; renderTools(); } invalidate(true); }
  else if (drag.kind === 'torch') { torchAt(ev); invalidate(true); }
  else if (drag.kind === 'loupe') { V.lens = { x: ev.clientX, y: ev.clientY }; invalidate(true); }
  else if (drag.kind === 'grind') carveAt(ev);
  else if (drag.kind === 'line') { drag.x = ev.clientX; drag.y = ev.clientY; showLine(drag); }
  else if (drag.kind === 'lasso') { const l = drag.pts[drag.pts.length - 1]; if (Math.hypot(ev.clientX - l[0], ev.clientY - l[1]) > 4) { drag.pts.push([ev.clientX, ev.clientY]); showLasso(drag.pts); } }
});
function endPtr(ev) {
  ptrs.delete(ev.pointerId); if (!drag) return;
  if (drag.tray && Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < 6) { const it = pickTray(ev.clientX, ev.clientY); V.sel = it ? it.id : null; if (it) focusItem(); else { const lay = trayLayout(trayItems()); cam.t = [0, 6, 0]; cam.dist = Math.max(200, Math.max(lay.half[0], lay.half[1]) * 2.5); } renderSide(); invalidate(false); }
  if (drag.kind === 'grind') { const s = V.rec, p = V.piece; refreshQuote(s, p, true); V.note = `本次打磨花费 ${Math.max(1, Math.round(strokeCost))} 元。`; save(); renderAll(); }
  if (drag.kind === 'loupe' && ev.pointerType !== 'mouse') { V.lens = null; invalidate(false); }
  if (drag.kind === 'lasso') { showLasso(null); doPeel(drag.pts); }
  if (drag.kind === 'line') {
    showLine(null);
    if (Math.hypot(drag.x - drag.x0, drag.y - drag.y0) > 24) {
      const r1 = rayAt(drag.x0, drag.y0), r2 = rayAt(drag.x, drag.y);
      let n = [r1.rd[1] * r2.rd[2] - r1.rd[2] * r2.rd[1], r1.rd[2] * r2.rd[0] - r1.rd[0] * r2.rd[2], r1.rd[0] * r2.rd[1] - r1.rd[1] * r2.rd[0]]; const l = Math.hypot(n[0], n[1], n[2]); n = n.map(v => v / l);
      V.cut = { n, d: n[0] * r1.ro[0] + n[1] * r1.ro[1] + n[2] * r1.ro[2] }; V.cut.pv = C.cutPreview(V.rec, V.piece, V.cut.n, V.cut.d); V.note = '';
      renderTools(); invalidate(false);
    }
  }
  if (drag.kind === 'pinch' && ptrs.size) return;
  drag = null;
}
canvas.addEventListener('pointerup', endPtr); canvas.addEventListener('pointercancel', endPtr);
canvas.addEventListener('pointerleave', () => { if (V.lens && !drag) { V.lens = null; invalidate(false); } });
canvas.addEventListener('wheel', ev => { if (!V.e && V.mode !== 'tray') return; ev.preventDefault(); cam.dist = Math.min(1500, Math.max(40, cam.dist * Math.exp(ev.deltaY * 0.0012))); invalidate(true); }, { passive: false });
new ResizeObserver(() => invalidate(false)).observe(canvas);

/* ---------- 启动 ---------- */
const hadSave = !!load();
W = load() || C.newWorld((Date.now() ^ 0x5f3759df) >>> 0);
window.JadeDebug = { V, cam, Q, render, invalidate, view, world: () => W, setWorld: w => { W = w; } };
if (!W.market || !W.market.length) C.enterScene(W, W.scene || '夜市地摊');
fillManual();
view('market', W.market.find(L => !L.sold) || null, null);
if (!hadSave) { $('#help').hidden = false; showPane('play'); }
})();
