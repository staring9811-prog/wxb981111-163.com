/* 翡翠博弈 · 界面与三维工作台 */
(function () {
'use strict';
const C = window.Core, $ = s => document.querySelector(s), fmt = C.fmt;
const SAVE_KEY = 'jade-save', OLD_KEYS = ['jade-bargain-web-v11', 'jade-bargain-web-v10', 'jade-bargain-web-v9'];
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
function tex3d(unit) { const t = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_3D, t); for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_3D, p, gl.LINEAR); if (unit === 1) gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR); for (const p of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R]) gl.texParameteri(gl.TEXTURE_3D, p, gl.CLAMP_TO_EDGE); return t; }
const tGeom = tex3d(0), tMat = tex3d(1);
gl.uniform1i(u('uGeom'), 0); gl.uniform1i(u('uMat'), 1);
gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
let loaded = null;
function upload(vol) {
  if (loaded === vol) return; loaded = vol;
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_3D, tGeom); gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGBA16F, vol.nx, vol.ny, vol.nz, 0, gl.RGBA, gl.FLOAT, vol.geom);
  gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_3D, tMat); gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGBA8, vol.nx, vol.ny, vol.nz, 0, gl.RGBA, gl.UNSIGNED_BYTE, vol.mat); gl.generateMipmap(gl.TEXTURE_3D);
}
function uploadBox(vol, b) {
  const w = b[1] - b[0] + 1, h = b[3] - b[2] + 1, d = b[5] - b[4] + 1, tmp = new Float32Array(w * h * d * 4); let o = 0;
  for (let k = b[4]; k <= b[5]; k++) for (let j = b[2]; j <= b[3]; j++) { const s = (b[0] + vol.nx * (j + vol.ny * k)) * 4; tmp.set(vol.geom.subarray(s, s + w * 4), o); o += w * 4; }
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_3D, tGeom); gl.texSubImage3D(gl.TEXTURE_3D, 0, b[0], b[2], b[4], w, h, d, gl.RGBA, gl.FLOAT, tmp);
}

/* ---------- 音效（合成，无素材） ---------- */
const Snd = (() => { let ac = null, on = true, amb = null; const ctx = () => { if (!ac) try { ac = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { } return ac; };
  function noise(d, f, q, g) { const a = ctx(); if (!a || !on) return; const n = Math.floor(a.sampleRate * d), b = a.createBuffer(1, n, a.sampleRate), ch = b.getChannelData(0); for (let i = 0; i < n; i++) ch[i] = Math.random() * 2 - 1; const s = a.createBufferSource(); s.buffer = b; const bp = a.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = f; bp.Q.value = q; const gn = a.createGain(); gn.gain.setValueAtTime(0, a.currentTime); gn.gain.linearRampToValueAtTime(g, a.currentTime + 0.04); gn.gain.linearRampToValueAtTime(0, a.currentTime + d); s.connect(bp); bp.connect(gn); gn.connect(a.destination); s.start(); }
  function tone(f, d, g, type, delay) { const a = ctx(); if (!a || !on) return; const o = a.createOscillator(), gn = a.createGain(), t = a.currentTime + (delay || 0); o.type = type || 'sine'; o.frequency.value = f; gn.gain.setValueAtTime(0, t); gn.gain.linearRampToValueAtTime(g, t + 0.01); gn.gain.exponentialRampToValueAtTime(0.0001, t + d); o.connect(gn); gn.connect(a.destination); o.start(t); o.stop(t + d + 0.05); }
  return { saw() { noise(1.15, 2600, 3, 0.22); tone(170, 1.15, 0.04, 'sawtooth'); }, grind() { noise(0.12, 4300, 2, 0.06); }, coin() { tone(1320, 0.12, 0.10); tone(1760, 0.3, 0.08, 'sine', 0.08); }, win() { [523, 659, 784, 1047].forEach((f, i) => tone(f, 0.35, 0.09, 'triangle', i * 0.09)); }, lose() { tone(196, 0.5, 0.10); tone(147, 0.8, 0.10, 'sine', 0.2); }, tap() { tone(700, 0.05, 0.04); }, toggle() { on = !on; if (!on && amb) { try { amb.g.gain.value = 0; } catch (e) { } } else if (on && amb) amb.g.gain.value = amb.v; return on; },
    // 环境声：夜市和集散地是人声嗡嗡加偶尔的碰石头声，公盘安静，场口是风
    amb(scene) { const a = ctx(); if (!a) return; if (amb) { try { amb.s.stop(); } catch (e) { } clearInterval(amb.t); amb = null; }
      const n = a.sampleRate * 3, b = a.createBuffer(1, n, a.sampleRate), ch = b.getChannelData(0); let last = 0; for (let i = 0; i < n; i++) { last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02; ch[i] = last * 3.5; }
      const s = a.createBufferSource(); s.buffer = b; s.loop = true; const f = a.createBiquadFilter(), g = a.createGain(); const P = { '夜市地摊': ['bandpass', 420, 0.6, 0.11], '玉石集散地': ['bandpass', 520, 0.5, 0.08], '翡翠公盘': ['lowpass', 180, 0.7, 0.04], '场口直采': ['bandpass', 260, 1.4, 0.10] }[scene] || ['lowpass', 300, 0.7, 0.05];
      f.type = P[0]; f.frequency.value = P[1]; f.Q.value = P[2]; g.gain.value = on ? P[3] : 0; s.connect(f); f.connect(g); g.connect(a.destination); s.start();
      const t = setInterval(() => { if (!on) return; if (scene === '场口直采') { try { f.frequency.linearRampToValueAtTime(180 + Math.random() * 260, a.currentTime + 2.5); } catch (e) { } } else if (scene !== '翡翠公盘' && Math.random() < 0.5) { tone(1500 + Math.random() * 1400, 0.05, 0.012, 'triangle'); tone(900 + Math.random() * 500, 0.07, 0.008, 'sine', 0.03); } }, 2600);
      amb = { s, g, t, v: P[3] }; } }; })();

/* ---------- 状态 ---------- */
let W = null;
const V = { mode: null, rec: null, piece: null, e: null, tool: 'rotate', burr: '中磨头', torch: { on: false, p: null, n: null, rake: false, tilt: 0, az: 0, h: 0 }, lampBody: true, room: true, lens: null, cut: null, cutT: 12, section: 0, msg: '', note: '', wk: { route: 'bracelet', master: '平洲镯师', theme: '师傅定' }, ref: false, sel: null, cab: false };
const cam = { yaw: 0.6, pitch: 0.35, dist: 300, t: [0, 0, 0] };
const Q = { scale: 1, fast: 0.45, K: 16, tuned: false, user: 1 };
let tab = 'market', thumbs = new Map(), qcache = new Map();

function save() { try { localStorage.setItem(SAVE_KEY, C.serialize(W)); } catch (e) { /* 存不了也能继续玩 */ } }
function parseSave(s) { const w = JSON.parse(s); if (!w || typeof w !== 'object' || !w.seed || !w.markets || !(w.v >= 9)) return null; C.migrate(w); w.market = w.markets[w.scene] || []; C.applyTools(w); C.lifeCost(w); return w; }
function load() { for (const k of [SAVE_KEY].concat(OLD_KEYS)) { try { const s = localStorage.getItem(k); if (!s) continue; const w = parseSave(s); if (w) { if (k !== SAVE_KEY) { try { localStorage.setItem('jade-save-bak', s); } catch (e) { } } return w; } } catch (e) { } } return null; }
function sumOf(w) { return `第 ${w.day} 天 · ${C.rankOf(w)} · 现金 ${fmt(w.cash)} · ${(C.CHAPTERS[w.chapter] || { title: '主线完成' }).title}`; }
function useWorld(w) { C.volCache.clear(); thumbs.clear(); qcache.clear(); loaded = null; W = w; save(); tab = 'market'; $('#saves').hidden = true; $('#start').hidden = true; view('market', W.market.find(L => !L.sold) || W.market[0], null); renderAll(); }
function renderSaves(msg) { let h = `<div class="row"><h2 style="margin:0">存档</h2><button data-act="savesclose">关闭（Esc）</button></div><p class="note">游戏每一步都自动存在这台设备的这个浏览器里。更新版本不会清档：旧存档会自动升级，教程和主线进度都留着。换设备、换浏览器或清了浏览器数据，要靠下面的「导出」。</p>
    <div class="row"><span><b>当前进度</b> <span class="dim">${sumOf(W)}</span></span></div>`;
  for (let i = 1; i <= 3; i++) { let s = null; try { s = JSON.parse(localStorage.getItem('jade-slot-' + i) || 'null'); } catch (e) { } h += `<div class="row"><span><b>存档位 ${i}</b> <span class="dim">${s ? sumOf(s) + (s.savedAt ? ' · 存于 ' + s.savedAt : '') : '空'}</span></span><span><button data-act="slotsave" data-i="${i}">存到这里</button> <button data-act="slotload" data-i="${i}" ${s ? '' : 'disabled'}>读取</button> <button data-act="slotdel" data-i="${i}" ${s ? '' : 'disabled'}>删除</button></span></div>`; }
  let bak = false; try { bak = !!localStorage.getItem('jade-save-bak'); } catch (e) { }
  if (bak) h += `<div class="row"><span><b>更新前的备份</b> <span class="dim">上次版本升级时自动留的一份</span></span><button data-act="slotload" data-i="bak">读取</button></div>`;
  h += `<div class="row"><span class="dim">导出：把存档变成一个文件或一段文字，自己收好。</span><span><button data-act="saveexport">下载存档文件</button> <button data-act="savetext">显示成文字</button></span></div>
    <div class="row"><span class="dim">导入：选一个存档文件，或把存档文字贴到下面再点读取。会覆盖当前进度。</span><span><input type="file" id="saveFile" accept=".json,.txt" style="max-width:190px"> <button data-act="saveimport">读取文字</button></span></div>
    <textarea id="saveText" rows="4" style="width:100%;box-sizing:border-box;background:var(--raise);color:var(--fg);border:1px solid var(--line);border-radius:4px;font:12px monospace" placeholder="存档文字"></textarea><p class="say" id="saveMsg">${msg || ''}</p>`;
  $('#savesbody').innerHTML = h; }

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
function invalidate(fast) { clearTimeout(fullTimer); if (fast) fullTimer = setTimeout(() => invalidate(false), 170); if (pending) { pendingFast = pendingFast && fast; return; } pending = true; pendingFast = !!fast; requestAnimationFrame(() => { pending = false; render(pendingFast ? Q.fast : 1); drawLayout(); }); }
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
  gl.uniform1f(u('uFakeT'), V.fakeT != null ? V.fakeT : V.rec && V.rec.fake && V.mode !== 'review' ? ({ paint: 1, veneer: 2, dye: 3 }[V.rec.fake.type] || 0) : 0);
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
  if (V.lens && !forceSize) { const R = Math.min(w, h) * 0.2; gl.uniform4f(u('uLens'), (V.lens.x - rect.left) / rect.width * w, (1 - (V.lens.y - rect.top) / rect.height) * h, R, [3.2, 5, 8][W.tools.loupe - 1]); } else if (V.lensAll) gl.uniform4f(u('uLens'), w / 2, h / 2, w * 3, 1); else gl.uniform4f(u('uLens'), 0, 0, 0, 1);
  const cutOn = V.cut && (V.tool === 'cut' || V.sawing) && V.mode === 'own' && !forceSize;
  gl.uniform1f(u('uCutOn'), cutOn ? (V.sawing ? 2 + (V.sawing % 7) : 1) : 0); if (cutOn) gl.uniform4f(u('uCut'), V.cut.n[0], V.cut.n[1], V.cut.n[2], V.cut.d);
  const SC = { '夜市地摊': [0, [0.075, 0.05, 0.03], [0.014, 0.010, 0.009], [1.0, 0.82, 0.56]], '玉石集散地': [1, [0.125, 0.115, 0.10], [0.022, 0.02, 0.018], [1.0, 0.97, 0.92]], '翡翠公盘': [2, [0.05, 0.06, 0.08], [0.008, 0.01, 0.014], [0.92, 0.97, 1.0]], '场口直采': [3, [0.3, 0.25, 0.18], [0.12, 0.10, 0.08], [1.0, 0.94, 0.84]] }[(V.rec && V.rec.scene) || W.scene] || [1, [0.115, 0.1, 0.085], [0.02, 0.018, 0.016], [1, 0.96, 0.9]];
  gl.uniform1i(u('uScene'), V.mode === 'market' ? SC[0] : 1); gl.uniform3fv(u('uBgA'), V.mode === 'market' ? SC[1] : [0.115, 0.1, 0.085]); gl.uniform3fv(u('uBgB'), V.mode === 'market' ? SC[2] : [0.02, 0.018, 0.016]); gl.uniform3fv(u('uKeyCol'), V.mode === 'market' ? SC[3] : [1, 0.96, 0.9]);
  { const tab = { '夜市地摊': [0.20, 0.07, 0.05], '玉石集散地': [0.10, 0.16, 0.13], '翡翠公盘': [0.035, 0.04, 0.055], '场口直采': [0.30, 0.23, 0.15] }; const on = !forceSize && V.info && V.mode !== 'review' && V.floor !== false; gl.uniform1f(u('uFloorOn'), on ? 1 : 0); gl.uniform1f(u('uDecor'), on && V.mode === 'market' ? 1 : 0); if (on) { gl.uniform1f(u('uFloorY'), V.info.lo - 0.4); gl.uniform1f(u('uFloorR'), Math.max(120, V.info.radius * 3.2)); gl.uniform3fv(u('uTabCol'), V.mode === 'market' ? (tab[(V.rec && V.rec.scene) || W.scene] || tab['玉石集散地']) : [0.09, 0.14, 0.12]); } }
  gl.uniform1i(u('uK'), scale < 1 ? 10 : Q.K); gl.uniform1f(u('uHi'), scale < 1 ? 0 : 1);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
  if (scale === 1 && !forceSize && !Q.tuned) { const px = new Uint8Array(4); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); const ms = performance.now() - t0; Q.slow = ms > 350 ? (Q.slow || 0) + 1 : 0; if (ms > 350 && Q.slow < 3) { invalidate(false); } else if (ms > 350 && Q.scale > 0.6) { Q.slow = 1; Q.scale *= 0.8; invalidate(false); } else Q.tuned = true; }
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
function openTray(ref, cab) { V.hold = null; V.spin = false; clearInterval(V.spinT); V.mode = 'tray'; V.ref = !!ref; V.cab = cab || false; V.rec = null; V.piece = null; V.e = null; V.sel = null; V.tool = 'rotate'; const lay = trayLayout(trayItems()); cam.t = [0, 6, 0]; cam.yaw = 0.35; cam.pitch = 0.85; cam.dist = Math.max(200, Math.max(lay.half[0], lay.half[1]) * 2.5); V.note = ''; tab = 'tray'; renderAll(); }
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
/* 三维排料图：把内核排出来的每一件用线框投影画在石头上 */
function drawLayout() { const el = $('#layoutg'); if (!el) return; if (!V.layoutOn || !V.layout || V.mode !== 'own' || !V.e || tab !== 'mine') { if (el.firstChild) el.innerHTML = ''; return; }
  const rc = canvas.getBoundingClientRect(), see = C.skillsOf(W).layout >= 1, cb = camBasis(), TA = Math.PI * 2; let h = '';
  const path = pts => 'M' + pts.map(p => { const q = proj(p); return (q[0] - rc.left).toFixed(1) + ' ' + (q[1] - rc.top).toFixed(1); }).join('L') + 'Z';
  const add = (c, u, v, a, b) => [c[0] + u[0] * a + v[0] * b, c[1] + u[1] * a + v[1] * b, c[2] + u[2] * a + v[2] * b];
  const circ = (c, u, v, ru, rv) => { const pts = []; for (let i = 0; i < 28; i++) pts.push(add(c, u, v, Math.cos(i / 28 * TA) * ru, Math.sin(i / 28 * TA) * rv)); return path(pts); };
  const el1 = (d, col, fill) => `<path d="${d}" fill="${fill ? col : 'none'}" fill-opacity="0.2" fill-rule="evenodd" stroke="${col}" stroke-width="1.3" stroke-opacity="0.95"/>`;
  const frame2 = n => { const t1 = Math.abs(n[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0], a = [n[1] * t1[2] - n[2] * t1[1], n[2] * t1[0] - n[0] * t1[2], n[0] * t1[1] - n[1] * t1[0]], l = Math.hypot(a[0], a[1], a[2]), u = [a[0] / l, a[1] / l, a[2] / l]; return [u, [n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0]]]; };
  for (const s of V.layout.shapes) { const col = !see ? '#8fd8c0' : s.k >= 0.5 ? '#5fe0a0' : '#f0b84a';
    if (s.type === 'ring') { const [u, v] = frame2(s.n), top = add(s.c, s.n, s.n, 4.5, 0), bot = add(s.c, s.n, s.n, -4.5, 0); h += el1(circ(top, u, v, 36, 36) + circ(top, u, v, 28, 28), col, true) + el1(circ(bot, u, v, 36, 36) + circ(bot, u, v, 28, 28), col, false); }
    else if (s.type === 'box') { const f = (a, b, hh) => add(add(s.c, s.t1, s.t2, a, b), s.n, s.n, hh, 0), T = [f(19, 13, 4), f(-19, 13, 4), f(-19, -13, 4), f(19, -13, 4)], B = [f(19, 13, -4), f(-19, 13, -4), f(-19, -13, -4), f(19, -13, -4)]; h += el1(path(T), col, true) + el1(path(B), col, false); for (let i = 0; i < 4; i++) h += el1(path([T[i], B[i]]), col, false); }
    else if (s.type === 'cab') h += el1(circ(s.c, s.t1, s.t2, 6, 5), col, true) + el1(circ(s.c, s.t1, s.n, 6, 2.6), col, false);
    else if (s.type === 'bead') h += el1(circ(s.c, cb.r, cb.up, 5, 5), col, true);
    else h += el1(circ(s.c, s.t1, s.t2, s.r[0], s.r[1]), col, true) + el1(circ(s.c, s.t1, s.n, s.r[0], s.r[2]), col, false) + el1(circ(s.c, s.t2, s.n, s.r[1], s.r[2]), col, false); }
  el.innerHTML = h; }
