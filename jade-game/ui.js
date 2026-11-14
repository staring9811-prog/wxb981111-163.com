/* 翡翠博弈 · 界面与三维工作台 */
(function () {
'use strict';
const C = window.Core, $ = s => document.querySelector(s), fmt = C.fmt;
const SAVE_KEY = 'jade-bargain-web-v8';
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
const V = { mode: null, rec: null, piece: null, e: null, tool: 'rotate', burr: '中磨头', torch: { on: false, p: null, n: null, rake: false, tilt: 0, az: 0, h: 0 }, lampBody: true, room: true, lens: null, cut: null, cutT: 12, section: 0, msg: '', note: '', wk: { route: 'bracelet', master: '平洲镯师', theme: '师傅定' }, ref: false, sel: null, cab: false };
const cam = { yaw: 0.6, pitch: 0.35, dist: 300, t: [0, 0, 0] };
const Q = { scale: 1, fast: 0.45, K: 16, tuned: false, user: 1 };
let tab = 'market', thumbs = new Map(), qcache = new Map();

function save() { try { localStorage.setItem(SAVE_KEY, C.serialize(W)); } catch (e) { /* 存不了也能继续玩 */ } }
function load() { try { const s = localStorage.getItem(SAVE_KEY); if (s) { const w = JSON.parse(s); if (w && w.v === 8) { w.market = w.markets[w.scene] || []; C.applyTools(w); return w; } } } catch (e) { } return null; }

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
  const dpr0 = window.devicePixelRatio || 1, rect = canvas.getBoundingClientRect(), pr = (dpr0 >= 1.5 ? Math.min(dpr0, 2) : 1.5) * Q.scale * Q.user * scale; // 普通屏幕按 1.5 倍超采样，抗锯齿
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
  gl.uniform1i(u('uNPl'), Math.min(16, pc.planes.length)); gl.uniform4fv(u('uPl'), PL);
  const HO = new Float32Array(128), HN = new Int32Array(4), hs = (pc.holes || []).slice(0, 4); hs.forEach((H, k) => { HN[k] = Math.min(8, H.length); H.slice(0, 8).forEach((P, j) => HO.set(P, (k * 8 + j) * 4)); });
  { const SP = new Float32Array(36), sp = V.sawPlan && V.mode === 'own' && !forceSize ? V.sawPlan.box : []; sp.forEach((P, j) => SP.set(P, j * 4)); gl.uniform1i(u('uSawN'), sp.length); gl.uniform4fv(u('uSaw'), SP); } gl.uniform1i(u('uNHo'), hs.length); gl.uniform4fv(u('uHo'), HO); gl.uniform1iv(u('uHoN'), HN); gl.uniform1f(u('uPristine'), V.mode === 'review' ? 1 : 0);
  const sk = st.skin, H = C.HUES[st.hue];
  gl.uniform3fv(u('uSkinCol'), sk.col); gl.uniform1f(u('uSkinSig'), sk.sig); gl.uniform1f(u('uSkinGrain'), sk.grain); gl.uniform1f(u('uSkinRel'), C.ORIGINS[st.origin].rel); gl.uniform1f(u('uWeather'), sk.weather); gl.uniform1f(u('uPhase'), sk.phase);
  gl.uniform3fv(u('uBodyCol'), C.BODIES[st.body]); gl.uniform3fv(u('uBandCol'), H.band); gl.uniform3fv(u('uHueAbs'), H.abs); gl.uniform3fv(u('uFogCol'), st.fog.col); gl.uniform1f(u('uFogT'), st.fog.t);
  const A = new Float32Array(40), B = new Float32Array(40), Cc = new Float32Array(40), Tt = new Float32Array(30);
  st.cracks.slice(0, 10).forEach((c, i) => { A.set([c.c[0], c.c[1], c.c[2], c.R], i * 4); B.set([c.n[0], c.n[1], c.n[2], c.open], i * 4); Cc.set([c.warp, c.freq, c.phase, c.skinVis], i * 4); Tt.set(c.t1, i * 3); });
  gl.uniform1f(u('uFakeT'), V.rec && V.rec.fake && V.mode !== 'review' ? (V.rec.fake.type === 'paint' ? 1 : 2) : 0);
  gl.uniform1i(u('uNCr'), Math.min(10, st.cracks.length)); gl.uniform4fv(u('uCrA'), A); gl.uniform4fv(u('uCrB'), B); gl.uniform4fv(u('uCrC'), Cc); gl.uniform3fv(u('uCrT'), Tt);
  const T = V.torch;
  if (T.on && T.p) {
    const p = T.p, n = T.n, skinT = C.sampleG(vol, 2, p[0], p[1], p[2]), depth0 = -C.sampleG(vol, 0, p[0], p[1], p[2]);
    const onFlesh = depth0 > skinT - 0.2, left = Math.max(0, skinT - Math.max(0, depth0)), inset = onFlesh ? 0.6 : left + 0.6, entry = onFlesh ? 1 : Math.max(0.02, Math.exp(-sk.sig * left));
    const dn = b.r[0] * n[0] + b.r[1] * n[1] + b.r[2] * n[2]; let tan = [b.r[0] - n[0] * dn, b.r[1] - n[1] * dn, b.r[2] - n[2] * dn];
    const tl = Math.hypot(tan[0], tan[1], tan[2]) || 1; tan = tan.map(v => v / tl);
    const Td = T.dir || n, cT = Math.max(0.08, Td[0] * n[0] + Td[1] * n[1] + Td[2] * n[2]), sT = Math.sqrt(Math.max(0, 1 - cT * cT)), H = T.h || 0;
    const dir = [-Td[0], -Td[1], -Td[2]];   // 光射入的方向
    const lamp = [p[0] - dir[0] * (H + 2.5), p[1] - dir[1] * (H + 2.5), p[2] - dir[2] * (H + 2.5)];  // 灯头位置
    // 贴着压灯光全进去；抬高或放斜，进去的少、洒在表面的多
    gl.uniform4f(u('uTorch'), p[0] - n[0] * inset, p[1] - n[1] * inset, p[2] - n[2] * inset, 28 * (T.dim ? 0.4 : 1) * [1, 1.9, 3.6][W.tools.torch - 1] * Math.max(entry, [0, 0.05, 0.14][W.tools.torch - 1]) * Math.pow(cT, 0.6) / (1 + (H / 9) * (H / 9)));
    gl.uniform3fv(u('uTorchDir'), dir); gl.uniform3fv(u('uTorchSurf'), p); gl.uniform3fv(u('uTorchCol'), T.yellow ? [1.0, 0.80, 0.45] : [1, 1, 1]);
    gl.uniform3fv(u('uRakePos'), lamp); gl.uniform1f(u('uRakeFall'), 30 + H * H * 5 + sT * 1400); gl.uniform1f(u('uRakeI'), 0.5 + 2.0 * sT + Math.min(1.1, H * 0.04));
    T.spread = 260 * (1 + H / 12);
    gl.uniform3fv(u('uLampA'), lamp); gl.uniform3f(u('uLampB'), lamp[0] - dir[0] * 42, lamp[1] - dir[1] * 42, lamp[2] - dir[2] * 42); gl.uniform1f(u('uLampOn'), forceSize || !V.lampBody ? 0 : 1);
    const v = [p[0] - b.pos[0], p[1] - b.pos[1], p[2] - b.pos[2]], z = v[0] * b.f[0] + v[1] * b.f[1] + v[2] * b.f[2];
    const vis = Math.max(0, -(n[0] * b.f[0] + n[1] * b.f[1] + n[2] * b.f[2]));
    gl.uniform3f(u('uGlare'), w / 2 + (v[0] * b.r[0] + v[1] * b.r[1] + v[2] * b.r[2]) / z / TANF * h / 2, h / 2 + (v[0] * b.up[0] + v[1] * b.up[1] + v[2] * b.up[2]) / z / TANF * h / 2, forceSize ? 0 : vis * 0.06 * Math.sqrt(entry) * (0.4 + 0.6 * cT) / (1 + H / 15));
  } else { gl.uniform4f(u('uTorch'), 0, 0, 0, 0); gl.uniform3f(u('uGlare'), 0, 0, 0); gl.uniform1f(u('uLampOn'), 0); }
  gl.uniform1f(u('uSpread'), (T.on && T.spread) || 260); gl.uniform1f(u('uAmbient'), V.room ? 1 : 0.06);
  if (V.lens && !forceSize) { const R = Math.min(w, h) * 0.2; gl.uniform4f(u('uLens'), (V.lens.x - rect.left) / rect.width * w, (1 - (V.lens.y - rect.top) / rect.height) * h, R, [3.2, 5, 8][W.tools.loupe - 1]); } else gl.uniform4f(u('uLens'), 0, 0, 0, 1);
  const cutOn = V.cut && V.tool === 'cut' && V.mode === 'own' && !forceSize;
  gl.uniform1f(u('uCutOn'), cutOn ? 1 : 0); if (cutOn) gl.uniform4f(u('uCut'), V.cut.n[0], V.cut.n[1], V.cut.n[2], V.cut.d);
  const SC = { '夜市地摊': [0, [0.075, 0.05, 0.03], [0.014, 0.010, 0.009], [1.0, 0.82, 0.56]], '玉石集散地': [1, [0.125, 0.115, 0.10], [0.022, 0.02, 0.018], [1.0, 0.97, 0.92]], '翡翠公盘': [2, [0.05, 0.06, 0.08], [0.008, 0.01, 0.014], [0.92, 0.97, 1.0]], '场口直采': [3, [0.3, 0.25, 0.18], [0.12, 0.10, 0.08], [1.0, 0.94, 0.84]] }[(V.rec && V.rec.scene) || W.scene] || [1, [0.115, 0.1, 0.085], [0.02, 0.018, 0.016], [1, 0.96, 0.9]];
  gl.uniform1i(u('uScene'), V.mode === 'market' ? SC[0] : 1); gl.uniform3fv(u('uBgA'), V.mode === 'market' ? SC[1] : [0.115, 0.1, 0.085]); gl.uniform3fv(u('uBgB'), V.mode === 'market' ? SC[2] : [0.02, 0.018, 0.016]); gl.uniform3fv(u('uKeyCol'), V.mode === 'market' ? SC[3] : [1, 0.96, 0.9]);
  { const tab = { '夜市地摊': [0.20, 0.07, 0.05], '玉石集散地': [0.10, 0.16, 0.13], '翡翠公盘': [0.035, 0.04, 0.055], '场口直采': [0.30, 0.23, 0.15] }; const on = !forceSize && V.info && V.mode !== 'review' && V.floor !== false; gl.uniform1f(u('uFloorOn'), on ? 1 : 0); gl.uniform1f(u('uDecor'), on && V.mode === 'market' ? 1 : 0); if (on) { gl.uniform1f(u('uFloorY'), V.info.lo - 0.4); gl.uniform1f(u('uFloorR'), Math.max(120, V.info.radius * 3.2)); gl.uniform3fv(u('uTabCol'), V.mode === 'market' ? (tab[(V.rec && V.rec.scene) || W.scene] || tab['玉石集散地']) : [0.09, 0.14, 0.12]); } }
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
function trayItems() { return V.ref ? REF : W.items.filter(i => i.state === (V.cab === 'shelf' ? 'shelf' : V.cab ? 'kept' : 'ready')).slice(0, 16); }
function trayLayout(items) { const n = items.length, cols = Math.max(1, Math.ceil(Math.sqrt(n * 1.5))), rows = Math.ceil(n / cols), sp = 84; return { cols, rows, sp, pos: items.map((_, i) => [((i % cols) - (cols - 1) / 2) * sp, (Math.floor(i / cols) - (rows - 1) / 2) * sp]), half: [cols * sp / 2 + 14, rows * sp / 2 + 14] }; }
function renderTray(scale) {
  gl.useProgram(progT);
  const rect = canvas.getBoundingClientRect(), pr = Math.min(window.devicePixelRatio || 1, 2) * Q.scale * scale, w = Math.max(2, Math.round(rect.width * pr)), h = Math.max(2, Math.round(rect.height * pr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  gl.viewport(0, 0, w, h);
  const hold = V.hold != null ? (V.ref ? REF : W.items).find(x => x.id === V.hold) : null;
  const items = hold ? [hold] : trayItems(), lay = hold ? { pos: [[0, 0]], half: [60, 60] } : trayLayout(items), b = camBasis();
  gl.uniform1f(ut('uHold'), hold ? 1 : 0); gl.uniform1f(ut('uBack'), hold && V.back ? 3.2 : 1);
  gl.uniform2f(ut('uRes'), w, h); gl.uniform3fv(ut('uCamPos'), b.pos); gl.uniformMatrix3fv(ut('uCamRot'), false, [b.r[0], b.r[1], b.r[2], b.up[0], b.up[1], b.up[2], -b.f[0], -b.f[1], -b.f[2]]); gl.uniform1f(ut('uTan'), TANF); gl.uniform2f(ut('uTray'), Math.max(60, lay.half[0]), Math.max(60, lay.half[1]));
  const It = new Float32Array(64), Ic = new Float32Array(64), Ib = new Float32Array(64), Ix = new Float32Array(64);
  items.forEach((it, i) => { It.set([lay.pos[i][0], lay.pos[i][1], TYPE_ID[it.type], it.seed % 97], i * 4); Ic.set([it.band[0], it.band[1], it.band[2], it.w], i * 4); Ib.set([it.body[0], it.body[1], it.body[2], it.lv], i * 4); Ix.set([V.sel === it.id ? 1 : 0, it.cot, ({ '素面无事牌': 0, '观音佛公': 1, '山水': 2, '花鸟龙凤': 3 })[it.theme] != null ? ({ '素面无事牌': 0, '观音佛公': 1, '山水': 2, '花鸟龙凤': 3 })[it.theme] : 4, 0], i * 4); });
  gl.uniform1i(ut('uN'), items.length); gl.uniform4fv(ut('uIt'), It); gl.uniform4fv(ut('uIc'), Ic); gl.uniform4fv(ut('uIb'), Ib); gl.uniform4fv(ut('uIx'), Ix);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
}
function holdItem(id) { V.hold = id; V.back = false; const it = (V.ref ? REF : W.items).find(x => x.id === id); cam.t = [0, it.type === 'carve' ? 17 : 5, 0]; cam.dist = it.type === 'cab' ? 60 : it.type === 'carve' ? 150 : 135; cam.pitch = 0.45; cam.yaw = 0.5; renderTools(); renderSide(); invalidate(false); }
function openTray(ref, cab) { V.hold = null; V.mode = 'tray'; V.ref = !!ref; V.cab = cab || false; V.rec = null; V.piece = null; V.e = null; V.sel = null; V.tool = 'rotate'; const lay = trayLayout(trayItems()); cam.t = [0, 6, 0]; cam.yaw = 0.35; cam.pitch = 0.85; cam.dist = Math.max(200, Math.max(lay.half[0], lay.half[1]) * 2.5); V.note = ''; tab = 'tray'; renderAll(); }
function focusItem() { const items = trayItems(), i = items.findIndex(x => x.id === V.sel); if (i < 0) return; const lay = trayLayout(items); cam.t = [lay.pos[i][0], items[i].type === 'carve' ? 16 : 5, lay.pos[i][1]]; cam.dist = items[i].type === 'cab' ? 80 : 170; cam.pitch = Math.min(cam.pitch, 0.62); }
function pickTray(cx, cy) { const r = rayAt(cx, cy); if (r.rd[1] >= 0) return null; const t = (5 - r.ro[1]) / r.rd[1], x = r.ro[0] + r.rd[0] * t, z = r.ro[2] + r.rd[2] * t, items = trayItems(), lay = trayLayout(items); let best = null, bd = 44; items.forEach((it, i) => { const d = Math.hypot(x - lay.pos[i][0], z - lay.pos[i][1]); if (d < bd) { bd = d; best = it; } }); return best; }
function lookAlong(n) { cam.pitch = Math.max(-1.55, Math.min(1.55, Math.asin(Math.max(-1, Math.min(1, n[1]))))); cam.yaw = Math.atan2(n[0], n[2]); }
function thumb(s, piece) {
  const e = C.getVol(s);
  const key = s.id + ':' + piece.id + ':' + e.vol.ver + ':' + piece.planes.length + ':' + (piece.holes || []).length;
  if (thumbs.has(key)) return thumbs.get(key);
  const keepE = V.e, keepRec = V.rec; V.e = e; V.rec = s;
  const keep = { cam: { yaw: cam.yaw, pitch: cam.pitch, dist: cam.dist, t: cam.t }, piece: V.piece, torch: V.torch.on, room: V.room, lens: V.lens, mode: V.mode };
  const inf = C.pieceInfo(e.vol, piece), slab = C.slabOf(piece);
  V.piece = piece; V.mode = 'own'; V.torch.on = false; V.room = true; V.lens = null; cam.t = inf.center; cam.dist = inf.radius * 3.9;
  if (slab) lookAlong(slab.n); else if (piece.planes.length) lookAlong(piece.planes[piece.planes.length - 1]); else { cam.yaw = 0.6; cam.pitch = 0.35; }
  render(1, 128); const url = canvas.toDataURL('image/jpeg', 0.8);
  Object.assign(cam, keep.cam); V.piece = keep.piece; V.torch.on = keep.torch; V.room = keep.room; V.lens = keep.lens; V.mode = keep.mode; V.e = keepE; V.rec = keepRec;
  thumbs.set(key, url); return url;
}

/* ---------- 选择 ---------- */
function frame() { const inf = C.pieceInfo(V.e.vol, V.mode === 'review' ? C.WHOLE : curPiece(), [0, 1, 0]); cam.t = inf.center; cam.dist = Math.max(60, inf.radius * 4.3); V.info = inf; }
function view(mode, rec, piece) {
  V.ref = false; if (tab === 'tray') tab = 'mine'; $('#sawbox').hidden = true;
  V.mode = mode; V.rec = rec; V.piece = piece; V.e = rec ? C.getVol(rec) : null; V.torch.p = null; V.torch.on = false; V.lens = null; V.cut = null; V.msg = ''; V.note = '';
  if (V.e) { if (mode === 'review') V.section = V.e.vol.hy; frame(); }
  if (mode !== 'own' && (V.tool === 'grind' || V.tool === 'cut' || V.tool === 'peel' || V.tool === 'saw')) V.tool = 'rotate';
  renderAll();
}
function getQuotes(s, p) { const e = C.getVol(s), key = s.id + ':' + p.id + ':' + e.vol.ver + ':' + W.day + ':' + p.planes.length + ':' + (p.holes || []).length; let q = qcache.get(key); if (!q) { q = C.quotes(W, s, p); qcache.set(key, q); } return q; }
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
  const el = $('#panel'); let h = goalCard();
  if (tab === 'market') {
    h += `<div class="scenes">${Object.keys(C.SCENES).map(k => { const S = C.SCENES[k], ok = C.sceneOpen(W, k); return `<button data-act="scene" data-k="${k}" aria-pressed="${W.scene === k}" ${ok ? '' : 'disabled'}>${k}${ok ? '' : `<small>眼力 ${S.eye}</small>`}</button>`; }).join('')}</div><p class="note">${C.SCENES[W.scene].tip}</p>${W.event ? `<p class="say">今日行情：${esc(W.event.t)}</p>` : ''}`;
    W.market.forEach((L, i) => {
      const sel = V.mode === 'market' && V.rec === L;
      h += `<article class="card ${sel ? 'sel' : ''} ${L.sold ? 'gone' : ''}" data-act="listing" data-i="${i}"><div class="row"><b>${L.origin} · ${L.info.skin}</b><span class="price">${L.sold ? '已买' : L.auction ? '底价 ' + fmt(L.floor) : fmt(L.ask)}</span></div>
      <div class="row dim"><span>${(L.info.weight / 1000).toFixed(2)} kg · ${L.info.dims.join('×')} mm</span><span>${L.channel}</span></div>
      <div class="tags"><span class="tag ${L.info.window ? 'w' : ''}">${L.info.window ? '卖家已开窗' : '全蒙头'}</span>${betHtml(L.info.bet, sel)}</div>`;
      if (sel && !L.sold && !L.called) h += `<div class="row"><span class="dim">觉得皮或窗口做过手脚？说对了老板大降价，说错了他翻脸不卖。</span><button data-act="callout">当面说这是假货</button></div>`;
      if (sel && !L.sold) h += `${(L.patter || []).map(x => `<p class="patter">${esc(x)}</p>`).join('')}${L.opinion ? `<p class="say">${esc(L.opinion)}</p>` : `<div class="row"><span class="dim">拿不准？</span><button data-act="appr">请师傅掌眼（${fmt(C.appraiseFee(L))}）</button></div>`}`;
      if (L.auction && L.bid && !L.sold) h += `<div class="row"><span class="say">已投标 ${fmt(L.bid)}，收工后开标</span></div>`;
      if (sel && !L.sold && L.auction) h += `<div class="bargain"><label for="offer">暗标出价（元）。别人出多少你看不到，出高了白花钱，出低了拿不到。</label><div class="row"><input id="offer" type="number" inputmode="numeric" min="0" step="100" value="${L.bid || V.offer || L.floor}"><button data-act="bid" class="pri">${L.bid ? '改标' : '投标'}</button></div>${V.msg ? `<p class="say">${esc(V.msg)}</p>` : ''}</div>`;
      else if (sel && !L.sold) h += `<div class="bargain"><label for="offer">出价（元）</label><div class="row"><input id="offer" type="number" inputmode="numeric" min="0" step="100" value="${V.offer || Math.round(L.ask * 0.7 / 100) * 100}"><button data-act="offer">还价</button><button data-act="take" class="pri">照价买 ${fmt(L.ask)}</button></div>${L.ask >= 20000 ? `<div class="row"><button data-act="partner" aria-pressed="${!!V.partner}">找人合伙</button><span class="dim">${V.partner ? '合伙人出一半本钱，赚了亏了都对半分。' : '本钱不够或怕风险，可以拉人各出一半。'}</span></div>` : ''}${V.msg ? `<p class="say">${esc(V.msg)}</p>` : ''}</div>`;
      h += `</article>`;
    });
  } else if (tab === 'mine') {
    const open = W.stones.filter(s => !s.closed), ready = W.items.filter(i => i.state === 'ready').length;
    if (!open.length && !W.works.length) h += `<p class="note">还没有存货。到「货源」里挑一块买下，就能在这里开窗、下刀、询价或送去做件。</p>`;
    for (const k of W.works) h += `<article class="card"><div class="row"><b>加工中 · ${esc(k.from)}</b><span class="dim">第 ${k.ready} 天取货</span></div><div class="row dim"><span>${esc(k.what)}，按看得见的料预计 ${k.expected} 件。开出来才知道。</span></div></article>`;
    const raws = []; for (const s of open) for (const p of s.pieces) if (!p.sold && !p.kept) raws.push([s, p]);
    if (raws.length > 1) { h += `<article class="card"><div class="row"><b>料头盘</b><span class="dim">${raws.length} 块待处理</span></div><p class="note">切下来的料都先放在这里，不用急着卖或加工。点一块拿到工作台上看、再切或送去做件。</p><div class="felt">`;
      for (const [s, p] of raws) { const t = thumb(s, p), lq = s.last[p.id]; h += `<button class="pc ${V.mode === 'own' && V.piece === p ? 'on' : ''}" data-act="piece" data-s="${s.id}" data-p="${p.id}">${t ? `<img src="${t}" alt="">` : '<i></i>'}<span>#${s.id} ${p.name}</span><span class="dim">${lq ? fmt(lq.best) : '未询价'}</span></button>`; }
      h += `</div></article>`; }
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
      for (const p of s.pieces) { if (p.sold || p.kept) continue; const t = thumb(s, p); h += `<button class="pc ${act && V.piece === p ? 'on' : ''}" data-act="piece" data-s="${s.id}" data-p="${p.id}">${t ? `<img src="${t}" alt="">` : '<i></i>'}<span>${p.name}</span></button>`; }
      h += `</div>`;
      if (act && V.piece && !V.piece.sold) {
        const q = getQuotes(s, V.piece), last = s.last[V.piece.id], stt = q.stats;
        h += `<div class="quotes"><div class="row dim"><span>${V.piece.name} · ${Math.round(stt.weight)} g${stt.isSlab ? ` · 片厚 ${stt.thickness.toFixed(0)} mm` : ''}${stt.bracelets ? ` · 可见手镯位 ${stt.bracelets}` : ''} · 看清程度 ${Math.round(stt.kAvg * 100)}%</span></div>`;
        if (last && last.prev != null && last.prev !== q.best) h += `<p class="delta">较上次报价 ${pct(q.best, Math.max(1, last.prev))}${last.why && last.why.length ? '：' + esc(last.why.join('；')) : ''}</p>`;
        for (const o of q.list) h += `<div class="row q"><span><span class="ava" style="background:${{ '稳健同行': '#4a6a5a', '直播货主': '#8a4a5a', '私人藏家': '#6a5a8a', '急收商人': '#8a6a3a' }[o.buyer]}">${o.buyer[0]}</span><b>${o.buyer}</b> <i>${o.rel ? o.rel + ' · ' : ''}${esc(o.note)}</i></span>${o.price ? `<button data-act="sell" data-b="${o.buyer}">${fmt(o.price)} 卖</button>` : '<span class="dim">不收</span>'}</div>`;
        const K = V.wk, plan = C.workPlan(W, s, V.piece, K.route, K.master, K.theme), themed = K.route === 'pendant' || K.route === 'carve';
        const opt = (o, cur, f) => Object.keys(o).map(k => `<option value="${k}" ${k === cur ? 'selected' : ''}>${f(k)}</option>`).join('');
        h += `<div class="work"><b>送去做件</b>
          <div class="row"><label for="wkRoute">做什么</label><select id="wkRoute">${opt(C.ROUTES, K.route, k => C.ROUTES[k].name)}</select></div><p class="note">${C.ROUTES[K.route].tip}</p>
          <div class="row"><label for="wkMaster">找谁做</label><select id="wkMaster">${opt(C.MASTERS, K.master, k => k)}</select></div><p class="note">${C.MASTERS[K.master].tip}</p>
          ${themed ? `<div class="row"><label for="wkTheme">题材</label><select id="wkTheme">${opt(C.THEMES, K.theme, k => k === '师傅定' ? k : `${k}（行情${C.demandWord(C.themeDemand(W, k))}）`)}</select></div><p class="note">${C.THEMES[K.theme].tip}</p>` : ''}
          ${K.route === 'cab' && plan.ok ? `<div class="row"><span class="dim">${K.cabKey === s.id + ':' + V.piece.id ? `你定的尺寸：${K.cabText}` : '可以自己盯着师傅一号一号放大，贪大有风险。'}</span><button data-act="cabgo" ${K.cabKey === s.id + ':' + V.piece.id ? 'disabled' : ''}>自己盯着取</button></div>` : ''}
          ${plan.warn.map(x => `<p class="say">${esc(x)}</p>`).join('')}
          <div class="row"><span class="dim">预计 ${plan.n} ${C.ROUTES[K.route].unit} · 工费 ${fmt(plan.fee)} · ${plan.days} 天</span><button data-act="work" class="pri" ${plan.ok ? '' : 'disabled'}>送去</button></div></div>`;
        h += `<div class="row q"><span><b>不急着卖</b> <i>${V.piece.shelf ? '已摆在铺面' : '摆进铺面零售，或收进藏品柜'}</i></span><span><button data-act="pshelf" ${V.piece.shelf ? 'disabled' : ''}>摆进铺面</button> <button data-act="pkeep">收藏</button></span></div>`;
        h += `<p class="note">报价只在今天有效。账面开涨不是现金到账。</p></div>`;
      }
      h += `</article>`;
    }
  } else if (tab === 'tray') {
    const items = trayItems();
    if (V.ref) { h += `<p class="note">对照盘：上面六块素面牌从豆种到玻璃种，下面是同为冰种、不同颜色的蛋面。转动托盘，对着光看它们的差别。</p>`; for (const it of items) h += `<article class="card ${V.sel === it.id ? 'sel' : ''}" data-act="isel" data-i="${it.id}"><div class="row"><b>${it.name}</b></div><div class="row dim"><span>${it.note}</span></div><div class="row"><button data-act="hold" data-i="${it.id}">拿起来看</button></div></article>`; h += `<button data-act="trayback" class="pri">回到我的托盘</button>`; }
    else {
      h += `<div class="scenes"><button data-act="cab0" aria-pressed="${!V.cab}">待售托盘</button><button data-act="cab2" aria-pressed="${V.cab === 'shelf'}">铺面柜台（${C.shelfCount(W)}/${C.SHOPLV[W.shop].slots}）</button><button data-act="cab1" aria-pressed="${V.cab === true}">藏品柜（${W.items.filter(i => i.state === 'kept').length}）</button></div>`;
      const rawOf = key => { const o = []; for (const s of W.stones) for (const p of s.pieces) if (p[key] && !p.sold) o.push([s, p]); return o; }, rawCard = (s, p, lbl) => `<article class="card"><div class="row"><b>料头 #${s.id} ${p.name}</b><span class="price">${fmt(((s.last[p.id] || {}).best || 0) * (lbl === 'shelf' ? 1.12 * C.SHOPLV[W.shop].mult : 1))}</span></div><div class="row">${thumb(s, p) ? `<img class="rawimg" src="${thumb(s, p)}" alt="">` : ''}<span class="dim">${s.origin} · ${s.info.skin}。这是没加工的明料，拿到工作台上可以转着看、打灯把玩。</span></div><div class="row"><button data-act="pview" data-s="${s.id}" data-p="${p.id}">拿到工作台看</button><button data-act="pback" data-s="${s.id}" data-p="${p.id}">撤回料头盘</button></div></article>`;
      if (V.cab === 'shelf') h += rawOf('shelf').map(x => rawCard(x[0], x[1], 'shelf')).join(''); if (V.cab === true) h += rawOf('kept').map(x => rawCard(x[0], x[1], 'kept')).join('');
      if (V.cab === 'shelf') { h += `<p class="note">${W.shop ? `${C.SHOPLV[W.shop].name}：摆在这里的成品每天有散客上门，按零售价${C.SHOPLV[W.shop].mult > 1 ? '加一点' : ''}买走，口碑越好卖得越快。` : '还没有铺面。到「账本」里盘一个柜台，成品就能自己零售，不用再让批发商压价。'}</p>`; for (const it of items) h += `<article class="card ${V.sel === it.id ? 'sel' : ''}" data-act="isel" data-i="${it.id}"><div class="row"><b>${esc(it.name)}</b><span class="price">${fmt(it.value * C.SHOPLV[W.shop].mult)}</span></div><div class="row dim"><span>${C.waterName(it.w)} · 第 ${it.shelfDay} 天上柜</span></div><div class="row"><button data-act="hold" data-i="${it.id}">拿起来看</button><button data-act="unshelf" data-i="${it.id}">撤回托盘</button></div></article>`; }
      if (!V.cab && W.event) h += `<p class="say">今日行情：${esc(W.event.t)}（${W.event.m > 1 ? '+' : ''}${Math.round((W.event.m - 1) * 100)}%）</p>`;
      if (!V.cab) { h += `<article class="card"><b>客户订单</b>${W.orders.map(o => `<div class="row dim"><span>${esc(C.orderText(o))}</span><span>加价 ${Math.round((o.bonus - 1) * 100)}% · 第 ${o.due} 天前</span></div>`).join('') || '<div class="row dim"><span>暂时没有订单</span></div>'}</article>`;
      for (const k of W.works) h += `<article class="card"><div class="row"><b>加工中 · ${esc(k.from)}</b><span class="dim">第 ${k.ready} 天取货</span></div><div class="row dim"><span>${esc(k.what)}</span></div></article>`; }
      if (V.cab === true) { if (!items.length) h += `<p class="note">藏品柜是空的。舍不得卖的成品可以收进来，随时拿出来看。</p>`; for (const it of items) h += `<article class="card ${V.sel === it.id ? 'sel' : ''}" data-act="isel" data-i="${it.id}"><div class="row"><b>${esc(it.name)}</b><span class="price">${fmt(it.value)}</span></div><div class="row dim"><span>${C.waterName(it.w)} · ${it.master} · 出自 #${it.stone}</span></div><div class="row"><button data-act="hold" data-i="${it.id}">拿起来看</button><button data-act="unkeep" data-i="${it.id}">拿回托盘出售</button></div></article>`; }
      else if (!V.cab && !items.length) h += `<p class="note">托盘是空的。把料送去做件，做好后成品会摆在这里，可以转着看，一件件卖或整盘卖。</p>`;
      else if (!V.cab) { const tot = items.reduce((a, i) => a + i.value, 0); h += `<article class="card"><div class="row"><b>整盘 ${items.length} 件</b><span>零售估值 ${fmt(tot)}</span></div><div class="row"><button data-act="iall" data-how="whole">整盘批发现结 ${fmt(tot * 0.6)}</button><button data-act="iall" data-how="retail" class="pri">整盘寄卖 ${fmt(tot * 0.95)}</button></div></article>`; }
      if (!V.cab) for (const it of items) h += `<article class="card ${V.sel === it.id ? 'sel' : ''}" data-act="isel" data-i="${it.id}"><div class="row"><b>${esc(it.name)}</b><span class="price">${fmt(it.value)}</span></div><div class="row dim"><span>${C.waterName(it.w)} · ${it.lv > 0.6 ? '色满' : it.lv > 0.25 ? '带色' : it.lv > 0.08 ? '飘色' : '无色'}${it.theme && it.theme !== '师傅定' ? ' · ' + it.theme : ''} · ${it.master} · 出自 #${it.stone}</span></div>
        <div class="row"><button data-act="hold" data-i="${it.id}">拿起来看</button><button data-act="isell" data-i="${it.id}" data-how="whole">批发 ${fmt(it.value * 0.6 * C.productDemand(W, it.type))}</button><button data-act="isell" data-i="${it.id}" data-how="retail">寄卖 ${fmt(it.value * 0.95 * C.productDemand(W, it.type))}（6–14 天）</button>${W.orders.filter(o => C.orderMatch(o, it)).slice(0, 1).map(o => `<button data-act="iorder" data-i="${it.id}" data-o="${o.id}" class="pri">交给${o.who} ${fmt(it.value * o.bonus)}</button>`).join('')}<button data-act="shelf" data-i="${it.id}">摆进铺面</button><button data-act="keep" data-i="${it.id}">收藏</button></div></article>`;
      h += `<button data-act="trayref">看种水与颜色对照盘</button>`;
    }
  } else {
    const recv = W.recv.map(r => `<div class="row dim"><span>${r.from}</span><span>第 ${r.day} 天到账 ${fmt(r.amt)}</span></div>`).join('');
    h += `<article class="card"><div class="row"><b>资金</b><span>现金 ${fmt(W.cash)}</span></div>${recv || '<div class="row dim"><span>没有在途货款</span></div>'}<div class="row dim"><span>每天铺面与生活开销 ${C.ECON.daily}</span></div></article>`;
    for (const s of W.stones.filter(s => s.closed).reverse()) {
      const r = s.review, net = s.proceeds - s.buyPrice - s.costs;
      h += `<article class="card ${V.mode === 'review' && V.rec === s ? 'sel' : ''}"><div class="row"><b>复盘 #${s.id} ${s.origin} · ${s.info.skin}</b><span class="${net >= 0 ? 'up' : 'down'}">${net >= 0 ? '+' : ''}${fmt(net)}</span></div>
      <div class="row dim"><span>买入 ${fmt(s.buyPrice)} · 加工 ${fmt(s.costs)} · 回款 ${fmt(s.proceeds)} · 持有 ${s.closeDay - s.buyDay} 天</span></div>${s.share < 1 ? `<div class="row"><span class="say">合伙料：你出一半本钱，结账${s.settle >= 0 ? `分给合伙人 ${fmt(s.settle)}` : `合伙人补给你 ${fmt(-s.settle)}`}，你实际净${(s.proceeds - s.buyPrice - s.costs) >= 0 ? '赚' : '亏'} ${fmt(Math.abs((s.proceeds - s.buyPrice - s.costs) * s.share))}</span></div>` : ''}
      <div class="row dim"><span>买入当天原样转手最高 ${fmt(s.flip)}；途中账面最高 ${fmt(s.best)}</span></div>
      ${r.fake ? `<div class="row"><span class="say">这是一块假料：${r.fake}</span></div>` : ''}
      <div class="row dim"><span>真相：${r.water}，${r.feats.length ? r.hue + '（' + r.feats.join('、') + '）' : '基本无色'}，${r.cracks} 条裂${r.shift ? '，' + r.shift : ''}；全部做成件的零售价值约 ${fmt(r.truth)}</span></div>
      ${s.guessResult ? `<div class="row"><span class="say">判断本：你写的是 ${C.waterName(C.GRADES[s.guess.water])}／${{ none: '无色', skin: '贴皮色', deep: '色吃进去', full: '满色' }[s.guess.color]}／${s.guess.crack === 'few' ? '裂少' : '裂多'}，实际 ${C.waterName(C.GRADES[s.guessResult.water])}／${{ none: '无色', skin: '贴皮色', deep: '色吃进去', full: '满色' }[s.guessResult.color]}／${s.guessResult.crack === 'few' ? '裂少' : '裂多'}。眼力 +${s.guessResult.pts}</span></div>` : ''}
      <div class="row"><span class="dim">一次赚钱不等于判断正确，亏了也不一定是决策错。</span><button data-act="review" data-s="${s.id}">看剖面</button></div></article>`;
    }
    { const S = C.SHOPLV[W.shop], nx = C.SHOPLV[W.shop + 1]; h += `<article class="card"><div class="row"><b>铺面：${S.name}</b><span class="dim">口碑 ${Math.round(W.fame)}</span></div>${W.shop ? `<div class="row dim"><span>日租 ${S.rent} · 柜位 ${C.shelfCount(W)}/${S.slots} · 零售价 ×${S.mult}</span></div>` : ''}${nx ? `<div class="row"><span class="dim">${nx.tip} 日租 ${nx.rent}。</span><button data-act="shopup">盘下${nx.name} ${fmt(nx.cost)}</button></div>` : ''}<div class="row dim"><span>熟客：${Object.keys(C.BUYERS).map(k => `${k} ${C.relWord(C.relOf(W, k))}`).join('，')}</span></div></article>`; }
    h += `<article class="card"><b>工具铺</b>${Object.keys(C.SHOP).map(k => { const S = C.SHOP[k], lv = W.tools[k], mx = lv >= S.levels.length; return `<div class="row"><span><b>${S.levels[lv - 1]}</b> <span class="dim">${S.tip}</span></span>${mx ? '<span class="dim">已是最好的</span>' : `<button data-act="tool" data-k="${k}">换${S.levels[lv]} ${fmt(S.price[lv - 1])}</button>`}</div>`; }).join('')}</article>`;
    if (!W.flags.debt) h += `<article class="card"><div class="row"><b>父亲留下的欠条</b><span>${fmt(C.DEBT)}</span></div><div class="row"><span class="dim">还清它是第三章的目标之一。还的时候要留够周转的钱。</span><button data-act="debt">还清</button></div></article>`;
    h += `<article class="card"><div class="row"><b>${C.rankOf(W)}</b><span>眼力 ${W.eye} · 身家 ${fmt(C.netWorth(W))}</span></div><div class="row dim"><span>${C.RANKS.map(r => `${r[1]} ${r[0]}`).join(' → ')}</span></div><div class="achs">${C.ACH_ALL.map(a => { const g = W.ach[a[0]]; return `<span class="${g ? 'got' : ''}" title="${g ? '第 ' + g.day + ' 天达成' : '未达成'}">${g ? '★' : '☆'} ${a[1]}</span>`; }).join('')}</div><div class="row dim"><span>已达成 ${C.ACH_ALL.filter(a => W.ach[a[0]]).length} / ${C.ACH_ALL.length}</span></div></article>`;
    h += `<article class="card"><b>流水</b>${W.log.slice(-40).reverse().map(l => `<div class="row dim"><span>第 ${l.day} 天 ${esc(l.t)}</span><span>${l.amt ? (l.amt > 0 ? '+' : '') + fmt(l.amt) : ''}</span></div>`).join('')}</article>`;
  }
  el.innerHTML = h;
}
const HINTS = {
  rotate: '拖动转石头，滚轮或双指缩放。右键拖动在任何工具下都能转。',
  torch: '点或拖到石头上放灯，灯会留在原处。贴着压（离皮 0、倾斜 0）光进得最深；放斜贴着皮扫，裂和起伏最明显；抬高是照表面。',
  loupe: '移动放大镜看皮壳颗粒、松花、细裂和玉肉晶粒。可以和手电一起用。',
  grind: '在石头上拖动磨皮开窗。同一处来回磨会越磨越深，磨掉的料回不来。',
  saw: '小锯取料：在看得清的面上圈出想要的那一块（比如色带），沿圈直着锯穿，把它单独取下来。圈会被拉成最多六条边的形状。',
  peel: '在石头上画一个圈，圈里的皮会被整片切掉，只剥到刚露肉，不伤里面的料。圈越大切工越贵，想象空间也越少。',
  cut: '在石头上拖一条线，就是锯片走的位置；或者把想切的面转到正对自己，按厚度切一片。橙线是下刀处。',
};
function cutFromView() {
  const b = camBasis(), n = [-b.f[0], -b.f[1], -b.f[2]], inf = C.pieceInfo(V.e.vol, V.piece, n);
  V.cut = { n, d: inf.hi - V.cutT, base: inf.hi }; V.cut.pv = C.cutPreview(V.rec, V.piece, V.cut.n, V.cut.d);
}
function renderTools() {
  const own = V.mode === 'own' && V.piece && !V.piece.sold, tray = V.mode === 'tray';
  document.querySelectorAll('#tools button[data-tool]').forEach(b => { b.setAttribute('aria-pressed', b.dataset.tool === V.tool); b.disabled = ((b.dataset.tool === 'grind' || b.dataset.tool === 'cut' || b.dataset.tool === 'peel' || b.dataset.tool === 'saw') && !own) || (tray && b.dataset.tool !== 'rotate'); });
  let o = '';
  if (V.mode === 'review') o += `<label for="sec">剖面高度</label><input id="sec" type="range" min="${(-V.e.vol.hy).toFixed(0)}" max="${V.e.vol.hy.toFixed(0)}" step="0.5" value="${V.section}"><span class="dim">复盘：这是石头原本的内部</span>`;
  else if (V.tool === 'torch') o += `<label for="tTilt">倾斜 <b id="tTiltV">${V.torch.tilt}</b>°</label><input id="tTilt" type="range" min="0" max="85" step="5" value="${V.torch.tilt}"><label for="tAz">朝向</label><input id="tAz" type="range" min="0" max="360" step="15" value="${V.torch.az}"><label for="tH">离皮 <b id="tHV">${V.torch.h}</b> mm</label><input id="tH" type="range" min="0" max="60" step="2" value="${V.torch.h}"><button data-act="lbody" aria-pressed="${V.lampBody}">显示筒身</button><button data-act="toff" ${V.torch.on ? '' : 'disabled'}>关灯</button>`;
  else if (V.tool === 'saw' && own) o += V.sawPlan ? `<span class="dim">橙框是要取的范围。在石头旁的小框里调深度、确认或重画；右键拖动可以转着看。</span>` : `<button data-act="sawsmart">智能圈色</button><span class="dim">或自己在料上圈出要取的那一块。画完线先预览，确认了才锯。</span>`;
  else if (V.tool === 'grind') o += Object.keys(C.TOOLS).map(k => `<button data-act="burr" data-k="${k}" aria-pressed="${V.burr === k}">${k}</button>`).join('');
  else if (V.tool === 'cut' && own) {
    o += `<label for="cutT">片厚 <b id="cutV">${V.cutT}</b> mm</label><input id="cutT" type="range" min="3" max="60" step="1" value="${V.cutT}"><button data-act="cview">从正对我的面切这么厚</button>`;
    if (V.cut) o += `<select id="betSel" aria-label="和旁边的行家赌这一刀"><option value="">不赌</option><option value="up" ${V.bet === 'up' ? 'selected' : ''}>赌这刀切涨</option><option value="down" ${V.bet === 'down' ? 'selected' : ''}>赌这刀切垮</option></select><button data-act="cut" class="pri">下刀（切工 ${fmt(V.cut.pv.cost)}）</button><button data-act="ccancel">取消</button><span class="dim">两侧约 ${Math.round(V.cut.pv.a)} g / ${Math.round(V.cut.pv.b)} g</span>`;
  }
  if (tray && V.hold != null) o = `<button data-act="back" aria-pressed="${!!V.back}">打背光</button><button data-act="unhold" class="pri">放回托盘</button>`;
  else if (tray) o = `<span class="dim">点一件选中，再点「拿起来看」</span>`;

  $('#opts').innerHTML = o;
  let t = V.e ? HINTS[V.tool] : '从右侧「货源」里点一块石头开始看料。';
  if (tray && V.hold != null) t = '拿在手里看：拖动可以转到任何角度，包括背面和底下。打开背光看它透不透、色根怎么走。';
  else if (tray) t = V.ref ? '对照盘：拖动转托盘，点一件看说明。' : '成品托盘：拖动转着看，点一件选中，在右侧一件件卖或整盘卖。';
  if (V.mode === 'review') t = '复盘剖面：拖动滑块看这块石头原本的内部结构。';
  $('#hint').textContent = V.note || t;
  $('#title').textContent = tray ? (V.ref ? '种水与颜色对照盘' : '成品托盘') : V.rec ? (V.mode === 'market' ? `${V.rec.origin} · ${V.rec.info.skin}` : `#${V.rec.id} ${V.rec.origin} · ${V.rec.info.skin}${V.mode === 'own' && V.piece ? ' · ' + V.piece.name : ''}${V.mode === 'review' ? ' · 复盘' : ''}`) : '';
}
/* ---------- 激活码 ---------- */
function sha256(ascii) { const rr = (v, a) => (v >>> a) | (v << (32 - a)), mp = Math.pow, mw = mp(2, 32); let res = ''; const words = [], bl = ascii.length * 8; const hash = sha256.h = sha256.h || [], k = sha256.k = sha256.k || []; let pc = k.length; const comp = {};
  for (let c = 2; pc < 64; c++) if (!comp[c]) { for (let i = 0; i < 313; i += c) comp[i] = c; hash[pc] = (mp(c, .5) * mw) | 0; k[pc++] = (mp(c, 1 / 3) * mw) | 0; }
  ascii += '\x80'; while (ascii.length % 64 - 56) ascii += '\x00';
  for (let i = 0; i < ascii.length; i++) { const j = ascii.charCodeAt(i); if (j >> 8) return ''; words[i >> 2] |= j << ((3 - i) % 4) * 8; }
  words[words.length] = ((bl / mw) | 0); words[words.length] = bl; let H = hash.slice(0, 8);
  for (let j = 0; j < words.length;) { const w = words.slice(j, j += 16), old = H; H = H.slice(0, 8);
    for (let i = 0; i < 64; i++) { const w15 = w[i - 15], w2 = w[i - 2], a = H[0], e = H[4];
      const t1 = H[7] + (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) + ((e & H[5]) ^ ((~e) & H[6])) + k[i] + (w[i] = (i < 16) ? w[i] : (w[i - 16] + (rr(w15, 7) ^ rr(w15, 18) ^ (w15 >>> 3)) + w[i - 7] + (rr(w2, 17) ^ rr(w2, 19) ^ (w2 >>> 10))) | 0);
      const t2 = (rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) + ((a & H[1]) ^ (a & H[2]) ^ (H[1] & H[2])); H = [(t1 + t2) | 0].concat(H); H[4] = (H[4] + t1) | 0; }
    for (let i = 0; i < 8; i++) H[i] = (H[i] + old[i]) | 0; }
  for (let i = 0; i < 8; i++) for (let j = 3; j + 1; j--) { const b = (H[i] >> (j * 8)) & 255; res += ((b < 16) ? 0 : '') + b.toString(16); }
  return res; }
const CFG = window.JADE_CONFIG || { license: false, trialDays: 3, buyText: '' };
function codeOk(c) { c = String(c || '').toUpperCase().replace(/[^A-Z0-9]/g, ''); return c.length === 16 && (window.JADE_LICENSES || []).indexOf(sha256('jade:' + c)) >= 0; }
function licensed() { if (!CFG.license) return true; try { return codeOk(localStorage.getItem('jade-license')); } catch (e) { return false; } }
/* ---------- 新手教学：牛叔带着看第一块石头 ---------- */
const COACH = [
  ['牛叔：先别急着买。按住石头拖一拖，四面都转着看一遍。', () => W.flags.orbit],
  ['牛叔：左下角那支手电，按住它拖到石头上。', () => W.flags.torch],
  ['牛叔：把右上角的室内灯关了，看光透出来多大一片。再点石头别的位置比一比。', () => W.flags.dark],
  ['牛叔：看右边这块料的标签和老板说的话。觉得行就还个价买下来；不行就点别的料。', () => W.stones.length > 0],
  ['牛叔：买下了。先在右边的「判断本」里写下你觉得的种水、色、裂，以后对答案。', () => W.flags.guess],
  ['牛叔：选底下的「画圈开皮」，在石头上圈一小块，看看皮下面是什么。', () => W.flags.open],
  ['牛叔：右边报价变了，还写了原因。可以卖给出价最高的，也可以接着切。卖出一件货，我就不啰嗦了。', () => W.stat.sold > 0],
];
function coachUpdate() { const el = $('#coach'); if (!W || W.flags.tut || V.mode === 'tray' || !$('#start').hidden) { el.hidden = true; return; }
  let i = 0; while (i < COACH.length && COACH[i][1]()) i++;
  if (i >= COACH.length) { W.flags.tut = true; el.hidden = true; save(); V.note = '牛叔：行了，剩下的自己摸。右上角「教程」里有图鉴，忘了就翻。'; renderAll(); return; }
  el.hidden = false; el.innerHTML = `<span>${esc(COACH[i][0])}</span><small>${i + 1} / ${COACH.length}</small><button data-act="skiptut">跳过教学</button>`; }
function flag(k) { if (W && !W.flags[k]) { W.flags[k] = true; coachUpdate(); storyCheck(); } }
function storyCheck() { const ch = C.checkStory(W); if (!ch) return; save(); Snd.win(); const nx = C.CHAPTERS[W.chapter];
  $('#storybody').innerHTML = `<h2>${ch.title} · 完成</h2><p>${esc(ch.done)}</p><p class="say">眼力 +${ch.reward.eye}${ch.reward.cash ? `，奖励 ${fmt(ch.reward.cash)}` : ''}</p>${nx ? `<h3>${nx.title}</h3><p>${esc(nx.story)}</p><ul>${nx.goals.map(g => `<li>${g[1]}</li>`).join('')}</ul>` : '<p>主线完成。生意可以一直做下去。</p>'}<button data-act="storyok" class="pri">继续</button>`;
  $('#story').hidden = false; renderTop(); renderSide(); }
function goalCard() { const ch = C.CHAPTERS[W.chapter]; if (!ch) return `<article class="card goal"><div class="row"><b>主线完成</b><span class="dim">一代货主</span></div></article>`;
  return `<article class="card goal"><div class="row"><b>${ch.title}</b><button data-act="storyshow">剧情</button></div>${ch.goals.map(g => { const d = C.goalDone(W, g[0]); return `<div class="row ${d ? 'done' : ''}"><span>${d ? '✔' : '○'} ${g[1]}</span></div>`; }).join('')}</article>`; }
/* 场景里的人：摊主、公盘上竞标的人。只是剪影和对话气泡 */
const NPC_LOOK = { '小商贩': ['#6b4a2a', 'hat'], '个人转让': ['#4a5560', 'cap'], '二级供应商': ['#3f4a3a', 'glass'], '大型集散地': ['#51463a', 'glass'], '拍卖市场': ['#2f3440', 'suit'], '场口直采': ['#5a4a32', 'hat'] };
function npcSvg(col, acc, s) { return `<svg viewBox="0 0 120 130" width="${s}" height="${s * 1.08}" aria-hidden="true"><ellipse cx="60" cy="128" rx="58" ry="46" fill="${col}"/><rect x="50" y="62" width="20" height="20" fill="#b98f6a"/><circle cx="60" cy="46" r="24" fill="#c79f78"/><circle cx="51" cy="44" r="2.4" fill="#2a2018"/><circle cx="69" cy="44" r="2.4" fill="#2a2018"/><path d="M51 56 Q60 62 69 56" stroke="#2a2018" stroke-width="2" fill="none"/>${acc === 'hat' ? '<ellipse cx="60" cy="27" rx="38" ry="8" fill="#b89a5a"/><path d="M38 27 Q60 -6 82 27Z" fill="#c9ab68"/>' : acc === 'cap' ? '<path d="M36 36 Q60 8 84 36Z" fill="#2c3a4a"/><rect x="72" y="32" width="22" height="5" rx="2" fill="#2c3a4a"/>' : acc === 'glass' ? '<path d="M37 34 Q60 14 83 34 L83 28 Q60 6 37 28Z" fill="#2a2018"/><circle cx="51" cy="44" r="7" fill="none" stroke="#2a2018" stroke-width="2"/><circle cx="69" cy="44" r="7" fill="none" stroke="#2a2018" stroke-width="2"/><path d="M58 44h4" stroke="#2a2018" stroke-width="2"/>' : '<path d="M37 34 Q60 14 83 34 L83 28 Q60 6 37 28Z" fill="#1c1c1c"/><path d="M52 82 L60 96 L68 82Z" fill="#e8e2d6"/><path d="M58 84h4l2 22h-8z" fill="#7a2a2a"/>'}</svg>`; }
function renderNpc() { const el = $('#npc'); if (!el) return; const L = V.rec; if (V.mode !== 'market' || !L || !V.e) { el.hidden = true; return; } el.hidden = false;
  const lk = NPC_LOOK[L.channel] || NPC_LOOK['小商贩'], lines = (L.patter || []).filter(x => x.startsWith('老板')).map(x => x.replace(/^老板：/, ''));
  let say = V.msg ? V.msg.replace(/^老板[^：]*：/, '').replace(/[“”]/g, '') : L.sold ? '拿好，回头再来。' : L.auction ? (L.bid ? '标书收到了，晚上开标。' : '看好了就写个价，暗标，价高者得。') : lines[(V.npcI || 0) % Math.max(1, lines.length)] || '随便看，看好了再说价。';
  let h = '';
  if (L.auction) h += `<div class="rivals">${[0, 1, 2].map(i => `<span style="opacity:${0.5 + 0.15 * i}">${npcSvg(['#3a3f4c', '#4c3a3a', '#3a4c44'][i], ['suit', 'glass', 'cap'][i], 46)}<i>${['也在看这块', '写了标书', '摇摇头走了'][(L.seed + i) % 3]}</i></span>`).join('')}</div>`;
  h += `<div class="seller"><button class="bubble" data-act="npcnext" title="再听听老板怎么说">${esc(say)}</button>${npcSvg(lk[0], lk[1], 92)}<b>${L.auction ? '公盘主持' : L.channel === '个人转让' ? '卖家' : '老板'} · ${L.channel}</b></div>`;
  el.innerHTML = h; }
function renderAll() { storyCheck(); coachUpdate(); renderTop(); renderSide(); renderTools(); renderDock(); renderNpc(); invalidate(false); $('#over').hidden = !W.over; }
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
  const shot = (st, vol, torch) => { V.mode = 'own'; V.rec = null; V.piece = C.WHOLE; V.e = { st, vol }; V.lens = null; V.room = !torch; cam.yaw = 0.5; cam.pitch = 0.3; cam.t = [0, 0, 0]; cam.dist = Math.max(vol.hx, vol.hy, vol.hz) * 3.9; V.torch = { on: false, p: null, n: null, rake: false, tilt: 0, az: 0, h: 0 };
    if (torch) { const b = camBasis(), h = C.pick(vol, C.WHOLE, b.pos, b.f); if (h) V.torch = { on: true, p: h.p, n: h.n, dir: h.n, h: 0 }; }
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
/* 种色图鉴：每种种水、每种颜色各拍四张——隔皮压灯、开窗、窗口压灯、切开 */
const CASES = [
  ['豆种', { w: 0.10 }, '隔着皮几乎不透，灯头只亮一小团。窗口像粗瓷，发白发干，看得见一粒粒晶体。切开是不透的白，没有水感。'],
  ['糯种', { w: 0.25 }, '光晕比豆种大一圈，发浑发柔。窗口细腻，像糯米汤。切开匀净、温吞，光只进表层。'],
  ['糯冰种', { w: 0.45 }, '光晕明显变大，边缘柔和。窗口半透，有点水感。切开能往里看进去一点，絮开始看得见。'],
  ['冰种', { w: 0.65 }, '隔着皮透出一大片，颜色干净。窗口像冰块，清亮。切开通透，里面的棉絮像冰里的气泡和云。'],
  ['高冰种', { w: 0.82 }, '整块都被点亮。窗口起光，清澈。切开几乎没有杂质，像冻住的清水。'],
  ['玻璃种', { w: 0.95 }, '通体透亮像灯泡。窗口像玻璃，表面有一层荧光。切开接近透明，能看穿到背后。'],
  ['淡绿', { w: 0.55, hue: '淡绿', full: 0.8 }, '灯下泛一层很淡的绿，开窗是清淡的豆青。最容易被灯高估：灯下看着有色，自然光下很浅。只比无色贵一点。'],
  ['阳绿', { w: 0.6, hue: '阳绿', full: 0.9 }, '灯下是鲜亮带黄味的绿光。窗口翠、亮、活。切开颜色鲜阳。满色时比无色贵十几倍。'],
  ['正绿', { w: 0.6, hue: '正绿', full: 0.95 }, '灯下绿得浓而正，不偏黄不偏蓝。窗口沉稳饱满。切开色浓均匀。满色贵几十倍。'],
  ['帝王绿', { w: 0.65, hue: '帝王绿', full: 1 }, '色太浓，灯下反而发暗发黑，要强光才透出深绿。窗口浓艳深沉。切开像墨绿的玻璃，薄处才显翠。最贵。'],
  ['紫罗兰', { w: 0.5, hue: '紫罗兰', full: 0.9 }, '灯下泛粉紫。紫色见光“死”：灯下好看，自然光下会淡一截。窗口是淡淡的藕紫。'],
  ['黄翡', { w: 0.45, hue: '黄翡', full: 0.9 }, '灯下是暖黄到橙。多在皮下一层（雾和皮色渗进来的），往里常常就没了。'],
  ['油青', { w: 0.55, hue: '油青', full: 0.9 }, '灯下灰蓝绿，发闷。窗口色沉、带灰。种好的叫蓝水，种差就是油青，价钱差很多。'],
  ['飘花', { w: 0.65, hue: '阳绿', float: 0.9 }, '灯下光晕里有一团团绿影，位置换了影子也跟着变。窗口和切面是白底上散着絮状、丝状的绿。种定底价，花定倍数。'],
  ['色带', { w: 0.5, hue: '正绿', ribbon: 0.95 }, '隔着皮只在色带经过的地方透绿，挪开灯就白了。窗口如果正好开在带子上会以为满色。切开才知道是一条：宽窄、走向、有没有穿过去。'],
];
let casesStarted = false;
function buildCases() {
  if (casesStarted) return; casesStarted = true;
  const host = $('#caseAtlas'); host.innerHTML = '';
  const keep = { mode: V.mode, rec: V.rec, piece: V.piece, e: V.e, torch: V.torch, room: V.room, lens: V.lens, cam: { yaw: cam.yaw, pitch: cam.pitch, dist: cam.dist, t: cam.t } };
  const restore = () => { V.mode = keep.mode; V.rec = keep.rec; V.piece = keep.piece; V.e = keep.e; V.torch = keep.torch; V.room = keep.room; V.lens = keep.lens; Object.assign(cam, keep.cam); loaded = null; invalidate(false); };
  let i = 0;
  const step = () => {
    if (i >= CASES.length || $('#help').hidden) { restore(); if (i < CASES.length) casesStarted = false; return; }
    const [name, o, text] = CASES[i++];
    try {
      const st = C.genStone(515151, '木那', '二级供应商'); st.cracks = []; st.dirt = []; st.shift = null; st.wVar = 0; st.cot = 0.22; st.planes = []; st.fog = { t: 0, col: [1, 1, 1] }; st.body = '白底'; st.w0 = o.w; st.hue = o.hue || '阳绿';
      const a = st.rad[0], sd = 77; st.feats = [];
      if (o.full) st.feats.push({ type: 'full', strength: o.full, seed: sd, c: [0, 0, 0] });
      if (o.float) st.feats.push({ type: 'float', strength: o.float, seed: sd, c: [0, 0, 0], R: a * 1.3 });
      if (o.ribbon) st.feats.push({ type: 'ribbon', strength: o.ribbon, seed: sd, n: [0.26, 0.93, 0.26], t1: [0.96, -0.27, 0], t2: [0.07, 0.25, -0.97], c: [0, 4, 0], width: 5.5, R: a * 1.6, warp: 3, freq: 0.05, phase: 1 });
      st.skin = { name: '黄砂皮', col: C.SKINS['黄砂皮'].col, grain: 0.78, sig: 0.75, weather: 0.45, t: 1.6, phase: 3 };
      const vol = C.bake(st, 44), R0 = Math.max(vol.hx, vol.hy, vol.hz);
      V.mode = 'own'; V.rec = null; V.e = { st, vol }; V.lens = null; cam.yaw = 0.5; cam.pitch = 0.3; cam.t = [0, 0, 0];
      const shot = (torch, piece, dist) => { V.piece = piece; V.room = !torch; cam.dist = R0 * dist; const b = camBasis(); V.torch = { on: false, p: null, n: null };
        if (torch) { const h = C.pick(vol, piece, b.pos, b.f); if (h) V.torch = { on: true, p: h.p, n: h.n, dir: h.n, h: 0 }; }
        const lb = V.lampBody; V.lampBody = false; render(1, 176); V.lampBody = lb; return canvas.toDataURL('image/jpeg', 0.85); };
      const img1 = shot(true, C.WHOLE, 3.7);
      const b = camBasis(), h = C.pick(vol, C.WHOLE, b.pos, b.f), sk = C.sampleG(vol, 2, h.p[0], h.p[1], h.p[2]), g = [b.r, b.up];
      for (const [dx, dy] of [[0, 0], [7, 2], [-7, -1], [1, 7], [-2, -7]]) { const q = [0, 1, 2].map(k => h.p[k] + g[0][k] * dx + g[1][k] * dy), rr = C.pick(vol, C.WHOLE, [q[0] - b.f[0] * 300, q[1] - b.f[1] * 300, q[2] - b.f[2] * 300], b.f); if (rr) C.carve(vol, C.WHOLE, rr.p[0] + rr.n[0] * (9 - sk - 1.3), rr.p[1] + rr.n[1] * (9 - sk - 1.3), rr.p[2] + rr.n[2] * (9 - sk - 1.3), 9); }
      loaded = null;
      const img2 = shot(false, C.WHOLE, 2.3), img3 = shot(true, C.WHOLE, 2.6), cut = { planes: [[-b.f[0], -b.f[1], -b.f[2], 0]] }, img4 = shot(false, cut, 3.4);
      host.insertAdjacentHTML('beforeend', `<article class="case"><div class="row"><b>${name}</b><span class="dim">${C.waterName(o.w)}${o.hue ? ' · ' + o.hue : ' · 无色'}</span></div><div class="four">${[['隔着皮压灯', img1], ['开窗', img2], ['对着窗口压灯', img3], ['切开', img4]].map(x => `<figure><img src="${x[1]}" alt="${name}${x[0]}"><figcaption>${x[0]}</figcaption></figure>`).join('')}</div><p>${text}</p></article>`);
    } catch (e) { host.insertAdjacentHTML('beforeend', `<p class="note">${name} 的图没拍出来：${e.message}</p>`); }
    $('#caseProg').textContent = i < CASES.length ? `正在拍第 ${i + 1} / ${CASES.length} 组…` : '';
    setTimeout(step, 30);
  };
  setTimeout(step, 30);
}
function showPane(k) { document.querySelectorAll('#help [data-pane]').forEach(x => x.hidden = x.dataset.pane !== k); document.querySelectorAll('#help [data-act=pane]').forEach(x => x.setAttribute('aria-pressed', x.dataset.k === k)); if (k === 'skin' || k === 'water') buildAtlas(); if (k === 'atlas') buildCases(); }

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
  if (b.dataset.tool) { V.tool = b.dataset.tool; V.lens = null; V.cut = null; V.sawPlan = null; showLasso(null); $('#sawbox').hidden = true; V.note = ''; renderTools(); invalidate(false); return; }
  const a = b.dataset.act;
  if (a !== 'menu') $('#hmenu').classList.remove('open');
  if (a === 'listing') { if (ev.target.closest('.bargain')) return; const L = W.market[+b.dataset.i]; V.offer = 0; if (V.rec !== L) view('market', L, null); }
  else if (a === 'offer' || a === 'take') {
    const L = V.rec, offer = a === 'take' ? L.ask : +($('#offer').value || 0); V.offer = offer;
    const sh = V.partner && L.ask >= 20000 ? 0.5 : 1, r = C.negotiate(W, L, offer, sh); V.msg = r.msg;
    if (r.res === 'deal') { Snd.coin(); const s = C.buy(W, L, r.price, sh); V.partner = false; tab = 'mine'; view('own', s, s.pieces[0]); refreshQuote(s, s.pieces[0], true); save(); V.note = `成交 ${fmt(r.price)}。可以直接询价转手，也可以开窗、下刀或送加工。`; renderAll(); return; }
    save(); renderSide(); renderNpc();
  }
  else if (a === 'piece') { const s = W.stones.find(x => x.id === +b.dataset.s), p = s.pieces.find(x => x.id === +b.dataset.p); view('own', s, p); if (!s.last[p.id]) refreshQuote(s, p); renderAll(); }
  else if (a === 'sell') { const s = V.rec, p = V.piece, q = getQuotes(s, p).list.find(o => o.buyer === b.dataset.b); C.sell(W, s, p, q); Snd.coin(); qcache.clear(); save(); afterStoneChange(s); }
  else if (a === 'work') { const s = V.rec, K = V.wk, r = C.sendWork(W, s, V.piece, K.route, K.master, K.theme, K.route === 'cab' && K.cabKey === s.id + ':' + V.piece.id ? { cabMult: K.cabMult } : null); if (!r.ok) { V.note = r.msg; renderTools(); return; } qcache.clear(); save(); afterStoneChange(s); V.note = `已送去，工费 ${fmt(r.fee)}，${r.days} 天后到托盘取成品。`; renderTools(); }
  else if (a === 'scene') { C.enterScene(W, b.dataset.k); save(); Snd.tap(); view('market', W.market.find(L => !L.sold) || null, null); }
  else if (a === 'bid') { const L = V.rec, r = C.placeBid(W, L, +($('#offer').value || 0)); V.msg = r.msg; if (r.ok) Snd.coin(); save(); renderTop(); renderSide(); renderNpc(); }
  else if (a === 'cab0') openTray(false, false);
  else if (a === 'cab1') openTray(false, true);
  else if (a === 'keep') { C.keepItem(W, W.items.find(x => x.id === +b.dataset.i)); save(); openTray(false, false); }
  else if (a === 'unkeep') { W.items.find(x => x.id === +b.dataset.i).state = 'ready'; save(); openTray(false, true); }
  else if (a === 'iorder') { const it = W.items.find(x => x.id === +b.dataset.i), o = W.orders.find(x => x.id === +b.dataset.o); C.sellToOrder(W, it, o); Snd.win(); save(); openTray(false, false); }
  else if (a === 'quality') { const o = [[1, '画质 标准'], [1.35, '画质 高'], [0.7, '画质 省电']], i = (o.findIndex(x => x[0] === Q.user) + 1) % o.length; Q.user = o[i][0]; b.textContent = o[i][1]; Q.tuned = false; Q.scale = 1; invalidate(false); }
  else if (a === 'mute') { b.textContent = Snd.toggle() ? '声音 开' : '声音 关'; }
  else if (a === 'tray') openTray(false);
  else if (a === 'trayref') openTray(true);
  else if (a === 'trayback') openTray(false);
  else if (a === 'isel') { if (ev.target.closest('button')) return; V.sel = V.ref ? b.dataset.i : +b.dataset.i; focusItem(); renderSide(); invalidate(false); }
  else if (a === 'isell') { const it = W.items.find(x => x.id === +b.dataset.i); C.sellItem(W, it, b.dataset.how); Snd.coin(); save(); const s = W.stones.find(x => x.id === it.stone); if (s && s.closed && !trayItems().length) { tab = 'ledger'; view('review', s, null); } else openTray(false); }
  else if (a === 'iall') { for (const it of trayItems()) C.sellItem(W, it, b.dataset.how); save(); tab = 'ledger'; view(null, null, null); }
  else if (a === 'review') { view('review', W.stones.find(x => x.id === +b.dataset.s), null); }
  else if (a === 'rake') { V.torch.rake = !V.torch.rake; renderTools(); invalidate(false); }
  else if (a === 'sawno') { V.sawPlan = null; showLasso(null); $('#sawbox').hidden = true; V.note = ''; renderTools(); }
  else if (a === 'sawsmart') { smartSaw(); }
  else if (a === 'pshelf') { const r = C.pieceShelf(W, V.rec, V.piece); V.note = r.ok ? '已摆进铺面，散客会按零售价来买。' : r.msg; save(); renderAll(); }
  else if (a === 'pkeep') { const s = V.rec, p = V.piece; C.pieceKeep(W, s, p, true); save(); V.note = '已收进藏品柜。'; if (s.closed) { tab = 'ledger'; view('review', s, null); } else renderAll(); }
  else if (a === 'pback') { const s = W.stones.find(x => x.id === +b.dataset.s), p = s.pieces.find(x => x.id === +b.dataset.p); if (p.kept) C.pieceKeep(W, s, p, false); p.shelf = false; save(); openTray(false, V.cab); }
  else if (a === 'pview') { const s = W.stones.find(x => x.id === +b.dataset.s), p = s.pieces.find(x => x.id === +b.dataset.p); tab = 'mine'; view('own', s, p); if (!s.last[p.id]) refreshQuote(s, p); renderAll(); }
  else if (a === 'sawgo') { const s = V.rec, p = V.piece, r = C.saw(W, s, p, V.sawPlan.planes); V.sawPlan = null; showLasso(null); $('#sawbox').hidden = true;
    if (!r.ok) { V.note = r.msg; renderTools(); return; }
    Snd.saw(); refreshQuote(s, p, false); refreshQuote(s, r.piece, true); save(); V.note = `取出 ${r.piece.name}，锯工 ${fmt(r.cost)}。它已放进料头盘，可单独查看、出售或送去做件。`; tab = 'mine'; frame(); renderAll(); }
  else if (a === 'hold') { holdItem(V.ref ? b.dataset.i : +b.dataset.i); }
  else if (a === 'unhold') { openTray(V.ref, V.cab); }
  else if (a === 'back') { V.back = !V.back; renderTools(); invalidate(false); }
  else if (a === 'tool') { const r = C.buyTool(W, b.dataset.k); V.note = r.msg; if (r.ok) Snd.coin(); save(); renderAll(); }
  else if (a === 'appr') { const rec = V.rec, r = C.appraise(W, rec); if (!r.ok) V.msg = r.msg; else Snd.tap(); save(); renderTop(); renderSide(); }
  else if (a === 'lbody') { V.lampBody = !V.lampBody; renderDock(); invalidate(false); }
  else if (a === 'tpower') { const T = V.torch; if (T.on && T.p) T.on = false; else if (T.p) T.on = true; Snd.tap(); renderDock(); invalidate(false); }
  else if (a === 'tcolor') { V.torch.yellow = !V.torch.yellow; Snd.tap(); renderDock(); invalidate(false); }
  else if (a === 'tdim') { V.torch.dim = !V.torch.dim; Snd.tap(); renderDock(); invalidate(false); }
  else if (a === 'partner') { V.partner = !V.partner; renderSide(); }
  else if (a === 'cabgo') { const s = V.rec, p = V.piece, g = C.cabGame(W, s, p); V.cab_ = { g, k: 0, hurt: false, done: false, key: s.id + ':' + p.id }; renderCab(); $('#cabgame').hidden = false; }
  else if (a === 'cabup') { const c = V.cab_, i = c.k; if (c.g.rolls[i] < c.g.risks[i]) { c.hurt = true; c.done = true; Snd.lose(); } else { c.k++; Snd.grind(); if (c.k >= c.g.max) c.done = true; } renderCab(); }
  else if (a === 'cabstop') { V.cab_.done = true; renderCab(); }
  else if (a === 'cabok') { const c = V.cab_; V.wk.cabMult = c.g.mults[c.k] / c.g.mults[Math.min(c.g.max, 2)] * (c.hurt ? 0.6 : 1); V.wk.cabKey = c.key; V.wk.cabText = `${c.g.sizes[c.k]} mm${c.hurt ? '（磨伤了）' : ''}`; $('#cabgame').hidden = true; renderSide(); }
  else if (a === 'menu') { $('#hmenu').classList.toggle('open'); }
  else if (a === 'skiptut') { W.flags.tut = true; save(); renderAll(); }
  else if (a === 'storyok') { $('#story').hidden = true; }
  else if (a === 'storyshow') { const ch = C.CHAPTERS[W.chapter]; $('#storybody').innerHTML = `<h2>${ch.title}</h2><p>${esc(ch.story)}</p><ul>${ch.goals.map(g => `<li>${C.goalDone(W, g[0]) ? '✔ ' : ''}${g[1]}</li>`).join('')}</ul><button data-act="storyok" class="pri">知道了</button>`; $('#story').hidden = false; }
  else if (a === 'debt') { const r = C.payDebt(W); V.note = r.msg; if (r.ok) Snd.coin(); save(); renderAll(); }
  else if (a === 'startgo') { $('#start').hidden = true; Snd.tap(); renderAll(); }
  else if (a === 'startnew') { C.volCache.clear(); thumbs.clear(); qcache.clear(); loaded = null; W = C.newWorld((Date.now() ^ (Math.random() * 1e9)) >>> 0); save(); tab = 'market'; $('#start').hidden = true; view('market', W.market.find(L => !L.sold && !L.fake) || W.market[0], null); const ch = C.CHAPTERS[0]; $('#storybody').innerHTML = `<h2>${ch.title}</h2><p>${esc(ch.story)}</p><ul>${ch.goals.map(g => `<li>${g[1]}</li>`).join('')}</ul><button data-act="storyok" class="pri">进夜市</button>`; $('#story').hidden = false; }
  else if (a === 'starthelp') { $('#start').hidden = true; $('#help').hidden = false; showPane('play'); renderAll(); }
  else if (a === 'home') { showStart(); }
  else if (a === 'codego') { const c = $('#codeIn').value; if (codeOk(c)) { try { localStorage.setItem('jade-license', c); } catch (e) { } $('#paywall').hidden = true; Snd.win(); V.note = '激活成功，谢谢支持。'; showStart(); } else { $('#codeMsg').textContent = '这个激活码不对。检查一下有没有输错，字母不分大小写。'; } }
  else if (a === 'codeopen') { $('#codeMsg').textContent = ''; $('#paywall').hidden = false; }
  else if (a === 'codeclose') { $('#paywall').hidden = true; }
  else if (a === 'npcnext') { V.npcI = (V.npcI || 0) + 1; V.msg = ''; Snd.tap(); renderNpc(); }
  else if (a === 'callout') { const r = C.callOut(W, V.rec); V.msg = r.msg; if (r.ok) Snd.win(); else Snd.lose(); save(); renderTop(); renderSide(); renderNpc(); }
  else if (a === 'shopup') { const r = C.upgradeShop(W); V.note = r.msg; if (r.ok) Snd.coin(); save(); renderAll(); }
  else if (a === 'shelf') { const r = C.toShelf(W, W.items.find(x => x.id === +b.dataset.i)); if (!r.ok) { V.note = r.msg; renderTools(); } save(); openTray(false, false); }
  else if (a === 'unshelf') { W.items.find(x => x.id === +b.dataset.i).state = 'ready'; save(); openTray(false, 'shelf'); }
  else if (a === 'cab2') openTray(false, 'shelf');
  else if (a === 'toff') { V.torch.on = false; renderTools(); invalidate(false); }
  else if (a === 'room') { if (b.dataset.moved) { delete b.dataset.moved; return; } V.room = !V.room; if (!V.room && V.torch.on) flag('dark'); Snd.tap(); renderTools(); renderDock(); invalidate(false); }
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
      let betMsg = ''; if (V.bet) { const stake = Math.min(W.cash, Math.max(200, Math.round(before * 0.05 / 10) * 10)), win = (V.bet === 'up' && d >= 3) || (V.bet === 'down' && d <= -3), push = Math.abs(d) < 3; if (!push) { W.cash += win ? stake : -stake; W.log.push({ day: W.day, t: `和行家赌一刀（赌${V.bet === 'up' ? '涨' : '垮'}）`, amt: win ? stake : -stake }); } betMsg = push ? '平开，赌注不算。' : win ? `赌对了，赢了行家 ${fmt(stake)}。` : `赌错了，输给行家 ${fmt(stake)}。`; V.bet = ''; save(); renderTop(); }
      const up = d >= 3, down = d <= -3; if (up) { Snd.win(); C.achieve(W, 'cutup', '第一刀切涨'); } else if (down) Snd.lose(); else Snd.tap();
      rv.className = up ? 'up' : down ? 'down' : 'flat';
      rv.innerHTML = `<h2>${up ? '切涨了' : down ? '切垮了' : '平开'}</h2><p class="big">${d >= 0 ? '+' : ''}${d.toFixed(0)}%</p><p>账面 ${fmt(before)} → ${fmt(after)}</p>${why.map(x => `<p class="why2">${esc(x)}</p>`).join('')}${betMsg ? `<p class="say">${betMsg}</p>` : ''}<button data-act="rvok" class="pri">继续</button>`;
      V.note = `切工 ${fmt(r.cost)}。分出的 ${r.piece.name} 在右侧，可单独查看、再切、出售或送去做件。`; renderTools();
    }, 1150);
  }
  else if (a === 'rvok') { $('#reveal').hidden = true; }
  else if (a === 'next') { if (!licensed() && W.day >= CFG.trialDays) { $('#codeMsg').textContent = `试玩到第 ${CFG.trialDays} 天为止。输入激活码后可以接着这个存档一直玩下去。`; $('#paywall').hidden = false; return; } const n = C.nextDay(W); qcache.clear(); for (const s of W.stones) if (!s.closed) for (const p of s.pieces) if (!p.sold && C.volCache.get(s.seed)) refreshQuote(s, p, true); save(); const fresh = W.items.some(i => i.state === 'ready'); tab = 'market'; view(null, null, null); V.note = `第 ${W.day} 天。${n.join('，')}。货源已更新，昨天的报价作废。`; renderTools(); if (fresh && n.some(x => x.includes('做好了'))) { openTray(false); V.note = n.filter(x => x.includes('做好了')).join('；'); renderTools(); } }
  else if (a === 'restart') { $('#confirm').hidden = false; }
  else if (a === 'no') { $('#confirm').hidden = true; }
  else if (a === 'yes') { $('#confirm').hidden = true; C.volCache.clear(); thumbs.clear(); qcache.clear(); loaded = null; W = C.newWorld((Date.now() ^ (Math.random() * 1e9)) >>> 0); save(); tab = 'market'; view(null, null, null); }
  else if (a === 'help') { $('#help').hidden = !$('#help').hidden; if (!$('#help').hidden) showPane('play'); }
  else if (a === 'pane') showPane(b.dataset.k);
  else if (a === 'gotoref') { $('#help').hidden = true; openTray(true); }
});
document.addEventListener('input', ev => {
  if (ev.target.id === 'cutT') { V.cutT = +ev.target.value; $('#cutV').textContent = V.cutT; if (V.cut && V.cut.fromView) { V.cut.d = V.cut.base - V.cutT; V.cut.pv = C.cutPreview(V.rec, V.piece, V.cut.n, V.cut.d); renderTools(); } invalidate(true); }
  if (ev.target.id === 'gW' || ev.target.id === 'gC' || ev.target.id === 'gK') { const s = V.rec, w = $('#gW').value; s.guess = w === '' ? null : { water: +w, color: $('#gC').value, crack: $('#gK').value }; save(); if (s.guess) flag('guess'); }
  if (ev.target.id === 'wkRoute' || ev.target.id === 'wkMaster' || ev.target.id === 'wkTheme') { V.wk[{ wkRoute: 'route', wkMaster: 'master', wkTheme: 'theme' }[ev.target.id]] = ev.target.value; renderSide(); }
  if (ev.target.id === 'tTilt' || ev.target.id === 'tAz' || ev.target.id === 'tH') { V.torch.tilt = +$('#tTilt').value; V.torch.az = +$('#tAz').value; V.torch.h = +$('#tH').value; $('#tTiltV').textContent = V.torch.tilt; $('#tHV').textContent = V.torch.h; invalidate(true); }
  if (ev.target.id === 'sawD' && V.sawPlan) { V.sawPlan.depth = +ev.target.value; sawRebuild(); const el = $('#sawD'); if (el) el.focus(); }
  if (ev.target.id === 'tDist') { V.torch.h = +ev.target.value; $('#tDistV').textContent = V.torch.h; invalidate(true); }
  if (ev.target.id === 'betSel') V.bet = ev.target.value;
  if (ev.target.id === 'sec') { V.section = +ev.target.value; invalidate(true); }
});
const ptrs = new Map(); let drag = null, lastCarve = null, strokeCost = 0; const lineEl = $('#cutline');
function torchAt(ev) { const r = rayAt(ev.clientX, ev.clientY), h = C.pick(V.e.vol, curPiece(), r.ro, r.rd, V.mode === 'review'); if (h) { flag('torch'); const T = V.torch; T.on = true; T.p = h.p; T.n = h.n; if (!T.dir || T.dir[0] * h.n[0] + T.dir[1] * h.n[1] + T.dir[2] * h.n[2] < 0.15) { T.dir = h.n; } } return h; }
function carveAt(ev) {
  const r = rayAt(ev.clientX, ev.clientY), h = C.pick(V.e.vol, V.piece, r.ro, r.rd); if (!h) return;
  if (lastCarve && Math.hypot(h.p[0] - lastCarve[0], h.p[1] - lastCarve[1], h.p[2] - lastCarve[2]) < 1.2) return;
  lastCarve = h.p; Snd.grind(); const res = C.grind(W, V.rec, V.piece, h.p, h.n, V.burr); strokeCost += res.removed * C.ECON.grind;
  uploadBox(V.e.vol, res.box); invalidate(true);
}
function showLine(d) { const r = canvas.getBoundingClientRect(); if (d) lineEl.removeAttribute('hidden'); else lineEl.setAttribute('hidden', ''); if (d) { lineEl.setAttribute('x1', d.x0 - r.left); lineEl.setAttribute('y1', d.y0 - r.top); lineEl.setAttribute('x2', d.x - r.left); lineEl.setAttribute('y2', d.y - r.top); } }
/* 手电是场景里的实物：从左下角的手电上拖出来放到石头上；抓灯头挪位置，抓筒尾转角度、拉远 */
function proj(wp) { const r = canvas.getBoundingClientRect(), b = camBasis(), v = [wp[0] - b.pos[0], wp[1] - b.pos[1], wp[2] - b.pos[2]], z = v[0] * b.f[0] + v[1] * b.f[1] + v[2] * b.f[2]; return [r.left + r.width / 2 + (v[0] * b.r[0] + v[1] * b.r[1] + v[2] * b.r[2]) / z / TANF * r.height / 2, r.top + r.height / 2 - (v[0] * b.up[0] + v[1] * b.up[1] + v[2] * b.up[2]) / z / TANF * r.height / 2]; }
function torchPts() { const T = V.torch, d = T.dir || T.n, h = (T.h || 0) + 2.5; return { head: [T.p[0] + d[0] * h, T.p[1] + d[1] * h, T.p[2] + d[2] * h], tail: [T.p[0] + d[0] * (h + 42), T.p[1] + d[1] * (h + 42), T.p[2] + d[2] * (h + 42)] }; }
function torchTail(ev) { const T = V.torch, r = rayAt(ev.clientX, ev.clientY), b = camBasis(), den = r.rd[0] * b.f[0] + r.rd[1] * b.f[1] + r.rd[2] * b.f[2];
  const tt = ((T.p[0] - r.ro[0]) * b.f[0] + (T.p[1] - r.ro[1]) * b.f[1] + (T.p[2] - r.ro[2]) * b.f[2]) / den, q = [r.ro[0] + r.rd[0] * tt, r.ro[1] + r.rd[1] * tt, r.ro[2] + r.rd[2] * tt];
  let v = [q[0] - T.p[0], q[1] - T.p[1], q[2] - T.p[2]]; const len = Math.hypot(v[0], v[1], v[2]) || 1; v = v.map(x => x / len); const dn = v[0] * T.n[0] + v[1] * T.n[1] + v[2] * T.n[2];
  if (dn < 0.09) { v = v.map((x, i) => x + T.n[i] * (0.09 - dn)); const l2 = Math.hypot(v[0], v[1], v[2]); v = v.map(x => x / l2); }
  if (drag && drag.kind === 'tmid') { const d0 = T.dir || T.n, along = (q[0] - T.p[0]) * d0[0] + (q[1] - T.p[1]) * d0[1] + (q[2] - T.p[2]) * d0[2]; T.h = Math.max(0, Math.min(90, along - 23.5)); } // 抓筒身中段：沿筒身拉远拉近
  else { const g = gyroBasis(), d0 = T.dir || T.n, cT0 = Math.max(-1, Math.min(1, d0[0] * T.n[0] + d0[1] * T.n[1] + d0[2] * T.n[2])), rr = Math.acos(cT0) / 1.45, sx = d0[0] * g.tx[0] + d0[1] * g.tx[1] + d0[2] * g.tx[2], sy = d0[0] * g.ty[0] + d0[1] * g.ty[1] + d0[2] * g.ty[2], l = Math.hypot(sx, sy) || 1;
    let px = sx / l * rr + (ev.clientX - drag.lx) / 150, py = sy / l * rr - (ev.clientY - drag.ly) / 150; const pl = Math.hypot(px, py); if (pl > 1) { px /= pl; py /= pl; } drag.lx = ev.clientX; drag.ly = ev.clientY; gyroSet(px, py); return; } // 抓筒尾：往下拖向自己倒，往上拖向对面倒，左右拖左右倒
  invalidate(true); renderDock(); }