/* 人物画像：手绘风格的半身像，会呼吸、眨眼、偶尔偏一下头。o = { kind: wife|lover|kid|baby|master|man, seed } */
function photoKey(o) { const F = window.JADE_FACES || {}, f = W && W.fam; let k = null;
  if (o.kind === 'wife') k = 'w_' + (o.name || (f && f.wife)); else if (o.kind === 'lover') k = 'l_' + (o.name || (f && f.lover && f.lover.name)); else if (o.kind === 'master') k = 'm_' + o.mname;
  else if (o.months != null) { const girl = o.name.charCodeAt(1) % 2 === 0, m = o.months, band = m < 36 ? 0 : m < 84 ? 1 : m < 156 ? 2 : m < 216 ? 3 : 4, alt = o.name.charCodeAt(1) % 3 === 0 ? 'b' : ''; k = (girl ? 'g' : 'b') + band; if (F[k + alt]) k += alt; }
  return k && F[k] ? F[k] : null; }
function faceSvg(o, size) { const ph = photoKey(o); if (ph) return `<span class="ph" style="width:${size}px;height:${Math.round(size * 1.12)}px"><img src="${ph}" alt="${o.name || ''}" style="animation-delay:-${((o.seed || 1) % 7) * 0.6}s,-${((o.seed || 1) % 5) * 1.7}s"></span>`; const sd = (o.seed || 1) * 9301 % 233280, rnd = k => ((sd * (k + 3) * 49297) % 233280) / 233280, id = 'pf' + (faceSvg.n = (faceSvg.n || 0) + 1);
  const fem = o.kind === 'wife' || o.kind === 'lover' || o.girl, kid = o.kind === 'kid', baby = o.kind === 'baby', old = o.kind === 'master';
  const skin = ['#f0c9a4', '#e8bb93', '#dcab82', '#f3d2b3'][Math.floor(rnd(1) * 4)], skinD = '#b98360', hair = old ? '#8d8a86' : ['#1d1512', '#2a1c14', '#33231a'][Math.floor(rnd(2) * 3)], cloth = o.cloth || ['#7a3e48', '#3f5f7a', '#4f6a4a', '#8a6a3a', '#5a4a7a'][Math.floor(rnd(3) * 5)];
  const fw = baby ? 30 : kid ? 27 : fem ? 24 : 26, fh = baby ? 27 : kid ? 28 : 31, cy = baby ? 62 : 56, ey = cy + (baby || kid ? 2 : -1), ex = baby ? 11 : 10, er = baby || kid ? 3.4 : 2.7, d = (3 + rnd(5) * 3).toFixed(1), d2 = (rnd(6) * 4).toFixed(1);
  const hairBack = fem ? (o.kind === 'lover' ? `<path d="M${60 - fw - 5} ${cy - 4} Q${60 - fw - 10} ${cy + 46} ${60 - fw + 4} ${cy + 62} L${60 + fw - 4} ${cy + 62} Q${60 + fw + 10} ${cy + 46} ${60 + fw + 5} ${cy - 4} Z" fill="${hair}"/>` : `<circle cx="60" cy="${cy - fh - 4}" r="11" fill="${hair}"/><path d="M${60 - fw - 3} ${cy} Q${60 - fw - 6} ${cy + 26} ${60 - fw + 6} ${cy + 30} L${60 + fw - 6} ${cy + 30} Q${60 + fw + 6} ${cy + 26} ${60 + fw + 3} ${cy} Z" fill="${hair}"/>`) : '';
  const hairTop = baby ? `<path d="M${60 - 12} ${cy - fh + 3} Q60 ${cy - fh - 7} ${60 + 12} ${cy - fh + 3} Q60 ${cy - fh + 1} ${60 - 12} ${cy - fh + 3}Z" fill="${hair}"/>` : fem ? `<path d="M${60 - fw - 2} ${cy - 2} Q${60 - fw - 3} ${cy - fh - 9} 60 ${cy - fh - 8} Q${60 + fw + 3} ${cy - fh - 9} ${60 + fw + 2} ${cy - 2} Q${60 + fw - 4} ${cy - fh + 12} ${60 + 4} ${cy - fh + 7} Q${60 - fw + 6} ${cy - fh + 10} ${60 - fw - 2} ${cy - 2}Z" fill="${hair}"/>` : `<path d="M${60 - fw - 1} ${cy - 6} Q${60 - fw - 2} ${cy - fh - 8} 60 ${cy - fh - 7} Q${60 + fw + 2} ${cy - fh - 8} ${60 + fw + 1} ${cy - 6} Q${60 + fw - 3} ${cy - fh + 8} 60 ${cy - fh + 6} Q${60 - fw + 3} ${cy - fh + 8} ${60 - fw - 1} ${cy - 6}Z" fill="${hair}"/>${old ? `<path d="M${60 - fw - 3} ${cy - fh + 9} h${fw * 2 + 6} v-5 q-${fw + 3} -16 -${fw * 2 + 6} 0z" fill="#3b4a5a"/><path d="M${60 + 6} ${cy - fh + 8} h${fw + 6} v3 h-${fw + 6}z" fill="#2c3946"/>` : ''}`;
  const eye = x => `<g class="pf-eye" style="transform-origin:${x}px ${ey}px;animation-delay:-${d2}s"><ellipse cx="${x}" cy="${ey}" rx="${er + 1.2}" ry="${er}" fill="#fff"/><circle cx="${x}" cy="${ey}" r="${er * 0.78}" fill="#2a1a12"/><circle cx="${x + 0.9}" cy="${ey - 0.9}" r="${er * 0.26}" fill="#fff"/></g><path d="M${x - er - 1.6} ${ey - er * 0.6} Q${x} ${ey - er - 1.8} ${x + er + 1.6} ${ey - er * 0.6}" stroke="${fem ? '#1d1512' : '#5a4030'}" stroke-width="${fem ? 1.5 : 1}" fill="none"/><path d="M${x - er - 2} ${ey - er - 4.5} q${er + 2} -${old ? 1 : 2.4} ${er * 2 + 4} 0" stroke="${hair}" stroke-width="${fem || kid || baby ? 1.3 : 2.1}" fill="none" stroke-linecap="round"/>`;
  return `<svg class="pf" viewBox="0 0 120 130" width="${size}" height="${Math.round(size * 1.08)}" role="img" aria-label="${o.name || ''}"><defs><radialGradient id="${id}s" cx="42%" cy="36%" r="75%"><stop offset="0" stop-color="${skin}"/><stop offset="0.7" stop-color="${skin}"/><stop offset="1" stop-color="${skinD}"/></radialGradient><linearGradient id="${id}c" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${cloth}"/><stop offset="1" stop-color="#1c1814"/></linearGradient><clipPath id="${id}k"><rect x="0" y="0" width="120" height="130" rx="10"/></clipPath></defs>
  <g clip-path="url(#${id}k)"><rect width="120" height="130" fill="#221d18"/><ellipse cx="60" cy="40" rx="62" ry="50" fill="#3a3027" opacity="0.7"/>
  <g class="pf-body" style="animation-duration:${d}s"><path d="M${baby ? 26 : 12} 132 Q${baby ? 28 : 16} ${baby ? 100 : 92} 60 ${baby ? 96 : 88} Q${baby ? 92 : 104} ${baby ? 100 : 92} ${baby ? 94 : 108} 132Z" fill="url(#${id}c)"/>${fem ? `<path d="M48 90 L60 104 L72 90" stroke="#00000055" stroke-width="2" fill="none"/>` : baby ? '' : `<path d="M50 89 L60 99 L70 89 L66 88 L60 94 L54 88Z" fill="#00000040"/>`}
  <g class="pf-head" style="transform-origin:60px ${cy + fh}px;animation-duration:${(+d * 1.9).toFixed(1)}s">${hairBack}<rect x="${60 - 8}" y="${cy + fh - 8}" width="16" height="18" fill="${skinD}"/>
  <ellipse cx="${60 - fw - 1}" cy="${cy + 2}" rx="3.6" ry="6" fill="${skinD}"/><ellipse cx="${60 + fw + 1}" cy="${cy + 2}" rx="3.6" ry="6" fill="${skinD}"/>
  <ellipse cx="60" cy="${cy}" rx="${fw}" ry="${fh}" fill="url(#${id}s)"/>${old ? `<path d="M${60 - 9} ${cy - fh + 15} q9 2 18 0 M${60 - 15} ${cy + 13} q3 4 1 8 M${60 + 15} ${cy + 13} q-3 4 -1 8" stroke="#a37250" stroke-width="0.8" fill="none"/>` : ''}
  <ellipse cx="${60 - ex - 4}" cy="${ey + 9}" rx="6" ry="3.6" fill="#e58a7a" opacity="${fem || kid || baby ? 0.38 : 0.14}"/><ellipse cx="${60 + ex + 4}" cy="${ey + 9}" rx="6" ry="3.6" fill="#e58a7a" opacity="${fem || kid || baby ? 0.38 : 0.14}"/>
  ${eye(60 - ex)}${eye(60 + ex)}<path d="M60 ${ey + 3} q-3 ${baby ? 5 : 8} 0.5 ${baby ? 6 : 9.5} q2 0.6 3.4 -0.6" stroke="${skinD}" stroke-width="1.2" fill="none" stroke-linecap="round"/>
  <path class="pf-mouth" d="M${60 - 7} ${ey + (baby ? 14 : 18)} Q60 ${ey + (baby ? 19 : 22) + (o.sad ? -4 : 0)} ${60 + 7} ${ey + (baby ? 14 : 18)}" stroke="${fem ? '#b8424e' : '#8a4a3c'}" stroke-width="${fem ? 2.6 : 1.8}" fill="none" stroke-linecap="round"/>
  ${hairTop}${!fem && !kid && !baby && !old && rnd(7) > 0.5 ? `<path d="M${60 - 11} ${ey + 25} q11 5 22 0" stroke="#3a2a20" stroke-width="3" opacity="0.25" fill="none"/>` : ''}</g></g></g></svg>`; }
function kidFace(k, size) { return faceSvg({ months: k.months, kind: k.months < 30 ? 'baby' : k.months < 204 ? 'kid' : 'man', seed: k.name.charCodeAt(1) * 7 + k.name.length, name: k.name, girl: k.name.charCodeAt(1) % 2 === 0 && k.months >= 204 }, size); }
function workCard(k) { const is = C.issueOf(W, k); let h = `<article class="card"><div class="row"><b>加工中 · ${esc(k.from)}</b><span class="dim">${is ? '停工，等你拿主意' : '第 ' + k.ready + ' 天取货'}</span></div><div class="row dim"><span>${esc(k.what)}，按看得见的料预计 ${k.expected} 件。</span></div>`;
  if (is) h += issueHtml(k, is); else if (k.issue && k.issue.done) h += `<p class="${k.issue.win ? 'note' : 'say'}">${esc(k.issue.note)}</p>`; return h + '</article>'; }
function issueHtml(k, is) { const word = p => p >= 1 ? '稳' : is.see ? Math.round(p * 100) + '% 把握' : p > 0.7 ? '把握大' : p > 0.45 ? '五五开' : '把握不大'; return `<p class="say">${esc(is.text)}</p>${is.opts.map((o, i) => `<div class="row"><span class="dim">${word(o.p)}${o.p < 1 ? `：成了 ×${o.win}，不成 ×${o.lose}` : `：×${o.win}`}</span><button data-act="issue" data-id="${k.id}" data-i="${i}">${esc(o.label)}</button></div>`).join('')}${is.see ? '' : '<p class="note">学了相应的手艺，这里能看到具体几成把握。</p>'}`; }
function bookOf(s) { let v = s.proceeds, all = true; for (const p of s.pieces) if (!p.sold) { if (!C.volCache.get(s.seed)) { all = false; continue; } v += getQuotes(s, p).best; } if (W.works.some(k => k.stone === s.id)) all = false; for (const it of W.items) if (it.stone === s.id) { if (it.state === 'sold') continue; v += it.value * 0.6; } return { v, all }; }

/* ---------- 面板 ---------- */
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
function pct(a, b) { const r = (a / b - 1) * 100; return `<span class="${r >= 0 ? 'up' : 'down'}">${r >= 0 ? '+' : ''}${r.toFixed(0)}%</span>`; }
let lastCash = null;
function floatCash(d) { const h = $('#stats'), s = document.createElement('span'); s.className = 'floater ' + (d > 0 ? 'up' : 'down'); s.textContent = (d > 0 ? '+' : '') + fmt(d); h.appendChild(s); setTimeout(() => s.remove(), 1500); }
function dayCard(lines) { const el = $('#daycard'); el.innerHTML = `<p class="eyebrow">${W.scene}</p><h2>第 ${W.day} 天</h2>${lines.slice(0, 4).map(x => `<p>${esc(x)}</p>`).join('')}`; el.hidden = false; el.classList.remove('go'); void el.offsetWidth; el.classList.add('go'); setTimeout(() => { el.hidden = true; }, 2300); }
function renderTop() {
  const recv = W.recv.reduce((a, r) => a + r.amt, 0);
  let inv = 0; for (const s of W.stones) if (!s.closed) for (const p of s.pieces) if (!p.sold) inv += (s.last[p.id] || {}).best || 0;
  const cashNow = W.cash; 
  $('#stats').innerHTML = `<div><span>第</span><b>${W.day}</b><span>天</span></div><div><span>现金</span><b>${fmt(W.cash)}</b></div><div><span>应收</span><b>${fmt(recv)}</b></div><div><span>存货报价</span><b>${fmt(inv)}</b></div><div><span>${C.rankOf(W)} · 眼力</span><b>${W.eye}</b></div>${C.can(W, 'live') ? `<div><span>粉丝</span><b>${fmt(W.fans)}</b></div>` : ''}`;
  if (lastCash != null && Math.abs(cashNow - lastCash) >= 1 && $('#start').hidden) floatCash(cashNow - lastCash); lastCash = cashNow;
}
function betHtml(bet, full) { return `<span class="tag b">${bet.main}</span>${bet.tags.map(t => `<span class="tag">${t}</span>`).join('')}${full ? `<p class="why">${esc(bet.why)}</p>` : ''}`; }
function renderSide() {
  document.querySelectorAll('#tabs button').forEach(b => b.setAttribute('aria-selected', b.dataset.tab === tab));
  const el = $('#panel'); let h = goalCard();
  if (tab === 'market') {
    h += `<div class="scenes">${Object.keys(C.SCENES).map(k => { const S = C.SCENES[k], ok = C.sceneOpen(W, k); return `<button data-act="scene" data-k="${k}" aria-pressed="${W.scene === k}" ${ok ? '' : 'disabled'}>${k}${ok ? '' : `<small>第 ${C.SCENE_CH[k] + 1} 章开放</small>`}</button>`; }).join('')}</div><p class="note">${C.SCENES[W.scene].tip}</p>${W.event ? `<p class="say">今日行情：${esc(W.event.t)}</p>` : ''}`;
    W.market.forEach((L, i) => {
      const sel = V.mode === 'market' && V.rec === L;
      h += `<article class="card ${sel ? 'sel' : ''} ${L.sold ? 'gone' : ''}" data-act="listing" data-i="${i}"><div class="row"><b>${L.origin} · ${L.info.skin}</b><span class="price">${L.sold ? '已买' : L.auction ? '底价 ' + fmt(L.floor) : fmt(L.ask)}</span></div>
      <div class="row dim"><span>${(L.info.weight / 1000).toFixed(2)} kg · ${L.info.dims.join('×')} mm</span><span>${L.channel}</span></div>
      <div class="tags"><span class="tag ${L.info.window ? 'w' : ''}">${L.info.window ? '卖家已开窗' : '全蒙头'}</span>${betHtml(L.info.bet, sel)}</div>`;
      if (sel && !L.sold && !L.called && C.can(W, 'buy')) h += `<div class="row"><span class="dim">觉得皮或窗口做过手脚？说对了老板大降价，说错了他翻脸不卖。</span><button data-act="callout">当面说这是假货</button></div>`;
      if (sel && !L.sold) { const eff = C.famEff(W, 'spotter'); if (eff > 0) { const kid = W.fam.kids.find(k => k.job === 'spotter'), st = C.getVol(L).st, rr = new C.Rng(C.seedOf(L.seed, 'kidsay')), right = rr.u() < 0.35 + eff * 0.9, gi = C.gradeIdx(st.w0), g2 = right ? gi : Math.max(0, Math.min(5, gi + (rr.u() < 0.5 ? 1 : -1))); h += `<p class="patter">${kid.name}凑过来小声说：“我看像${['豆种', '糯种', '糯冰种', '冰种', '高冰种', '玻璃种'][g2]}${L.fake && rr.u() < eff + 0.2 ? '，可这皮我觉得不对劲' : ''}。”</p>`; } }
      if (sel && !L.sold) h += `${(L.patter || []).map(x => `<p class="patter">${esc(x)}</p>`).join('')}${L.opinion ? `<p class="say">${esc(L.opinion)}</p>` : `<div class="row"><span class="dim">拿不准？</span><button data-act="appr">请师傅掌眼（${fmt(C.appraiseFee(L))}）</button></div>`}`;
      if (L.auction && L.bid && !L.sold) h += `<div class="row"><span class="say">已投标 ${fmt(L.bid)}，收工后开标</span></div>`;
      if (sel && !L.sold && L.auction) h += `<div class="bargain"><label for="offer">暗标出价（元）。别人出多少你看不到，出高了白花钱，出低了拿不到。</label><div class="row"><input id="offer" type="number" inputmode="numeric" min="0" step="100" value="${L.bid || V.offer || L.floor}"><button data-act="bid" class="pri">${L.bid ? '改标' : '投标'}</button></div>${V.msg ? `<p class="say">${esc(V.msg)}</p>` : ''}</div>`;
      else if (sel && !L.sold && !C.can(W, 'buy')) { const g = V.wg || {}, o = (arr, cur) => arr.map(x => `<option value="${x[0]}" ${String(cur) === String(x[0]) ? 'selected' : ''}>${x[1]}</option>`).join('');
        h += `<div class="work"><b>围观：先猜，再看他切</b><p class="note">你还没本钱，也没人信你。先把判断写下来，别人切开后对答案：猜得准涨眼力，猜对种水还能赢旁人的彩头。今天还能看 ${W.watchLeft} 块。</p>
          <div class="row"><label for="wW">种水</label><select id="wW">${o([['', '还没想好'], [0, '豆种'], [1, '糯种'], [2, '糯冰种'], [3, '冰种'], [4, '高冰种'], [5, '玻璃种']], g.water == null ? '' : g.water)}</select></div>
          <div class="row"><label for="wC">色</label><select id="wC">${o([['none', '基本无色'], ['skin', '只有贴皮一层'], ['deep', '有色吃进去'], ['full', '满色']], g.color || 'none')}</select></div>
          <div class="row"><label for="wK">裂</label><select id="wK">${o([['few', '裂少（至多一条）'], ['many', '裂多（两条以上）']], g.crack || 'few')}</select></div>
          <div class="row"><span class="say">${esc(V.msg || '')}</span><button data-act="watch" class="pri">看他切</button></div></div>`; }
      else if (sel && !L.sold) h += `<div class="bargain"><label for="offer">出价（元）</label><div class="row"><input id="offer" type="number" inputmode="numeric" min="0" step="100" value="${V.offer || Math.round(L.ask * 0.7 / 100) * 100}"><button data-act="offer">还价</button><button data-act="take" class="pri">照价买 ${fmt(L.ask)}</button></div>${L.ask >= 8000 ? `<div class="row"><button data-act="partner" aria-pressed="${!!V.partner}">找人合伙</button><span class="dim">${V.partner ? '合伙人出一半本钱，赚了亏了都对半分。' : '本钱不够或怕风险，可以拉人各出一半。'}</span></div>` : ''}${V.msg ? `<p class="say">${esc(V.msg)}</p>` : ''}</div>`;
      h += `</article>`;
    });
  } else if (tab === 'mine') {
    const open = W.stones.filter(s => !s.closed), ready = W.items.filter(i => i.state === 'ready').length;
    if (!open.length && !W.works.length) h += `<p class="note">还没有存货。到「货源」里挑一块买下，就能在这里开窗、下刀、询价或送去做件。</p>`;
    for (const k of W.works) h += workCard(k);
    if (C.can(W, 'work')) { const sk = C.skillsOf(W); h += `<article class="card"><b>我的手艺</b>${Object.keys(C.SKILLS).map(id => { const S = C.SKILLS[id], lv = sk[id]; return `<div class="row"><span>${S.name} <span class="dim">${'●'.repeat(lv)}${'○'.repeat(3 - lv)} ${lv < 3 ? '下一层：' + S.tips[lv] : '学满了'}</span></span>${lv < 3 ? `<button data-act="learn" data-k="${id}">学（${fmt(S.cost[lv])}）</button>` : ''}</div>`; }).join('')}${W.own && W.staff.master > 0 ? `<div class="row dim"><span>驻店师傅${W.own.name}：避裂 ${Math.round(C.masterOf(W, '自家师傅').dodge * 100)} · 做色 ${Math.round(C.masterOf(W, '自家师傅').color * 100)} · 设计 ${Math.round(C.masterOf(W, '自家师傅').design * 100)}，做过 ${W.own.jobs} 单</span></div>` : ''}</article>`; }
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
        if (C.can(W, 'work')) { const K = V.wk; if (C.mastersFor(W).indexOf(K.master) < 0) K.master = '街边师傅'; const MM = C.masterOf(W, K.master), props = C.proposals(W, s, V.piece, K.master), lay = C.skillsOf(W).layout, plan = C.workPlan(W, s, V.piece, K.route, K.master, K.theme), themed = K.route === 'pendant' || K.route === 'carve';
        { const key = [s.id, V.piece.id, V.piece.planes.length, (V.piece.holes || []).length, K.route, Math.round(stt.kAvg * 50)].join(':'); if (V.layoutOn && V.layoutKey !== key) { try { V.layout = C.layoutPlan(W, s, V.piece, K.route); } catch (e) { V.layout = { shapes: [], n: 0, unsure: 0 }; } V.layoutKey = key; } }
        const opt = (o, cur, f) => Object.keys(o).map(k => `<option value="${k}" ${k === cur ? 'selected' : ''}>${f(k)}</option>`).join('');
        h += `<div class="work"><b>送去做件</b>
          <div class="row"><label for="wkRoute">做什么</label><select id="wkRoute">${opt(C.ROUTES, K.route, k => C.ROUTES[k].name)}</select></div><p class="note">${C.ROUTES[K.route].tip}</p>
          <div class="row"><label for="wkMaster">找谁做</label><select id="wkMaster">${C.mastersFor(W).map(k => `<option value="${k}" ${k === K.master ? 'selected' : ''}>${k === '自家师傅' && W.own ? '自家师傅 ' + W.own.name : k}</option>`).join('')}</select></div><div class="row" style="align-items:flex-start;gap:10px">${faceSvg({ kind: 'master', mname: K.master, seed: K.master.charCodeAt(0), cloth: '#4a4a44' }, 62)}<p class="note" style="flex:1;margin:0">${C.MASTERS[K.master].tip}</p></div>
          <div class="row dim"><span>避裂 ${Math.round(MM.dodge * 100)} · 做色 ${Math.round(MM.color * 100)} · 设计 ${Math.round(MM.design * 100)}</span><span>${MM.dodge >= 0.7 ? '擅长避裂' : ''}${MM.color >= 0.7 ? ' 擅长做色' : ''}${MM.design >= 0.7 ? ' 擅长设计' : ''}</span></div>
          ${props.length ? `<div class="props"><span class="dim">${K.master}看了料，给你几个提案（也可以不听，自己在上面选）：</span>${props.map((o, i) => `<div class="row"><span><b>${o.title}</b> ${C.ROUTES[o.route].name}${o.theme !== '师傅定' ? ' · ' + o.theme : ''} <span class="dim">${o.n} ${C.ROUTES[o.route].unit}${lay >= 1 ? `，他估能卖 ${fmt(o.lo)}–${fmt(o.hi)}` : ''}，工费 ${fmt(o.fee)}</span><br><i>“${esc(o.say)}”</i></span><button data-act="prop" data-r="${o.route}" data-t="${o.theme}" ${K.route === o.route && K.theme === o.theme ? 'disabled' : ''}>照这个</button></div>`).join('')}${lay < 1 ? '<span class="dim">学了「排料设计」能看到每个提案大概值多少。</span>' : ''}</div>` : ''}
          ${themed ? `<div class="row"><label for="wkTheme">题材</label><select id="wkTheme">${opt(C.THEMES, K.theme, k => k === '师傅定' ? k : `${k}（行情${C.demandWord(C.themeDemand(W, k))}）`)}</select></div><p class="note">${C.THEMES[K.theme].tip}</p>` : ''}
          ${K.route === 'cab' && plan.ok ? `<div class="row"><span class="dim">${K.cabKey === s.id + ':' + V.piece.id ? `你定的尺寸：${K.cabText}` : '可以自己盯着师傅一号一号放大，贪大有风险。'}</span><button data-act="cabgo" ${K.cabKey === s.id + ':' + V.piece.id ? 'disabled' : ''}>自己盯着取</button></div>` : ''}
          ${plan.warn.map(x => `<p class="say">${esc(x)}</p>`).join('')}
          <div class="row"><span class="dim">${V.layoutOn && V.layout ? (V.layout.n ? `石头上画出了 ${V.layout.n} ${K.route === 'bead' ? '颗珠子' : K.route === 'carve' ? '件的大致轮廓' : C.ROUTES[K.route].unit}的位置${lay >= 1 ? `：绿的是看清了的料${V.layout.unsure ? `，黄的 ${V.layout.unsure} 处还没看清，里面可能有裂或没色` : ''}` : '。学了「排料设计」能分出哪些位置没看清'}。已经让开看得见的裂。转动石头可以从各个方向看。` : '按现在看得见的料，这种件一件也排不下。') : '把这种件按看得见的料一件件摆进石头里。'}</span><button data-act="layout">${V.layoutOn ? '收起排料图' : '看排料图'}</button></div>
          <div class="row"><span class="dim">预计 ${plan.n} ${C.ROUTES[K.route].unit} · 工费 ${fmt(plan.fee)} · ${plan.days} 天</span><button data-act="work" class="pri" ${plan.ok ? '' : 'disabled'}>送去</button></div></div>`; } else h += `<p class="note">下刀和做成品要到第三章「自己做货」才解锁。现在先学会低买高卖。</p>`;
        h += `<div class="row q"><span><b>不急着卖</b> <i>${V.piece.shelf ? '已摆在铺面' : '摆进铺面零售，或收进藏品柜'}</i></span><span><button data-act="pshelf" ${V.piece.shelf ? 'disabled' : ''}>摆进铺面</button> <button data-act="pkeep">收藏</button></span></div>`;
        h += `<p class="note">报价只在今天有效。账面开涨不是现金到账。</p></div>`;
      }
      h += `</article>`;
    }
  } else if (tab === 'home') {
    const f = W.fam, lc = C.lifeCost(W), bar = (v, c) => `<span class="bar"><i style="width:${Math.round(v)}%;background:${c}"></i></span>`, sel = (id, opts, cur) => `<select id="${id}">${opts.map(o => `<option value="${o[0]}" ${String(o[0]) === String(cur) ? 'selected' : ''}>${o[1]}</option>`).join('')}</select>`;
    h += `<div class="people">${f.wife ? `<figure>${faceSvg({ kind: 'wife', seed: f.wife.charCodeAt(0) + f.wife.charCodeAt(1), name: f.wife, sad: f.har < 35 }, 84)}<figcaption>${f.wife}</figcaption></figure>` : ''}${f.kids.filter(k => !k.withMom).map(k => `<figure>${kidFace(k, 64)}<figcaption>${k.name} ${C.kidAge(k)}岁</figcaption></figure>`).join('')}${f.lover ? `<figure>${faceSvg({ kind: 'lover', seed: f.lover.name.charCodeAt(1), name: f.lover.name, cloth: '#8a2f45' }, 64)}<figcaption>${f.lover.name}</figcaption></figure>` : ''}</div>`;
    h += `<article class="card"><div class="row"><b>${f.wife ? '你和' + f.wife : '单身'}，${f.kids.filter(k => !k.withMom).length} 个孩子在身边</b><span class="dim">每天家用 ${fmt(lc.total)}</span></div>
      <div class="row"><span>身体 ${Math.round(f.hp)}</span>${bar(f.hp, f.hp < 30 ? 'var(--up)' : 'var(--jade)')}</div><div class="row"><span>家和 ${Math.round(f.har)}</span>${bar(f.har, f.har < 30 ? 'var(--up)' : 'var(--lamp)')}</div>
      <div class="row dim"><span>${lc.items.map(x => `${x[0]} ${x[1]}`).join(' · ')}</span></div>
      <div class="row"><label for="fFood">吃</label>${sel('fFood', C.FOODS.map((x, i) => [i, `${x.name}（每天 ${x.cost}）`]), f.food)}</div>
      <div class="row"><span class="dim">吃得差、住得差，身体和家和每天都在掉；掉到底会生病、吵架。家里过一个月，游戏里是一天。</span><button data-act="rest" ${f.rested === W.day ? 'disabled' : ''}>今天歇业陪家人</button></div></article>`;
    { const FC = C.FAMC; h += `<article class="card"><b>婚姻和孩子</b>
      ${f.wife ? `<div class="row"><span class="dim">再要一个孩子：产检、生产、月子 ${fmt(FC.baby)}。多一张嘴，以后也多一个帮手。</span><button data-act="baby">和${f.wife}再生一个</button></div>
      <div class="row"><label for="dvLaw">离婚请律师</label><select id="dvLaw">${C.LAWYERS.map((L, i) => `<option value="${i}" ${(V.law || 0) === i ? 'selected' : ''}>${L.name}${L.fee ? '（' + fmt(L.fee) + '）' : ''}：分走 ${Math.round(C.divorceShare(W, i) * 100)}% 现金</option>`).join('')}</select></div><div class="row"><span class="dim">另加手续 ${fmt(FC.divorce)}。你外面有人会多分给她；她有错被你抓到会少分。</span><span><button data-act="divorce" data-k="1">离婚，孩子跟我</button> <button data-act="divorce" data-k="0">离婚，孩子跟她</button></span></div>` : `<div class="row"><span class="dim">${f.lover ? `和${f.lover.name}结婚` : '托人介绍，再婚'}：彩礼婚礼 ${fmt(f.lover ? FC.wedding * 0.6 : FC.wedding)}。没有人带的小孩子每天要请保姆 ${FC.nanny}。</span><button data-act="marry">结婚</button></div>`}
      ${f.lover ? `<div class="row"><span>外面有人：${f.lover.name} <span class="dim">每天开销 ${FC.loverDaily}，家和一直掉，随时可能被发现</span></span><span><button data-act="baby" data-k="lover">和她生一个</button> <button data-act="affairend">断掉（${fmt(FC.breakup)}）</button></span></div>` : (f.wife ? `<div class="row"><span class="dim">婚外情：每天多一笔开销，家和下降，被发现就是赔礼或者离婚；名气越大越容易被认出来。</span><button data-act="affair">在外面找一个</button></div>` : '')}</article>`; }
    h += `<article class="card"><div class="row"><b>住：${C.HOMES[f.home].name}</b><span class="dim">${C.HOMES[f.home].rent ? '日租 ' + C.HOMES[f.home].rent : '自有'}</span></div>${C.HOMES.map((x, i) => i === f.home ? '' : `<div class="row"><span class="dim">${x.name}${x.price ? ' ' + fmt(x.price) : `（日租 ${x.rent}）`}</span><button data-act="asset" data-k="home" data-i="${i}">${i > f.home ? (x.price ? '买下' : '搬过去') : (C.HOMES[f.home].price ? '卖房，搬到这里' : '搬过去')}</button></div>`).join('')}</article>`;
    h += `<article class="card"><div class="row"><b>行：${C.CARS[f.car].name}</b><span class="dim">${C.CARS[f.car].tip}</span></div>${C.CARS.map((x, i) => i === f.car || i === 0 && f.car === 0 ? '' : `<div class="row"><span class="dim">${x.name}${x.price ? ' ' + fmt(x.price) + '。' + x.tip : ''}</span><button data-act="asset" data-k="car" data-i="${i}">${i > f.car ? '买' : (i === 0 ? '卖车' : '卖掉，换这个')}</button></div>`).join('')}</article>`;
    f.kids.forEach((k, i) => { const sch = C.schoolsFor(k), can12 = k.months >= 144 && !k.away, T = [['book', '读书'], ['craft', '手艺'], ['eye', '眼力'], ['talk', '口才'], ['manage', '管事']];
      h += `<article class="card"><div class="row"><b>${k.name} · ${C.kidAge(k)} 岁${k.months % 12 ? ' ' + (k.months % 12) + ' 个月' : ''}</b><span class="dim">${k.withMom ? '跟妈妈过，你付抚养费' : k.away ? '在外地' : C.SCHOOLS[k.school].name}</span></div>
        ${k.months >= 36 ? `<div class="row dim"><span>${T.map(x => `${x[1]}${C.traitWord(k.t[x[0]])}`).join(' · ')}</span></div>` : '<div class="row dim"><span>还在吃奶，什么都看不出来。</span></div>'}
        ${k.away ? '' : `<div class="row"><label for="kS${i}">上学</label>${sel('kS' + i, sch.map(id => [id, `${C.SCHOOLS[id].name}（每天 ${C.SCHOOLS[id].cost}）`]), k.school)}</div>`}
        ${!k.away && k.months >= 60 ? `<div class="row"><label for="kT${i}">花钱培养</label><span><select id="kT${i}">${Object.keys(C.TRAIN).map(id => `<option value="${id}">${C.TRAIN[id].name}（${C.TRAIN[id].cost}）</option>`).join('')}</select> <button data-act="train" data-i="${i}" ${k.trained === W.day ? 'disabled' : ''}>去</button></span></div>${(k.tired || 0) > 3 ? '<p class="note">这阵子练得太密，孩子累了。歇几天或者去锻炼一下。</p>' : ''}` : ''}
        ${can12 ? `<div class="row"><label for="kJ${i}">帮忙</label>${sel('kJ' + i, Object.keys(C.JOBS).map(id => [id, C.JOBS[id].name]), k.job)}</div><p class="note">${k.job !== 'none' ? C.JOBS[k.job].tip + (k.school === 'work' ? '全职在干。' : '课余帮忙，效果减半。') : '满 12 岁了，可以课余帮忙；不上学全职干效果翻倍，但书就不读了，16 岁前这样做家里也有怨气。'}</p>` : (k.months >= 72 ? '<p class="note">学校不只决定成绩：同学、老师、路上遇到的人，都会在以后的日子里冒出来。贵的不一定适合这个孩子。</p>' : '')}</article>`; });
    h += `<article class="card"><b>借钱</b>${f.loans.map((L, i) => `<div class="row"><span>${C.LOANS[L.type].name} ${fmt(L.principal)} <span class="dim">每天利息 ${fmt(L.principal * L.rate)}</span></span><button data-act="repay" data-i="${i}">还清</button></div>`).join('') || '<div class="row dim"><span>没有欠债</span></div>'}
      ${Object.keys(C.LOANS).map(t => { const room = C.loanRoom(W, t); return `<div class="row"><span class="dim">${C.LOANS[t].name}：还能借 ${fmt(room)}，日息 ${(C.LOANS[t].rate * 100).toFixed(2)}%${t === 'shark' ? '。拖过 25 天会有人上门' : ''}</span>${room >= 5000 ? `<span><button data-act="borrow" data-t="${t}" data-a="${Math.min(room, 20000)}">借 ${fmt(Math.min(room, 20000))}</button> <button data-act="borrow" data-t="${t}" data-a="${room}">借满</button></span>` : ''}</div>`; }).join('')}</article>`;
  } else if (tab === 'tray') {
    const items = trayItems();
    if (!C.can(W, 'tray') && !V.ref) h += `<p class="note">成品盘在第三章「自己做货」解锁。现在可以先看看对照盘，认一认各种种水和颜色。</p>`;
    if (V.ref) { h += `<p class="note">对照盘：上面六块素面牌从豆种到玻璃种，下面是同为冰种、不同颜色的蛋面。转动托盘，对着光看它们的差别。</p>`; for (const it of items) h += `<article class="card ${V.sel === it.id ? 'sel' : ''}" data-act="isel" data-i="${it.id}"><div class="row"><b>${it.name}</b></div><div class="row dim"><span>${it.note}</span></div><div class="row"><button data-act="hold" data-i="${it.id}">拿起来看</button></div></article>`; h += `<button data-act="trayback" class="pri">回到我的托盘</button>`; }
    else {
      h += `<div class="scenes"><button data-act="cab0" aria-pressed="${!V.cab}">待售托盘</button><button data-act="cab2" aria-pressed="${V.cab === 'shelf'}">铺面柜台（${C.shelfCount(W)}/${C.slotsOf(W)}）</button><button data-act="cab1" aria-pressed="${V.cab === true}">藏品柜（${W.items.filter(i => i.state === 'kept').length}）</button></div>`;
      const rawOf = key => { const o = []; for (const s of W.stones) for (const p of s.pieces) if (p[key] && !p.sold) o.push([s, p]); return o; }, rawCard = (s, p, lbl) => `<article class="card"><div class="row"><b>料头 #${s.id} ${p.name}</b><span class="price">${fmt(((s.last[p.id] || {}).best || 0) * (lbl === 'shelf' ? 1.12 * C.SHOPLV[W.shop].mult : 1))}</span></div><div class="row">${thumb(s, p) ? `<img class="rawimg" src="${thumb(s, p)}" alt="">` : ''}<span class="dim">${s.origin} · ${s.info.skin}。这是没加工的明料，拿到工作台上可以转着看、打灯把玩。</span></div><div class="row"><button data-act="pview" data-s="${s.id}" data-p="${p.id}">拿到工作台看</button><button data-act="pback" data-s="${s.id}" data-p="${p.id}">撤回料头盘</button></div></article>`;
      if (V.cab === 'shelf') h += rawOf('shelf').map(x => rawCard(x[0], x[1], 'shelf')).join(''); if (V.cab === true) h += rawOf('kept').map(x => rawCard(x[0], x[1], 'kept')).join('');
      if (V.cab === 'shelf') { h += `<p class="note">${W.shop ? `${C.SHOPLV[W.shop].name}：摆在这里的成品每天有散客上门，按零售价${C.SHOPLV[W.shop].mult > 1 ? '加一点' : ''}买走，口碑越好卖得越快。` : '还没有铺面。到「账本」里盘一个柜台，成品就能自己零售，不用再让批发商压价。'}</p>`; for (const it of items) h += `<article class="card ${V.sel === it.id ? 'sel' : ''}" data-act="isel" data-i="${it.id}"><div class="row"><b>${esc(it.name)}</b><span class="price">${fmt(it.value * C.SHOPLV[W.shop].mult)}</span></div><div class="row dim"><span>${C.waterName(it.w)} · 第 ${it.shelfDay} 天上柜</span></div><div class="row"><button data-act="hold" data-i="${it.id}">拿起来看</button><button data-act="unshelf" data-i="${it.id}">撤回托盘</button></div></article>`; }
      if (!V.cab && C.can(W, 'live')) h += `<article class="card"><div class="row"><b>直播间</b><span>粉丝 ${fmt(W.fans)}</span></div><div class="row"><span class="dim">${W.liveDay === W.day ? '今天已经播过了。' : '把托盘和柜台里的成品挂上去卖。当天切过石头再播，看的人更多。'}</span><button data-act="livego" class="pri" ${W.liveDay === W.day ? 'disabled' : ''}>开直播</button></div></article>`;
      if (!V.cab && W.event) h += `<p class="say">今日行情：${esc(W.event.t)}（${W.event.m > 1 ? '+' : ''}${Math.round((W.event.m - 1) * 100)}%）</p>`;
      if (!V.cab) { h += `<article class="card"><b>客户订单</b>${W.orders.map(o => `<div class="row dim"><span>${esc(C.orderText(o))}</span><span>加价 ${Math.round((o.bonus - 1) * 100)}% · 第 ${o.due} 天前</span></div>`).join('') || '<div class="row dim"><span>暂时没有订单</span></div>'}</article>`;
      for (const k of W.works) h += workCard(k); }
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
    if (!C.can(W, 'shop')) h += `<article class="card"><div class="row"><b>铺面</b><span class="dim">第四章解锁</span></div></article>`;
    if (C.can(W, 'chain')) h += `<article class="card"><div class="row"><b>分店与员工</b><span class="dim">分店 ${W.branches} 家 · 柜位共 ${C.slotsOf(W)}</span></div><div class="row"><span class="dim">每家分店多 10 个柜位、货更好卖，日租 ${C.BRANCH_RENT}。</span><button data-act="branch">开分店 ${fmt(C.BRANCH_COST)}</button></div>${Object.keys(C.STAFF).map(k => { const S = C.STAFF[k]; return `<div class="row"><span><b>${S.name} ${W.staff[k]}/${S.max}</b> <span class="dim">日薪 ${S.pay}。${S.tip}</span></span><span><button data-act="hire" data-k="${k}" data-d="-1" ${W.staff[k] ? '' : 'disabled'}>辞</button> <button data-act="hire" data-k="${k}" data-d="1" ${W.staff[k] >= S.max ? 'disabled' : ''}>雇</button></span></div>`; }).join('')}</article>`;
    if (C.can(W, 'shop')) { const S = C.SHOPLV[W.shop], nx = C.SHOPLV[W.shop + 1]; h += `<article class="card"><div class="row"><b>铺面：${S.name}</b><span class="dim">口碑 ${Math.round(W.fame)}</span></div>${W.shop ? `<div class="row dim"><span>日租 ${S.rent} · 柜位 ${C.shelfCount(W)}/${S.slots} · 零售价 ×${S.mult}</span></div>` : ''}${nx ? `<div class="row"><span class="dim">${nx.tip} 日租 ${nx.rent}。</span><button data-act="shopup">盘下${nx.name} ${fmt(nx.cost)}</button></div>` : ''}<div class="row dim"><span>熟客：${Object.keys(C.BUYERS).map(k => `${k} ${C.relWord(C.relOf(W, k))}`).join('，')}</span></div></article>`; }
    if (C.can(W, 'tools')) h += `<article class="card"><b>工具铺</b>${Object.keys(C.SHOP).map(k => { const S = C.SHOP[k], lv = W.tools[k], mx = lv >= S.levels.length; return `<div class="row"><span><b>${S.levels[lv - 1]}</b> <span class="dim">${S.tip}</span></span>${mx ? '<span class="dim">已是最好的</span>' : `<button data-act="tool" data-k="${k}">换${S.levels[lv]} ${fmt(S.price[lv - 1])}</button>`}</div>`; }).join('')}</article>`;
    h += `<article class="card"><div class="row"><b>${C.rankOf(W)}</b><span>眼力 ${W.eye} · 身家 ${fmt(C.netWorth(W))}</span></div><div class="row dim"><span>${C.RANKS.map(r => `${r[1]} ${r[0]}`).join(' → ')}</span></div><div class="achs">${C.ACH_ALL.map(a => { const g = W.ach[a[0]]; return `<span class="${g ? 'got' : ''}" title="${g ? '第 ' + g.day + ' 天达成' : '未达成'}">${g ? '★' : '☆'} ${a[1]}</span>`; }).join('')}</div><div class="row dim"><span>已达成 ${C.ACH_ALL.filter(a => W.ach[a[0]]).length} / ${C.ACH_ALL.length}</span></div></article>`;
    h += `<article class="card"><b>流水</b>${W.log.slice(-40).reverse().map(l => `<div class="row dim"><span>第 ${l.day} 天 ${esc(l.t)}</span><span>${l.amt ? (l.amt > 0 ? '+' : '') + fmt(l.amt) : ''}</span></div>`).join('')}</article>`;
  }
  el.innerHTML = h;
}
const HINTS = {
  rotate: '拖动转石头，滚轮或双指缩放。右键拖动在任何工具下都能转。',
  torch: '点或拖到石头上放灯，灯会留在原处。贴着压（离皮 0、倾斜 0）光进得最深；放斜贴着皮扫，裂和起伏最明显；抬高是照表面。',
  loupe: '移动放大镜看皮壳颗粒、松花、细裂和玉肉晶粒。把镜子移到一条线上，会标出它是哪种裂、还是不算裂的石纹。可以和手电一起用。',
  grind: '在石头上拖动磨皮开窗。同一处来回磨会越磨越深，磨掉的料回不来。',
  saw: '小锯取料：在看得清的面上圈出想要的那一块（比如色带），沿圈直着锯穿，把它单独取下来。圈会被拉成最多六条边的形状。',
  peel: '在石头上画一个圈，确认后圈里的皮会被整片切掉，只剥到刚露肉，不伤里面的料。圈越大切工越贵，想象空间也越少。',
  cut: '在石头上拖一条线，就是锯片走的位置；或者把想切的面转到正对自己，按厚度切一片。橙线是下刀处。',
};
function cutFromView() {
  const b = camBasis(), n = [-b.f[0], -b.f[1], -b.f[2]], inf = C.pieceInfo(V.e.vol, V.piece, n);
  V.cut = { n, d: inf.hi - V.cutT, base: inf.hi }; V.cut.pv = C.cutPreview(V.rec, V.piece, V.cut.n, V.cut.d);
}
function renderTools() {
  const own = V.mode === 'own' && V.piece && !V.piece.sold, tray = V.mode === 'tray';
  document.querySelectorAll('#tools button[data-tool]').forEach(b => { b.setAttribute('aria-pressed', b.dataset.tool === V.tool); b.disabled = ((b.dataset.tool === 'cut' || b.dataset.tool === 'saw') && !C.can(W, 'cut')) || ((b.dataset.tool === 'grind' || b.dataset.tool === 'cut' || b.dataset.tool === 'peel' || b.dataset.tool === 'saw') && !own) || (tray && b.dataset.tool !== 'rotate'); });
  let o = '';
  if (V.mode === 'review') o += `<label for="sec">剖面高度</label><input id="sec" type="range" min="${(-V.e.vol.hy).toFixed(0)}" max="${V.e.vol.hy.toFixed(0)}" step="0.5" value="${V.section}"><span class="dim">复盘：这是石头原本的内部</span>`;
  else if (V.tool === 'torch') o += `<label for="tTilt">倾斜 <b id="tTiltV">${V.torch.tilt}</b>°</label><input id="tTilt" type="range" min="0" max="85" step="5" value="${V.torch.tilt}"><label for="tAz">朝向</label><input id="tAz" type="range" min="0" max="360" step="15" value="${V.torch.az}"><label for="tH">离皮 <b id="tHV">${V.torch.h}</b> mm</label><input id="tH" type="range" min="0" max="60" step="2" value="${V.torch.h}"><button data-act="lbody" aria-pressed="${V.lampBody}">显示筒身</button><button data-act="toff" ${V.torch.on ? '' : 'disabled'}>关灯</button>`;
  else if (V.tool === 'peel' && own) o += V.peelPlan ? `<span class="dim">虚线圈是要切的范围。在石头旁的小框里确认或取消；右键拖动可以转着看。</span>` : `<button data-act="peelall" ${V.rec.peeled ? 'disabled' : ''}>${V.rec.peeled ? '已全去皮' : '全去皮'}</button><span class="dim">或在石头上画圈，只切圈里的皮。画完先预览，确认了才切。全去皮最干净，但想象空间也全没了。</span>`;
  else if (V.tool === 'saw' && own) o += V.sawPlan ? `<span class="dim">橙框是要取的范围。在石头旁的小框里调深度、确认或重画；右键拖动可以转着看。</span>` : `<button data-act="sawsmart">智能圈色</button><span class="dim">或自己在料上圈出要取的那一块。画完线先预览，确认了才锯。</span>`;
  else if (V.tool === 'grind') o += Object.keys(C.TOOLS).map(k => `<button data-act="burr" data-k="${k}" aria-pressed="${V.burr === k}">${k}</button>`).join('');
  else if (V.tool === 'cut' && own) {
    o += `<label for="cutT">片厚 <b id="cutV">${V.cutT}</b> mm</label><input id="cutT" type="range" min="3" max="60" step="1" value="${V.cutT}"><button data-act="cview">从正对我的面切这么厚</button>`;
    if (V.cut) o += `<select id="betSel" aria-label="和旁边的行家赌这一刀"><option value="">不赌</option><option value="up" ${V.bet === 'up' ? 'selected' : ''}>赌这刀切涨</option><option value="down" ${V.bet === 'down' ? 'selected' : ''}>赌这刀切垮</option></select><button data-act="cut" class="pri">下刀（切工 ${fmt(V.cut.pv.cost)}）</button><button data-act="ccancel">取消</button><span class="dim">两侧约 ${Math.round(V.cut.pv.a)} g / ${Math.round(V.cut.pv.b)} g</span>`;
  }
  if (tray && V.hold != null) o = `<button data-act="spin" aria-pressed="${!!V.spin}">慢慢转</button><button data-act="back" aria-pressed="${!!V.back}">打背光</button><button data-act="unhold" class="pri">放回托盘</button>`;
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
  [['牛叔：没本钱不要紧，先学看。按住石头拖着转，四面看一遍。', () => W.flags.orbit], ['牛叔：左下角那支手电，按住拖到石头上；再把右上角的灯关了，看光透出来多大一片。', () => W.flags.torch && W.flags.dark], ['牛叔：在右边写下你猜的种水、色、裂，然后点「看他切」。猜对种水，旁边的人输你彩头。', () => W.stat.watch > 0]],
  [['牛叔：有本钱了，挑一块便宜的，还个价买下来。看不准的不买；老板吆喝得越凶越要小心。', () => W.stones.length > 0], ['牛叔：用底下的「画圈开皮」开个小窗。窗口好看，报价就涨。', () => W.flags.open], ['牛叔：卖给出价最高的人。窗口漂亮的时候卖，常常比接着开划算。', () => W.stat.sold > 0]],
  [['牛叔：现在可以下刀了。选「大锯下刀」，在石头上拖一条线，再点下刀。', () => W.stat.cuts > 0], ['牛叔：切开的料，在右边「送去做件」里挑做什么、找谁做。', () => W.works.length > 0 || W.items.length > 0], ['牛叔：过几天成品做好，到「成品盘」里卖，或者交给客户订单。', () => W.items.some(i => i.state === 'sold')]],
  [['牛叔：到「账本」里盘一个铺面。', () => W.shop >= 1], ['牛叔：把成品或料头「摆进铺面」，散客会按零售价上门买。', () => C.shelfCount(W) > 0 || W.stat.shelfSold > 0]],
  [['牛叔：到「成品盘」点「开直播」。当天切过石头再播，看的人更多。', () => W.stat.live > 0]],
  [['牛叔：到「账本」里开分店、雇人。店员卖货，师傅做货，主播替你播。', () => W.branches > 0 || W.staff.clerk + W.staff.master + W.staff.host > 0]],
];
function coachUpdate() { const el = $('#coach'), key = 'tut' + (W ? W.chapter : 0), steps = W && COACH[W.chapter]; if (!W || !steps || W.flags[key] || W.flags.notut || V.mode === 'tray' && W.chapter < 2 || !$('#start').hidden) { el.hidden = true; return; }
  let i = 0; while (i < steps.length && steps[i][1]()) i++;
  if (i >= steps.length) { W.flags[key] = true; el.hidden = true; save(); return; }
  el.hidden = false; el.innerHTML = `<span>${esc(steps[i][0])}</span><small>${i + 1} / ${steps.length}</small><button data-act="skiptut">不用教了</button>`; }