function gyroBasis() { const T = V.torch, n = T.n, b = camBasis(), pr = v => { const d = v[0] * n[0] + v[1] * n[1] + v[2] * n[2]; let o = [v[0] - n[0] * d, v[1] - n[1] * d, v[2] - n[2] * d]; const l = Math.hypot(o[0], o[1], o[2]) || 1; return o.map(x => x / l); }; const tx = pr(b.r); let ty = [n[1] * tx[2] - n[2] * tx[1], n[2] * tx[0] - n[0] * tx[2], n[0] * tx[1] - n[1] * tx[0]]; if (ty[0] * b.up[0] + ty[1] * b.up[1] + ty[2] * b.up[2] < 0) ty = ty.map(x => -x); return { tx, ty }; }
function gyroSet(px, py) { const T = V.torch; if (!T.p) return; const g = gyroBasis(), r = Math.min(1, Math.hypot(px, py)), tilt = r * 1.45, s = Math.sin(tilt), c = Math.cos(tilt), k = r > 1e-3 ? 1 / Math.hypot(px, py) : 0;
  T.dir = [0, 1, 2].map(i => T.n[i] * c + (g.tx[i] * px + g.ty[i] * py) * k * s); invalidate(true); renderDock(); }
function gyroPad(ev) { const r = $('#gyro').getBoundingClientRect(); gyroSet(((ev.clientX - r.left) / r.width - 0.5) * 2, -((ev.clientY - r.top) / r.height - 0.5) * 2); }
function renderDock() { const d = $('#torchdock'), T = V.torch, show = !!V.e && V.mode !== 'tray'; d.hidden = !show; $('#lightsw').hidden = !show; if (!show) return;
  d.classList.toggle('lit', T.on && !!T.p); $('#tkPower').setAttribute('aria-pressed', T.on && !!T.p); $('#tkColor').setAttribute('aria-pressed', !!T.yellow); $('#tkColor').textContent = T.yellow ? '黄光' : '白光'; $('#tkDim').setAttribute('aria-pressed', !T.dim); $('#tkDim').textContent = T.dim ? '弱光' : '强光'; $('#tkBody').setAttribute('aria-pressed', V.lampBody);
  $('#tkName').textContent = C.SHOP.torch.levels[W.tools.torch - 1]; $('#tkTip').textContent = T.on && T.p ? '点石头换位置；抓筒尾上下左右拖来倾斜；抓筒身或滑杆拉远' : '按住拖到石头上'; $('#lightsw').setAttribute('aria-pressed', V.room);
  const placed = T.on && !!T.p; $('#gyrowrap').hidden = !placed; const fl = $('#tfloat'); fl.hidden = !placed || !V.lampBody;
  if (placed) { const g = gyroBasis(), d = T.dir || T.n, cT = Math.max(-1, Math.min(1, d[0] * T.n[0] + d[1] * T.n[1] + d[2] * T.n[2])), rr = Math.acos(cT) / 1.45, sx = d[0] * g.tx[0] + d[1] * g.tx[1] + d[2] * g.tx[2], sy = d[0] * g.ty[0] + d[1] * g.ty[1] + d[2] * g.ty[2], l = Math.hypot(sx, sy) || 1; $('#gyrodot').style.left = (50 + sx / l * rr * 46) + '%'; $('#gyrodot').style.top = (50 - sy / l * rr * 46) + '%'; $('#tDist').value = T.h || 0; $('#tDistV').textContent = Math.round(T.h || 0);
    const sr = canvas.getBoundingClientRect(), tp = proj(torchPts().tail); fl.style.left = Math.max(4, Math.min(sr.width - 70, tp[0] - sr.left + 10)) + 'px'; fl.style.top = Math.max(4, Math.min(sr.height - 30, tp[1] - sr.top - 12)) + 'px'; $('#tfP').setAttribute('aria-pressed', true); $('#tfC').textContent = T.yellow ? '黄' : '白'; } }