function flag(k) { if (W && !W.flags[k]) { W.flags[k] = true; coachUpdate(); storyCheck(); } }
function storyCheck() { if (!$('#story').hidden) return; const ch = C.checkStory(W); if (!ch) return; W.flags.notut = false; save(); Snd.win(); const nx = C.CHAPTERS[W.chapter];
  $('#storybody').innerHTML = `<h2>${ch.title} · 完成</h2><p>${esc(ch.done)}</p><p class="say">眼力 +${ch.reward.eye}${ch.reward.cash ? `，到手 ${fmt(ch.reward.cash)}` : ''}${ch.unlock ? `。解锁：${ch.unlock}` : ''}</p>${nx ? `<h3>${nx.title}</h3><p>${esc(nx.story)}</p><ul>${nx.goals.map(g => `<li>${g[1]}</li>`).join('')}</ul>` : '<p>主线完成。生意可以一直做下去。</p>'}<button data-act="storyok" class="pri">继续</button>`;
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
  h += `<div class="seller"><button class="bubble" data-act="npcnext" title="再听听老板怎么说">${esc(say)}</button>${(() => { const F = window.JADE_FACES || {}, ks = ['n0', 'n1', 'n2', 'n3', 'n4', 'n5'], k = ks[(L.auction ? 3 : L.channel.charCodeAt(0) + L.channel.length + (W.scene || '').length) % ks.length]; return F[k] ? `<span class="ph" style="width:84px;height:94px;margin-bottom:10px"><img src="${F[k]}" alt=""></span>` : npcSvg(lk[0], lk[1], 92); })()}<b>${L.auction ? '公盘主持' : L.channel === '个人转让' ? '卖家' : '老板'} · ${L.channel}</b></div>`;
  if (el.dataset.say === say) { el.innerHTML = h; return; } el.dataset.say = say; el.innerHTML = h;
  const bub = el.querySelector('.bubble'); clearInterval(renderNpc.t); let n = 0; bub.textContent = ''; renderNpc.t = setInterval(() => { n += 2; bub.textContent = say.slice(0, n); if (n >= say.length) clearInterval(renderNpc.t); }, 40); } // 话是一个字一个字说出来的
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
    h = ''; V.lensAll = true; for (const [nm, gr, tx] of [['粗砂', 0.95, '颗粒大、松、扎手。里面晶粒通常也粗：豆种居多'], ['中砂', 0.55, '颗粒看得见但排得紧。糯种到糯冰'], ['细砂', 0.22, '颗粒要凑近才看得出，摸着像细砂纸。种老的相'], ['蜡壳、极细', 0.05, '几乎看不到颗粒，表面发亮像打了蜡。常见于老坑高种']]) { const s3 = mk(); s3.w0 = 0.4; s3.skin = { name: '黄砂皮', col: C.SKINS['黄砂皮'].col, grain: gr, sig: 0.7, weather: 0.35, t: 1.6, phase: 3 }; const v3 = C.bake(s3, 44); V.mode = 'own'; V.rec = null; V.piece = C.WHOLE; V.e = { st: s3, vol: v3 }; V.lens = null; V.room = true; cam.yaw = 0.5; cam.pitch = 0.3; cam.t = [0, 0, 0]; cam.dist = Math.max(v3.hx, v3.hy, v3.hz) * 1.3; V.torch = { on: false, p: null, n: null }; loaded = null; render(1, 168);
      h += `<figure><img src="${canvas.toDataURL('image/jpeg', 0.85)}" alt="${nm}"><figcaption><b>${nm}</b><span>${tx}</span></figcaption></figure>`; } V.lensAll = false;
    $('#grainAtlas').innerHTML = h;
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
    if (i >= CASES.length || $('#help').hidden || $('#help [data-pane=atlas]').hidden) { restore(); if (i < CASES.length) casesStarted = false; return; }
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
function showPane(k) { document.querySelectorAll('#help [data-pane]').forEach(x => x.hidden = x.dataset.pane !== k); document.querySelectorAll('#help [data-act=pane]').forEach(x => x.setAttribute('aria-pressed', x.dataset.k === k)); if (k === 'skin' || k === 'water') buildAtlas(); if (k === 'atlas') buildCases(); if (k === 'crack') buildCracks(); if (k === 'fake') buildFakes(); }