function renderCab() { const c = V.cab_, g = c.g, el = $('#cabbody'), nxt = c.k < g.max ? g.risks[c.k] : 0;
  let h = `<p>师傅把色最浓的那块粘在杆上，先磨了个 ${g.sizes[0]} 毫米的小蛋面。${g.hint}</p><div class="cabrow">${g.sizes.slice(0, g.max + 1).map((s, i) => `<span class="${i === c.k ? 'on' : i < c.k ? 'past' : ''}"><i style="width:${s * 2.2}px;height:${s * 1.8}px"></i>${s} mm<small>×${g.mults[i].toFixed(1)}</small></span>`).join('')}</div>`;
  if (c.hurt) h += `<p class="say">放大的时候磨出了一道裂。只能退回 ${g.sizes[c.k]} 毫米，品相也打了折扣。</p>`;
  else if (c.done) h += `<p class="say">定在 ${g.sizes[c.k]} 毫米，干干净净。</p>`;
  else h += `<p>现在是 ${g.sizes[c.k]} 毫米。再放大一号，价值大约涨到 ${(g.mults[c.k + 1] / g.mults[c.k]).toFixed(1)} 倍；师傅估计有 ${Math.round(nxt * 100)}% 的可能磨出裂或脏。</p>`;
  h += c.done ? `<button data-act="cabok" class="pri">就按这个做</button>` : `<div class="row"><button data-act="cabup">再放大一号</button><button data-act="cabstop" class="pri">收手，就这么大</button></div>`;
  el.innerHTML = h; }
function showLasso(pts) { const el = $('#lasso'), r = canvas.getBoundingClientRect(); if (pts) el.removeAttribute('hidden'); else el.setAttribute('hidden', ''); if (pts) el.setAttribute('points', pts.map(p => (p[0] - r.left) + ',' + (p[1] - r.top)).join(' ')); }
function planSaw(pts) {
  // 凸包，再削到最多六个角
  const P = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]), cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]), lo = [], up = [];
  for (const p of P) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
  for (let i = P.length - 1; i >= 0; i--) { const p = P[i]; while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
  let hull = lo.slice(0, -1).concat(up.slice(0, -1));
  while (hull.length > 6) { let bi = 0, ba = 1e18; for (let i = 0; i < hull.length; i++) { const a = Math.abs(cr(hull[(i + hull.length - 1) % hull.length], hull[i], hull[(i + 1) % hull.length])); if (a < ba) { ba = a; bi = i; } } hull.splice(bi, 1); }
  if (hull.length < 3 || Math.abs(hull.reduce((s, p, i) => s + cr([0, 0], p, hull[(i + 1) % hull.length]), 0)) < 600) { showLasso(null); V.note = '圈得太小了。'; renderTools(); return; }
  const cx = hull.reduce((s, p) => s + p[0], 0) / hull.length, cy = hull.reduce((s, p) => s + p[1], 0) / hull.length, rc = rayAt(cx, cy), planes = [];
  for (let i = 0; i < hull.length; i++) { const r1 = rayAt(hull[i][0], hull[i][1]), r2 = rayAt(hull[(i + 1) % hull.length][0], hull[(i + 1) % hull.length][1]);
    let n = [r1.rd[1] * r2.rd[2] - r1.rd[2] * r2.rd[1], r1.rd[2] * r2.rd[0] - r1.rd[0] * r2.rd[2], r1.rd[0] * r2.rd[1] - r1.rd[1] * r2.rd[0]]; const l = Math.hypot(n[0], n[1], n[2]); n = n.map(v => v / l);
    if (n[0] * rc.rd[0] + n[1] * rc.rd[1] + n[2] * rc.rd[2] > 0) n = n.map(v => -v);
    planes.push([n[0], n[1], n[2], n[0] * r1.ro[0] + n[1] * r1.ro[1] + n[2] * r1.ro[2]]); }
  showLasso(null);
  // 取料深度从看得见的表面往里量：取圈里离眼睛最近的那一点作基准
  const f = camBasis().f; let d0 = 1e9; for (const q of hull.concat([[cx, cy]])) { const rr = rayAt(q[0], q[1]), hh = C.pick(V.e.vol, V.piece, rr.ro, rr.rd); if (hh) d0 = Math.min(d0, hh.p[0] * f[0] + hh.p[1] * f[1] + hh.p[2] * f[2]); }
  if (d0 > 1e8) { V.note = '圈里没有料。'; renderTools(); return; }
  V.sawPlan = { side: planes, f, d0, depth: V.sawDepth || 18 }; sawRebuild();
  renderTools();
}
function sawRebuild() { const P = V.sawPlan, back = [P.f[0], P.f[1], P.f[2], P.d0 + P.depth]; P.planes = P.side.concat([back]); P.box = P.planes.concat([[-P.f[0], -P.f[1], -P.f[2], -(P.d0 - 1.5)]]); P.pv = C.sawPreview(V.rec, V.piece, P.planes); V.sawDepth = P.depth;
  V.note = '橙色的框就是小锯要取走的范围，还没有锯。可以右键拖动转过去看它伸进去多深，调好深度再确认。';
  const sb = $('#sawbox'); sb.hidden = false;
  sb.innerHTML = `<span>取出约 <b>${Math.round(P.pv.a)} g</b>，剩下约 ${Math.round(P.pv.b)} g</span><label for="sawD">取料深度 <b id="sawDV">${P.depth}</b> mm</label><input id="sawD" type="range" min="3" max="80" step="1" value="${P.depth}"><span class="dim">锯工 ${fmt(P.pv.cost)}</span><div class="row"><button data-act="sawno">重画</button><button data-act="sawgo" class="pri" ${P.pv.a < 3 ? 'disabled' : ''}>确认下锯</button></div>`;
  renderTools(); invalidate(false); }