/* 裂图鉴：每种裂拍四张——皮上、隔皮压灯、切开、切面压灯 */
const CRK = [
  ['通天大裂', '整块贯穿的大裂。皮上是一条带锈边的黑线，能绕石头一圈。压灯时光走到裂面就停，一边亮一边暗。切开是一条贯通的暗线，靠皮的一段被水和铁锈沁黄。沿着它下刀把料分成两半，两半各自还能用；横跨它的镯位全废。', (a, r, u) => [['through', [0, 0, 0], [r[0] + u[0] * 0.2, r[1] + u[1] * 0.2, r[2] + u[2] * 0.2], a * 1.6, 1, 1]]],
  ['皮上起头的裂', '风化从外往里，多数裂都是从皮上起头，往里吃一截就停。皮上看得到线，压灯时裂挡住的只是靠皮的一片。切开看它吃了多深：浅的磨掉一层就没了，深的要让开它取料。', (a, r, u) => [['edge', [u[0] * a * 0.62, u[1] * a * 0.62, u[2] * a * 0.62], r, a * 0.55, 1, 1]]],
  ['隐裂（皮上看不见）', '皮厚或者皮色深，裂在皮上不露头。只有压灯才能发现：光晕里突然一条明暗分界。全蒙头的料最怕这个，所以要多换几个位置、几个方向压灯。', (a, r, u) => [['through', [r[0] * 6, r[1] * 6, r[2] * 6], [r[0] - u[0] * 0.25, r[1] - u[1] * 0.25, r[2] - u[2] * 0.25], a * 1.5, 1, 0]]],
  ['小绺、碎裂', '一组方向差不多的短裂，是同一次受力留下的。单条不深，但挤在一起这一片就取不出整料，只能做小件、珠子，或者用雕工把它们藏进纹路里。', (a, r, u) => [-2, -1, 0, 1, 2].map(k => ['hair', [r[0] * k * 7 + u[0] * (k % 2 ? 9 : -6), r[1] * k * 7 + u[1] * (k % 2 ? 9 : -6), r[2] * k * 7 + u[2] * (k % 2 ? 9 : -6)], [r[0] + u[0] * 0.12 * k, r[1] + u[1] * 0.12 * k, r[2] + u[2] * 0.12 * k], a * 0.26, 1, 0])],
  ['石纹（愈合的裂）', '很早以前裂开过，后来又被矿物长死了。切面上是一条发白的线，没有黑缝，不挡光，指甲划过去不卡。不算裂，对取料影响很小，只是不好看。别把它当成裂吓得贱卖。', (a, r, u) => [['healed', [0, 0, 0], [r[0] + u[0] * 0.3, r[1] + u[1] * 0.3, r[2] + u[2] * 0.3], a * 1.4, 0.2, 0]]],
  ['十字裂', '两组方向的裂交叉，把料分成几小块。每一块都小，出不了镯子，只能按小件算价。看到皮上两条裂相交，就别按整料的价钱去想了。', (a, r, u) => [['through', [0, 0, 0], r, a * 1.6, 1, 1], ['through', [0, 0, 0], [u[0] + r[0] * 0.15, u[1] + r[1] * 0.15, u[2] + r[2] * 0.15], a * 1.6, 1, 1]]],
];
let cracksStarted = false;
function buildCracks() {
  if (cracksStarted) return; cracksStarted = true;
  const host = $('#crackAtlas'); host.innerHTML = '';
  const keep = { mode: V.mode, rec: V.rec, piece: V.piece, e: V.e, torch: V.torch, room: V.room, lens: V.lens, cam: { yaw: cam.yaw, pitch: cam.pitch, dist: cam.dist, t: cam.t } };
  const restore = () => { V.mode = keep.mode; V.rec = keep.rec; V.piece = keep.piece; V.e = keep.e; V.torch = keep.torch; V.room = keep.room; V.lens = keep.lens; Object.assign(cam, keep.cam); loaded = null; invalidate(false); };
  const nrm = v => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; }, crs = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  let i = 0;
  const step = () => {
    if (i >= CRK.length || $('#help').hidden || $('#help [data-pane=crack]').hidden) { restore(); if (i < CRK.length) cracksStarted = false; return; }
    const [name, text, make] = CRK[i++];
    try {
      const st = C.genStone(515151, '木那', '二级供应商'); st.dirt = []; st.shift = null; st.wVar = 0; st.cot = 0.18; st.planes = []; st.fog = { t: 0, col: [1, 1, 1] }; st.body = '白底'; st.w0 = 0.5; st.feats = [];
      st.skin = { name: '黄砂皮', col: C.SKINS['黄砂皮'].col, grain: 0.78, sig: 0.75, weather: 0.45, t: 1.6, phase: 3 };
      V.mode = 'own'; V.rec = null; V.lens = null; cam.yaw = 0.5; cam.pitch = 0.3; cam.t = [0, 0, 0]; const b = camBasis();
      st.cracks = make(st.rad[0], b.r, b.up).map((c, k) => { const n = nrm(c[2]); return { kind: c[0], c: c[1], n, t1: nrm(crs(n, [0.31, 0.87, 0.38])), R: c[3], warp: 1.3, freq: 0.06, phase: 1 + k * 1.7, open: c[4], skinVis: c[5] }; });
      const vol = C.bake(st, 44), R0 = Math.max(vol.hx, vol.hy, vol.hz); V.e = { st, vol }; loaded = null;
      const shot = (torch, piece, dist) => { V.piece = piece; V.room = !torch; cam.dist = R0 * dist; const bb = camBasis(); V.torch = { on: false, p: null, n: null };
        if (torch) { const o = [0, 1, 2].map(k => bb.pos[k] - bb.r[k] * R0 * 0.42), h = C.pick(vol, piece, o, bb.f); if (h) V.torch = { on: true, p: h.p, n: h.n, dir: h.n, h: 0 }; }
        const lb = V.lampBody; V.lampBody = false; render(1, 176); V.lampBody = lb; return canvas.toDataURL('image/jpeg', 0.85); };
      const cut = { planes: [[-b.f[0], -b.f[1], -b.f[2], 0]] };
      const imgs = [['皮上', shot(false, C.WHOLE, 3.0)], ['隔着皮压灯', shot(true, C.WHOLE, 3.4)], ['切开', shot(false, cut, 3.2)], ['切面压灯', shot(true, cut, 3.2)]];
      host.insertAdjacentHTML('beforeend', `<article class="case"><div class="row"><b>${name}</b></div><div class="four">${imgs.map(x => `<figure><img src="${x[1]}" alt="${name}${x[0]}"><figcaption>${x[0]}</figcaption></figure>`).join('')}</div><p>${text}</p></article>`);
    } catch (e) { host.insertAdjacentHTML('beforeend', `<p class="note">${name} 的图没拍出来：${e.message}</p>`); }
    $('#crackProg').textContent = i < CRK.length ? `正在拍第 ${i + 1} / ${CRK.length} 组…` : '';
    setTimeout(step, 30);
  };
  setTimeout(step, 30);
}
/* 假料图鉴：每种假料和真料并排，各拍四张 */
const FAKES = [
  ['染色做皮（假松花）', 'paint', ['皮上远看', '放大镜看皮', '隔着皮压灯', '切开'], '皮上一身绿斑，卖家说是“松花”，是满色料的相。真松花是里面的色顶到皮上来的：颜色有深有浅，藏在砂粒之间，压灯时附近透出绿光。染的松花是刷上去的：放大镜下色块平、边缘齐、盖在砂粒上面没有颗粒感；压灯时光是白的，一点绿都透不出来。切开，真的里面有色，假的一片白。'],
  ['贴片假窗', 'veneer', ['窗口', '放大镜看窗口', '对着窗口压灯', '切开'], '窗口看上去种好色好，其实是在差料上挖个坑，贴了一片好料。放大镜沿着窗口边缘找：真窗口是皮到肉自然过渡，贴片的窗口边上有一圈黄色胶线。压灯时光只在薄薄一片里亮，透不到周围。切开后好料只有两三毫米厚，后面全是差料。'],
  ['窗口上色', 'dye', ['窗口', '放大镜看窗口', '对着窗口压灯', '切开'], '窗口是真开的，但窗面上染了绿。远看绿得又匀又艳，没有深浅变化。放大镜下，真色是从里面透出来的，有色根，浓淡过渡自然；染的色沿着晶粒之间的缝隙走，像一张绿色的网，晶粒中间反而是白的。往里磨一点，或者切开，色就没了。'],
];
let fakesStarted = false;
function buildFakes() {
  if (fakesStarted) return; fakesStarted = true;
  const host = $('#fakeAtlas'); host.innerHTML = '';
  const keep = { mode: V.mode, rec: V.rec, piece: V.piece, e: V.e, torch: V.torch, room: V.room, lens: V.lens, cam: { yaw: cam.yaw, pitch: cam.pitch, dist: cam.dist, t: cam.t } };
  const restore = () => { V.fakeT = null; V.lensAll = false; V.mode = keep.mode; V.rec = keep.rec; V.piece = keep.piece; V.e = keep.e; V.torch = keep.torch; V.room = keep.room; V.lens = keep.lens; Object.assign(cam, keep.cam); loaded = null; invalidate(false); };
  const jobs = []; for (const f of FAKES) { jobs.push([f, false]); jobs.push([f, true]); } let i = 0, rowHtml = '';
  const step = () => {
    if (i >= jobs.length || $('#help').hidden || $('#help [data-pane=fake]').hidden) { restore(); if (i < jobs.length) fakesStarted = false; return; }
    const [[name, type, caps, text], fake] = jobs[i++];
    try {
      const st = C.genStone(515151, '木那', '二级供应商'); st.cracks = []; st.dirt = []; st.shift = null; st.wVar = 0; st.cot = 0.2; st.planes = []; st.fog = { t: 0, col: [1, 1, 1] }; st.body = '白底'; st.hue = '阳绿'; st.feats = [];
      st.w0 = fake ? (type === 'veneer' ? 0.18 : 0.4) : 0.55; if (!fake) st.feats.push({ type: 'full', strength: 0.85, seed: 77, c: [0, 0, 0] });
      st.skin = { name: '黄砂皮', col: C.SKINS['黄砂皮'].col, grain: 0.78, sig: 0.75, weather: 0.45, t: 1.6, phase: 3 };
      const vol = C.bake(st, 44), R0 = Math.max(vol.hx, vol.hy, vol.hz);
      V.mode = 'own'; V.rec = null; V.e = { st, vol }; V.lens = null; cam.yaw = 0.5; cam.pitch = 0.3; cam.t = [0, 0, 0]; cam.dist = R0 * 3.4; const b = camBasis();
      if (type !== 'paint') { const h = C.pick(vol, C.WHOLE, b.pos, b.f), sk = C.sampleG(vol, 2, h.p[0], h.p[1], h.p[2]), sp = [];
        for (const [dx, dy] of [[0, 0], [7, 2], [-7, -1], [1, 7], [-2, -7]]) { const q = [0, 1, 2].map(k => h.p[k] + b.r[k] * dx + b.up[k] * dy), rr = C.pick(vol, C.WHOLE, [q[0] - b.f[0] * 300, q[1] - b.f[1] * 300, q[2] - b.f[2] * 300], b.f); if (rr) { const c = [0, 1, 2].map(k => rr.p[k] + rr.n[k] * (9 - sk - 1.3)); C.carve(vol, C.WHOLE, c[0], c[1], c[2], 9); sp.push(c[0], c[1], c[2], 9); } }
        if (fake) (type === 'veneer' ? C.veneer : C.dyeWin)(vol, sp); }
      loaded = null; V.fakeT = fake ? { paint: 1, veneer: 2, dye: 3 }[type] : 0;
      const shot = (torch, piece, dist, lens) => { V.piece = piece; V.room = !torch; V.lensAll = !!lens; cam.dist = R0 * dist; const bb = camBasis(); V.torch = { on: false, p: null, n: null };
        if (torch) { const h = C.pick(vol, piece, bb.pos, bb.f); if (h) V.torch = { on: true, p: h.p, n: h.n, dir: h.n, h: 0 }; }
        const lb = V.lampBody; V.lampBody = false; render(1, 176); V.lampBody = lb; V.lensAll = false; return canvas.toDataURL('image/jpeg', 0.85); };
      const cut = { planes: [[-b.f[0], -b.f[1], -b.f[2], 0]] }, near = type === 'paint' ? 3.2 : 2.3;
      const imgs = [shot(false, C.WHOLE, near), shot(false, C.WHOLE, 1.25, true), shot(true, C.WHOLE, type === 'paint' ? 3.5 : 2.6), shot(false, cut, 3.3)];
      rowHtml += `<div class="row"><b class="${fake ? 'say' : ''}" style="min-width:2.5em">${fake ? '假' : '真'}</b></div><div class="four">${imgs.map((x, k) => `<figure><img src="${x}" alt="${name}${fake ? '假' : '真'}${caps[k]}"><figcaption>${caps[k]}</figcaption></figure>`).join('')}</div>`;
      if (fake) { host.insertAdjacentHTML('beforeend', `<article class="case"><div class="row"><b>${name}</b></div>${rowHtml}<p>${text}</p></article>`); rowHtml = ''; }
    } catch (e) { host.insertAdjacentHTML('beforeend', `<p class="note">${name} 的图没拍出来：${e.message}</p>`); rowHtml = ''; }
    $('#fakeProg').textContent = i < jobs.length ? `正在拍第 ${Math.floor(i / 2) + 1} / ${FAKES.length} 组…` : '';
    setTimeout(step, 30);
  };
  setTimeout(step, 30);
}
/* Esc：关掉最上面一层打开的东西 */
addEventListener('keydown', ev => { if (ev.key !== 'Escape') return; const open = id => $(id) && !$(id).hidden; let done = true;
  if (open('#saves')) $('#saves').hidden = true;
  else if (V.peelPlan) { V.peelPlan = null; showLasso(null); $('#sawbox').hidden = true; renderTools(); }
  else if (open('#help')) $('#help').hidden = true;
  else if (open('#confirm')) $('#confirm').hidden = true;
  else if (open('#story')) { const bs = $('#storybody').querySelectorAll('button'); if (bs.length === 1) bs[0].click(); else done = false; }
  else if (open('#live')) { const x = $('#live [data-act=liveend]'); if (x) x.click(); else done = false; }
  else if (open('#sawbox')) { const x = document.querySelector('[data-act=sawno]'); if (x) x.click(); else done = false; }
  else { const x = document.querySelector('[data-act=trayback],[data-act=ccancel],[data-act=codeclose],[data-act=pback]'); if (x && x.offsetParent) x.click(); else if (V.lens || V.cut) { V.lens = null; V.cut = null; renderTools(); invalidate(false); } else done = false; }
  if (done) ev.preventDefault(); });
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
  if (b.dataset.tool) { if ($('#crlabel')) $('#crlabel').hidden = true; V.tool = b.dataset.tool; V.lens = null; V.cut = null; V.sawPlan = null; V.peelPlan = null; showLasso(null); $('#sawbox').hidden = true; V.note = ''; renderTools(); invalidate(false); return; }
  const a = b.dataset.act;
  if (a !== 'menu') $('#hmenu').classList.remove('open');
  if (a === 'listing') { if (ev.target.closest('.bargain')) return; const L = W.market[+b.dataset.i]; V.offer = 0; if (V.rec !== L) view('market', L, null); }
  else if (a === 'offer' || a === 'take') {
    const L = V.rec, offer = a === 'take' ? L.ask : +($('#offer').value || 0); V.offer = offer;
    const sh = V.partner && L.ask >= 8000 ? 0.5 : 1, r = C.negotiate(W, L, offer, sh); V.msg = r.msg;
    if (r.res === 'deal') { Snd.coin(); const s = C.buy(W, L, r.price, sh); V.partner = false; tab = 'mine'; view('own', s, s.pieces[0]); refreshQuote(s, s.pieces[0], true); save(); V.note = `成交 ${fmt(r.price)}。可以直接询价转手，也可以开窗、下刀或送加工。`; renderAll(); return; }
    save(); renderSide(); renderNpc();
  }
  else if (a === 'piece') { const s = W.stones.find(x => x.id === +b.dataset.s), p = s.pieces.find(x => x.id === +b.dataset.p); view('own', s, p); if (!s.last[p.id]) refreshQuote(s, p); renderAll(); }
  else if (a === 'sell') { const s = V.rec, p = V.piece, q = getQuotes(s, p).list.find(o => o.buyer === b.dataset.b); C.sell(W, s, p, q); Snd.coin(); qcache.clear(); save(); afterStoneChange(s); }
  else if (a === 'layout') { V.layoutOn = !V.layoutOn; V.layoutKey = null; renderSide(); invalidate(false); }
  else if (a === 'prop') { V.wk.route = b.dataset.r; V.wk.theme = b.dataset.t; renderTools(); renderSide(); drawLayout(); }
  else if (a === 'learn') { const r = C.learnSkill(W, b.dataset.k); V.note = r.msg; if (r.ok) Snd.win(); save(); renderAll(); }
  else if (a === 'issue') { const r = C.resolveIssue(W, +b.dataset.id, +b.dataset.i); if (!r.ok) return; if (r.win) Snd.win(); save(); V.note = r.msg; $('#storybody').innerHTML = `<h2>${r.win ? '成了' : '没成'}</h2><p>${esc(r.msg)}</p><button data-act="storyok" class="pri">知道了</button>`; $('#story').hidden = false; renderAll(); }
  else if (a === 'work') { const s = V.rec, K = V.wk, r = C.sendWork(W, s, V.piece, K.route, K.master, K.theme, K.route === 'cab' && K.cabKey === s.id + ':' + V.piece.id ? { cabMult: K.cabMult } : null); if (!r.ok) { V.note = r.msg; renderTools(); return; } qcache.clear(); save(); afterStoneChange(s); V.note = `已送去，工费 ${fmt(r.fee)}，${r.days} 天后到托盘取成品。`; renderTools(); }
  else if (a === 'scene') { C.enterScene(W, b.dataset.k); save(); Snd.tap(); Snd.amb(b.dataset.k); view('market', W.market.find(L => !L.sold) || null, null); }
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
  else if (a === 'peelgo') { doPeel(); }
  else if (a === 'peelno') { V.peelPlan = null; showLasso(null); $('#sawbox').hidden = true; V.note = ''; renderTools(); }
  else if (a === 'peelall') { if (b.dataset.sure !== '1') { b.dataset.sure = '1'; b.textContent = `整块的皮都剥掉，花 ${fmt(C.peelAllCost(V.rec))}，回不去。再点一次确认`; return; } const r = C.peelAll(W, V.rec); if (!r.ok) { V.note = r.msg; renderTools(); return; } flag('open'); loaded = null; qcache.clear(); Snd.saw(); refreshQuote(V.rec, V.piece, true); save(); V.note = `全去皮完成，花费 ${fmt(r.cost)}。里面什么样，现在谁都看得见了。`; renderAll(); }
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
  else if (a === 'spin') { V.spin = !V.spin; renderTools(); clearInterval(V.spinT); if (V.spin) V.spinT = setInterval(() => { if (V.hold == null || V.mode !== 'tray') { clearInterval(V.spinT); V.spin = false; return; } cam.yaw += 0.035; render(0.7); }, 70); else invalidate(false); }
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
  else if (a === 'watch') { const L = V.rec, g = V.wg || {}; if (g.water == null) { V.msg = '先选一个种水再看。'; renderSide(); return; } const r = C.watch(W, L, { water: g.water, color: g.color || 'none', crack: g.crack || 'few' }); if (!r.ok) { V.msg = r.msg; renderSide(); return; }
    V.wg = null; Snd.saw(); save(); L.id = '围观'; const nm = ['豆种', '糯种', '糯冰种', '冰种', '高冰种', '玻璃种'], cn = { none: '基本无色', skin: '只有贴皮色', deep: '色吃进去了', full: '满色' };
    $('#storybody').innerHTML = `<h2>他一刀切开了</h2><p>实际是：<b>${nm[r.water]}</b>，${cn[r.color]}，${r.crack === 'few' ? '裂少' : '裂多'}。${r.fake ? '而且这是一块假料：' + r.fake + '。' : ''}</p><p>你猜的是：${nm[g.water]}，${cn[g.color || 'none']}，${(g.crack || 'few') === 'few' ? '裂少' : '裂多'}。</p><p class="say">眼力 +${r.pts}${r.tip ? `；种水猜对了，旁边的人输给你 ${r.tip} 块彩头` : ''}</p><p class="note">关掉这个框后可以拖动「剖面高度」看这块石头里面到底什么样，和你刚才打灯看到的对一对。</p><button data-act="storyok" class="pri">看剖面</button>`;
    $('#story').hidden = false; view('review', L, null); }
  else if (a === 'livego') { const r = C.liveRun(W); if (!r.ok) { V.note = r.msg; renderTools(); renderSide(); return; } save(); const box = $('#livechat'); box.innerHTML = ''; $('#liveview').textContent = r.viewers + ' 人在看'; $('#liveend').hidden = true; $('#live').hidden = false;
    r.lines.forEach((ln, i) => setTimeout(() => { const d = document.createElement('p'); d.className = ln[0]; d.textContent = ln[0] === 'c' ? '观众：' + ln[1] : ln[1]; box.appendChild(d); box.scrollTop = box.scrollHeight; if (ln[0] === 'sys' && i) Snd.coin(); if (i === r.lines.length - 1) $('#liveend').hidden = false; }, 350 + i * 520)); }
  else if (a === 'liveend') { $('#live').hidden = true; openTray(false, false); }
  else if (a === 'branch') { const r = C.openBranch(W); V.note = r.msg; if (r.ok) Snd.coin(); save(); renderAll(); }
  else if (a === 'hire') { const r = C.hire(W, b.dataset.k, +b.dataset.d); V.note = r.msg; save(); renderAll(); }
  else if (a === 'train') { const r = C.trainKid(W, +b.dataset.i, $('#kT' + b.dataset.i).value); V.note = r.msg; if (r.ok) Snd.coin(); save(); renderAll(); }
  else if (a === 'baby') { const r = C.haveBaby(W, b.dataset.k === 'lover'); V.note = r.msg; if (r.ok) Snd.win(); save(); renderAll(); }
  else if (a === 'divorce') { if (b.dataset.sure !== '1') { b.dataset.sure = '1'; b.textContent = '再点一次确认：' + b.textContent; return; } const r = C.divorce(W, b.dataset.k === '1', V.law || 0); V.note = r.msg; save(); renderAll(); }
  else if (a === 'marry') { const r = C.marry(W); V.note = r.msg; if (r.ok) Snd.win(); save(); renderAll(); }
  else if (a === 'affair') { const r = C.startAffair(W); V.note = r.msg; save(); renderAll(); }
  else if (a === 'affairend') { const r = C.endAffair(W); V.note = r.msg; save(); renderAll(); }
  else if (a === 'rest') { C.restDay(W); Snd.tap(); V.note = '今天不出摊，陪家里人。身体和家和都回来一些。'; save(); renderSide(); renderTools(); }
  else if (a === 'asset') { const r = C.buyAsset(W, b.dataset.k, +b.dataset.i); V.note = r.msg; if (r.ok) Snd.coin(); save(); renderAll(); }
  else if (a === 'borrow') { const r = C.borrow(W, b.dataset.t, +b.dataset.a); V.note = r.msg; if (r.ok) Snd.coin(); save(); renderAll(); }
  else if (a === 'repay') { const r = C.repay(W, +b.dataset.i); V.note = r.msg; if (r.ok) Snd.coin(); save(); renderAll(); }
  else if (a === 'evopt') { const r = C.applyEvent(W, V.lifeEv, +b.dataset.i); if (!r.ok) { $('#evmsg').textContent = r.msg; return; } save(); V.lifeEv = null; if (r.note) { $('#storybody').innerHTML = `<h2>后来</h2><p>${esc(r.note)}</p><button data-act="storyok" class="pri">知道了</button>`; } else $('#story').hidden = true; renderAll(); }
  else if (a === 'skiptut') { W.flags.notut = true; save(); renderAll(); }
  else if (a === 'storyok') { $('#story').hidden = true; renderAll(); }
  else if (a === 'storyshow') { const ch = C.CHAPTERS[W.chapter]; $('#storybody').innerHTML = `<h2>${ch.title}</h2><p>${esc(ch.story)}</p><ul>${ch.goals.map(g => `<li>${C.goalDone(W, g[0]) ? '✔ ' : ''}${g[1]}</li>`).join('')}</ul><button data-act="storyok" class="pri">知道了</button>`; $('#story').hidden = false; }
  else if (a === 'debt') { const r = C.payDebt(W); V.note = r.msg; if (r.ok) Snd.coin(); save(); renderAll(); }
  else if (a === 'startgo') { $('#start').hidden = true; Snd.tap(); Snd.amb(W.scene); renderAll(); }
  else if (a === 'startnew') { C.volCache.clear(); thumbs.clear(); qcache.clear(); loaded = null; W = C.newWorld((Date.now() ^ (Math.random() * 1e9)) >>> 0); save(); tab = 'market'; $('#start').hidden = true; Snd.amb('夜市地摊'); view('market', W.market.find(L => !L.sold && !L.fake) || W.market[0], null); const ch = C.CHAPTERS[0]; $('#storybody').innerHTML = `<h2>${ch.title}</h2><p>${esc(ch.story)}</p><ul>${ch.goals.map(g => `<li>${g[1]}</li>`).join('')}</ul><button data-act="storyok" class="pri">去夜市蹲着</button>`; $('#story').hidden = false; }
  else if (a === 'starthelp') { $('#start').hidden = true; $('#help').hidden = false; showPane('play'); renderAll(); }
  else if (a === 'home') { showStart(); }
  else if (a === 'saves') { renderSaves(); $('#saves').hidden = false; }
  else if (a === 'savesclose') { $('#saves').hidden = true; }
  else if (a === 'slotsave') { try { const o = JSON.parse(C.serialize(W)); o.savedAt = new Date().toLocaleString(); localStorage.setItem('jade-slot-' + b.dataset.i, JSON.stringify(o)); renderSaves('已存到存档位 ' + b.dataset.i + '。'); } catch (e) { renderSaves('存不进去：浏览器不让写，或者空间满了。用「导出」留一份。'); } }
  else if (a === 'slotdel') { if (b.dataset.sure !== '1') { b.dataset.sure = '1'; b.textContent = '再点一次确认'; return; } try { localStorage.removeItem('jade-slot-' + b.dataset.i); } catch (e) { } renderSaves('已删除。'); }
  else if (a === 'slotload') { if (b.dataset.sure !== '1') { b.dataset.sure = '1'; b.textContent = '会覆盖当前进度，再点一次'; return; } try { const w = parseSave(localStorage.getItem(b.dataset.i === 'bak' ? 'jade-save-bak' : 'jade-slot-' + b.dataset.i)); if (w) { useWorld(w); V.note = '已读取存档。'; renderTools(); } else renderSaves('这个存档读不出来。'); } catch (e) { renderSaves('这个存档读不出来。'); } }
  else if (a === 'savetext') { $('#saveText').value = C.serialize(W); $('#saveText').select(); $('#saveMsg').textContent = '全选复制，存到备忘录或发给自己。'; }
  else if (a === 'saveexport') { try { const u = URL.createObjectURL(new Blob([C.serialize(W)], { type: 'application/json' })), l = document.createElement('a'); l.href = u; l.download = `翡翠博弈存档-第${W.day}天.json`; document.body.appendChild(l); l.click(); l.remove(); setTimeout(() => URL.revokeObjectURL(u), 2000); $('#saveMsg').textContent = '如果没有开始下载，用「显示成文字」复制。'; } catch (e) { $('#saveMsg').textContent = '这里不让下载文件，用「显示成文字」复制。'; } }
  else if (a === 'saveimport') { try { const w = parseSave($('#saveText').value.trim()); if (w) { useWorld(w); V.note = '已导入存档。'; renderTools(); } else $('#saveMsg').textContent = '这段文字不是存档。'; } catch (e) { $('#saveMsg').textContent = '这段文字不是存档，或者不完整。'; } }
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
    rv.className = 'sawing'; rv.innerHTML = '<p>锯片吃进去了…</p>'; rv.hidden = false; Snd.saw(); canvas.classList.add('shake'); if (navigator.vibrate) try { navigator.vibrate([40, 30, 40, 30, 80]); } catch (e) { }
    V.sawing = 1; const fx = setInterval(() => { V.sawing++; render(Q.fast); }, 110); setTimeout(() => { clearInterval(fx); V.sawing = 0; canvas.classList.remove('shake'); }, 1100);
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
  else if (a === 'next') { if (!licensed() && W.day >= CFG.trialDays) { $('#codeMsg').textContent = `试玩到第 ${CFG.trialDays} 天为止。输入激活码后可以接着这个存档一直玩下去。`; $('#paywall').hidden = false; return; } const n = C.nextDay(W); qcache.clear(); for (const s of W.stones) if (!s.closed) for (const p of s.pieces) if (!p.sold && C.volCache.get(s.seed)) refreshQuote(s, p, true); save(); const fresh = W.items.some(i => i.state === 'ready'); tab = 'market'; view(null, null, null); V.note = `第 ${W.day} 天。${n.join('，')}。货源已更新，昨天的报价作废。`; renderTools(); dayCard(n); Snd.amb(W.scene);
    { const kk = W.works.find(k => C.issueOf(W, k)); if (kk) setTimeout(() => { if (!$('#story').hidden) return; $('#storybody').innerHTML = `<h2>师傅来电话</h2><div class="people">${faceSvg({ kind: 'master', mname: kk.master, seed: kk.master.charCodeAt(0), cloth: '#4a4a44' }, 84)}</div><p class="dim">${esc(kk.from)} · ${esc(kk.what)}</p>${issueHtml(kk, C.issueOf(W, kk))}<button data-act="storyok">先放着，回头再定</button>`; $('#story').hidden = false; }, 5200); }
    const lev = C.lifeEvent(W); if (lev) setTimeout(() => { if (!$('#story').hidden) return; V.lifeEv = lev; $('#storybody').innerHTML = `<h2>家里的事</h2>${(() => { const f = W.fam, k = f.kids.find(x => lev.text.indexOf(x.name) >= 0); return '<div class="people">' + (f.lover && lev.text.indexOf(f.lover.name) >= 0 && !lev.cuck ? faceSvg({ kind: 'lover', seed: f.lover.name.charCodeAt(1), cloth: '#8a2f45' }, 84) : '') + (f.wife && lev.text.indexOf(f.wife) >= 0 ? faceSvg({ kind: 'wife', seed: f.wife.charCodeAt(0) + f.wife.charCodeAt(1), sad: f.har < 35 || lev.cuck || f.caught }, 84) : '') + (k ? kidFace(k, 84) : '') + '</div>'; })()}<p>${esc(lev.text)}</p><p id="evmsg" class="say"></p>${lev.opts.map((o, i) => `<button data-act="evopt" data-i="${i}">${esc(o.label)}</button>`).join('')}`; $('#story').hidden = false; }, 2400); if (fresh && n.some(x => x.includes('做好了'))) { openTray(false); V.note = n.filter(x => x.includes('做好了')).join('；'); renderTools(); } }
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
  if (ev.target.id === 'wW' || ev.target.id === 'wC' || ev.target.id === 'wK') { const w0 = $('#wW').value; V.wg = { water: w0 === '' ? null : +w0, color: $('#wC').value, crack: $('#wK').value }; }
  if (ev.target.id === 'saveFile' && ev.target.files[0]) { const fr = new FileReader(); fr.onload = () => { try { const w = parseSave(String(fr.result)); if (w) { useWorld(w); V.note = '已导入存档。'; renderTools(); } else $('#saveMsg').textContent = '这个文件不是存档。'; } catch (e) { $('#saveMsg').textContent = '这个文件不是存档。'; } }; fr.readAsText(ev.target.files[0]); }
  if (ev.target.id === 'dvLaw') { V.law = +ev.target.value; }
  if (ev.target.id === 'fFood') { W.fam.food = +ev.target.value; save(); renderSide(); }
  if (/^kS\d+$/.test(ev.target.id)) { const r = C.setSchool(W, +ev.target.id.slice(2), ev.target.value); V.note = r.msg; save(); renderSide(); renderTools(); }
  if (/^kJ\d+$/.test(ev.target.id)) { C.setJob(W, +ev.target.id.slice(2), ev.target.value); save(); renderSide(); }
  if (ev.target.id === 'wkRoute' || ev.target.id === 'wkMaster' || ev.target.id === 'wkTheme') { V.wk[{ wkRoute: 'route', wkMaster: 'master', wkTheme: 'theme' }[ev.target.id]] = ev.target.value; renderSide(); drawLayout(); }
  if (ev.target.id === 'tTilt' || ev.target.id === 'tAz' || ev.target.id === 'tH') { V.torch.tilt = +$('#tTilt').value; V.torch.az = +$('#tAz').value; V.torch.h = +$('#tH').value; $('#tTiltV').textContent = V.torch.tilt; $('#tHV').textContent = V.torch.h; invalidate(true); }
  if (ev.target.id === 'sawD' && V.sawPlan) { V.sawPlan.depth = +ev.target.value; sawRebuild(); const el = $('#sawD'); if (el) el.focus(); }
  if (ev.target.id === 'tDist') { V.torch.h = +ev.target.value; $('#tDistV').textContent = V.torch.h; invalidate(true); }
  if (ev.target.id === 'betSel') V.bet = ev.target.value;
  if (ev.target.id === 'sec') { V.section = +ev.target.value; invalidate(true); }
});
const ptrs = new Map(); let drag = null, lastCarve = null, strokeCost = 0; const lineEl = $('#cutline');
function torchAt(ev) { const r = rayAt(ev.clientX, ev.clientY), h = C.pick(V.e.vol, curPiece(), r.ro, r.rd, V.mode === 'review'); if (h) { flag('torch'); const T = V.torch; T.on = true; T.p = h.p; T.n = h.n; T.dir = h.n; } return h; }
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
function planPeel(pts) {
  if (pts.length < 6) { showLasso(null); return; }
  let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9; for (const p of pts) { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); }
  if (x1 - x0 < 12 || y1 - y0 < 12) { showLasso(null); return; }
  const inside = (x, y) => { let c = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const a = pts[i], b = pts[j]; if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) c = !c; } return c; };
  const step = Math.max(5, Math.sqrt((x1 - x0) * (y1 - y0) / 900)), hits = [];
  for (let y = y0; y <= y1; y += step) for (let x = x0; x <= x1; x += step) if (inside(x, y)) { const r = rayAt(x, y), h = C.pick(V.e.vol, V.piece, r.ro, r.rd); if (h && !h.flat) hits.push(h); }
  const todo = hits.filter(h => C.peelLeft(V.rec, h.p) > 0.05);
  if (!todo.length) { showLasso(null); V.note = '圈里没有可切的皮。'; renderTools(); return; }
  V.peelPlan = { hits: todo }; showLasso(pts);
  const bx = $('#sawbox'); bx.innerHTML = `<b>画圈开皮</b><span class="dim">圈里有 ${todo.length} 处皮要切，只剥到刚露肉。切了就回不去，露出来的买家也都看得见。</span><div class="row"><button data-act="peelgo" class="pri">确认切皮</button><button data-act="peelno">取消重画</button></div>`; bx.hidden = false; renderTools();
}
function doPeel() { const hits = V.peelPlan ? V.peelPlan.hits : []; V.peelPlan = null; showLasso(null); $('#sawbox').hidden = true;
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
  if (V.e && V.mode !== 'tray' && V.torch.on && V.torch.p && ev.button !== 2) { const tp = torchPts(), a = proj(tp.tail), b2 = proj(tp.head), mid = [(a[0] + b2[0]) / 2, (a[1] + b2[1]) / 2], dt = Math.hypot(ev.clientX - a[0], ev.clientY - a[1]), dh = Math.hypot(ev.clientX - b2[0], ev.clientY - b2[1]), dm = Math.hypot(ev.clientX - mid[0], ev.clientY - mid[1]), seg = (() => { const vx = a[0] - b2[0], vy = a[1] - b2[1], l2 = vx * vx + vy * vy || 1, t = Math.max(0, Math.min(1, ((ev.clientX - b2[0]) * vx + (ev.clientY - b2[1]) * vy) / l2)); return [Math.hypot(ev.clientX - b2[0] - vx * t, ev.clientY - b2[1] - vy * t), t]; })(), mn = Math.min(dt, dh, dm);
    if (mn < 26 || seg[0] < 20) { if (mn >= 26) { canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]); drag = { kind: seg[1] < 0.3 ? 'torch' : seg[1] > 0.7 ? 'ttail' : 'tmid', lx: ev.clientX, ly: ev.clientY }; return; } canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]); drag = { kind: mn === dt ? 'ttail' : mn === dh ? 'torch' : 'tmid', lx: ev.clientX, ly: ev.clientY }; return; } }
  if (V.mode === 'tray') { canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]); drag = { kind: 'orbit', x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY, tray: true }; return; }
  if (!V.e) return; canvas.setPointerCapture(ev.pointerId); ptrs.set(ev.pointerId, [ev.clientX, ev.clientY]);
  if (ptrs.size === 2) { showLine(null); const a = [...ptrs.values()]; drag = { kind: 'pinch', d: Math.hypot(a[0][0] - a[1][0], a[0][1] - a[1][1]), x: (a[0][0] + a[1][0]) / 2, y: (a[0][1] + a[1][1]) / 2 }; return; }
  const own = V.mode === 'own' && V.piece && !V.piece.sold;
  const orbit = ev.button === 2 || V.tool === 'rotate' || ev.shiftKey || ((V.tool === 'grind' || V.tool === 'cut' || V.tool === 'peel' || V.tool === 'saw') && !own);
  if (orbit) drag = { kind: 'orbit', x: ev.clientX, y: ev.clientY, x0: ev.clientX, y0: ev.clientY, click: ev.button !== 2 };
  else if (V.tool === 'torch') { drag = { kind: 'torch' }; torchAt(ev); renderTools(); invalidate(true); }
  else if (V.tool === 'loupe') { drag = { kind: 'loupe' }; V.lens = { x: ev.clientX, y: ev.clientY }; invalidate(true); }
  else if (V.tool === 'grind') { drag = { kind: 'grind' }; lastCarve = null; strokeCost = 0; carveAt(ev); }
  else if ((V.tool === 'saw' && V.sawPlan) || (V.tool === 'peel' && V.peelPlan)) { drag = { kind: 'orbit', x: ev.clientX, y: ev.clientY }; }
  else if (V.tool === 'peel' || V.tool === 'saw') { drag = { kind: 'lasso', saw: V.tool === 'saw', pts: [[ev.clientX, ev.clientY]] }; V.sawPlan = null; }
  else if (V.tool === 'cut') { drag = { kind: 'line', x0: ev.clientX, y0: ev.clientY, x: ev.clientX, y: ev.clientY }; }
});
/* 放大镜指到一条线上：告诉你它是什么 */
const CRK_NAME = { through: ['通天大裂', '整块贯穿，挡光。横跨它的位置出不了镯子，顺着它下刀损失最小'], edge: ['皮上起头的裂', '从皮往里吃了一截，看它吃多深，取料要让开'], hair: ['小绺', '短而浅的细裂，影响小，做小件或雕花可以避开'], branch: ['岔裂', '从大裂上岔出来的小裂，跟着主裂一起让开'] };
function crackLabel(ev) { const el = $('#crlabel'); if (!el) return; if (V.tool !== 'loupe' || !V.e || V.mode === 'tray') { el.hidden = true; return; }
  const r = rayAt(ev.clientX, ev.clientY), h = C.pick(V.e.vol, curPiece(), r.ro, r.rd, V.mode === 'review'); if (!h) { el.hidden = true; return; }
  const vol = V.e.vol, flesh = h.flat || -C.sampleG(vol, 0, h.p[0], h.p[1], h.p[2]) > C.sampleG(vol, 2, h.p[0], h.p[1], h.p[2]) - 0.3, out = [0, 0]; let best = null, bd = 2.4;
  for (const c of V.e.st.cracks) { if (!flesh && (c.skinVis !== 1 || c.open <= 0.5)) continue; C.crackG(c, h.p[0], h.p[1], h.p[2], out); const d = Math.abs(out[0]); if (out[1] > 0.3 && d < bd) { bd = d; best = c; } }
  if (!best) { el.hidden = true; return; }
  const nm = best.open <= 0.5 ? ['石纹（不算裂）', '很早裂过又长死了。没有缝、不挡光，不影响取料，只是不好看'] : (CRK_NAME[best.kind] || CRK_NAME.hair), rc = $('#stage') ? $('#stage').getBoundingClientRect() : canvas.getBoundingClientRect();
  el.innerHTML = `<b class="${best.open <= 0.5 ? '' : 'say'}">${nm[0]}</b><span>${nm[1]}</span>`; el.style.left = Math.min(rc.width - 240, Math.max(6, ev.clientX - rc.left + 18)) + 'px'; el.style.top = Math.max(6, ev.clientY - rc.top + 22) + 'px'; el.hidden = false; }
canvas.addEventListener('pointermove', ev => {
  if (!V.e && V.mode !== 'tray') return;
  crackLabel(ev);
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
  if (drag.kind === 'lasso') { if (drag.saw) planSaw(drag.pts); else planPeel(drag.pts); }
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