// 智能圈色：在当前看到的露肉面上找最大的一片色，自动把线画好
function smartSaw() {
  const r = canvas.getBoundingClientRect(), vol = V.e.vol, m = vol.mat, g = vol.geom, N = 46, cw = r.width / N, ch = r.height / N, val = new Float32Array(N * N); let mx = 0;
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) { const ry = rayAt(r.left + (i + 0.5) * cw, r.top + (j + 0.5) * ch), h = C.pick(vol, V.piece, ry.ro, ry.rd); if (!h) continue;
    const q = [h.p[0] - h.n[0] * 1.2, h.p[1] - h.n[1] * 1.2, h.p[2] - h.n[2] * 1.2], ii = Math.max(0, Math.min(vol.nx - 1, Math.floor((q[0] + vol.hx) / vol.vx))), jj = Math.max(0, Math.min(vol.ny - 1, Math.floor((q[1] + vol.hy) / vol.vx))), kk = Math.max(0, Math.min(vol.nz - 1, Math.floor((q[2] + vol.hz) / vol.vx))), b = (ii + vol.nx * (jj + vol.ny * kk)) * 4;
    if (!(-g[b] > g[b + 2])) continue; const c = m[b] / 255; val[i + N * j] = c; if (c > mx) mx = c; }
  const thr = Math.max(0.22, mx * 0.55), seen = new Uint8Array(N * N); let best = [];
  for (let s0 = 0; s0 < N * N; s0++) { if (seen[s0] || val[s0] < thr) continue; const comp = [], st = [s0]; seen[s0] = 1; while (st.length) { const c = st.pop(); comp.push(c); const i = c % N, j = (c / N) | 0; for (const [di, dj] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) { const a = i + di, b2 = j + dj; if (a < 0 || b2 < 0 || a >= N || b2 >= N) continue; const k = a + N * b2; if (!seen[k] && val[k] >= thr) { seen[k] = 1; st.push(k); } } } if (comp.length > best.length) best = comp; }
  if (best.length < 4) { V.note = '这个面上没找到成片的色。把带色的切面或窗口转到正对自己再试。'; renderTools(); return; }
  const pts = []; for (const c of best) { const x = r.left + (c % N + 0.5) * cw, y = r.top + (((c / N) | 0) + 0.5) * ch; pts.push([x - cw * 0.7, y - ch * 0.7], [x + cw * 0.7, y - ch * 0.7], [x - cw * 0.7, y + ch * 0.7], [x + cw * 0.7, y + ch * 0.7]); }
  planSaw(pts);
}
function doPeel(pts) {
  if (pts.length < 6) return;
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9; for (const p of pts) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); }
  if (x1 - x0 < 12 || y1 - y0 < 12) return;
  const inside = (x, y) => { let c = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const a = pts[i], b = pts[j]; if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) c = !c; } return c; };
  const step = Math.max(5, Math.sqrt((x1 - x0) * (y1 - y0) / 900)), hits = [];
  for (let y = y0; y <= y1; y += step) for (let x = x0; x <= x1; x += step) if (inside(x, y)) { const r = rayAt(x, y), h = C.pick(V.e.vol, V.piece, r.ro, r.rd); if (h && !h.flat) hits.push(h); }
  let cost = 0, n = 0; for (const h of hits) { const res = C.peelAt(W, V.rec, V.piece, h.p, h.n); if (res) { cost += res.cost; n++; } }
  if (!n) { V.note = '圈里没有可切的皮。'; renderTools(); return; }
  flag('open'); loaded = null; Snd.saw(); refreshQuote(V.rec, V.piece, true); save(); V.note = `切皮完成，花费 ${Math.max(1, Math.round(cost))} 元。`; renderAll();
}
canvas.addEventListener('contextmenu', e => e.preventDefault());
{ const sw = $('#lightsw'); let mv = null; try { const s = JSON.parse(localStorage.getItem('jade-lightsw') || 'null'); if (s) { sw.style.left = s[0] + 'px'; sw.style.top = s[1] + 'px'; sw.style.right = 'auto'; } } catch (e) { }
  sw.addEventListener('pointerdown', ev => { sw.setPointerCapture(ev.pointerId); const r = sw.getBoundingClientRect(); mv = { x: ev.clientX, y: ev.clientY, ox: ev.clientX - r.left, oy: ev.clientY - r.top, moved: false }; });
  sw.addEventListener('pointermove', ev => { if (!mv) return; if (!mv.moved && Math.hypot(ev.clientX - mv.x, ev.clientY - mv.y) < 6) return; mv.moved = true; const st = $('#stage').getBoundingClientRect(), x = Math.max(4, Math.min(st.width - 40, ev.clientX - st.left - mv.ox)), y = Math.max(4, Math.min(st.height - 60, ev.clientY - st.top - mv.oy)); sw.style.left = x + 'px'; sw.style.top = y + 'px'; sw.style.right = 'auto'; });
  sw.addEventListener('pointerup', () => { if (mv && mv.moved) { sw.dataset.moved = '1'; try { localStorage.setItem('jade-lightsw', JSON.stringify([parseFloat(sw.style.left), parseFloat(sw.style.top)])); } catch (e) { } } mv = null; }); }
$('#gyro').addEventListener('pointerdown', ev => { ev.stopPropagation(); ev.preventDefault(); $('#gyro').setPointerCapture(ev.pointerId); gyroPad(ev); });
$('#gyro').addEventListener('pointermove', ev => { if (ev.buttons || ev.pointerType !== 'mouse') gyroPad(ev); });
$('#gyro').addEventListener('pointerup', () => invalidate(false));
$('#gyro').addEventListener('dblclick', () => { gyroSet(0, 0); invalidate(false); });
$('#torchdock').addEventListener('pointerdown', ev => { if (ev.target.closest('button') || ev.target.closest('#gyrowrap') || !V.e) return; ev.preventDefault(); canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]); drag = { kind: 'torch' }; V.torch.h = 0; V.torch.dir = null; });
canvas.addEventListener('pointerdown', ev => {
  if (V.e && V.mode !== 'tray' && V.torch.on && V.torch.p && ev.button !== 2) { const tp = torchPts(), a = proj(tp.tail), b2 = proj(tp.head), mid = [(a[0] + b2[0]) / 2, (a[1] + b2[1]) / 2], dt = Math.hypot(ev.clientX - a[0], ev.clientY - a[1]), dh = Math.hypot(ev.clientX - b2[0], ev.clientY - b2[1]), dm = Math.hypot(ev.clientX - mid[0], ev.clientY - mid[1]), mn = Math.min(dt, dh, dm);
    if (mn < 24) { canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]); drag = { kind: mn === dt ? 'ttail' : mn === dh ? 'torch' : 'tmid', lx: ev.clientX, ly: ev.clientY }; return; } }
  if (V.mode === 'tray') { canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]); drag = { kind: 'orbit', x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY, tray: true }; return; }
  if (!V.e) return; canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]);
  if (ptrs.size === 2) { showLine(null); const a = [...ptrs.values()]; drag = { kind: 'pinch', d: Math.hypot(a[0][0] - a[1][0], a[0][1] - a[1][1]), x: (a[0][0] + a[1][0]) / 2, y: (a[0][1] + a[1][1]) / 2 }; return; }
  const own = V.mode === 'own' && V.piece && !V.piece.sold;
  const orbit = ev.button === 2 || V.tool === 'rotate' || ev.shiftKey || ((V.tool === 'grind' || V.tool === 'cut' || V.tool === 'peel' || V.tool === 'saw') && !own);
  if (orbit) drag = { kind: 'orbit', x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY, click: ev.button !== 2 };
  else if (V.tool === 'torch') { drag = { kind: 'torch' }; torchAt(ev); renderTools(); invalidate(true); }
  else if (V.tool === 'loupe') { drag = { kind: 'loupe' }; V.lens = { x: ev.clientX, y: ev.clientY }; invalidate(true); }
  else if (V.tool === 'grind') { drag = { kind: 'grind' }; lastCarve = null; strokeCost = 0; carveAt(ev); }
  else if (V.tool === 'saw' && V.sawPlan) { drag = { kind: 'orbit', x: ev.clientX, y: ev.clientY }; }
  else if (V.tool === 'peel' || V.tool === 'saw') { drag = { kind: 'lasso', saw: V.tool === 'saw', pts: [[ev.clientX, ev.clientY]] }; V.sawPlan = null; }
  else if (V.tool === 'cut') { drag = { kind: 'line', x0: ev.clientX, y0: ev.clientY, x: ev.clientX, y: ev.clientY }; }
});
canvas.addEventListener('pointermove', ev => {
  if (!V.e && V.mode !== 'tray') return;
  if (ptrs.has(ev.pointerId)) ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]);
  if (!drag) { if (V.tool === 'loupe' && ev.pointerType === 'mouse') { V.lens = { x: ev.clientX, y: ev.clientY }; invalidate(true); } return; }
  if (drag.kind === 'pinch' && ptrs.size === 2) { const a = [...ptrs.values()], d = Math.hypot(a[0][0] - a[1][0], a[0][1] - a[1][1]), x = (a[0][0] + a[1][0]) / 2, y = (a[0][1] + a[1][1]) / 2; cam.dist = Math.min(1500, Math.max(40, cam.dist * drag.d / Math.max(1, d))); cam.yaw -= (x - drag.x) * 0.008; cam.pitch = Math.max(-1.5, Math.min(1.5, cam.pitch + (y - drag.y) * 0.008)); drag.d = d; drag.x = x; drag.y = y; invalidate(true); }
  else if (drag.kind === 'orbit') { cam.yaw -= (ev.clientX - drag.x) * 0.008; cam.pitch = Math.max(V.mode === 'tray' && V.hold == null ? 0.12 : -1.5, Math.min(1.5, cam.pitch + (ev.clientY - drag.y) * 0.008)); drag.x = ev.clientX; drag.y = ev.clientY; if (V.cut && V.cut.fromView) { V.cut = null; renderTools(); } invalidate(true); }
  else if (drag.kind === 'torch') { torchAt(ev); invalidate(true); }
  else if (drag.kind === 'ttail' || drag.kind === 'tmid') torchTail(ev);
  else if (drag.kind === 'loupe') { V.lens = { x: ev.clientX, y: ev.clientY }; invalidate(true); }
  else if (drag.kind === 'grind') carveAt(ev);
  else if (drag.kind === 'line') { drag.x = ev.clientX; drag.y = ev.clientY; showLine(drag); }
  else if (drag.kind === 'lasso') { const l = drag.pts[drag.pts.length - 1]; if (Math.hypot(ev.clientX - l[0], ev.clientY - l[1]) > 4) { drag.pts.push([ev.clientX, ev.clientY]); showLasso(drag.pts); } }
});
function endPtr(ev) {
  ptrs.delete(ev.pointerId); if (!drag) return;
  if (drag.tray && V.hold == null && Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < 6) { const it = pickTray(ev.clientX, ev.clientY); V.sel = it ? it.id : null; if (it) focusItem(); else { const lay = trayLayout(trayItems()); cam.t = [0, 6, 0]; cam.dist = Math.max(200, Math.max(lay.half[0], lay.half[1]) * 2.5); } renderSide(); invalidate(false); }
  if (drag.kind === 'orbit' && Math.hypot(ev.clientX - (drag.x0 || ev.clientX), ev.clientY - (drag.y0 || ev.clientY)) > 30) flag('orbit');
  if (drag.kind === 'grind') { flag('open'); const s = V.rec, p = V.piece; refreshQuote(s, p, true); V.note = `本次打磨花费 ${Math.max(1, Math.round(strokeCost))} 元。`; save(); renderAll(); }
  if (drag.kind === 'loupe' && ev.pointerType !== 'mouse') { V.lens = null; invalidate(false); }
  if (drag.kind === 'orbit' && drag.click && V.torch.on && V.torch.p && V.e && V.mode !== 'tray' && Math.hypot(ev.clientX - drag.x0, ev.clientY - drag.y0) < 5) { torchAt(ev); Snd.tap(); } // 手电亮着时，点一下石头就把灯挪过去
  if (drag.kind === 'torch' || drag.kind === 'ttail' || drag.kind === 'tmid' || drag.kind === 'orbit') { renderDock(); invalidate(false); }
  if (drag.kind === 'lasso') { if (drag.saw) planSaw(drag.pts); else { showLasso(null); doPeel(drag.pts); } }
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
window.JadeDebug = { torchScreen: () => { const t = torchPts(); return { tail: proj(t.tail), head: proj(t.head) }; }, V, cam, Q, render, invalidate, view, world: () => W, setWorld: w => { W = w; } };
if (!W.market || !W.market.length) C.enterScene(W, W.scene || '夜市地摊');
fillManual();
view('market', W.market.find(L => !L.sold) || null, null);
function showStart() { const st = $('#start'); st.hidden = false; $('#stCont').hidden = !hadSaveNow(); $('#stInfo').textContent = hadSaveNow() ? `存档：第 ${W.day} 天 · ${C.rankOf(W)} · 现金 ${fmt(W.cash)} · ${(C.CHAPTERS[W.chapter] || { title: '主线完成' }).title}` : '还没有存档'; $('#stLic').textContent = !CFG.license ? '' : licensed() ? '已激活' : `试玩版：可以玩到第 ${CFG.trialDays} 天`; $('#stCode').hidden = !CFG.license || licensed(); $('#buyText').textContent = CFG.buyText || ''; coachUpdate(); }
function hadSaveNow() { return !!load() && (W.day > 1 || W.stones.length > 0 || W.flags.tut); }
showStart();
})();
