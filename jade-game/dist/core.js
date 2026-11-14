/* 翡翠博弈 · 内核（无 DOM 依赖，可在 Node 中运行测试）
 * 四层信息：StoneTruth（genStone/truthAt/bake）→ 公开证据（evalPiece 的露肉格）→ 市场认知（quote）→ 玩家自己用眼睛判断。
 * 所有数值是游戏平衡参数，不是真实行情。 */
(function (root) {
'use strict';
const TAU = Math.PI * 2;

/* ---------- 确定性随机与噪声 ---------- */
function mulberry(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function hashStr(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
function seedOf() { return hashStr(Array.prototype.join.call(arguments, '|')); }
class Rng {
  constructor(seed) { this.f = mulberry(seed); }
  u() { return this.f(); }
  range(a, b) { return a + (b - a) * this.f(); }
  int(a, b) { return a + Math.floor(this.f() * (b - a + 1)); }
  chance(p) { return this.f() < p; }
  norm() { const u = Math.max(1e-9, this.f()), v = this.f(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(TAU * v); }
  pick(a) { return a[Math.floor(this.f() * a.length)]; }
  dir() { const z = this.range(-1, 1), t = this.range(0, TAU), r = Math.sqrt(1 - z * z); return [r * Math.cos(t), z, r * Math.sin(t)]; }
}
function h3(x, y, z, s) { let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(z, 1274126177) ^ Math.imul(s, 2246822519); h = Math.imul(h ^ (h >>> 13), 1274126177); h ^= h >>> 16; return (h >>> 0) / 4294967296; }
function vn(x, y, z, s) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  let fx = x - xi, fy = y - yi, fz = z - zi;
  fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy); fz = fz * fz * (3 - 2 * fz);
  const a = h3(xi, yi, zi, s), b = h3(xi + 1, yi, zi, s), c = h3(xi, yi + 1, zi, s), d = h3(xi + 1, yi + 1, zi, s);
  const e = h3(xi, yi, zi + 1, s), f = h3(xi + 1, yi, zi + 1, s), g = h3(xi, yi + 1, zi + 1, s), h = h3(xi + 1, yi + 1, zi + 1, s);
  const ab = a + (b - a) * fx, cd = c + (d - c) * fx, ef = e + (f - e) * fx, gh = g + (h - g) * fx;
  const l = ab + (cd - ab) * fy, u = ef + (gh - ef) * fy;
  return l + (u - l) * fz;
}
function fbm(x, y, z, s, o) { let a = 0.5, t = 0, n = 0; for (let i = 0; i < o; i++) { t += a * vn(x, y, z, s + i * 17); n += a; x *= 2.03; y *= 2.03; z *= 2.03; a *= 0.5; } return t / n; }
const clamp = (v, a, b) => v < a ? a : v > b ? b : v;
const lerp = (a, b, t) => a + (b - a) * t;
const sstep = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm3 = a => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };

/* ---------- 平衡表 ---------- */
const ORIGINS = {
  '莫西沙': { w: 47, wsd: 15, c: 42, csd: 23, crack: 34, rel: 0.72, skins: ['灰白盐砂', '白砂皮', '灰绿薄皮', '黄砂皮', '青灰皮'] },
  '木那': { w: 41, wsd: 17, c: 52, csd: 25, crack: 39, rel: 0.64, skins: ['黄砂皮', '白砂皮', '黄红雾', '灰绿薄皮', '褐黄砂'] },
  '大马坎': { w: 34, wsd: 16, c: 47, csd: 24, crack: 31, rel: 0.69, skins: ['黄红雾', '红褐皮', '褐黄砂', '铁锈皮', '黄砂皮'] },
  '会卡': { w: 30, wsd: 20, c: 58, csd: 27, crack: 51, rel: 0.48, skins: ['乌砂皮', '黑乌砂', '黑蜡皮', '铁锈皮', '灰绿薄皮'] },
  '南齐': { w: 36, wsd: 18, c: 49, csd: 26, crack: 42, rel: 0.57, skins: ['铁锈皮', '红褐皮', '乌砂皮', '褐黄砂', '黄砂皮'] },
  '莫湾基': { w: 32, wsd: 21, c: 55, csd: 29, crack: 57, rel: 0.39, skins: ['黑乌砂', '乌砂皮', '黑蜡皮', '铁锈皮', '青灰皮'] },
};
const CHANNELS = {
  '场口直采': { skill: 0.74, margin: 0.08, window: 0.15 },
  '二级供应商': { skill: 0.72, margin: 0.15, window: 0.45 },
  '拍卖市场': { skill: 0.68, margin: 0.11, window: 0.4 },
  '小商贩': { skill: 0.47, margin: 0.18, window: 0.3 },
  '个人转让': { skill: 0.33, margin: 0.07, window: 0.2 },
  '大型集散地': { skill: 0.79, margin: 0.12, window: 0.55 },
};
// sig: 皮壳每毫米挡光系数；t: 皮厚范围 mm
const SKINS = {
  '黄砂皮': { col: [0.60, 0.47, 0.31], grain: 0.78, sig: 0.75, weather: 0.45, t: [1.2, 3.6] },
  '白砂皮': { col: [0.70, 0.69, 0.60], grain: 0.48, sig: 0.55, weather: 0.55, t: [1.0, 3.2] },
  '乌砂皮': { col: [0.20, 0.23, 0.20], grain: 0.62, sig: 1.25, weather: 0.70, t: [1.5, 4.5] },
  '红褐皮': { col: [0.52, 0.33, 0.25], grain: 0.38, sig: 0.95, weather: 0.60, t: [1.2, 4.0] },
  '灰绿薄皮': { col: [0.38, 0.43, 0.35], grain: 0.22, sig: 0.45, weather: 0.35, t: [0.5, 1.5] },
  '黑乌砂': { col: [0.12, 0.15, 0.13], grain: 0.74, sig: 1.45, weather: 0.80, t: [2.0, 5.5] },
  '黄红雾': { col: [0.64, 0.45, 0.27], grain: 0.42, sig: 0.85, weather: 0.65, t: [1.0, 3.0] },
  '灰白盐砂': { col: [0.78, 0.77, 0.69], grain: 0.55, sig: 0.60, weather: 0.50, t: [1.0, 3.0] },
  '铁锈皮': { col: [0.43, 0.25, 0.16], grain: 0.58, sig: 1.10, weather: 0.75, t: [1.5, 4.5] },
  '青灰皮': { col: [0.30, 0.34, 0.32], grain: 0.30, sig: 0.70, weather: 0.55, t: [0.8, 2.5] },
  '黑蜡皮': { col: [0.17, 0.165, 0.14], grain: 0.20, sig: 1.35, weather: 0.65, t: [1.5, 5.0] },
  '褐黄砂': { col: [0.55, 0.42, 0.23], grain: 0.68, sig: 0.90, weather: 0.55, t: [1.2, 3.8] },
};
// band: 色带反照色；abs: 色素吸收（RGB 每单位浓度）；grade: 色价值系数
const HUES = {
  '淡绿': { band: [0.62, 0.82, 0.62], abs: [0.50, 0.06, 0.40], grade: 0.03 },
  '油青': { band: [0.24, 0.42, 0.38], abs: [0.90, 0.32, 0.48], grade: 0.03 },
  '黄翡': { band: [0.86, 0.62, 0.20], abs: [0.08, 0.34, 1.00], grade: 0.015 },
  '紫罗兰': { band: [0.68, 0.54, 0.80], abs: [0.34, 0.60, 0.10], grade: 0.05 },
  '阳绿': { band: [0.30, 0.74, 0.28], abs: [1.00, 0.05, 0.85], grade: 0.6 },
  '正绿': { band: [0.12, 0.56, 0.28], abs: [1.10, 0.10, 0.75], grade: 1.3 },
  '帝王绿': { band: [0.04, 0.42, 0.21], abs: [1.30, 0.18, 0.85], grade: 3.3 },
};
const BODIES = {
  '白底': [0.93, 0.94, 0.90], '灰底': [0.72, 0.74, 0.72], '晴水': [0.80, 0.90, 0.86],
  '蓝水': [0.62, 0.78, 0.78], '黄底': [0.90, 0.86, 0.72], '藕粉': [0.88, 0.82, 0.88],
};
const BUYERS = {
  '稳健同行': { skill: 0.71, risk: 0.72, margin: 0.17, opt: 0.85, cash: 300000, days: 0, pref: '净度' },
  '直播货主': { skill: 0.57, risk: 0.48, margin: 0.22, opt: 1.22, cash: 180000, days: 0, pref: '表现' },
  '私人藏家': { skill: 0.43, risk: 0.36, margin: 0.08, opt: 1.05, cash: 500000, days: 2, pref: '色' },
  '急收商人': { skill: 0.62, risk: 0.82, margin: 0.28, opt: 0.80, cash: 120000, days: 0, pref: '周转' },
};
const TOOLS = { '细磨头': { r: 4, bite: 1.0 }, '中磨头': { r: 7, bite: 1.5 }, '粗磨头': { r: 12, bite: 2.2 } };
const ECON = { startCash: 8000, daily: 300, base: 16.7, yield: 0.3, braceletBonus: 4, rough: 0.6, pressFail: 0.05, grind: 0.06, cutBase: 80, cutArea: 0.015, kerf: 1.2, density: 3.33, priorScale: 0.8 };
// 相对无色手镯零售价：豆 0.1 万、糯 0.5 万、糯冰 3 万、冰 15 万、高冰 40 万、玻璃 90 万（见 research/value-chain.md）
const WATER_ANCHORS = [[0.10, 1], [0.25, 5], [0.45, 30], [0.65, 150], [0.82, 400], [0.95, 900]];
function waterName(w) { w *= 100; return w < 18 ? '豆种' : w < 35 ? '糯种' : w < 55 ? '糯冰种' : w < 74 ? '冰种' : w < 89 ? '高冰种' : '玻璃种'; }
function qWater(w) {
  const A = WATER_ANCHORS;
  if (w <= A[0][0]) return Math.max(0.3, w / A[0][0]);
  for (let i = 1; i < A.length; i++) if (w <= A[i][0]) { const t = (w - A[i - 1][0]) / (A[i][0] - A[i - 1][0]); return Math.exp(lerp(Math.log(A[i - 1][1]), Math.log(A[i][1]), t)); }
  return A[A.length - 1][1];
}
// 每立方厘米成品潜力（元）。种与色相乘，体现种色协同。
function vd(w, c, cot, dirt, grade) { return ECON.base * qWater(w) * (1 + 30 * c * grade) * (1 - 0.6 * cot) * (1 - 0.9 * dirt); }

/* ---------- 原石真相（由种子完全决定） ---------- */
function genStone(seed, originId, channelId) {
  const r = new Rng(seedOf(seed, 'stone:v1'));
  const O = ORIGINS[originId];
  const st = { seed, origin: originId, channel: channelId };
  const kg = 0.5 + 6.5 * Math.pow(r.u(), 1.8); // 0.5–7 公斤，中等以上的料更常见，够切够做
  const ry = r.range(0.55, 0.85), rz = r.range(0.72, 1.0);
  const a = Math.cbrt(3 * kg / ECON.density * 1e6 / (4 * Math.PI * ry * rz));
  st.rad = [a, a * ry, a * rz];
  st.shapeSeed = r.int(1, 1e6);
  st.planes = []; const np = r.int(0, 2);
  for (let i = 0; i < np; i++) st.planes.push({ n: r.dir(), h: r.range(0.62, 0.9) });
  const skinName = r.pick(O.skins), S = SKINS[skinName];
  st.skin = { name: skinName, col: S.col, grain: S.grain, sig: S.sig, weather: clamp(S.weather + r.range(-0.12, 0.12), 0.15, 0.95), t: r.range(S.t[0], S.t[1]), phase: r.range(0, 100) };
  const foggy = skinName === '黄红雾' || skinName === '红褐皮' || originId === '大马坎';
  st.fog = foggy ? { t: r.range(1, 3.5), col: r.chance(0.6) ? [0.86, 0.66, 0.30] : [0.74, 0.36, 0.24] } : (r.chance(0.3) ? { t: r.range(0.5, 1.5), col: [0.92, 0.92, 0.88] } : { t: 0, col: [1, 1, 1] });
  st.w0 = clamp(O.w + O.wsd * r.norm(), 4, 97) / 100;
  st.wGrad = r.dir(); st.wVar = r.range(0, 0.12);
  st.shift = r.chance(0.28) ? { n: r.dir(), h: r.range(-0.3, 0.3) * a, drop: r.range(0.08, 0.25) * (r.chance(0.25) ? -1 : 1) } : null;
  st.body = r.pick(['白底', '白底', '白底', '灰底', '灰底', '晴水', '蓝水', '黄底', '藕粉']);
  const cs = clamp(O.c + O.csd * r.norm(), 0, 100);
  st.colorScore = cs;
  st.hue = cs >= 93 ? '帝王绿' : cs >= 78 ? r.pick(['正绿', '正绿', '阳绿']) : cs >= 55 ? r.pick(['阳绿', '阳绿', '紫罗兰', '淡绿']) : r.pick(['淡绿', '淡绿', '油青', '黄翡', '紫罗兰']);
  const nf = cs < 30 ? (r.chance(0.25) ? 1 : 0) : cs < 55 ? 1 : cs < 80 ? r.int(1, 2) : r.int(2, 3);
  st.feats = [];
  for (let i = 0; i < nf; i++) {
    const u = r.u();
    const type = u < 0.28 ? 'ribbon' : u < 0.45 ? 'pinch' : u < 0.65 ? 'skin' : u < 0.80 ? 'blob' : u < 0.95 ? 'float' : (cs > 70 ? 'full' : 'ribbon');
    const n = r.dir(); let t1 = norm3(cross(n, [0.31, 0.87, 0.38])); const t2 = cross(n, t1);
    const cdir = r.dir(), cr = r.range(0, 0.75);
    st.feats.push({
      type, n, t1, t2, c: [cdir[0] * st.rad[0] * cr, cdir[1] * st.rad[1] * cr, cdir[2] * st.rad[2] * cr],
      width: r.range(2.2, 8), R: a * r.range(0.35, 1.2), warp: r.range(1, 6), freq: r.range(0.03, 0.09), phase: r.range(0, TAU),
      strength: clamp(cs / 100 * r.range(0.6, 1.25), 0.15, 1), depth: r.range(2, 7), cone: r.range(0.2, 0.8),
      radii: [a * r.range(0.15, 0.45), a * r.range(0.12, 0.35), a * r.range(0.15, 0.45)], seed: r.int(1, 1e6),
    });
  }
  // 裂按成因生成：地应力让裂成组平行（节理），所以先定两个主方向；风化从外往里，所以多数裂从皮上起头往里吃；
  // 通天裂整块贯穿；小绺是内部的短纹；愈合裂（石纹）被后来的矿物长死了，只剩一条白线，不算裂。
  st.cracks = []; const nc = Math.round(O.crack / 100 * r.range(1.5, 9)), sets = [r.dir(), r.dir()];
  for (let i = 0; i < Math.min(nc, 6); i++) {
    const s0 = sets[r.chance(0.7) ? 0 : 1], j = r.dir(), n = norm3([s0[0] + j[0] * 0.22, s0[1] + j[1] * 0.22, s0[2] + j[2] * 0.22]), u = r.u(), d = r.dir(), seen = r.chance(S.sig > 1 ? 0.35 : 0.65) ? 1 : 0;
    const kind = u < 0.16 ? 'through' : u < 0.58 ? 'edge' : u < 0.82 ? 'hair' : 'healed';
    let c, R, open = 1, skinVis = seen;
    if (kind === 'through' || kind === 'healed') { const cr = r.range(0, 0.3); c = [d[0] * st.rad[0] * cr, d[1] * st.rad[1] * cr, d[2] * st.rad[2] * cr]; R = a * r.range(1.1, 1.7); if (kind === 'healed') { open = 0.2; R = a * r.range(0.5, 1.3); } }
    else if (kind === 'edge') { const e = norm3(cross(n, d)); c = [e[0] * st.rad[0] * 0.92, e[1] * st.rad[1] * 0.92, e[2] * st.rad[2] * 0.92]; R = a * r.range(0.35, 0.85); skinVis = r.chance(S.sig > 1 ? 0.5 : 0.8) ? 1 : 0; }
    else { const cr = r.range(0.1, 0.75); c = [d[0] * st.rad[0] * cr, d[1] * st.rad[1] * cr, d[2] * st.rad[2] * cr]; R = a * r.range(0.12, 0.3); open = r.chance(0.6) ? 1 : 0.2; }
    st.cracks.push({ kind, c, n, t1: norm3(cross(n, [0.31, 0.87, 0.38])), R, warp: r.range(0.4, 2.2), freq: r.range(0.03, 0.09), phase: r.range(0, TAU), open, skinVis });
  }
  { // 分叉：主裂上岔出去的小裂
    const rb = new Rng(seedOf(seed, 'branch')), base = st.cracks.slice();
    for (const c of base) { if (st.cracks.length >= 10) break; const nb = c.kind === 'hair' ? 0 : rb.chance(0.55) ? (rb.chance(0.3) ? 2 : 1) : 0;
      for (let k = 0; k < nb && st.cracks.length < 10; k++) {
        const t2 = cross(c.n, c.t1), ang = rb.range(0, TAU), rr = c.R * rb.range(0.25, 0.7), dir = [c.t1[0] * Math.cos(ang) + t2[0] * Math.sin(ang), c.t1[1] * Math.cos(ang) + t2[1] * Math.sin(ang), c.t1[2] * Math.cos(ang) + t2[2] * Math.sin(ang)];
        const tilt = rb.range(0.4, 0.95) * (rb.chance(0.5) ? 1 : -1), n = norm3([c.n[0] * Math.cos(tilt) + dir[0] * Math.sin(tilt), c.n[1] * Math.cos(tilt) + dir[1] * Math.sin(tilt), c.n[2] * Math.cos(tilt) + dir[2] * Math.sin(tilt)]), R = c.R * rb.range(0.25, 0.5);
        st.cracks.push({ c: [c.c[0] + dir[0] * rr + n[0] * 0, c.c[1] + dir[1] * rr, c.c[2] + dir[2] * rr], n, t1: norm3(cross(n, [0.31, 0.87, 0.38])), R, warp: c.warp * 0.7, freq: c.freq * 1.6, phase: rb.range(0, TAU), open: c.open > 0.5 ? (rb.chance(0.7) ? 1 : 0.2) : 0.2, skinVis: c.skinVis, branch: 1, kind: 'branch' });
      } }
  }
  st.cot = clamp(0.3 + 0.2 * r.norm(), 0, 0.9) * (1 - st.w0 * 0.5); st.cotSeed = r.int(1, 1e6);
  st.dirt = []; const nd = r.chance(O.crack > 45 ? 0.55 : 0.3) ? r.int(1, 2) : 0;
  for (let i = 0; i < nd; i++) {
    let c; if (st.feats.length && r.chance(0.6)) { const f = r.pick(st.feats); c = [f.c[0] + r.range(-8, 8), f.c[1] + r.range(-8, 8), f.c[2] + r.range(-8, 8)]; } else { const d = r.dir(), cr = r.range(0.2, 0.9); c = [d[0] * st.rad[0] * cr, d[1] * st.rad[1] * cr, d[2] * st.rad[2] * cr]; }
    st.dirt.push({ c, r: a * r.range(0.1, 0.3), s: r.range(0.4, 1), seed: r.int(1, 1e6) });
  }
  st.kg = kg;
  return st;
}
function shapeF(st, x, y, z) {
  const R = st.rad, qx = x / R[0], qy = y / R[1], qz = z / R[2];
  const l = Math.hypot(qx, qy, qz), f = 1.7 / R[0];
  const disp = 0.30 * (fbm(x * f, y * f, z * f, st.shapeSeed, 3) - 0.5) + 0.07 * (fbm(x * f * 3.6, y * f * 3.6, z * f * 3.6, st.shapeSeed + 9, 2) - 0.5);
  let v = l - 1 - disp;
  for (const p of st.planes) v = Math.max(v, qx * p.n[0] + qy * p.n[1] + qz * p.n[2] - p.h);
  return v;
}
// 裂面函数：返回 [到翘曲裂面的带符号距离, 是否在裂片范围内 0..1]。着色器里有同一公式。
function crackG(c, x, y, z, out) {
  const dx = x - c.c[0], dy = y - c.c[1], dz = z - c.c[2], n = c.n, t1 = c.t1;
  let h = dx * n[0] + dy * n[1] + dz * n[2];
  const qx = dx - n[0] * h, qy = dy - n[1] * h, qz = dz - n[2] * h, r = Math.hypot(qx, qy, qz);
  const t2x = n[1] * t1[2] - n[2] * t1[1], t2y = n[2] * t1[0] - n[0] * t1[2], t2z = n[0] * t1[1] - n[1] * t1[0];
  const a = qx * t1[0] + qy * t1[1] + qz * t1[2], b = qx * t2x + qy * t2y + qz * t2z;
  h += c.warp * (Math.sin(a * c.freq + c.phase) + Math.sin(b * c.freq * 1.37 + c.phase * 2.1)) * 0.5;
  const z1 = a * c.freq * 1.9 + c.phase, z2 = b * c.freq * 2.3 - c.phase; // 折线状的锯齿：裂不是光滑的面
  h += c.warp * 0.35 * ((Math.abs(z1 - Math.floor(z1) - 0.5) * 4 - 1) + 0.6 * (Math.abs(z2 - Math.floor(z2) - 0.5) * 4 - 1));
  const R = c.R * (1 + 0.18 * Math.sin(Math.atan2(b, a) * 3 + c.phase));
  out[0] = h; out[1] = 1 - sstep(R * 0.85, R, r);
}
const _cg = [0, 0];
function truthAt(st, x, y, z, depth, out) {
  const a = st.rad[0];
  let w = st.w0 + st.wVar * (x * st.wGrad[0] + y * st.wGrad[1] + z * st.wGrad[2]) / a + (fbm(x * 0.018, y * 0.018, z * 0.018, st.seed & 0xffff, 2) - 0.5) * 0.16;
  if (st.shift) { const s = st.shift, d = x * s.n[0] + y * s.n[1] + z * s.n[2] - s.h; w -= s.drop / (1 + Math.exp(-d / 4)); }
  w = clamp(w, 0.03, 0.99);
  let ch = 0;
  for (const f of st.feats) {
    const dx = x - f.c[0], dy = y - f.c[1], dz = z - f.c[2]; let p = 0;
    if (f.type === 'ribbon' || f.type === 'pinch') {
      const al = dx * f.t1[0] + dy * f.t1[1] + dz * f.t1[2], be = dx * f.t2[0] + dy * f.t2[1] + dz * f.t2[2];
      const h = dx * f.n[0] + dy * f.n[1] + dz * f.n[2] + f.warp * Math.sin(al * f.freq + f.phase) + f.warp * 0.5 * Math.sin(be * f.freq * 1.7 + f.phase * 1.3);
      const r = Math.hypot(al, be);
      let wd = f.width * (0.6 + 0.8 * vn(x * 0.05, y * 0.05, z * 0.05, f.seed)) * (1 - sstep(f.R * 0.45, f.R, r));
      if (f.type === 'pinch') wd *= sstep(-f.R * 0.2, f.R * 0.6, al);
      if (wd > 0.05) p = Math.exp(-(h * h) / (wd * wd)) * f.strength;
    } else if (f.type === 'skin') {
      const l = Math.hypot(x, y, z) || 1, cs = (x * f.n[0] + y * f.n[1] + z * f.n[2]) / l;
      p = f.strength * sstep(f.cone, f.cone + 0.2, cs) * (0.55 + 0.45 * vn(x * 0.06, y * 0.06, z * 0.06, f.seed)) * (1 - sstep(f.depth * 0.6, f.depth * 1.3, depth));
    } else if (f.type === 'blob') {
      const l = Math.hypot(dx / f.radii[0], dy / f.radii[1], dz / f.radii[2]) + (vn(x * 0.08, y * 0.08, z * 0.08, f.seed) - 0.5) * 0.6;
      p = f.strength * (1 - sstep(0.6, 1.0, l));
    } else if (f.type === 'float') {
      const l = Math.hypot(dx, dy, dz) / (f.R * 0.9);
      p = f.strength * sstep(0.56, 0.72, fbm(x * 0.09, y * 0.09, z * 0.09, f.seed, 2)) * (1 - sstep(0.6, 1, l));
    } else { p = f.strength * (0.45 + 0.55 * fbm(x * 0.03, y * 0.03, z * 0.03, f.seed, 2)); }
    if (p > ch) ch = p;
  }
  let cot = st.cot * sstep(0.48, 0.78, fbm(x * 0.06, y * 0.06, z * 0.06, st.cotSeed, 3)) + (vn(x * 0.5, y * 0.5, z * 0.5, st.cotSeed + 5) > 0.93 ? st.cot * 0.5 : 0);
  let dirt = 0;
  for (const d of st.dirt) { const l = Math.hypot(x - d.c[0], y - d.c[1], z - d.c[2]) / d.r + (vn(x * 0.1, y * 0.1, z * 0.1, d.seed) - 0.5) * 0.7; const v = d.s * (1 - sstep(0.5, 1, l)); if (v > dirt) dirt = v; }
  out[0] = clamp(ch, 0, 1); out[1] = w; out[2] = clamp(cot, 0, 1); out[3] = dirt;
}

/* ---------- 体数据烘焙：geom(原始距离, 当前距离, 皮厚, 0) + mat(色, 种水, 棉, 脏) ---------- */
function bake(st, N) {
  N = N || 64;
  const hx0 = st.rad[0] * 1.3 + 3, vx = 2 * hx0 / N;
  const nx = N, ny = Math.max(8, Math.ceil((st.rad[1] * 1.3 + 3) * 2 / vx)), nz = Math.max(8, Math.ceil((st.rad[2] * 1.3 + 3) * 2 / vx));
  const hx = nx * vx / 2, hy = ny * vx / 2, hz = nz * vx / 2, n = nx * ny * nz;
  const f = new Float32Array(n), geom = new Float32Array(n * 4), mat = new Uint8Array(n * 4);
  let i = 0;
  for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let ii = 0; ii < nx; ii++) f[i++] = shapeF(st, (ii + 0.5) * vx - hx, (j + 0.5) * vx - hy, (k + 0.5) * vx - hz);
  const out = [0, 0, 0, 0], sy = nx, sz = nx * ny, sk = st.skin;
  let sw = 0, sc = 0, sn = 0, st_ = 0, stn = 0, solid = 0;
  i = 0;
  for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let ii = 0; ii < nx; ii++, i++) {
    const x = (ii + 0.5) * vx - hx, y = (j + 0.5) * vx - hy, z = (k + 0.5) * vx - hz;
    const gx = (f[ii < nx - 1 ? i + 1 : i] - f[ii > 0 ? i - 1 : i]) / ((ii > 0 && ii < nx - 1 ? 2 : 1) * vx);
    const gy = (f[j < ny - 1 ? i + sy : i] - f[j > 0 ? i - sy : i]) / ((j > 0 && j < ny - 1 ? 2 : 1) * vx);
    const gz = (f[k < nz - 1 ? i + sz : i] - f[k > 0 ? i - sz : i]) / ((k > 0 && k < nz - 1 ? 2 : 1) * vx);
    const d = clamp(f[i] / (Math.hypot(gx, gy, gz) || 1e-3), -12, 12);
    const skinT = sk.t * (0.55 + 0.9 * fbm(x * 0.03, y * 0.03, z * 0.03, st.shapeSeed + 77, 2));
    geom[i * 4] = d; geom[i * 4 + 1] = d; geom[i * 4 + 2] = skinT;
    if (d < 0) solid++;
    if (d < 4.5) {
      truthAt(st, x, y, z, Math.max(0, -d), out);
      mat[i * 4] = out[0] * 255; mat[i * 4 + 1] = out[1] * 255; mat[i * 4 + 2] = out[2] * 255; mat[i * 4 + 3] = out[3] * 255;
      if (d < 0 && -d < skinT) { st_ += skinT; stn++; }
      if (-d > skinT && -d < skinT + 12) { sw += out[1]; sc += out[0]; sn++; }
    }
  }
  return { nx, ny, nz, vx, hx, hy, hz, geom, mat, shallowW: sn ? sw / sn : st.w0, shallowC: sn ? sc / sn : 0, skinMean: stn ? st_ / stn : sk.t, weight0: solid * vx * vx * vx / 1000 * ECON.density, ver: 0 };
}
function sampleG(vol, ch, x, y, z) {
  const nx = vol.nx, ny = vol.ny, nz = vol.nz, g = vol.geom;
  let fx = clamp((x + vol.hx) / vol.vx - 0.5, 0, nx - 1.001), fy = clamp((y + vol.hy) / vol.vx - 0.5, 0, ny - 1.001), fz = clamp((z + vol.hz) / vol.vx - 0.5, 0, nz - 1.001);
  const i = fx | 0, j = fy | 0, k = fz | 0; fx -= i; fy -= j; fz -= k;
  const b = (i + nx * (j + ny * k)) * 4 + ch, X = 4, Y = nx * 4, Z = nx * ny * 4;
  const a0 = g[b] + (g[b + X] - g[b]) * fx, a1 = g[b + Y] + (g[b + Y + X] - g[b + Y]) * fx;
  const a2 = g[b + Z] + (g[b + Z + X] - g[b + Z]) * fx, a3 = g[b + Z + Y] + (g[b + Z + Y + X] - g[b + Z + Y]) * fx;
  const l = a0 + (a1 - a0) * fy, u = a2 + (a3 - a2) * fy;
  return l + (u - l) * fz;
}
function vIndex(vol, x, y, z) {
  const i = clamp(Math.floor((x + vol.hx) / vol.vx), 0, vol.nx - 1), j = clamp(Math.floor((y + vol.hy) / vol.vx), 0, vol.ny - 1), k = clamp(Math.floor((z + vol.hz) / vol.vx), 0, vol.nz - 1);
  return i + vol.nx * (j + vol.ny * k);
}
/* 一块料 = 原石体数据 + 若干切面（半空间）。piece.planes = [[nx,ny,nz,d]...]，保留 n·p <= d 的一侧。 */
// holes：被小锯挖走的凸块（每个是一组平面），落在里面的点不属于这块料
function planeD(piece, x, y, z) {
  let m = -1e9; const P = piece.planes; for (let i = 0; i < P.length; i++) { const v = P[i][0] * x + P[i][1] * y + P[i][2] * z - P[i][3]; if (v > m) m = v; }
  const H = piece.holes; if (H) for (let k = 0; k < H.length; k++) { let m2 = -1e9; const Q = H[k]; for (let i = 0; i < Q.length; i++) { const v = Q[i][0] * x + Q[i][1] * y + Q[i][2] * z - Q[i][3]; if (v > m2) m2 = v; } if (-m2 > m) m = -m2; }
  return m;
}
function limitNormal(piece, x, y, z) {
  let m = -1e9, n = [0, 1, 0]; for (const P of piece.planes) { const v = P[0] * x + P[1] * y + P[2] * z - P[3]; if (v > m) { m = v; n = [P[0], P[1], P[2]]; } }
  for (const Q of (piece.holes || [])) { let m2 = -1e9, q = null; for (const P of Q) { const v = P[0] * x + P[1] * y + P[2] * z - P[3]; if (v > m2) { m2 = v; q = P; } } if (-m2 > m) { m = -m2; n = [-q[0], -q[1], -q[2]]; } }
  return n;
}
const clipped = piece => piece.planes.length > 0 || (piece.holes && piece.holes.length > 0);
// 视线拾取：返回 {p, n} 或 null
function pick(vol, piece, ro, rd, pristine) {
  const ch = pristine ? 0 : 1, mn = [-vol.hx, -vol.hy, -vol.hz], mx = [vol.hx, vol.hy, vol.hz];
  let tn = -1e9, tf = 1e9;
  for (let a = 0; a < 3; a++) { const inv = 1 / (Math.abs(rd[a]) < 1e-9 ? 1e-9 : rd[a]); let t0 = (mn[a] - ro[a]) * inv, t1 = (mx[a] - ro[a]) * inv; if (t0 > t1) { const s = t0; t0 = t1; t1 = s; } if (t0 > tn) tn = t0; if (t1 < tf) tf = t1; }
  if (tn > tf || tf < 0) return null;
  let t = Math.max(tn, 0) + 0.01;
  for (let s = 0; s < 260; s++) {
    const x = ro[0] + rd[0] * t, y = ro[1] + rd[1] * t, z = ro[2] + rd[2] * t;
    const sd = sampleG(vol, ch, x, y, z), pd = planeD(piece, x, y, z), d = Math.max(sd, pd);
    if (d < 0.04) {
      if (pd > sd - 0.05) return { p: [x, y, z], n: limitNormal(piece, x, y, z), flat: true };
      const e = 1, n = norm3([sampleG(vol, ch, x + e, y, z) - sampleG(vol, ch, x - e, y, z), sampleG(vol, ch, x, y + e, z) - sampleG(vol, ch, x, y - e, z), sampleG(vol, ch, x, y, z + e) - sampleG(vol, ch, x, y, z - e)]);
      return { p: [x, y, z], n, flat: false };
    }
    t += Math.max(d * 0.8, 0.06); if (t > tf) return null;
  }
  return null;
}
// 磨头：球形刀具做减法，只影响当前这块料。返回去除体积 mm³。
function carve(vol, piece, cx, cy, cz, R) {
  const vx = vol.vx, nx = vol.nx, ny = vol.ny, nz = vol.nz, g = vol.geom, pad = R + vx;
  const i0 = clamp(Math.floor((cx - pad + vol.hx) / vx), 0, nx - 1), i1 = clamp(Math.ceil((cx + pad + vol.hx) / vx), 0, nx - 1);
  const j0 = clamp(Math.floor((cy - pad + vol.hy) / vx), 0, ny - 1), j1 = clamp(Math.ceil((cy + pad + vol.hy) / vx), 0, ny - 1);
  const k0 = clamp(Math.floor((cz - pad + vol.hz) / vx), 0, nz - 1), k1 = clamp(Math.ceil((cz + pad + vol.hz) / vx), 0, nz - 1);
  let removed = 0, flesh = 0;
  for (let k = k0; k <= k1; k++) for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
    const x = (i + 0.5) * vx - vol.hx, y = (j + 0.5) * vx - vol.hy, z = (k + 0.5) * vx - vol.hz;
    if (planeD(piece, x, y, z) > vx) continue;
    const nd = Math.min(12, R - Math.hypot(x - cx, y - cy, z - cz)), b = (i + nx * (j + ny * k)) * 4;
    if (nd > g[b + 1]) { const before = clamp(0.5 - g[b + 1] / vx, 0, 1), after = clamp(0.5 - nd / vx, 0, 1); removed += before - after; if (-g[b] > g[b + 2]) flesh += before - after; g[b + 1] = nd; }
  }
  vol.ver++;
  const v3 = vx * vx * vx;
  return { removed: removed * v3, flesh: flesh * v3, box: [i0, i1, j0, j1, k0, k1] };
}
// 这块料的重量、重心、包围半径，以及沿某方向的范围
function pieceInfo(vol, piece, dir) {
  const { nx, ny, nz, vx, geom: g } = vol; let w = 0, sx = 0, sy = 0, sz = 0, lo = 1e9, hi = -1e9, r2 = 0; const pts = [];
  for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    const g1 = g[(i + nx * (j + ny * k)) * 4 + 1]; if (g1 >= 0) continue;
    const x = (i + 0.5) * vx - vol.hx, y = (j + 0.5) * vx - vol.hy, z = (k + 0.5) * vx - vol.hz, pd = planeD(piece, x, y, z); if (pd > vx * 0.5) continue;
    const c = clamp(0.5 - g1 / vx, 0, 1) * clamp(0.5 - pd / vx, 0, 1); if (c <= 0) continue;
    w += c; sx += c * x; sy += c * y; sz += c * z; pts.push(x, y, z);
    if (dir) { const h = x * dir[0] + y * dir[1] + z * dir[2]; if (h < lo) lo = h; if (h > hi) hi = h; }
  }
  const c = w ? [sx / w, sy / w, sz / w] : [0, 0, 0];
  for (let i = 0; i < pts.length; i += 3) { const d = (pts[i] - c[0]) ** 2 + (pts[i + 1] - c[1]) ** 2 + (pts[i + 2] - c[2]) ** 2; if (d > r2) r2 = d; }
  return { weight: w * vx * vx * vx / 1000 * ECON.density, center: c, radius: Math.sqrt(r2) + vx, lo: lo - vx / 2, hi: hi + vx / 2 };
}
// 两个近乎平行相对的切面之间是“片”：返回 {n, T} 或 null
function slabOf(piece) { const P = piece.planes; let best = null; for (let a = 0; a < P.length; a++) for (let b = a + 1; b < P.length; b++) { const dt = P[a][0] * P[b][0] + P[a][1] * P[b][1] + P[a][2] * P[b][2]; if (dt < -0.95) { const T = P[a][3] + P[b][3]; if (!best || T < best.T) best = { n: [P[a][0], P[a][1], P[a][2]], T, hi: P[a][3], lo: -P[b][3] }; } } return best; }

/* ---------- 估值：真相价值与“仅凭公开证据”的市场认知 ---------- */
function evalPiece(st, vol, piece) {
  const { nx, ny, nz, vx, geom: g, mat: m } = vol, grade = HUES[st.hue].grade, slab = slabOf(piece), T = slab ? slab.T : 999;
  // 1) 覆盖率
  const cov = new Float32Array(nx * ny * nz); let nCov = 0, solidW = 0;
  for (let k = 0, id = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++, id++) {
    const g1 = g[id * 4 + 1]; if (g1 >= vx * 0.5) continue;
    let c = clamp(0.5 - g1 / vx, 0, 1);
    if (clipped(piece)) { const pd = planeD(piece, (i + 0.5) * vx - vol.hx, (j + 0.5) * vx - vol.hy, (k + 0.5) * vx - vol.hz); if (pd > vx * 0.5) continue; c *= clamp(0.5 - pd / vx, 0, 1); }
    if (c > 0) { cov[id] = c; nCov++; solidW += c; }
  }
  const s = nCov < 16000 ? 1 : 2, cx = Math.ceil(nx / s), cy = Math.ceil(ny / s), cz = Math.ceil(nz / s), nc = cx * cy * cz, v3 = vx * vx * vx / 1000;
  // 2) 露肉：磨穿皮壳的表面，或落在切面上的肉
  const expo = new Uint16Array(nc); let expVox = 0;
  for (let k = 0, id = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++, id++) {
    if (cov[id] <= 0) continue; const b = id * 4, g1 = g[b + 1]; if (g1 >= 0) continue;
    const windowed = g1 > -vx && g1 - g[b] > g[b + 2] + 0.2;
    let cutFace = false;
    if (!windowed && clipped(piece) && -g[b] > g[b + 2]) cutFace = planeD(piece, (i + 0.5) * vx - vol.hx, (j + 0.5) * vx - vol.hy, (k + 0.5) * vx - vol.hz) > -vx;
    if (windowed || cutFace) { expVox++; expo[Math.floor(i / s) + cx * (Math.floor(j / s) + cy * Math.floor(k / s))]++; }
  }
  // 3) 估值格
  const cells = [], E = []; let expColor = 0, expW = 0; const off = s === 2 ? 1 : 0;
  for (let k = 0; k < cz; k++) for (let j = 0; j < cy; j++) for (let i = 0; i < cx; i++) {
    const vi = Math.min(nx - 1, i * s + off), vj = Math.min(ny - 1, j * s + off), vk = Math.min(nz - 1, k * s + off), id = vi + nx * (vj + ny * vk), b = id * 4;
    let wt = cov[id]; if (s === 2) { wt = 0; for (let dk = 0; dk < 2; dk++) for (let dj = 0; dj < 2; dj++) for (let di = 0; di < 2; di++) { const a = i * 2 + di, bb = j * 2 + dj, cc = k * 2 + dk; if (a < nx && bb < ny && cc < nz) wt += cov[a + nx * (bb + ny * cc)]; } }
    if (wt <= 0 || !(-g[b] > g[b + 2])) continue;
    const c = m[b] / 255, w = m[b + 1] / 255, cid = i + cx * (j + cy * k);
    const cell = { cot: m[b + 2] / 255, dirt: m[b + 3] / 255, id: cid, p: [(vi + 0.5) * vx - vol.hx, (vj + 0.5) * vx - vol.hy, (vk + 0.5) * vx - vol.hz], v: vd(w, c, m[b + 2] / 255, m[b + 3] / 255, grade), w, c, wt, k: 0, e: 0, conf: 0, Ft: 1, Fk: 1 };
    cells.push(cell);
    if (expo[cid]) { E.push(cell); if (c > 0.25) expColor++; expW += w; }
  }
  const stride = Math.max(1, Math.ceil(E.length / 320)), Es = E.filter((_, i) => i % stride === 0);
  const known = st.cracks.map(c => c.open > 0.5 && c.skinVis === 1);
  for (let ci = 0; ci < st.cracks.length; ci++) { const c = st.cracks[ci]; if (c.open <= 0.5 || known[ci]) continue; for (const e of E) { crackG(c, e.p[0], e.p[1], e.p[2], _cg); if (Math.abs(_cg[0]) < 3.5 && _cg[1] > 0.5) { known[ci] = true; break; } } }
  const kGrid = new Float32Array(nc), thinK = T < 16 ? 0.92 - T * 0.01 : 0;
  let S1 = 0, S1u = 0, S2 = 0, S2u = 0, S3 = 0, S3u = 0, truth = 0, kSum = 0, wSum = 0;
  const ag = { Vclean: 0, Vcrack: 0, Vtop: 0, volClean: 0, volCrack: 0, volTop: 0, col: 0, w: 0, cot: 0, dirt: 0 };
  for (const cl of cells) {
    let dmin = 1e9, wn = 0.3, sw = 0, swv = 0;
    for (const e of Es) { const dx = cl.p[0] - e.p[0], dy = cl.p[1] - e.p[1], dz = cl.p[2] - e.p[2], d = Math.sqrt(dx * dx + dy * dy + dz * dz); if (d < dmin) { dmin = d; wn = e.w; } if (d < 70) { const ww = Math.exp(-d / 22); sw += ww; swv += ww * e.v; } }
    if (Es.length) { cl.k = Math.max(thinK, Math.exp(-dmin / (4 + 14 * wn * wn))); cl.conf = Math.exp(-dmin / 22); cl.e = sw > 0 ? swv / sw : 0; }
    for (let ci = 0; ci < st.cracks.length; ci++) { const c = st.cracks[ci]; if (c.open <= 0.5) continue; crackG(c, cl.p[0], cl.p[1], cl.p[2], _cg); if (Math.abs(_cg[0]) < 3 && _cg[1] > 0.5) { cl.Ft = 0.15; if (known[ci]) cl.Fk = 0.15; } }
    kGrid[cl.id] = cl.k; kSum += cl.k * cl.wt; wSum += cl.wt;
    const u = 1 - cl.k, F = cl.Fk * cl.wt;
    truth += cl.v * cl.Ft * cl.wt;
    if (cl.Ft === 1) { ag.Vclean += cl.v * cl.wt; ag.volClean += cl.wt; if (cl.c > 0.4) { ag.Vtop += cl.v * cl.wt; ag.volTop += cl.wt; } } else { ag.Vcrack += cl.v * cl.wt; ag.volCrack += cl.wt; }
    if (cl.c > 0.25) ag.col += cl.wt; ag.w += cl.w * cl.wt; ag.cot += cl.cot * cl.wt; ag.dirt += cl.dirt * cl.wt;
    S1 += F * cl.k * cl.v; S1u += F * cl.k * cl.v * u; S2 += F * u * cl.conf * cl.e; S2u += F * u * u * cl.conf * cl.e; S3 += F * u * (1 - cl.conf); S3u += F * u * u * (1 - cl.conf);
  }
  const sc = v3 * ECON.yield;
  // 4) 手镯位：外径 72、内径 56、厚 9 的无裂圆环。片料只能顺着片面取；整料试三个方向取最好的
  const fleshAt = (x, y, z) => { if (Math.abs(x) >= vol.hx || Math.abs(y) >= vol.hy || Math.abs(z) >= vol.hz) return false; if (clipped(piece) && planeD(piece, x, y, z) > 0) return false; const b = vIndex(vol, x, y, z) * 4; return g[b + 1] < 0 && -g[b] > g[b + 2]; };
  const kAt = (x, y, z) => kGrid[clamp(Math.floor((x + vol.hx) / vx / s), 0, cx - 1) + cx * (clamp(Math.floor((y + vol.hy) / vx / s), 0, cy - 1) + cy * clamp(Math.floor((z + vol.hz) / vx / s), 0, cz - 1))];
  function rings(n, useKnown) {
    const res = [], t1 = norm3(cross(n, Math.abs(n[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0])), t2 = cross(n, t1);
    const inf = pieceInfo(vol, piece, n); if (inf.hi - inf.lo < 9.5 || inf.radius < 36) return res;
    const c0 = inf.center, a0 = dot(c0, t1), b0 = dot(c0, t2), span = Math.max(0, inf.radius - 34);
    for (let top = inf.hi - 0.8; top - 9 >= inf.lo + 0.4; top -= 9 + ECON.kerf) {
      let best = null;
      for (let a = a0 - span; a <= a0 + span; a += 7) for (let b = b0 - span; b <= b0 + span; b += 7) {
        let ok = true, sv = 0, sk = 0, cnt = 0;
        for (let q = 0; q < 16 && ok; q++) {
          const ca = Math.cos(q * TAU / 16), sa = Math.sin(q * TAU / 16);
          for (const rr of [29, 35]) { for (const hh of [top - 1, top - 8]) {
            const u = a + ca * rr, v = b + sa * rr, x = t1[0] * u + t2[0] * v + n[0] * hh, y = t1[1] * u + t2[1] * v + n[1] * hh, z = t1[2] * u + t2[2] * v + n[2] * hh;
            if (!fleshAt(x, y, z)) { ok = false; break; }
            for (let ci = 0; ci < st.cracks.length; ci++) { const c = st.cracks[ci]; if (c.open <= 0.5 || (useKnown && !known[ci])) continue; crackG(c, x, y, z, _cg); if (Math.abs(_cg[0]) < 2.2 && _cg[1] > 0.5) { ok = false; break; } }
            if (!ok) break;
            const bb = vIndex(vol, x, y, z) * 4; sv += vd(m[bb + 1] / 255, m[bb] / 255, m[bb + 2] / 255, m[bb + 3] / 255, grade); sk += kAt(x, y, z); cnt++;
          } if (!ok) break; }
        }
        if (ok && cnt) { const r = { v: sv / cnt, k: sk / cnt }; if (!best || r.v > best.v) best = r; }
      }
      if (best) res.push(best);
    }
    return res;
  }
  const dirs = slab ? [slab.n] : [[0, 1, 0], [1, 0, 0], [0, 0, 1]];
  const bestRings = k => { let b = []; for (const d of dirs) { const r = rings(d, k); if (r.reduce((a, x) => a + x.v, 0) > b.reduce((a, x) => a + x.v, 0)) b = r; } return b; };
  const ringVol = Math.PI * (36 * 36 - 28 * 28) * 9 / 1000 * ECON.braceletBonus;
  const rT = wSum * v3 > 20 ? bestRings(false) : [], rK = wSum * v3 > 20 ? bestRings(true) : [];
  let truthB = 0; for (const r of rT) truthB += r.v * ringVol;
  let ext = 0; if (!slab) { const inf = pieceInfo(vol, piece, [0, 1, 0]); ext = inf.hi - inf.lo; }
  return {
    truth: truth * sc + truthB, truthParts: { small: truth * sc, rings: rT.map(r => r.v * ringVol), Vclean: ag.Vclean * v3, Vcrack: ag.Vcrack * v3, Vtop: ag.Vtop * v3, volClean: ag.volClean * v3, volCrack: ag.volCrack * v3, volTop: ag.volTop * v3, colorFrac: wSum ? ag.col / wSum : 0, wMean: wSum ? ag.w / wSum : 0.3, cotMean: wSum ? ag.cot / wSum : 0, dirtMean: wSum ? ag.dirt / wSum : 0 }, S: [S1 * sc, S1u * sc, S2 * sc, S2u * sc, S3 * sc, S3u * sc], rings: rK, ringVol,
    stats: {
      weight: solidW * v3 * ECON.density, fleshCm3: wSum * v3, thickness: slab ? T : ext, isSlab: !!slab,
      expArea: expVox * vx * vx / 100, expColor: E.length ? expColor / E.length : 0, expWater: E.length ? expW / E.length : 0,
      kAvg: wSum ? kSum / wSum : 0, knownCracks: known.filter(Boolean).length, bracelets: rK.length, hasWindow: E.length > 0,
    },
  };
}
// 观察者（买家或卖家）对未见部分的先验密度：场口常识 + 灯下浅层表现（受皮壳遮挡与水平限制）+ 个人偏差
function priorDensity(st, vol, who, skill) {
  const O = ORIGINS[st.origin], r = new Rng(seedOf(st.seed, 'prior', who));
  const relT = clamp(Math.exp(-st.skin.sig * vol.skinMean * 0.35), 0.15, 1) * Math.sqrt(O.rel);
  const th = skill * relT;
  const wp = clamp(lerp(O.w / 100, vol.shallowW, th) + r.norm() * (1 - th) * 0.09, 0.04, 0.97);
  const cp = clamp(lerp(O.c / 100 * 0.10, vol.shallowC, th) * (1 + r.norm() * 0.5 * (1 - th)), 0, 1);
  return vd(wp, cp, 0.15, 0.05, HUES[st.hue].grade * lerp(0.6, 1, th)) * ECON.priorScale;
}
function estimate(st, vol, ev, who, prof) {
  const O = ORIGINS[st.origin], P = priorDensity(st, vol, who, prof.skill), S = ev.S;
  const rho = 0.5 * prof.risk + 0.25 * O.crack / 100;
  let v = S[0] - rho * S[1] + prof.opt * (S[2] - rho * S[3]) + P * (S[4] - rho * S[5]);
  for (const r of ev.rings) { const u = 1 - r.k, b = r.k * r.v + u * (r.k * r.v * prof.opt + (1 - r.k) * P); v += ev.ringVol * b * (1 - rho * u) * lerp(1 - 0.5 * O.crack / 100, 1, r.k); }
  return Math.max(0, v) * ECON.rough; // 毛料按成品零售价的批发折扣计
}
function fmt(n) { n = Math.round(n); const a = Math.abs(n); if (a >= 1e6) return (n / 1e4).toFixed(0) + '万'; if (a >= 10000) return (n / 1000).toFixed(a >= 100000 ? 0 : 1).replace(/\.0$/, '') + 'K'; return String(n); }
// 这块料赌的是什么：只根据外部能看到的迹象（含可能骗人的皮壳表现），不读内部真相
function betOf(st, vol, hasWindowColor) {
  const O = ORIGINS[st.origin], r = new Rng(seedOf(st.seed, 'bet'));
  const tags = [], relT = clamp(Math.exp(-st.skin.sig * vol.skinMean * 0.35), 0.1, 1);
  const realColor = vol.shallowC > 0.09, fakeColor = !realColor && r.chance((1 - O.rel) * 0.5);
  let main, why;
  if (hasWindowColor) { main = '赌色'; why = '窗口已经见色。要判断的是这片色往里走多深：是一条带、一团，还是只有贴皮薄薄一层。'; }
  else if (realColor || fakeColor) { main = '赌色'; why = relT > 0.35 ? '皮上有松花，灯下带色。色是真是假、进得深不深，要换几个位置压灯比对。' : '皮上有松花，但皮厚挡光，灯下看不真切。松花可能只是皮上的表现。'; }
  else { main = '赌种水'; why = relT > 0.35 ? '没什么色的表现，价值全看种水：灯下光晕大而干净说明种老，发白发散说明种嫩。' : '皮厚不透光，也没见色。只能凭皮壳紧不紧、砂细不细猜种水，风险高。'; }
  const d = st.rad.map(v => v * 2).sort((a, b) => b - a);
  if (d[1] >= 90 && d[2] >= 50) tags.push('赌镯位');
  const vis = st.cracks.filter(c => c.open > 0.5 && c.skinVis === 1).length;
  if (vis >= 1) tags.push('赌裂');
  if (st.fog.t > 0.8) tags.push('有雾层');
  return { main, why, tags };
}

/* ---------- 世界、货源、交易 ---------- */
const volCache = new Map(); // seed -> {st, vol, applied}
// strokes: 每 5 个数一组 [x,y,z,R,clipIndex]；clips[i] 是当时那块料的切面集合
function getVol(rec) {
  let e = volCache.get(rec.seed);
  if (!e) { const st = genStone(rec.seed, rec.origin, rec.channel); const vol = bake(st); e = { st, vol, applied: 0 }; volCache.set(rec.seed, e); }
  const s = rec.strokes || [], clips = rec.clips || [[]];
  for (; e.applied < s.length; e.applied += 5) carve(e.vol, clipPiece(clips[s[e.applied + 4]]), s[e.applied], s[e.applied + 1], s[e.applied + 2], s[e.applied + 3]);
  if (rec.fake && !e.faked) { e.faked = true; e.st.fake = rec.fake.type; if (rec.fake.type === 'veneer') veneer(e.vol, rec.fake.spheres); }
  return e;
}
const WHOLE = { id: 0, planes: [] };
/* ---------- 造假料 ----------
 * paint：染色做皮，皮上满是“松花”，里面没有。放大镜下色块平、边缘齐、没有砂粒。
 * veneer：贴片假窗，窗口贴了两毫米好料，下面是原来的差料。压灯时光散不开，放大镜下窗口一圈有胶线。 */
function veneer(vol, spheres) {
  const { nx, ny, nz, vx, geom: g, mat: m } = vol;
  for (let q = 0; q + 3 < spheres.length; q += 4) { const cx = spheres[q], cy = spheres[q + 1], cz = spheres[q + 2], R = spheres[q + 3];
    for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) { const x = (i + 0.5) * vx - vol.hx, y = (j + 0.5) * vx - vol.hy, z = (k + 0.5) * vx - vol.hz, d = Math.hypot(x - cx, y - cy, z - cz);
      if (d < R - vx || d > R + 2.6) continue; const b = (i + nx * (j + ny * k)) * 4; if (g[b] > 1) continue; m[b] = 225; m[b + 1] = 200; m[b + 2] = 8; m[b + 3] = 0; } }
  vol.ver++;
}
const FAKE_RATE = { '夜市地摊': 0.28, '玉石集散地': 0.06, '翡翠公盘': 0, '场口直采': 0 };
const FAKE_NAME = { paint: '染色做皮：皮上的松花是染上去的', veneer: '贴片假窗：窗口贴了一层好料，底下是差料' };
// 当面指出是假货：说对了老板心虚大降价，说错了老板翻脸不卖
function callOut(w, L) {
  if (L.called) return { msg: '已经说过了。' }; L.called = true;
  if (L.fake) { L.reserve = Math.max(100, Math.round(L.reserve * 0.12 / 10) * 10); L.ask = Math.round(L.reserve * 1.3 / 10) * 10; L.exposed = true; w.eye += 5; achieve(w, 'fake', '识破一块假货'); return { ok: true, msg: `老板脸色一变：“……兄弟好眼力，这块 ${fmt(L.ask)} 你拿走，别声张。”（${FAKE_NAME[L.fake.type]}）眼力 +5` }; }
  L.patience = 0; w.fame = Math.max(-50, (w.fame || 0) - 2); return { ok: false, msg: '老板把石头一把收走：“不懂别乱讲！这是正经料子。”这块不卖你了。' };
}
/* ---------- 熟客与口碑 ---------- */
function relOf(w, name) { return (w.rel && w.rel[name]) || 0; }
function relWord(v) { return v >= 30 ? '老主顾' : v >= 10 ? '熟客' : v <= -25 ? '有过节' : v <= -8 ? '有点防你' : '生客'; }
function relAdd(w, name, d) { w.rel[name] = clamp(relOf(w, name) + d, -80, 80); }
/* ---------- 铺面 ---------- */
const SHOPLV = [
  { name: '没有铺面', cost: 0, rent: 0, slots: 0, mult: 0, p: 0 },
  { name: '市场小柜台', cost: 30000, rent: 400, slots: 4, mult: 1.0, p: 0.20, tip: '租一节玻璃柜，摆四件。路过的散客会按零售价买。' },
  { name: '临街铺面', cost: 150000, rent: 1200, slots: 8, mult: 1.06, p: 0.28, tip: '有门脸，客流更好，卖得比市场价高一点。' },
  { name: '精品店', cost: 600000, rent: 3500, slots: 14, mult: 1.15, p: 0.36, tip: '装修讲究，高货卖得上价，摆十四件。' },
];
function upgradeShop(w) { const nx = SHOPLV[w.shop + 1]; if (!nx) return { ok: false, msg: '已经是最好的铺面。' }; if (nx.cost > w.cash) return { ok: false, msg: '现金不够。' }; w.cash -= nx.cost; w.shop++; w.log.push({ day: w.day, t: `盘下${nx.name}`, amt: -nx.cost }); achieve(w, 'shop', '有了自己的铺面'); return { ok: true, msg: `盘下了${nx.name}，每天租金 ${nx.rent}。` }; }
function shelfCount(w) { let n = w.items.filter(i => i.state === 'shelf').length; for (const s of w.stones) if (!s.closed) for (const p of s.pieces) if (p.shelf && !p.sold) n++; return n; }
// 料头也能摆进铺面零售，或收进藏品柜
function pieceShelf(w, s, p) { if (shelfCount(w) >= slotsOf(w)) return { ok: false, msg: w.shop ? '柜台摆满了。' : '还没有铺面，先到账本里盘一个。' }; p.shelf = true; p.kept = false; return { ok: true }; }
function pieceKeep(w, s, p, on) { p.kept = on; p.shelf = false; if (on) { achieve(w, 'keep', '第一件藏品'); closeStone(w, s); } else if (s.closed) { s.closed = false; } }
function toShelf(w, it) { if (shelfCount(w) >= slotsOf(w)) return { ok: false, msg: w.shop ? '柜台摆满了。' : '还没有铺面，先到账本里盘一个。' }; it.state = 'shelf'; it.shelfDay = w.day; return { ok: true }; }
/* ---------- 场景、眼力、订单、成就 ---------- */
const SCENES = {
  '夜市地摊': { channels: ['小商贩', '个人转让'], eye: 0, cash: 0, n: 6, tip: '灯泡底下的地摊。便宜、杂，卖家自己也看不准，假表现多，捡漏和打眼都在这里。' },
  '玉石集散地': { channels: ['二级供应商', '大型集散地'], eye: 15, cash: 6e5, n: 6, tip: '档口整齐，开窗料多，卖家是行家，价格贴着货走。看得准才有差价。' },
  '翡翠公盘': { channels: ['拍卖市场'], eye: 40, cash: 2e6, n: 5, auction: true, tip: '暗标竞拍：每块料写一口价，收工后开标，压过所有人才拿得到，出多少付多少。' },
  '场口直采': { channels: ['场口直采'], eye: 80, cash: 6e6, n: 6, tip: '矿上刚出的蒙头料，没人开过窗，价低量大，全凭皮壳和灯下功夫。' },
};
// 工具铺：等级从 1 开始，price[i] 是升到 i+2 级的价钱
const SHOP = {
  torch: { name: '手电', levels: ['普通手电', '强光手电', '超强探照灯'], price: [8000, 45000], tip: '光更强，照得更深更远，厚皮黑皮也能打进一点。' },
  loupe: { name: '放大镜', levels: ['3 倍放大镜', '5 倍放大镜', '8 倍放大镜'], price: [4000, 20000], tip: '放得更大，砂粒、细裂、晶粒看得更清。' },
  saw: { name: '锯机', levels: ['旧锯机', '薄片锯', '线切割机'], price: [12000, 60000], tip: '锯缝更窄（1.2 → 0.8 → 0.5 毫米），切工更便宜，少吃料。' },
};
const KERFS = [1.2, 0.8, 0.5], CUTK = [1, 0.85, 0.7];
function applyTools(w) { if (!w.tools) w.tools = { torch: 1, loupe: 1, saw: 1 }; ECON.kerf = KERFS[w.tools.saw - 1]; ECON.cutBase = Math.round(80 * CUTK[w.tools.saw - 1]); }
function buyTool(w, key) { const S = SHOP[key], lv = w.tools[key]; if (lv >= S.levels.length) return { ok: false, msg: '已经是最高级了。' }; const p = S.price[lv - 1]; if (p > w.cash) return { ok: false, msg: '现金不够。' }; w.cash -= p; w.tools[key]++; applyTools(w); w.log.push({ day: w.day, t: `添置 ${S.levels[lv]}`, amt: -p }); achieve(w, 'tool', '第一件好工具'); return { ok: true, msg: `换上了${S.levels[lv]}。` }; }
// 请师傅掌眼：付费买一个有可能出错的意见。同一块石头问几次都是同一个答案
function appraiseFee(rec) { return Math.max(200, Math.round((rec.ask || rec.buyPrice || 20000) * 0.01 / 10) * 10); }
function appraise(w, rec) {
  const fee = appraiseFee(rec); if (fee > w.cash) return { ok: false, msg: '现金不够付掌眼费。' };
  const st = getVol(rec).st, r = new Rng(seedOf(rec.seed, 'appraise')), gi = gradeIdx(st.w0), names = ['豆种', '糯种', '糯冰种', '冰种', '高冰种', '玻璃种'];
  const g = clamp(gi + (r.chance(0.68) ? 0 : (r.chance(0.5) ? 1 : -1)), 0, 5), cc = colorClass(st), cg = r.chance(0.66) ? cc : r.pick(['none', 'skin', 'deep']);
  const many = st.cracks.filter(c => c.open > 0.5).length >= 2, kg = r.chance(0.75) ? many : !many;
  const fk = rec.fake && r.chance(0.8);
  w.cash -= fee; w.log.push({ day: w.day, t: `请师傅掌眼 ${rec.origin}·${rec.info.skin}`, amt: -fee });
  rec.opinion = `师傅看了半天：“种水我看在${names[g]}上下，${{ none: '里面没什么色', skin: '色怕是只有贴皮一层', deep: '色应该能吃进去', full: '色应该能吃进去' }[cg]}，${kg ? '裂不少，取镯子要小心' : '裂不多'}。我也是凭经验，十次里总要错个两三次。”${fk ? `他又压低声音：“${rec.fake.type === 'paint' ? '这皮色我看着不对劲，像是做过的。' : '这窗口你拿放大镜看看边上，我怀疑是贴的。'}”` : ''}`;
  return { ok: true, fee };
}
// 卖家的话术：有的是实话，有的只是吆喝
function patter(st, vol, L) {
  const r = new Rng(seedOf(L.seed, 'patter')), C = CHANNELS[L.channel], honest = r.chance(0.35 + C.skill * 0.5), gi = gradeIdx(st.w0), cc = colorClass(st), lines = [];
  const goodW = honest ? gi >= 3 : r.chance(0.6), goodC = honest ? (cc === 'deep' || cc === 'full') : r.chance(0.6);
  lines.push(goodW ? r.pick(['老板：你压灯看这水头，光一下就散开了，种老得很。', '老板：这皮多紧，砂多细，里面种差不了。']) : r.pick(['老板：种嘛一般，胜在便宜，切开做点小件稳赚。', '老板：这块我不吹，自己看，看好了再说价。']));
  lines.push(goodC ? r.pick(['老板：松花都爬到这了，色肯定吃进去了。', '老板：上一块同口的，一刀下去满绿。']) : r.pick(['老板：色我不敢保，赌石嘛，赌的就是个未知。', '老板：没色也不怕，底子干净就值钱。']));
  if (L.channel === '个人转让') lines.push('这位是急用钱的散户，自己也说不清石头的来路。');
  return lines;
}
const EVENTS = [
  { t: '直播间这两天抢手镯，手镯成品行情热', type: 'bracelet', m: 1.18 }, { t: '婚庆旺季，蛋面戒面好卖', type: 'cab', m: 1.25 }, { t: '佛事节庆将近，牌子挂件走得快', type: 'pendant', m: 1.2 },
  { t: '珠串市场货多，价格被压', type: 'bead', m: 0.82 }, { t: '有藏家在收雕件摆件', type: 'carve', m: 1.3 }, { t: '手镯市场这几天冷清', type: 'bracelet', m: 0.88 },
];
function rollEvent(w) { const r = new Rng(seedOf(w.seed, 'event', w.day)); w.event = r.chance(0.55) ? r.pick(EVENTS) : null; }
function productDemand(w, type) { return w.event && w.event.type === type ? w.event.m : 1; }
/* ---------- 主线剧情与目标 ---------- */
const CHAPTERS = [
  { title: '第一章 路边看客', story: '你在瑞丽的玉器厂打零工，一家四口挤在厂区的工棚里：老婆阿秀，八岁的小满，还有刚出生的小宝。兜里只有八千块。每天下了班就蹲在姐告夜市的摊子边上，看别人打灯、讲价、下刀。摆摊的牛叔看你蹲了半个月，递过来一支旧手电：“光看热闹没用。你先猜，猜完看他切，对上了再说买。”',
    goals: [['watch3', '围观并猜 3 块石头（写下判断，再看别人切）'], ['tip', '猜对一次种水，赢旁边人的彩头'], ['eye8', '眼力达到 8']], reward: { eye: 2, cash: 12000 }, unlock: '可以自己买石头、开窗、转手了', done: '你猜对的次数多了，旁边的人开始回头看你。牛叔从腰包里数出一万二：“借你的。小料，买了就卖，别切。先学会当个二道贩子。”' },
  { title: '第二章 二道贩子', story: '二道贩子不切石头，赚的是眼力差：便宜买进来，擦个窗、换个人，加点钱卖出去。看不准的不买，买错了认。',
    goals: [['buy1', '买下第一块石头'], ['flip2', '做成 2 块赚钱的石头'], ['cash3', '现金达到 3 万']], reward: { eye: 5, cash: 0 }, unlock: '可以下刀切石头、送去做成品、接客户订单了；玉石集散地开放', done: '你把牛叔的钱连本带利还了。他摆摆手：“倒来倒去赚的是辛苦钱。真正的利润在成品上：一块料做成镯子戴到客人手上，中间那几道都是你的。”' },
  { title: '第三章 自己做货', story: '从卖石头到卖成品，中间隔着下刀、取料、找师傅。切对了一只镯子扛起整块料，切错了只能车珠子。客人要什么，订单上写着。',
    goals: [['cut1', '亲手下第一刀'], ['item1', '做出第一件成品'], ['order', '完成一张客户订单'], ['cash20', '现金达到 20 万']], reward: { eye: 8, cash: 0 }, unlock: '可以盘铺面、把货摆进柜台；翡翠公盘开放', done: '有客人开始问：“你有没有店？我带朋友来看。”你发现自己一直在给批发商打工，零售那一截利润从来没拿到过。' },
  { title: '第四章 开铺面', story: '盘一节柜台，把自己做的货摆进去。有了铺面，散客按零售价买，熟客会回头，口碑会传。',
    goals: [['shop1', '盘下一个铺面'], ['shelf3', '铺面卖出 3 件货'], ['regular', '有一位买家成为你的熟客']], reward: { eye: 10, cash: 30000 }, unlock: '可以开直播了；场口直采开放', done: '铺子稳了。隔壁档口的小姑娘架着手机对着石头讲了一晚上，卖得比你一个月还多。牛叔说：“你讲石头比她讲得好，就是没人听见。”' },
  { title: '第五章 开直播', story: '架起手机，把打灯、下刀、出货都播出去。切涨切垮都是内容，讲得实在才留得住人。粉丝多了，货卖得快，价也卖得上去。',
    goals: [['live1', '开第一场直播'], ['fans1w', '粉丝达到 1 万'], ['bid', '在翡翠公盘中标一次']], reward: { eye: 12, cash: 50000 }, unlock: '可以开分店、雇员工了', done: '“牛叔的徒弟”成了一个名字。有人从外地坐飞机来店里，有人想加盟，一个人已经忙不过来了。' },
  { title: '第六章 连锁', story: '开分店，雇店员、师傅和主播。你不用每块石头都自己照了，但每家店的货还得你把关。',
    goals: [['branch2', '开出 2 家分店'], ['staff3', '雇 3 名员工'], ['worth1000', '身家达到 1000 万']], reward: { eye: 30, cash: 0 }, unlock: '', done: '夜市还是那个夜市。灯泡底下蹲着一个年轻人，眼睛盯着别人手里的石头。你走过去，把那支旧手电递给他：“光看热闹没用。你先猜。”' },
];
// 每个玩法在第几章解锁（章节从 0 数）
const UNLOCK = { buy: 1, open: 1, tools: 1, cut: 2, work: 2, tray: 2, shop: 3, live: 4, chain: 5 };
function can(w, k) { return w.chapter >= (UNLOCK[k] || 0); }
const DEBT = 0;
function netWorth(w) { let v = w.cash; for (const r of w.recv) v += r.amt; for (const it of w.items) if (it.state === 'ready' || it.state === 'shelf' || it.state === 'kept') v += it.value * 0.6; return v; }
function goalDone(w, k) {
  const a = w.ach, st = w.stat, staff = w.staff.clerk + w.staff.master + w.staff.host;
  return ({ watch3: st.watch >= 3, tip: st.tips > 0, eye8: w.eye >= 8, buy1: w.stones.length > 0, flip2: st.wins >= 2, cash3: w.cash >= 3e4, cut1: st.cuts > 0, item1: w.items.length > 0, order: !!a.order, cash20: w.cash >= 2e5,
    shop1: w.shop >= 1, shelf3: st.shelfSold >= 3, regular: Object.keys(w.rel).some(k2 => w.rel[k2] >= 10), live1: st.live > 0, fans1w: w.fans >= 1e4, bid: !!a.bid, branch2: w.branches >= 2, staff3: staff >= 3, worth1000: netWorth(w) >= 1e7 })[k];
}
// 检查当前章节是否完成；完成则发奖励并进入下一章，返回刚完成的章节
function checkStory(w) {
  if (netWorth(w) >= 1e6) achieve(w, 'm1', '身家过百万'); if (netWorth(w) >= 1e7) achieve(w, 'm10', '身家过千万'); if (w.eye >= 100) achieve(w, 'eye100', '眼力过百'); if (w.stat.sold >= 20) achieve(w, 'sold20', '卖出二十件货'); if (w.stones.filter(s => s.closed).length >= 10) achieve(w, 'ten', '经手十块石头'); if (w.day >= 30) achieve(w, 'd30', '撑过第一个月');
  const ch = CHAPTERS[w.chapter]; if (!ch || !ch.goals.every(g => goalDone(w, g[0]))) return null;
  w.chapter++; w.eye += ch.reward.eye; w.cash += ch.reward.cash; if (ch.reward.cash) w.log.push({ day: w.day, t: `${ch.title} 完成`, amt: ch.reward.cash });
  return ch;
}
/* ---------- 围观：没本钱时先猜别人的石头 ---------- */
function watch(w, L, guess) {
  if (w.watchLeft <= 0) return { ok: false, msg: '今天看够了，摊主嫌你光看不买。明天再来。' };
  const st = getVol(L).st, gi = gradeIdx(st.w0), cc = colorClass(st), ck = st.cracks.filter(c => c.open > 0.5).length >= 2 ? 'many' : 'few', r = new Rng(seedOf(w.seed, 'watch', L.seed));
  const pts = Math.round(((guess.water === gi ? 10 : Math.abs(guess.water - gi) === 1 ? 5 : 0) + (guess.color === cc ? 8 : 0) + (guess.crack === ck ? 4 : 0)) * 0.5);
  const tip = guess.water === gi ? r.int(3, 8) * 100 : 0;
  w.watchLeft--; w.eye += pts; w.cash += tip; w.stat.watch++; if (tip) { w.stat.tips++; w.log.push({ day: w.day, t: '猜对种水，赢了旁人的彩头', amt: tip }); }
  L.sold = true; L.watched = true;
  return { ok: true, pts, tip, water: gi, color: cc, crack: ck, fake: L.fake ? FAKE_NAME[L.fake.type] : '' };
}
/* ---------- 直播 ---------- */
const CHAT = { open: ['来了来了', '主播今天切什么', '蹲一个涨', '新人报到', '这灯打得可以'], sold: ['拍了拍了', '手慢无', '这只我要了', '已下单', '主播实在'], miss: ['有点贵', '再看看', '种不够', '留着下次'], cut: ['刚才那刀我看了，刺激', '切石头的主播才是真主播', '垮了也敢播，关注了'], end: ['下播了？明天还来', '关注了', '明天几点'] };
function liveRun(w) {
  if (w.liveDay === w.day) return { ok: false, msg: '今天已经播过一场了。' };
  const items = w.items.filter(i => i.state === 'ready' || i.state === 'shelf').slice(0, 8);
  if (!items.length) return { ok: false, msg: '没有能上架的成品。先做几件货再开播。' };
  const r = new Rng(seedOf(w.seed, 'live', w.day)), drama = w.cutDay === w.day ? 1.6 : 1;
  const viewers = Math.round((300 + w.fans * 0.12 + Math.max(0, w.fame) * 30) * r.range(0.7, 1.4) * drama), lines = [], sold = []; let income = 0;
  lines.push(['sys', `开播，${viewers} 人在看`]); for (let i = 0; i < 2; i++) lines.push(['c', r.pick(CHAT.open)]); if (drama > 1) lines.push(['c', r.pick(CHAT.cut)]);
  for (const it of items) { const p = clamp(0.36 + viewers / 16000, 0.36, 0.92), k = (0.78 + Math.min(0.45, w.fans / 220000) + r.range(0, 0.1)) * productDemand(w, it.type);
    if (r.u() < p) { const price = Math.round(it.value * k / 10) * 10; it.state = 'sold'; it.price = price; income += price; sold.push(it); w.stat.sold++; lines.push(['sys', `${it.name} ${fmt(price)} 成交`]); lines.push(['c', r.pick(CHAT.sold)]); const s = w.stones.find(x => x.id === it.stone); if (s) { s.proceeds += price; if (!s.closed && stoneDone(w, s)) closeStone(w, s); } }
    else lines.push(['c', `${it.name}：${r.pick(CHAT.miss)}`]); }
  const gain = Math.round(viewers * 0.6 * drama + sold.length * 150 + r.range(0, 80)); w.fans += gain; w.cash += income; w.liveDay = w.day; w.stat.live++; w.stat.liveIncome += income;
  if (income) w.log.push({ day: w.day, t: `直播卖出 ${sold.length} 件`, amt: income }); lines.push(['c', r.pick(CHAT.end)]); lines.push(['sys', `下播。成交 ${sold.length} 件 ${fmt(income)}，涨粉 ${gain}`]);
  achieve(w, 'live', '第一场直播'); if (w.fans >= 1e4) achieve(w, 'fans1', '万粉博主'); if (w.fans >= 1e5) achieve(w, 'fans10', '十万粉博主');
  return { ok: true, viewers, lines, income, gain, sold: sold.length };
}
/* ---------- 分店与员工 ---------- */
const BRANCH_COST = 600000, BRANCH_RENT = 2500;
const STAFF = { clerk: { name: '店员', pay: 300, max: 8, tip: '每名店员让柜台里的货每天更容易卖出去。' }, master: { name: '驻店师傅', pay: 700, max: 2, tip: '自己人做货：工费省两成，工期少一天。' }, host: { name: '主播', pay: 600, max: 1, tip: '你不播的日子，他替你播一场。' } };
function openBranch(w) { if (w.shop < 2) return { ok: false, msg: '先把总店升到临街铺面。' }; if (w.cash < BRANCH_COST) return { ok: false, msg: '现金不够。' }; w.cash -= BRANCH_COST; w.branches++; w.log.push({ day: w.day, t: `开第 ${w.branches} 家分店`, amt: -BRANCH_COST }); achieve(w, 'branch', '第一家分店'); return { ok: true, msg: `第 ${w.branches} 家分店开张，多了 10 个柜位，日租 ${BRANCH_RENT}。` }; }
function hire(w, k, d) { if (k === 'master' && d > 0) ownMaster(w); const S = STAFF[k], n = w.staff[k] + d; if (n < 0 || n > S.max) return { ok: false, msg: d > 0 ? `${S.name}最多 ${S.max} 名。` : '' }; w.staff[k] = n; if (d > 0) achieve(w, 'hire', '第一名员工'); return { ok: true, msg: d > 0 ? `雇了一名${S.name}，日薪 ${S.pay}。` : `辞退了一名${S.name}。` }; }
function slotsOf(w) { return SHOPLV[w.shop].slots + w.branches * 10; }
/* ---------- 家：吃住行、妻儿、上学、帮工、借贷 ----------
 * 时间：游戏里过一天，家里过一个月（孩子按月长大）。数值是游戏平衡，不是现实物价。 */
const FOODS = [{ name: '粗茶淡饭', cost: 40, hp: -0.2, har: -0.2 }, { name: '家常饭菜', cost: 90, hp: 0.15, har: 0.15 }, { name: '吃得讲究', cost: 260, hp: 0.4, har: 0.5 }];
const HOMES = [{ name: '厂区工棚', price: 0, rent: 30, hp: -0.3, har: -0.3 }, { name: '城中村出租屋', price: 0, rent: 90, hp: 0, har: 0 }, { name: '两居室', price: 380000, rent: 0, hp: 0.3, har: 0.5 }, { name: '大平层', price: 1500000, rent: 0, hp: 0.5, har: 0.9 }, { name: '别墅', price: 6000000, rent: 0, hp: 0.7, har: 1.2 }];
const CARS = [{ name: '没有车', price: 0, cost: 0, tip: '' }, { name: '二手摩托', price: 4000, cost: 10, tip: '跑夜市省力气，身体少累一点。' }, { name: '面包车', price: 45000, cost: 40, tip: '能拉货，每个场子多看到一块料。' }, { name: '轿车', price: 180000, cost: 80, tip: '见客户有面子，订单多卖 5%。' }, { name: '越野车', price: 600000, cost: 150, tip: '跑场口方便，每个场子多看到两块料。' }];
// 学校：按年龄段可选。cost 是每天；g 是每月各项成长（学识 book、手艺 craft、眼力 eye、口才 talk、管事 manage）
const SCHOOLS = {
  home: { name: '在家带', min: 0, max: 72, cost: 0, g: { book: 0.1 } },
  kg_pub: { name: '公办幼儿园', min: 36, max: 72, cost: 20, g: { book: 0.35, talk: 0.2 } }, kg_priv: { name: '私立幼儿园', min: 36, max: 72, cost: 90, g: { book: 0.5, talk: 0.45 } },
  pri_vil: { name: '村小', min: 72, max: 144, cost: 5, g: { book: 0.3, craft: 0.15 } }, pri_pub: { name: '公办小学', min: 72, max: 144, cost: 25, g: { book: 0.5, talk: 0.1 } }, pri_priv: { name: '私立双语小学', min: 72, max: 144, cost: 160, g: { book: 0.75, talk: 0.3 } },
  mid_pub: { name: '公办初中', min: 144, max: 180, cost: 30, g: { book: 0.5 } }, mid_key: { name: '重点初中', min: 144, max: 180, cost: 130, g: { book: 0.9 }, need: 35 }, mid_trade: { name: '玉雕技校', min: 144, max: 216, cost: 60, g: { book: 0.15, craft: 1.0, eye: 0.3 } },
  high: { name: '高中', min: 180, max: 216, cost: 60, g: { book: 0.7 }, need: 40 }, voc: { name: '职高（电商直播）', min: 180, max: 216, cost: 50, g: { book: 0.3, talk: 0.9, manage: 0.4 } },
  college: { name: '外地上大学', min: 216, max: 264, cost: 220, g: { book: 0.9, manage: 0.5, talk: 0.3 }, need: 60, away: true },
  work: { name: '不上学，跟着干', min: 144, max: 9999, cost: 0, g: {} },
};
const JOBS = { none: { name: '不帮忙', trait: '' }, carver: { name: '学雕刻、做货', trait: 'craft', tip: '做件工费更省，成品更值钱。' }, manager: { name: '看店', trait: 'manage', tip: '柜台里的货卖得更快。' }, spotter: { name: '跟着看石头', trait: 'eye', tip: '看货源时会说出自己的判断，眼力越好越准。' }, cutter: { name: '开机器切石头', trait: 'craft', tip: '切工更便宜。' }, host: { name: '当主播', trait: 'talk', tip: '你没播的日子替你播一场。' } };
const GIFTS = ['book', 'craft', 'eye', 'talk', 'manage'];
function newKid(seed, name, months, school) { const r = new Rng(seedOf(seed, 'kid', name)); return { name, months, school, job: 'none', t: { book: months > 72 ? 18 : 0, craft: 2, eye: 2, talk: months > 72 ? 8 : 0, manage: 0, moral: 60 }, gift: r.pick(GIFTS), weak: r.pick(GIFTS), away: false }; }
const TRAIN = { book: { name: '请家教补课', cost: 800, trait: 'book', gain: 3 }, craft: { name: '送去玉雕师傅那里学手艺', cost: 1200, trait: 'craft', gain: 3.5 }, eye: { name: '带去公盘看石头练眼', cost: 1500, trait: 'eye', gain: 3.5 }, talk: { name: '口才主持班', cost: 1000, trait: 'talk', gain: 3.5 }, manage: { name: '到铺子里学记账管货', cost: 600, trait: 'manage', gain: 3 }, sport: { name: '体育锻炼、夏令营', cost: 400, trait: 'moral', gain: 2.5 } };
const BABY_NAMES = ['小禾', '小石', '小翠', '小安', '小舟', '小年', '小糯', '小冰', '小阳', '小川'], WIFE_NAMES = ['小芸', '阿琴', '玉兰', '晓梅'], LOVER_NAMES = ['小薇', '阿珍', '丽丽'];
const FAMC = { baby: 30000, divorce: 5000, wedding: 88000, loverDaily: 150, breakup: 15000, alimony: 60, nanny: 80, maxKids: 10 };
function newFamily(seed) { return { wife: '阿秀', hp: 70, har: 65, food: 0, home: 0, car: 0, kids: [newKid(seed, '小满', 96, 'pri_vil'), newKid(seed, '小宝', 2, 'home')], loans: [], rested: 0 }; }
function kidAge(k) { return Math.floor(k.months / 12); }
function schoolsFor(k) { return Object.keys(SCHOOLS).filter(id => { const S = SCHOOLS[id]; return k.months >= S.min && k.months < S.max && (!S.need || k.t.book >= S.need); }); }
function traitWord(v) { return v >= 70 ? '很出挑' : v >= 45 ? '不错' : v >= 25 ? '一般' : v >= 10 ? '刚入门' : '还小'; }
// 孩子帮工的效果：trait/100 × 投入（上学时课余帮忙算一半；出门上大学时帮不上）
function famEff(w, job) { let e = 0; for (const k of w.fam.kids) { if (k.job !== job || k.months < 144 || k.away) continue; e += k.t[JOBS[job].trait] / 100 * (k.school === 'work' ? 1 : 0.5); } return Math.min(1, e); }
function lifeCost(w) { const f = w.fam, here = f.kids.filter(k => !k.withMom), items = [['伙食', FOODS[f.food].cost + here.length * 12], ['住', HOMES[f.home].rent], ['车', CARS[f.car].cost]]; let sch = 0; for (const k of here) sch += SCHOOLS[k.school].cost; items.push(['学费', sch]);
  items.push(['保姆', !f.wife && here.some(k => k.months < 72 && !k.away) ? FAMC.nanny : 0], ['抚养费', f.kids.filter(k => (k.withMom || k.out) && k.months < 216).length * FAMC.alimony], ['外面的开销', f.lover ? FAMC.loverDaily : 0]);
  let intr = 0; for (const L of f.loans) intr += Math.round(L.principal * L.rate); items.push(['利息', intr]); return { items: items.filter(x => x[1] > 0), total: items.reduce((a, x) => a + x[1], 0) }; }
const LOANS = { home: { name: '房子抵押', rate: 0.0012, ltv: 0.6 }, car: { name: '车子抵押', rate: 0.002, ltv: 0.5 }, shark: { name: '民间借贷', rate: 0.012, ltv: 0 } };
function loanRoom(w, type) { const f = w.fam, used = f.loans.filter(L => L.type === type).reduce((a, L) => a + L.principal, 0); const cap = type === 'home' ? HOMES[f.home].price * 0.6 : type === 'car' ? CARS[f.car].price * 0.5 : 30000 + w.eye * 1500 + Math.max(0, w.fame) * 2000; return Math.max(0, Math.round(cap - used)); }
function borrow(w, type, amt) { amt = Math.round(amt); if (amt <= 0 || amt > loanRoom(w, type)) return { ok: false, msg: '借不了这么多。' }; w.fam.loans.push({ type, principal: amt, rate: LOANS[type].rate, day: w.day }); w.cash += amt; w.log.push({ day: w.day, t: `${LOANS[type].name}借入`, amt }); return { ok: true, msg: `借到 ${fmt(amt)}，每天利息 ${fmt(amt * LOANS[type].rate)}。` }; }
function repay(w, i) { const L = w.fam.loans[i]; if (!L) return { ok: false, msg: '' }; if (w.cash < L.principal) return { ok: false, msg: '现金不够还这一笔。' }; w.cash -= L.principal; w.log.push({ day: w.day, t: `还清${LOANS[L.type].name}`, amt: -L.principal }); w.fam.loans.splice(i, 1); return { ok: true, msg: '还清了。' }; }
function buyAsset(w, kind, lv) { const f = w.fam, T = kind === 'home' ? HOMES : CARS, cur = f[kind]; if (lv === cur) return { ok: false, msg: '' };
  const sell = T[cur].price * 0.8, debt = f.loans.filter(L => L.type === kind).reduce((a, L) => a + L.principal, 0), need = T[lv].price - sell + debt;
  if (need > w.cash) return { ok: false, msg: `还差 ${fmt(need - w.cash)}。${debt ? '（要先还清这项抵押）' : ''}` };
  w.cash -= need; f.loans = f.loans.filter(L => L.type !== kind); f[kind] = lv; w.log.push({ day: w.day, t: `${lv > cur ? '换成' : '卖掉，换成'}${T[lv].name}`, amt: -need });
  if (kind === 'home' && lv >= 2) achieve(w, 'house', '有了自己的房子'); return { ok: true, msg: lv > cur ? `${kind === 'home' ? '搬进了' : '换成了'}${T[lv].name}。` : `卖掉换成${T[lv].name}，回笼 ${fmt(-need)}。` }; }
function setSchool(w, i, id) { const k = w.fam.kids[i]; if (schoolsFor(k).indexOf(id) < 0) return { ok: false, msg: '这个年纪或成绩上不了。' }; k.school = id; k.away = !!SCHOOLS[id].away; if (k.away) k.job = 'none'; return { ok: true, msg: `${k.name}：${SCHOOLS[id].name}。` }; }
function setJob(w, i, job) { const k = w.fam.kids[i]; if (k.months < 144 || k.away) return { ok: false, msg: '还太小，或者人不在家。' }; k.job = job; return { ok: true, msg: '' }; }
function restDay(w) { w.fam.rested = w.day; w.fam.har = clamp(w.fam.har + 7, 0, 100); w.fam.hp = clamp(w.fam.hp + 5, 0, 100); }
// 花钱培养：每个孩子每天一次。天分对路的长得快；练得太密孩子会累，效果减半还伤家和
function trainKid(w, i, id) { const k = w.fam.kids[i], T = TRAIN[id]; if (!k || !T) return { ok: false, msg: '' }; if (k.away || k.withMom) return { ok: false, msg: '人不在身边。' }; if (k.months < 60) return { ok: false, msg: '还太小，五岁以后再说。' }; if (k.trained === w.day) return { ok: false, msg: `${k.name}今天已经练过了。` }; if (w.cash < T.cost) return { ok: false, msg: '现金不够。' };
  w.cash -= T.cost; w.log.push({ day: w.day, t: `培养${k.name}：${T.name}`, amt: -T.cost }); k.trained = w.day; k.tired = (k.tired || 0) + (id === 'sport' ? -1 : 1.5); const tired = k.tired > 4, r = new Rng(seedOf(w.seed, 'train', k.name, w.day));
  const g = T.gain * r.range(0.6, 1.4) * (T.trait === k.gift ? 1.8 : T.trait === k.weak ? 0.5 : 1) * (tired ? 0.5 : 1); k.t[T.trait] = clamp(k.t[T.trait] + g, 0, 100); if (id === 'sport') { k.tired = Math.max(0, k.tired); w.fam.har = clamp(w.fam.har + 1, 0, 100); } if (tired) { w.fam.har = clamp(w.fam.har - 2, 0, 100); k.t.moral = clamp(k.t.moral - 1.5, 0, 100); }
  return { ok: true, msg: tired ? `${k.name}练得太密，累了，没学进去多少，回家闷着不说话。` : g > T.gain * 1.5 ? `${k.name}学得很快，像是有这方面的天分。` : g < T.gain * 0.6 ? `${k.name}学得吃力，这方面好像不太开窍。` : `${k.name}有点长进。` }; }
// 再要一个孩子：和妻子生，或者和外面的人生（后者要付抚养费，被发现的风险也更高）。游戏一天是一个月，所以不设怀孕等待
function haveBaby(w, withLover) { const f = w.fam; if (withLover ? !f.lover : !f.wife) return { ok: false, msg: withLover ? '' : '现在是单身。' }; if (f.kids.length >= FAMC.maxKids) return { ok: false, msg: '家里实在住不下了。' }; if (f.babyDay === w.day) return { ok: false, msg: '今天已经添过一口人了。' }; if (w.cash < FAMC.baby) return { ok: false, msg: `产检、生产、月子要 ${fmt(FAMC.baby)}，现金不够。` };
  w.cash -= FAMC.baby; w.log.push({ day: w.day, t: '添了个孩子', amt: -FAMC.baby }); f.babyDay = w.day; const name = BABY_NAMES.find(n => !f.kids.some(k => k.name === n)) || '小' + (f.kids.length + 1), k = newKid(seedOf(w.seed, 'baby', w.day), name, 0, 'home'); if (withLover) { k.out = true; k.withMom = true; k.away = true; f.lover.heat = (f.lover.heat || 0) + 0.04; } else { f.har = clamp(f.har + 6, 0, 100); f.hp = clamp(f.hp - 3, 0, 100); } f.kids.push(k);
  return { ok: true, msg: withLover ? `${f.lover.name}生了个孩子，取名${name}。孩子跟她，你每天付抚养费。` : `${f.wife}生了，取名${name}。家里又多一张嘴。` }; }
// 离婚：现金分一半，手续费另算。孩子跟你（没人带小的就得请保姆）或跟她（付抚养费到 18 岁，帮不上家里的忙）
function divorce(w, keepKids) { const f = w.fam; if (!f.wife) return { ok: false, msg: '现在是单身。' }; const half = Math.max(0, Math.round(w.cash / 2)); w.cash -= half + FAMC.divorce; w.log.push({ day: w.day, t: `离婚（分给${f.wife}一半现金、手续）`, amt: -(half + FAMC.divorce) });
  for (const k of f.kids) { if (k.out) continue; k.t.moral = clamp(k.t.moral - 8, 0, 100); if (!keepKids && k.months < 216 && !k.away) { k.withMom = true; k.away = true; k.job = 'none'; } }
  f.ex = f.wife; f.wife = null; f.har = 40; f.caught = false; w.fame -= 3; return { ok: true, msg: `和${f.ex}离了，分走 ${fmt(half)}。${keepKids ? '孩子跟你。' : '孩子跟她，你付抚养费。'}` }; }
function marry(w) { const f = w.fam; if (f.wife) return { ok: false, msg: '' }; const cost = f.lover ? Math.round(FAMC.wedding * 0.6) : FAMC.wedding; if (w.cash < cost) return { ok: false, msg: `彩礼、婚礼要 ${fmt(cost)}，现金不够。` }; w.cash -= cost; w.log.push({ day: w.day, t: '结婚', amt: -cost });
  if (f.lover) { f.wife = f.lover.name; f.lover = null; for (const k of f.kids) if (k.out) { k.out = false; k.withMom = false; k.away = false; } } else f.wife = WIFE_NAMES.find(n => n !== f.ex) || '玉兰';
  for (const k of f.kids) if (!k.withMom && k.months > 36) k.t.moral = clamp(k.t.moral - 4, 0, 100); f.har = 68; return { ok: true, msg: `和${f.wife}结婚了。孩子们要花些时间适应。` }; }
// 婚外情：每天花钱、掉家和，每天都有被发现的可能，名气越大越容易被人认出来
function startAffair(w) { const f = w.fam; if (f.lover) return { ok: false, msg: '' }; f.lover = { name: LOVER_NAMES[(w.seed + w.day) % LOVER_NAMES.length], day: w.day, heat: 0 }; return { ok: true, msg: `你和${f.lover.name}走到了一起。每天多一笔开销，纸包不住火。` }; }
function endAffair(w) { const f = w.fam; if (!f.lover) return { ok: false, msg: '' }; if (w.cash < FAMC.breakup) return { ok: false, msg: `分手要给 ${fmt(FAMC.breakup)}，现金不够。` }; w.cash -= FAMC.breakup; w.log.push({ day: w.day, t: '分手费', amt: -FAMC.breakup }); const n = f.lover.name; f.lover = null; f.caught = false; return { ok: true, msg: `和${n}断了。` }; }
// 家里的事：每天小概率来一件，要么花钱，要么花感情
function lifeEvent(w) {
  const f = w.fam, r = new Rng(seedOf(w.seed, 'life', w.day));
  if (f.caught && f.wife && f.lover) return { text: `${f.wife}翻到了你的手机，知道了${f.lover.name}的事。她把手机摔在桌上，孩子在里屋哭。`, opts: [{ label: `认错，和${f.lover.name}断干净（分手费 ${fmt(FAMC.breakup)}，再赔礼 20000）`, cost: FAMC.breakup + 20000, har: -25, act: 'endaffair' }, { label: '离婚，孩子跟我（分一半现金）', act: 'divorce1' }, { label: '离婚，孩子跟她（分一半现金，付抚养费）', act: 'divorce0' }] };
  if (!r.chance(0.16)) return null;
  const k = r.pick(f.kids.filter(x => !x.away)) || f.kids[0], ki = f.kids.indexOf(k), sc = k.school, age = kidAge(k);
  const E = [];
  E.push({ text: `${k.name}半夜发烧，烧到三十九度。`, opts: [{ label: '去大医院（1500）', cost: 1500, har: 2 }, { label: '小诊所打一针（300）', cost: 300, hp: -2, risk: 0.3, riskNote: '没好利索，又折腾了几天，多花了 2000。', riskCost: 2000 }] });
  if (f.wife) E.push({ text: `${f.wife}说很久没回娘家了，想带孩子回去住几天。`, opts: [{ label: '一起回，买点东西（2500）', cost: 2500, har: 8 }, { label: '让她自己回，给点路费（600）', cost: 600, har: 1 }, { label: '最近太忙，过阵子再说', har: -7 }] });
  E.push({ text: '老家亲戚打电话，说家里盖房差一万，想跟你借。', opts: [{ label: '借（10000）', cost: 10000, har: 3, risk: 0.45, back: 10000 }, { label: '借一半（5000）', cost: 5000, har: 1, risk: 0.45, back: 5000 }, { label: '说自己也紧，不借', har: -3 }] });
  if (age >= 3 && age < 15) E.push({ text: `${k.name}的学校开家长会，正好撞上进货的日子。`, opts: [{ label: '去开会，今天少看两块料', har: 4, kid: { moral: 3 }, ki, watch: -2 }, { label: f.wife ? `让${f.wife}去` : '托邻居去听一下', har: -1 }, { label: '都不去', har: -4, kid: { moral: -3 }, ki }] });
  if (age >= 5 && age < 16) E.push({ text: `${k.name}想报个兴趣班。`, opts: [{ label: '学画画（3000）：手上有准头', cost: 3000, kid: { craft: 5 }, ki, har: 2 }, { label: '学主持演讲（3000）：敢说话', cost: 3000, kid: { talk: 6 }, ki, har: 2 }, { label: '不报，在家写作业', kid: { book: 1 }, ki, har: -1 }] });
  if (age >= 6 && age < 14) E.push({ text: `${k.name}放学蹲在你摊子边上，拿着手电照石头，问这块里面有没有绿。`, opts: [{ label: '停下来教半天', kid: { eye: 4 }, ki, har: 3, watch: -1 }, { label: '“别捣乱，写作业去”', kid: { eye: -1, moral: -1 }, ki }] });
  if (sc === 'pri_priv' || sc === 'kg_priv') E.push({ text: `${k.name}同学的爸爸是开珠宝店的，家长群里问你有没有好货。`, opts: [{ label: '请他来铺子看看', fame: 4, har: 1 }, { label: '不想沾家长圈的生意', har: 0 }] }, { text: `${k.name}说班上同学都穿名牌鞋，他也想要。`, opts: [{ label: '买（1800）', cost: 1800, kid: { moral: -2 }, ki, har: 1 }, { label: '不买，讲讲道理', kid: { moral: 2 }, ki, har: -1 }] });
  if (sc === 'pri_vil') E.push({ text: `${k.name}放了学总往村口玉雕师傅的棚子里钻，回来一手石粉。`, opts: [{ label: '由他去', kid: { craft: 5, book: -1 }, ki }, { label: '不许去，先把书读好', kid: { book: 2, moral: -1 }, ki }] });
  if (sc === 'mid_key' || sc === 'high') E.push({ text: `${k.name}压力大，连着几晚睡不着，老师建议休息一阵。`, opts: [{ label: '请假带出去散心（2000）', cost: 2000, har: 4, kid: { book: -2, moral: 3 }, ki }, { label: '咬牙挺过去', kid: { book: 3, moral: -4 }, ki, har: -3 }] });
  if (f.hp < 35) E.push({ text: '你这阵子吃不好睡不好，蹲着看石头一站起来眼前发黑。', opts: [{ label: '去医院查一查（1200），歇一天', cost: 1200, hp: 18, rest: true }, { label: '扛着', hp: -6 }] });
  if (f.lover) E.push({ text: `${f.lover.name}说看中了一个包，又说总这样偷偷摸摸不是办法。`, opts: [{ label: '买（8000）', cost: 8000 }, { label: '不买，哄两句', heat: 0.05 }] });
  if (f.har < 30 && f.wife) E.push({ text: `${f.wife}红着眼睛说：“这个家你还管不管？”`, opts: [{ label: '放下石头，陪家里一天', har: 15, rest: true }, { label: '“我这不是在挣钱吗”', har: -10 }] });
  if (f.loans.some(L => L.type === 'shark' && w.day - L.day > 25)) E.push({ text: '放贷的人堵到了家门口。', opts: [{ label: '当场凑钱给一部分（5000）', cost: 5000, har: -4 }, { label: '好话说尽，求再宽限', har: -10, fame: -5 }] });
  return r.pick(E);
}
function applyEvent(w, ev, i) { const o = ev.opts[i], f = w.fam, r = new Rng(seedOf(w.seed, 'lifeopt', w.day, i)); let note = '';
  if (o.cost) { if (o.cost > w.cash) return { ok: false, msg: '现金不够。' }; w.cash -= o.cost; w.log.push({ day: w.day, t: '家里的事', amt: -o.cost }); }
  if (o.har) f.har = clamp(f.har + o.har, 0, 100); if (o.hp) f.hp = clamp(f.hp + o.hp, 0, 100); if (o.fame) w.fame += o.fame; if (o.watch) w.watchLeft = Math.max(0, w.watchLeft + o.watch); if (o.rest) restDay(w); if (o.heat && f.lover) f.lover.heat = (f.lover.heat || 0) + o.heat;
  if (o.act === 'endaffair') { f.lover = null; f.caught = false; note = '她没再说什么，可这个家回不到从前了。'; } if (o.act === 'divorce1' || o.act === 'divorce0') note = divorce(w, o.act === 'divorce1').msg;
  if (o.kid) { const k = f.kids[o.ki]; for (const t2 in o.kid) k.t[t2] = clamp(k.t[t2] + o.kid[t2], 0, 100); }
  if (o.riskCost && r.chance(o.risk)) { w.cash -= o.riskCost; note = o.riskNote; w.log.push({ day: w.day, t: '家里的事（后续）', amt: -o.riskCost }); }
  if (o.back) { if (r.chance(o.risk)) note = '后来这笔钱一直没还，也不好意思再提。'; else { w.recv.push({ day: w.day + r.int(8, 20), amt: o.back, from: '亲戚还钱' }); note = '亲戚说过阵子就还。'; } }
  return { ok: true, note }; }
// 每天结算家里：扣开销、身体和家和的涨落、孩子长大和成长、到年龄自动升学
function lifeTick(w, notes) {
  const f = w.fam, lc = lifeCost(w); w.cash -= lc.total; w.log.push({ day: w.day, t: `家用（${lc.items.map(x => x[0]).join('、')}）`, amt: -lc.total });
  const busy = w.stones.filter(s => !s.closed).length > 3 ? 0.3 : 0;
  f.hp = clamp(f.hp + FOODS[f.food].hp + HOMES[f.home].hp + (f.car >= 1 ? 0.1 : -0.1) - 0.15 - busy, 0, 100);
  f.har = clamp(f.har + FOODS[f.food].har + HOMES[f.home].har - 0.2 - busy, 0, 100);
  if (!f.wife) f.har = clamp(f.har - 0.2, 0, 100);
  if (f.lover) { f.har = clamp(f.har - 0.5, 0, 100); const pr = 0.035 + (f.lover.heat || 0) + Math.max(0, w.fame) / 1500 + (w.fans || 0) / 400000; if (f.wife && !f.caught && new Rng(seedOf(w.seed, 'caught', w.day)).chance(pr)) { f.caught = true; if (w.fans > 2000) { w.fame -= 6; notes.push('你的事被人拍到发上了网，直播间里都在问'); } } }
  for (const k of f.kids) { k.months++; if (k.tired) k.tired = Math.max(0, k.tired - 0.5); const S = SCHOOLS[k.school], r = new Rng(seedOf(w.seed, 'grow', k.name, w.day));
    for (const t2 in S.g) k.t[t2] = clamp(k.t[t2] + S.g[t2] * r.range(0.5, 1.5) * (t2 === k.gift ? 1.8 : t2 === k.weak ? 0.5 : 1) * (f.har > 40 ? 1 : 0.6), 0, 100);
    if (k.job !== 'none' && k.months >= 144 && !k.away) { const tr = JOBS[k.job].trait; k.t[tr] = clamp(k.t[tr] + (k.school === 'work' ? 0.9 : 0.45) * (tr === k.gift ? 1.8 : tr === k.weak ? 0.5 : 1), 0, 100); if (k.school === 'work' && k.months < 192) { k.t.book = Math.max(0, k.t.book - 0.1); f.har = clamp(f.har - 0.15, 0, 100); } }
    k.t.moral = clamp(k.t.moral + (f.har > 60 ? 0.2 : f.har < 35 ? -0.5 : 0), 0, 100);
    if (k.months >= S.max && k.school !== 'work') {
      if (k.school === 'college') { k.away = false; const stay = new Rng(seedOf(w.seed, 'grad', k.name)).chance(0.35 + k.t.moral / 250 + f.har / 400); if (stay) { k.school = 'work'; notes.push(`${k.name}大学毕业回来了，说想把家里的生意做成品牌`); k.t.manage = clamp(k.t.manage + 15, 0, 100); k.t.talk = clamp(k.t.talk + 10, 0, 100); } else { k.school = 'work'; k.away = true; k.job = 'none'; notes.push(`${k.name}大学毕业留在了外地，过年才回来，每月往家里寄钱`); k.remit = 150; } }
      else { const opts = schoolsFor(k).filter(id => id !== 'work').sort((a, b) => SCHOOLS[a].cost - SCHOOLS[b].cost); k.school = opts[0] || 'work'; notes.push(`${k.name} ${kidAge(k)} 岁了，${k.school === 'work' ? '不再上学' : '升入' + SCHOOLS[k.school].name}。想换学校到「家」里选`); } }
    if (k.remit) w.cash += k.remit;
    if (k.months === 144) notes.push(`${k.name}满 12 岁了，可以在「家」里安排课余帮忙`);
  }
  for (const L of f.loans) if (L.type === 'shark' && w.day - L.day === 26) notes.push('民间借贷拖了快一个月，放贷的人开始上门了');
  if (f.hp < 25) notes.push('身体快撑不住了，该歇一天、吃好一点'); if (f.har < 25) notes.push('家里气氛很僵');
  return lc.total;
}
function payDebt(w) { if (w.flags.debt) return { ok: false, msg: '已经还清了。' }; if (w.cash < DEBT + 2000) return { ok: false, msg: '现金不够，还得留点周转。' }; w.cash -= DEBT; w.flags.debt = true; w.log.push({ day: w.day, t: '还清父亲的欠债', amt: -DEBT }); achieve(w, 'debt', '父债子还'); return { ok: true, msg: '欠条撕了。' }; }
const ACH_ALL = [['win', '第一块赚钱的石头'], ['cutup', '第一刀切涨'], ['steal', '捡漏：净赚超过买价两倍'], ['bust', '交学费：一块亏掉六成以上'], ['sharp', '火眼金睛：种、色、裂全部判断对'], ['fake', '识破一块假货'], ['bid', '公盘中标'], ['bangle', '第一只手镯'], ['ice', '做出冰种以上的成品'], ['cab', '一粒满色蛋面'], ['big', '单件成品过十万'], ['order', '第一张客户订单'], ['keep', '第一件藏品'], ['shop', '有了自己的铺面'], ['tool', '第一件好工具'], ['live', '第一场直播'], ['fans1', '万粉博主'], ['fans10', '十万粉博主'], ['branch', '第一家分店'], ['hire', '第一名员工'], ['house', '有了自己的房子'], ['m1', '身家过百万'], ['m10', '身家过千万'], ['eye100', '眼力过百'], ['sold20', '卖出二十件货'], ['ten', '经手十块石头'], ['d30', '撑过第一个月']];
const RANKS = [[0, '学徒'], [15, '跑摊的'], [40, '看货人'], [80, '行家'], [150, '掌眼师傅'], [260, '一代货主']];
function rankOf(w) { let n = RANKS[0][1]; for (const r of RANKS) if (w.eye >= r[0]) n = r[1]; return n; }
const SCENE_CH = { '夜市地摊': 0, '玉石集散地': 2, '翡翠公盘': 3, '场口直采': 4 };
function sceneOpen(w, name) { return w.chapter >= SCENE_CH[name]; }
function enterScene(w, name) {
  w.scene = name; if (!w.markets[name]) { w.markets[name] = []; for (let i = 0; i < SCENES[name].n + (w.fam.car >= 4 ? 2 : w.fam.car >= 2 ? 1 : 0); i++) w.markets[name].push(makeListing(w.seed, w.day, i, name)); }
  w.market = w.markets[name];
}
function achieve(w, key, name) { if (!w.ach[key]) { w.ach[key] = { day: w.day, name }; w.news.push('成就：' + name); } }
const GRADES = [0.10, 0.25, 0.45, 0.65, 0.82, 0.95];
function gradeIdx(w0) { w0 *= 100; return w0 < 18 ? 0 : w0 < 35 ? 1 : w0 < 55 ? 2 : w0 < 74 ? 3 : w0 < 89 ? 4 : 5; }
function colorClass(st) { if (!st.feats.length || st.feats.every(f => f.strength < 0.22)) return 'none'; if (st.feats.some(f => f.type === 'full')) return 'full'; if (st.feats.every(f => f.type === 'skin')) return 'skin'; return 'deep'; }
const ORDER_WHO = ['陈太太', '直播间老板', '广州客', '台湾藏家', '珠宝店王姐', '香港行家'];
function fillOrders(w) {
  w.orders = w.orders.filter(o => o.due >= w.day);
  for (let k = 0; w.orders.length < 3 && k < 6; k++) {
    const r = new Rng(seedOf(w.seed, 'order', w.day, k, w.nextId));
    w.orders.push({ id: w.nextId++, type: r.pick(['bracelet', 'bracelet', 'pendant', 'pendant', 'cab', 'bead', 'carve']), minW: r.pick([0.25, 0.25, 0.45, 0.45, 0.65]), color: r.chance(0.4), bonus: Math.round(r.range(1.25, 1.7) * 100) / 100, due: w.day + r.int(5, 10), who: r.pick(ORDER_WHO) });
  }
}
function orderMatch(o, it) { return it.type === o.type && it.w >= o.minW - 0.03 && (!o.color || it.lv > 0.25); }
function orderText(o) { return `${o.who}要一${ROUTES[o.type].unit}${waterName(o.minW)}以上${o.color ? '带色' : ''}的${ROUTES[o.type].name}`; }
function sellToOrder(w, it, o) {
  const price = Math.round(it.value * (o.bonus + (w.fam.car >= 3 ? 0.05 : 0)) / 10) * 10; it.state = 'sold'; it.price = price; w.cash += price; w.orders = w.orders.filter(x => x !== o); w.eye += 3;
  w.log.push({ day: w.day, t: `${it.name} 交给${o.who}的订单`, amt: price }); achieve(w, 'order', '第一张客户订单');
  const s = w.stones.find(x => x.id === it.stone); if (s) { s.proceeds += price; if (!s.closed && stoneDone(w, s)) closeStone(w, s); }
  return price;
}
function keepItem(w, it) { it.state = 'kept'; achieve(w, 'keep', '第一件藏品'); const s = w.stones.find(x => x.id === it.stone); if (s && !s.closed && stoneDone(w, s)) closeStone(w, s); }
function placeBid(w, L, amount) {
  amount = Math.round(amount); const old = L.bid || 0;
  if (amount < L.floor) return { ok: false, msg: `低于底价 ${fmt(L.floor)}，标书无效。` };
  if (amount - old > w.cash) return { ok: false, msg: '现金不够押这个标。' };
  w.cash += old - amount; L.bid = amount; return { ok: true, msg: `已投标 ${fmt(amount)}，标款先押着，收工后开标。` };
}
function newWorld(seed) { const w = { v: 11, seed, day: 1, cash: ECON.startCash, recv: [], stones: [], works: [], items: [], market: [], markets: {}, scene: '夜市地摊', eye: 0, orders: [], ach: {}, news: [], log: [], nextId: 1, over: false, tools: { torch: 1, loupe: 1, saw: 1 }, event: null, rel: {}, fame: 0, after: [], shop: 0, fam: newFamily(seed), chapter: 0, flags: {}, stat: { sold: 0, watch: 0, tips: 0, wins: 0, cuts: 0, shelfSold: 0, live: 0, liveIncome: 0 }, watchLeft: 3, fans: 0, liveDay: 0, cutDay: 0, branches: 0, staff: { clerk: 0, master: 0, host: 0 } }; applyTools(w); genMarket(w); fillOrders(w); rollEvent(w); return w; }
function sellerWindow(st, vol, r) {
  let best = null; const o = [0, 0, 0, 0], grade = HUES[st.hue].grade;
  for (let i = 0; i < 60; i++) {
    const d = r.dir(), ro = [d[0] * 400, d[1] * 400, d[2] * 400], h = pick(vol, WHOLE, ro, [-d[0], -d[1], -d[2]]);
    if (!h) continue;
    const sk = sampleG(vol, 2, h.p[0], h.p[1], h.p[2]), q = [h.p[0] - h.n[0] * (sk + 2.5), h.p[1] - h.n[1] * (sk + 2.5), h.p[2] - h.n[2] * (sk + 2.5)];
    truthAt(st, q[0], q[1], q[2], sk + 2.5, o);
    const score = vd(o[1], o[0], o[2], o[3], grade) * (0.7 + 0.6 * r.u());
    if (!best || score > best.score) best = { score, h, sk };
  }
  const s = []; if (!best) return s;
  const R = r.range(7, 11), h = best.h, dep = best.sk + 1.6, rd = v => Math.round(v * 10) / 10;
  const t1 = norm3(cross(h.n, [0.3, 0.8, 0.5])), t2 = cross(h.n, t1), k = r.int(1, 4);
  for (let i = 0; i < k; i++) { const a = i ? r.range(0, TAU) : 0, rr = i ? R * 0.7 : 0, ca = Math.cos(a) * rr, sa = Math.sin(a) * rr; s.push(rd(h.p[0] + t1[0] * ca + t2[0] * sa + h.n[0] * (R - dep)), rd(h.p[1] + t1[1] * ca + t2[1] * sa + h.n[1] * (R - dep)), rd(h.p[2] + t1[2] * ca + t2[2] * sa + h.n[2] * (R - dep)), rd(R), 0); }
  return s;
}
function makeListing(wseed, day, i, scene) {
  scene = scene || '夜市地摊';
  const r = new Rng(seedOf(wseed, 'mkt', day, i, scene));
  const origin = r.pick(Object.keys(ORIGINS)), channel = r.pick(SCENES[scene].channels), C = CHANNELS[channel];
  const L = { scene, seed: seedOf(wseed, 'stone', day, i, scene), origin, channel, strokes: [], clips: [[]], patience: 3, sold: false };
  let e = getVol(L);
  const fk = r.chance(FAKE_RATE[scene] || 0) ? (r.chance(0.5) ? 'paint' : 'veneer') : null;
  if ((r.chance(C.window) || fk === 'veneer') && scene !== '场口直采') { L.strokes = sellerWindow(e.st, e.vol, r); e = getVol(L); }
  if (fk === 'veneer' && L.strokes.length) { const sp = []; for (let q = 0; q < L.strokes.length && q < 20; q += 5) sp.push(L.strokes[q], L.strokes[q + 1], L.strokes[q + 2], L.strokes[q + 3]); L.fake = { type: 'veneer', spheres: sp }; e = getVol(L); }
  else if (fk === 'paint') { L.fake = { type: 'paint' }; e = getVol(L); }
  const ev = evalPiece(e.st, e.vol, WHOLE);
  const est = estimate(e.st, e.vol, ev, 'seller', { skill: C.skill, risk: 0.3, opt: 1.0 });
  L.reserve = Math.max(300, Math.round(est * (0.95 + C.margin) * Math.exp(r.norm() * 0.15) / 10) * 10);
  L.ask = Math.max(Math.round(L.reserve * 1.12 / 10) * 10, Math.round(est * (1.35 + C.margin * 2) * Math.exp(r.norm() * 0.2) / 10) * 10);
  if (SCENES[scene].auction) { L.auction = true; L.floor = Math.max(200, Math.round(L.reserve * 0.55 / 10) * 10); let top = 0; for (let k = 0; k < 4; k++) top = Math.max(top, L.reserve * r.range(0.62, 1.22)); L.top = Math.round(top / 10) * 10; }
  if (L.fake) { const k = L.fake.type === 'paint' ? r.range(1.8, 2.6) : r.range(1.1, 1.3); L.reserve = Math.round(L.reserve * k / 10) * 10; L.ask = Math.round(L.ask * k / 10) * 10; if (L.top) L.top = Math.round(L.top * k / 10) * 10; }
  L.patter = patter(e.st, e.vol, L); if (L.fake) L.patter[1] = L.fake.type === 'paint' ? '老板：你看这一身松花，满色料的相，过了这村没这店。' : '老板：窗都给你开好了，种色摆在这，闭着眼睛买。';
  L.info = { skin: e.st.skin.name, weight: ev.stats.weight, dims: e.st.rad.map(v => Math.round(v * 2)), window: L.strokes.length > 0, bet: betOf(e.st, e.vol, ev.stats.hasWindow && ev.stats.expColor > 0.15) };
  if (L.fake && L.fake.type === 'paint') { L.info.bet.main = '赌色'; L.info.bet.why = '皮上松花很多。色是真是假、进得深不深，要压灯和上放大镜比对。'; }
  return L;
}
function genMarket(w) {
  for (const k in w.markets) for (const L of w.markets[k]) if (!L.sold) volCache.delete(L.seed);
  w.markets = {}; enterScene(w, sceneOpen(w, w.scene) ? w.scene : '夜市地摊');
}
function negotiate(w, L, offer, share) {
  offer = Math.round(offer); share = share || 1;
  if (L.sold || L.patience <= 0) return { res: 'gone', msg: '老板摆摆手：这块不谈了。' };
  if (offer * share > w.cash) return { res: 'poor', msg: '现金不够。' };
  if (offer >= L.reserve) return { res: 'deal', price: Math.min(offer, L.ask), msg: '老板：行，拿走。' };
  L.patience--;
  if (offer >= L.reserve * 0.8) { L.ask = Math.max(Math.round(L.reserve * 1.03 / 10) * 10, Math.round((L.ask + offer) / 20) * 10); return { res: 'counter', msg: L.patience > 0 ? `老板：最低 ${fmt(L.ask)}，再少不卖。` : `老板：${fmt(L.ask)}，最后一口价。` }; }
  return { res: 'low', msg: L.patience > 0 ? '老板皱眉：这价连本都不够，诚心要就再加点。' : '老板把石头收了回去。' };
}
function buy(w, L, price, share) {
  share = share || 1; w.cash -= Math.round(price * share); L.sold = true;
  const s = { id: w.nextId++, seed: L.seed, origin: L.origin, channel: L.channel, strokes: L.strokes.slice(), clips: [[]], buyDay: w.day, buyPrice: price, costs: 0, proceeds: 0, pieces: [{ id: 0, name: '原石', planes: [], sold: false }], nextPiece: 1, best: 0, flip: 0, closed: false, info: L.info, last: {}, scene: L.scene, guess: null, fake: L.fake || null, exposed: !!L.exposed, share };
  w.stones.push(s);
  const q = quotes(w, s, s.pieces[0]); s.flip = q.best; s.best = q.best;
  w.log.push({ day: w.day, t: `买入 ${s.origin}·${s.info.skin} ${fmt(price)}${share < 1 ? '（合伙，你出一半）' : ''}`, amt: -Math.round(price * share) });
  return s;
}
function quotes(w, s, piece) {
  const e = getVol(s), ev = evalPiece(e.st, e.vol, piece), st = ev.stats, list = [];
  for (const name in BUYERS) {
    const B = BUYERS[name], r = new Rng(seedOf(w.seed, 'q', name, w.day, s.seed, piece.id));
    let v = estimate(e.st, e.vol, ev, name, B), note = '';
    if (s.fake && piece.id === 0 && !piece.planes.length && st.kAvg < 0.45 && new Rng(seedOf(s.seed, 'spot', name)).u() < B.skill + 0.1) { list.push({ buyer: name, price: 0, note: '看出是做过手脚的料' }); continue; }
    v *= 1 + clamp(relOf(w, name), -60, 60) * 0.0025;
    if (B.pref === '净度') v *= 1 - 0.06 * Math.min(st.knownCracks, 3);
    if (B.pref === '表现' && st.kAvg < 0.5 && st.hasWindow) v *= 1 + 0.25 * st.expColor;
    if (B.pref === '色') { if (st.kAvg < 0.5) { list.push({ buyer: name, price: 0, note: '只收看得明白的明料' }); continue; } v *= 0.8 + 0.6 * Math.min(1, st.expColor * 1.5); }
    v *= (1 - B.margin) * (0.93 + 0.14 * r.u());
    if (v > B.cash) { v = B.cash; note = '资金上限'; }
    if (v < 100) { list.push({ buyer: name, price: 0, note: '看不上' }); continue; }
    list.push({ buyer: name, price: Math.round(v / 10) * 10, days: B.days, rel: relWord(relOf(w, name)), note: note || (B.days ? `${B.days} 天后到账` : '现结') });
  }
  list.sort((a, b) => b.price - a.price);
  return { list, best: list[0].price, stats: st, truth: ev.truth, ev };
}
// 把两次公开证据的差异翻译成玩家能理解的理由
function explain(a, b) {
  const out = [];
  if (!a) return out;
  if (b.weight < a.weight - 3) out.push(`重量少了 ${Math.round(a.weight - b.weight)} 克`);
  if (b.expArea > a.expArea + 0.3) out.push(`露肉面积 ${a.expArea.toFixed(1)}→${b.expArea.toFixed(1)} cm²，未知部分变少`);
  if (Math.abs(b.expColor - a.expColor) > 0.04 && b.hasWindow && a.hasWindow) out.push(`露面带色比例 ${Math.round(a.expColor * 100)}%→${Math.round(b.expColor * 100)}%，买家${b.expColor > a.expColor ? '上调' : '下调'}色的延伸预期`);
  if (a.hasWindow && waterName(a.expWater) !== waterName(b.expWater)) out.push(`露面种水由 ${waterName(a.expWater)} 变为 ${waterName(b.expWater)}`);
  if (!a.hasWindow && b.hasWindow) out.push(`首次露肉：${waterName(b.expWater)}，带色 ${Math.round(b.expColor * 100)}%`);
  if (b.knownCracks > a.knownCracks) out.push(`新见 ${b.knownCracks - a.knownCracks} 条裂`);
  if (b.bracelets !== a.bracelets) out.push(`可见手镯位 ${a.bracelets}→${b.bracelets}`);
  return out;
}
function clipPiece(c) { return !c ? { planes: [] } : Array.isArray(c) ? { planes: c } : { planes: c.planes, holes: c.holes }; }
function clipIndex(s, piece) { const key = JSON.stringify({ planes: piece.planes, holes: piece.holes || [] }); for (let i = 0; i < s.clips.length; i++) if (JSON.stringify(Array.isArray(s.clips[i]) ? { planes: s.clips[i], holes: [] } : s.clips[i]) === key) return i; s.clips.push(JSON.parse(key)); return s.clips.length - 1; }
function grind(w, s, piece, p, n, toolName) {
  const T = TOOLS[toolName], e = getVol(s);
  const c = [p[0] + n[0] * (T.r - T.bite), p[1] + n[1] * (T.r - T.bite), p[2] + n[2] * (T.r - T.bite)].map(v => Math.round(v * 10) / 10);
  s.strokes.push(c[0], c[1], c[2], T.r, clipIndex(s, piece));
  const res = carve(e.vol, piece, c[0], c[1], c[2], T.r); e.applied = s.strokes.length;
  const cost = res.removed * ECON.grind; s.costs += cost; w.cash -= cost;
  return res;
}
// 切皮：只剥到刚露肉的深度（皮厚 + 0.45 毫米），已经露肉的地方不动
function peelAt(w, s, piece, p, n) {
  const e = getVol(s), v = e.vol, sk = sampleG(v, 2, p[0], p[1], p[2]), d0 = -sampleG(v, 0, p[0], p[1], p[2]), left = sk - Math.max(0, d0);
  if (left <= 0.05) return null;
  const R = 6, bite = left + 0.45, c0 = [p[0] + n[0] * (R - bite), p[1] + n[1] * (R - bite), p[2] + n[2] * (R - bite)].map(x => Math.round(x * 10) / 10);
  s.strokes.push(c0[0], c0[1], c0[2], R, clipIndex(s, piece));
  const res = carve(v, piece, c0[0], c0[1], c0[2], R); e.applied = s.strokes.length;
  const cost = res.removed * ECON.grind * 1.5; s.costs += cost; w.cash -= cost; res.cost = cost;
  return res;
}
// 预估沿平面 n·p = d 下刀后两侧的重量和切面面积
function cutPreview(s, piece, n, d) {
  const e = getVol(s), vol = e.vol, { nx, ny, nz, vx, geom: g } = vol; let a = 0, b = 0, area = 0;
  for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    const g1 = g[(i + nx * (j + ny * k)) * 4 + 1]; if (g1 >= 0) continue;
    const x = (i + 0.5) * vx - vol.hx, y = (j + 0.5) * vx - vol.hy, z = (k + 0.5) * vx - vol.hz; if (clipped(piece) && planeD(piece, x, y, z) > 0) continue;
    const h = n[0] * x + n[1] * y + n[2] * z - d; if (h > 0) b++; else a++; if (Math.abs(h) < vx / 2) area += vx * vx;
  }
  const k = vx * vx * vx / 1000 * ECON.density;
  return { a: a * k, b: b * k, area, cost: Math.round(ECON.cutBase + area * ECON.cutArea) };
}
// 沿任意平面下刀：一块变两块，锯缝吃掉 kerf 毫米
function cut(w, s, piece, n, d) {
  n = norm3(n).map(v => Math.round(v * 1e4) / 1e4); d = Math.round(d * 100) / 100;
  if (piece.planes.length >= 16) return { ok: false, msg: '这块料已经切了 16 个面，再切就碎了。' };
  const pv = cutPreview(s, piece, n, d);
  if (pv.a < 8 || pv.b < 8) return { ok: false, msg: '这一刀有一侧几乎没有料，换个位置。' };
  if (pv.cost > w.cash) return { ok: false, msg: '现金不够付切工。' };
  pv.cost = Math.round(pv.cost * (1 - 0.4 * famEff(w, 'cutter'))); w.cash -= pv.cost; s.costs += pv.cost;
  const A = piece.planes.concat([[n[0], n[1], n[2], d - ECON.kerf / 2]]), B = piece.planes.concat([[-n[0], -n[1], -n[2], -d - ECON.kerf / 2]]);
  const np = { id: s.nextPiece++, sold: false, holes: (piece.holes || []).map(h => h.slice()) }; np.name = '料' + np.id;
  if (pv.a >= pv.b) { piece.planes = A; np.planes = B; } else { piece.planes = B; np.planes = A; }
  s.pieces.push(np); getVol(s).vol.ver++;
  w.stat.cuts++; w.cutDay = w.day;
  w.log.push({ day: w.day, t: `下刀（#${s.id}）分出 ${np.name}`, amt: -pv.cost });
  return { ok: true, piece: np, cost: pv.cost };
}
// 小锯取料：planes 围成一个凸柱（保留 n·p<=d 的一侧），把柱内的料单独锯下来，其余留在原料上
function sawPreview(s, piece, planes) {
  const e = getVol(s), vol = e.vol, { nx, ny, nz, vx, geom: g } = vol; let a = 0, b = 0, edge = 0;
  for (let k = 0; k < nz; k++) for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
    if (g[(i + nx * (j + ny * k)) * 4 + 1] >= 0) continue;
    const x = (i + 0.5) * vx - vol.hx, y = (j + 0.5) * vx - vol.hy, z = (k + 0.5) * vx - vol.hz; if (clipped(piece) && planeD(piece, x, y, z) > 0) continue;
    let m = -1e9; for (const P of planes) { const v = P[0] * x + P[1] * y + P[2] * z - P[3]; if (v > m) m = v; }
    if (m <= 0) a++; else b++; if (Math.abs(m) < vx / 2) edge += vx * vx;
  }
  const kq = vx * vx * vx / 1000 * ECON.density;
  return { a: a * kq, b: b * kq, cost: Math.round(40 + edge * ECON.cutArea * 1.6) };
}
function saw(w, s, piece, planes) {
  planes = planes.map(P => { const n = norm3(P); return [Math.round(n[0] * 1e4) / 1e4, Math.round(n[1] * 1e4) / 1e4, Math.round(n[2] * 1e4) / 1e4, Math.round(P[3] * 100) / 100]; });
  if (planes.length < 3 || planes.length > 8) return { ok: false, msg: '圈得不成形，重新圈一下。' };
  if ((piece.holes || []).length >= 4) return { ok: false, msg: '这块料已经挖过四处了，先用大锯分开再取。' };
  if (piece.planes.length + planes.length > 16) return { ok: false, msg: '这块料切面太多，取不下来了。' };
  const pv = sawPreview(s, piece, planes);
  if (pv.a < 3) return { ok: false, msg: '圈里几乎没有料。' }; if (pv.b < 3) return { ok: false, msg: '整块都圈进去了，不用锯。' };
  if (pv.cost > w.cash) return { ok: false, msg: '现金不够付锯工。' };
  w.cash -= pv.cost; s.costs += pv.cost; const kf = ECON.kerf / 2;
  const np = { id: s.nextPiece++, sold: false, holes: (piece.holes || []).map(h => h.slice()), planes: piece.planes.concat(planes.map(P => [P[0], P[1], P[2], P[3] - kf])) }; np.name = '料' + np.id;
  piece.holes = (piece.holes || []).concat([planes.map(P => [P[0], P[1], P[2], P[3] + kf])]);
  s.pieces.push(np); getVol(s).vol.ver++;
  w.log.push({ day: w.day, t: `小锯取料（#${s.id}）取出 ${np.name}`, amt: -pv.cost });
  return { ok: true, piece: np, cost: pv.cost };
}
function sell(w, s, piece, q) {
  { // 买家回去切了才知道你卖的料怎么样：过几天见分晓
    const qq = quotes(w, s, piece), fair = qq.truth * ECON.rough, r = new Rng(seedOf(w.seed, 'after', s.seed, piece.id)), ratio = q.price / Math.max(1, fair);
    const fakeSold = s.fake && piece.id === 0 && !piece.planes.length && qq.stats.kAvg < 0.45;
    w.after.push({ day: w.day + r.int(2, 4), buyer: q.buyer, kind: fakeSold ? 'fake' : ratio > 1.35 ? 'bust' : ratio < 0.8 ? 'boom' : 'ok', amt: q.price, stone: s.id });
  }
  w.stat.sold++;
  piece.sold = true; piece.soldPrice = q.price; piece.soldDay = w.day; piece.buyer = q.buyer;
  s.proceeds += q.price;
  if (q.days) w.recv.push({ day: w.day + q.days, amt: q.price, from: q.buyer }); else w.cash += q.price;
  w.log.push({ day: w.day, t: `卖出 #${s.id} ${piece.name} → ${q.buyer}${q.days ? `（${q.days} 天后到账）` : ''}`, amt: q.price });
  closeStone(w, s);
}
/* ---------- 做件：玩家决定做什么、找谁做、什么题材 ---------- */
const ROUTES = {
  bracelet: { name: '手镯', unit: '只', fee: 150, tip: '一只好镯子能扛起整块料。需要够大的无裂圈位，片厚至少 10 毫米。' },
  pendant: { name: '牌子挂件', unit: '件', fee: 220, tip: '出货稳，吃工艺和题材。干净的料做素面，有棉有裂靠雕工遮。' },
  cab: { name: '蛋面戒面', unit: '粒', fee: 70, tip: '只取色最浓的部分，其余算废料。色好的小料走这条路最值钱。' },
  bead: { name: '珠串', unit: '串', fee: 130, tip: '车珠子能避开裂，碎料、裂多的料靠它回血。' },
  carve: { name: '雕件摆件', unit: '件', fee: 900, tip: '整块随形雕，裂和脏可以藏进题材里。好师傅能把垮料做活。' },
};
// craft: 各路线的工艺系数；fee: 工费倍率；press: 压镯失败率；salv: 雕工把裂区变成可用料的能力
const MASTERS = {
  '机雕厂': { dodge: 0.1, color: 0.1, design: 0.1, craft: { bracelet: 0.97, pendant: 0.62, cab: 0.85, bead: 1.0, carve: 0.55 }, fee: 0.3, days: 1, press: 0.06, salv: 0, tip: '便宜、一天交货。图案是模板，牌子和雕件卖不上价，适合低档料走量。' },
  '街边师傅': { dodge: 0.35, color: 0.35, design: 0.3, craft: { bracelet: 0.92, pendant: 0.88, cab: 0.9, bead: 0.95, carve: 0.85 }, fee: 0.6, days: 2, press: 0.09, salv: 0.1, tip: '什么都接，手艺一般，压镯偶尔失手。' },
  '平洲镯师': { dodge: 0.7, color: 0.4, design: 0.3, craft: { bracelet: 1.08, pendant: 0.9, cab: 0.9, bead: 1.0, carve: 0.8 }, fee: 1, days: 2, press: 0.02, salv: 0, tip: '专做手镯，圈口正、几乎不失手。雕件不是他的强项。' },
  '揭阳高货师': { dodge: 0.5, color: 0.9, design: 0.6, craft: { bracelet: 1.05, pendant: 1.05, cab: 1.35, bead: 1.0, carve: 1.0 }, fee: 2.2, days: 4, press: 0.03, salv: 0.1, high: 1.12, tip: '专做高种高色，蛋面起光最好；冰种以上的料交给他有溢价。普通料不划算。' },
  '苏工玉雕师': { dodge: 0.85, color: 0.6, design: 0.95, craft: { bracelet: 0.95, pendant: 1.5, cab: 0.9, bead: 0.95, carve: 1.6 }, fee: 4.5, days: 6, press: 0.05, salv: 0.35, tip: '设计和雕工一流，擅长化瑕为瑜。工费贵、工期长，料太差撑不起工费。' },
};
MASTERS['自家师傅'] = { own: true, dodge: 0.4, color: 0.4, design: 0.4, craft: { bracelet: 0.95, pendant: 0.95, cab: 0.95, bead: 1.0, carve: 0.95 }, fee: 0.35, days: 1, press: 0.05, salv: 0.15, tip: '你雇的驻店师傅：只收料工，随叫随到。每个人擅长的不一样，活做得越多手越熟。' };
// 自己雇的师傅：雇来时属性随机，有一项是长处；每做一单涨一点
function ownMaster(w) { if (!w.own) { const r = new Rng(seedOf(w.seed, 'own', w.day)), A = ['dodge', 'color', 'design'], best = r.pick(A), o = { name: r.pick(['老周', '阿坤', '陈师傅', '小梁']), jobs: 0 }; for (const k of A) o[k] = k === best ? r.range(0.6, 0.8) : r.range(0.2, 0.5); w.own = o; } return w.own; }
function masterOf(w, name) { const M = MASTERS[name]; if (!M.own) return M; const o = ownMaster(w), g = Math.min(0.2, o.jobs * 0.006), c = {}; for (const k in M.craft) c[k] = M.craft[k] + g + 0.15 * o.design * (k === 'pendant' || k === 'carve' ? 1 : 0.3); return Object.assign({}, M, { dodge: Math.min(0.95, o.dodge + g), color: Math.min(0.95, o.color + g), design: Math.min(0.95, o.design + g), craft: c, salv: 0.1 + 0.3 * o.dodge }); }
function mastersFor(w) { return Object.keys(MASTERS).filter(k => !MASTERS[k].own || w.staff.master > 0); }
// 手艺：玩家自己学的本事
const SKILLS = { layout: { name: '排料设计', cost: [4000, 15000, 50000], tips: ['能看懂师傅提案值多少钱，能让师傅按看得见的料排一遍各种件', '排得紧，工费省一成', '废料更少，成品总值多 6%'] }, crack: { name: '识裂避裂', cost: [4000, 15000, 50000], tips: ['遇到裂要拿主意时，能看出每条路有几成把握', '避裂的把握 +7%', '避裂的把握再 +7%'] }, color: { name: '追色留色', cost: [4000, 15000, 50000], tips: ['遇到色要拿主意时，能看出有几成把握', '追色留色的把握 +7%', '把握再 +7%'] } };
function skillsOf(w) { return w.skills || (w.skills = { layout: 0, crack: 0, color: 0 }); }
function learnSkill(w, id) { const S = SKILLS[id], sk = skillsOf(w), lv = sk[id]; if (!can(w, 'work')) return { ok: false, msg: '第三章「自己做货」以后才学得上。' }; if (lv >= 3) return { ok: false, msg: '已经学到头了。' }; if (w.cash < S.cost[lv]) return { ok: false, msg: '学费不够。' }; w.cash -= S.cost[lv]; sk[id]++; w.log.push({ day: w.day, t: `学${S.name}（第 ${lv + 1} 层）`, amt: -S.cost[lv] }); return { ok: true, msg: `${S.name}到第 ${lv + 1} 层：${S.tips[lv]}。` }; }
const THEMES = {
  '师傅定': { tip: '让师傅看料下刀，中规中矩。' },
  '素面无事牌': { tip: '不雕花，最显种水。料要干净：有棉有裂会很难看。' },
  '观音佛公': { tip: '常年好卖，不挑料。' },
  '山水': { tip: '棉可以做成雪和云，棉多的料反而出彩。' },
  '花鸟龙凤': { tip: '镂雕花件，裂可以顺着纹路藏掉。' },
};
function themeDemand(w, theme) { if (theme === '师傅定') return 1; const r = new Rng(seedOf(w.seed, 'theme', Math.floor(w.day / 5), theme)); return theme === '观音佛公' ? r.range(0.98, 1.15) : r.range(0.8, 1.3); }
function demandWord(d) { return d > 1.12 ? '热' : d < 0.92 ? '冷' : '平'; }
// 真相下某方案的零售总值与件数；visible=true 时只算看得见的手镯位（给玩家看的预估）
function routeValue(w, tp, ringsVisible, route, masterName, theme) {
  const M = masterOf(w, masterName), crackShare = tp.volCrack / Math.max(1e-6, tp.volCrack + tp.volClean);
  let craft = M.craft[route] * (M.high && tp.wMean > 0.6 ? M.high : 1), mat = 0, n = 0, salv = M.salv, fit = 1, note = '';
  if (route === 'bracelet') { n = ringsVisible; mat = (tp.Vclean) * 0.12; }
  else if (route === 'pendant') { mat = tp.Vclean * 0.5; n = clamp(Math.round(tp.volClean / 14), 1, 10); }
  else if (route === 'cab') { mat = tp.Vtop * 1.2; n = clamp(Math.round(tp.volTop / 1.5), 0, 12); }
  else if (route === 'bead') { mat = tp.Vclean * 0.3; salv = Math.max(salv, 0.55); n = clamp(Math.round((tp.volClean + tp.volCrack) / 25), 1, 6); }
  else { mat = tp.Vclean * 0.4; salv += 0.3; n = tp.volClean > 300 ? 2 : 1; }
  if (route === 'pendant' || route === 'carve') {
    let th = theme;
    const fits = { '素面无事牌': (tp.cotMean < 0.12 && crackShare < 0.04) ? 1.18 : 0.68, '观音佛公': 1, '山水': 0.92 + 0.9 * tp.cotMean, '花鸟龙凤': 0.95 };
    if (th === '师傅定') { fit = 0.97; if (M.craft[route] < 0.7) fit = 0.9; }
    else { fit = fits[th] * themeDemand(w, th); if (th === '花鸟龙凤') salv += 0.3; if (th === '山水') salv += 0.1; }
  }
  mat += tp.Vcrack * Math.min(0.6, salv) * (route === 'bracelet' || route === 'cab' ? 0 : 0.5);
  return { total: mat * craft * fit, n, craft, fit };
}
// 蛋面逐步取料：从小号开始，每放大一号都可能磨出裂或脏；磨出来就伤了，退回上一号还要打折
const CAB_SIZES = [8, 10, 12, 14, 16, 18], CAB_MULT = CAB_SIZES.map(s => Math.pow(s / 12, 3));
function cabGame(w, s, piece) {
  const e = getVol(s), tp = evalPiece(e.st, e.vol, piece).truthParts, r = new Rng(seedOf(w.seed, 'cab', s.seed, piece.id));
  const crackShare = tp.volCrack / Math.max(1e-6, tp.volCrack + tp.volClean), base = clamp(0.07 + 0.9 * crackShare + 0.35 * tp.dirtMean + 0.25 * tp.cotMean, 0.05, 0.6);
  const max = clamp(1 + Math.floor(tp.volTop / 1.2), 1, CAB_SIZES.length - 1), risks = [], rolls = [];
  for (let k = 1; k <= max; k++) { risks.push(clamp(base * (1 + 0.4 * (k - 1)), 0, 0.85)); rolls.push(r.u()); }
  return { sizes: CAB_SIZES, mults: CAB_MULT, max, risks, rolls, hint: base < 0.14 ? '料很干净，可以大胆放。' : base < 0.3 ? '有点棉和小纹，放大要掂量。' : '裂和脏不少，贪大容易伤。' };
}
function workPlan(w, s, piece, route, masterName, theme) {
  const e = getVol(s), ev = evalPiece(e.st, e.vol, piece), tp = ev.truthParts, M = masterOf(w, masterName), R = ROUTES[route];
  const rv = routeValue(w, tp, ev.stats.bracelets, route, masterName, theme), warn = [];
  if (route === 'bracelet' && !ev.stats.bracelets) warn.push('看不到完整的手镯位：料不够大、太薄，或被裂切断。');
  if (route === 'cab' && rv.n === 0) warn.push('没有够浓的色，出不了蛋面。');
  if (ev.stats.kAvg < 0.5) warn.push('这块料大部分还没看清，师傅只能边做边看，结果可能和预想差很多。');
  const fee = Math.round((120 + Math.max(1, rv.n) * R.fee) * M.fee * (w.staff.master ? 0.8 : 1) * (1 - 0.3 * famEff(w, 'carver')) * (skillsOf(w).layout >= 2 ? 0.9 : 1));
  return { fee, days: Math.max(1, M.days - (w.staff.master ? 1 : 0)), n: rv.n, warn, ok: !(route === 'cab' && rv.n === 0) && !(route === 'bracelet' && !ev.stats.bracelets) };
}
function sendWork(w, s, piece, route, masterName, theme, opts) {
  const plan = workPlan(w, s, piece, route, masterName, theme); if (!plan.ok) return { ok: false, msg: plan.warn[0] };
  if (plan.fee > w.cash) return { ok: false, msg: '现金不够付工费。' };
  const e = getVol(s), st = e.st, ev = evalPiece(st, e.vol, piece), tp = ev.truthParts, M = masterOf(w, masterName), R = ROUTES[route];
  const r = new Rng(seedOf(w.seed, 'work', s.seed, piece.id, route, masterName)), items = [], body = BODIES[st.body], band = HUES[st.hue].band;
  const mk = (type, name, value, lv) => { const t = clamp(lv, 0, 1); items.push({ id: w.nextId++, stone: s.id, type, name, theme: (type === 'pendant' || type === 'carve') ? theme : '', master: masterName, value: Math.max(20, Math.round(value)), w: Math.round(tp.wMean * 100) / 100, lv: Math.round(t * 100) / 100, body, band, cot: Math.round(tp.cotMean * 100) / 100, seed: r.int(1, 9999), state: 'work' }); };
  const wn = waterName(tp.wMean), lvOf = () => clamp(tp.colorFrac * 1.6 * r.range(0.3, 1.7), 0, 1);
  const rv = routeValue(w, tp, tp.rings.length, route, masterName, theme); if (route === 'cab' && opts && opts.cabMult) rv.total *= opts.cabMult; rv.total *= (1 + 0.15 * famEff(w, 'carver')) * (skillsOf(w).layout >= 3 ? 1.06 : 1);
  let lost = 0;
  if (route === 'bracelet') {
    for (const v of tp.rings) { if (r.chance(M.press)) { lost++; continue; } mk('bracelet', `${wn}手镯`, v * 1.1 * rv.craft, lvOf()); }
    if (tp.Vclean * 0.12 > 50) mk('pendant', '镯芯与边角小件', tp.Vclean * 0.12 * rv.craft, lvOf());
  } else {
    const n = Math.max(1, rv.n), wts = []; let sum = 0; for (let i = 0; i < n; i++) { const x = Math.exp(r.norm() * 0.45); wts.push(x); sum += x; } wts.sort((a, b) => b - a);
    const nm = { pendant: theme === '师傅定' ? '挂件' : theme, cab: '蛋面', bead: '珠串', carve: (theme === '师傅定' ? '随形' : theme) + '雕件' }[route];
    for (let i = 0; i < n; i++) mk(route, `${wn}${nm}`, rv.total * wts[i] / sum, route === 'cab' ? r.range(0.65, 1) : lvOf() * (i < n / 2 ? 1.3 : 0.7));
  }
  w.cash -= plan.fee; s.costs += plan.fee; piece.sold = true; piece.soldPrice = 0; piece.buyer = '送加工';
  // 做到一半会不会出状况：全看石头里看不清的那部分藏着什么。裂、色比想的好、色没吃进去
  let issue = null; { const hid = 1 - ev.stats.kAvg, cs = tp.volCrack / Math.max(1e-6, tp.volCrack + tp.volClean), ir = new Rng(seedOf(w.seed, 'issue', s.seed, piece.id, route));
    if (tp.volCrack > 0 && ir.chance(clamp((0.22 + 2.2 * cs) * (0.35 + 0.65 * hid) * (1 - 0.5 * M.dodge), 0, 0.75))) issue = { type: 'crack' };
    else if (hid > 0.2 && tp.colorFrac > 0.10 && route !== 'cab' && ir.chance(0.5)) issue = { type: 'color' };
    else if (hid > 0.2 && tp.colorFrac < 0.04 && st.feats.length && route !== 'bead' && ir.chance(0.45)) issue = { type: 'gone' };
    if (issue) { issue.day = w.day + 1; issue.done = false; } }
  if (M.own) ownMaster(w).jobs++;
  w.works.push({ id: w.nextId++, stone: s.id, from: `#${s.id} ${piece.name}`, what: `${R.name} · ${masterName}`, master: masterName, route, ready: Math.max(w.day + plan.days, issue ? w.day + 2 : 0), items, expected: plan.n, lost, issue });
  w.log.push({ day: w.day, t: `送加工 #${s.id} ${piece.name}（${R.name}，${masterName}）`, amt: -plan.fee });
  return { ok: true, fee: plan.fee, days: M.days };
}
// 师傅的提案：他按看得见的料和自己的眼光排几种做法。设计越好，对看不清的部分猜得越准
function proposals(w, s, piece, masterName) {
  const e = getVol(s), ev = evalPiece(e.st, e.vol, piece), tp = ev.truthParts, k = ev.stats.kAvg, M = masterOf(w, masterName), cand = [];
  for (const route in ROUTES) for (const th of (route === 'pendant' || route === 'carve') ? ['素面无事牌', '观音佛公', '山水', '花鸟龙凤'] : ['师傅定']) {
    const plan = workPlan(w, s, piece, route, masterName, th); if (!plan.ok) continue; const rv = routeValue(w, tp, ev.stats.bracelets, route, masterName, th), r = new Rng(seedOf(w.seed, 'prop', s.seed, piece.id, masterName, route, th));
    const est = rv.total * (1 + (1 - k) * (1 - 0.6 * M.design) * r.range(-0.5, 0.7)); cand.push({ route, theme: th, est, fee: plan.fee, days: plan.days, n: plan.n, net: est * 0.6 - plan.fee }); }
  cand.sort((a, b) => b.net - a.net); const out = []; const add = (c, title) => { if (c && !out.some(o => o.route === c.route && o.theme === c.theme)) out.push(Object.assign({ title }, c)); };
  add(cand[0], '主推'); add(cand.find(c => c.route !== (cand[0] || {}).route), '备选'); add(cand.find(c => c.route === 'bead') || cand.find(c => c.theme === '观音佛公'), '稳妥');
  const SAY = { bracelet: '先切片压镯子，镯芯和边角再出小件。镯子成了，这块料就回本了', pendant: '片成牌料，一块一块做', cab: '只挑色最浓的地方取蛋面，别的不要了', bead: '车珠子，裂和脏都能让开，不会亏大的', carve: '整块不切，随形雕一件大的，成了是一件能压柜的货' };
  for (const o of out) { o.say = SAY[o.route] + (o.theme !== '师傅定' ? `，题材做${o.theme}` : '') + (k < 0.5 ? '。里面大半没看清，做到一半可能要你拿主意。' : k < 0.8 ? '。还有些地方没看到，可能有变数。' : '。料看得差不多了，出入不会大。'); o.lo = Math.round(o.est * 0.6 * (1 - 0.35 * (1 - k)) / 100) * 100; o.hi = Math.round(o.est * 0.6 * (1 + 0.45 * (1 - k)) / 100) * 100; }
  return out; }
// 做到一半停下来等你拿主意
function issueOf(w, k) { if (!k.issue || k.issue.done || w.day < k.issue.day) return null; const M = masterOf(w, k.master), sk = skillsOf(w), bc = sk.crack >= 2 ? 0.07 * (sk.crack - 1) : 0, bo = sk.color >= 2 ? 0.07 * (sk.color - 1) : 0, P = x => clamp(x, 0.05, 0.95);
  if (k.issue.type === 'crack') return { see: sk.crack >= 1, text: `${k.master}：“做到一半，里面冒出一条裂，正好从${k.route === 'bracelet' ? '镯圈上' : '主件中间'}过。你拿个主意。”`, opts: [
    { label: '改小一号，让开裂（稳，货变小）', p: 1, win: 0.62, winNote: '让开了裂，货小了一圈，但是干净。' },
    { label: k.route === 'bracelet' ? '不压镯了，改成牌子把裂藏进纹路' : '顺着裂改题材，把裂藏进纹路', p: P(0.3 + 0.55 * M.dodge + bc), win: 0.95, lose: 0.42, winNote: '裂藏进了枝叶里，不说没人看得出来。', loseNote: '裂没藏住，成品正面一道明纹，只能折价。' },
    { label: '按原计划硬做，赌裂不深', p: P(0.2 + 0.3 * M.dodge + bc), win: 1.08, lose: 0.25, drop: true, winNote: '裂只是面上一丝，磨下去就没了。赌对了。', loseNote: '裂是通的，做到最后崩开了。' }] };
  if (k.issue.type === 'color') return { see: sk.color >= 1, text: `${k.master}：“磨进去才发现，色比外面看的深，还往里吃了一截。要不要改方案追这个色？改了就回不去了。”`, opts: [
    { label: '改方案追色，把色留在正面', p: P(0.35 + 0.5 * M.color + bo), win: 1.75, lose: 0.8, winNote: '色留得正，整件一下子活了，价钱翻上去。', loseNote: '追着追着色断了，形也改乱了，不如不动。' },
    { label: '按原计划做，色随缘', p: 1, win: 1.12, winNote: '原样做完，带到了一点色，比预想的好一些。' }] };
  return { see: sk.color >= 1, text: `${k.master}：“外面那点色只有一层皮，往里一磨就没了。怎么办？”`, opts: [
    { label: '薄薄留住这层色，做贴色的小件', p: P(0.3 + 0.55 * M.color + bo), win: 0.9, lose: 0.5, winNote: '色留住了，薄是薄，正面看着有绿。', loseNote: '太薄，磨穿了，色没了，料也小了。' },
    { label: '不留了，磨掉做素件', p: 1, win: 0.62, winNote: '磨掉了色，做成素件，按种水卖。' }] }; }
function resolveIssue(w, id, i) { const k = w.works.find(x => x.id === id), is = k && issueOf(w, k); if (!is || !is.opts[i]) return { ok: false, msg: '' }; const o = is.opts[i], win = new Rng(seedOf(w.seed, 'resolve', k.id, i)).chance(o.p), m = win ? o.win : o.lose;
  if (!win && o.drop && k.items.length > 1) { k.items.sort((a, b) => b.value - a.value); k.items.shift(); k.lost = (k.lost || 0) + 1; for (const it of k.items) it.value = Math.max(20, Math.round(it.value * 0.7)); } else for (const it of k.items) it.value = Math.max(20, Math.round(it.value * m));
  if (win && k.issue.type === 'color') for (const it of k.items) it.lv = clamp((it.lv || 0) + 0.25, 0, 1);
  k.issue.done = true; k.issue.note = win ? o.winNote : o.loseNote; k.issue.win = win; k.ready = Math.max(k.ready, w.day + 1); w.log.push({ day: w.day, t: `${k.from}：${o.label} → ${win ? '成了' : '没成'}`, amt: 0 }); if (win && m > 1.5) achieve(w, 'chase', '追色追对了'); return { ok: true, win, msg: k.issue.note }; }
function stoneDone(w, s) { return s.pieces.every(p => p.sold || p.kept) && !w.works.some(k => k.stone === s.id) && !w.items.some(i => i.stone === s.id && i.state !== 'sold' && i.state !== 'kept'); }
function sellItem(w, it, how) {
  const r = new Rng(seedOf(w.seed, 'item', it.id)), price = Math.round(it.value * productDemand(w, it.type) * (how === 'retail' ? 0.95 : 0.6) / 10) * 10, days = how === 'retail' ? r.int(6, 14) : 0;
  w.stat.sold++;
  it.state = 'sold'; it.price = price;
  if (days) w.recv.push({ day: w.day + days, amt: price, from: `寄卖 ${it.name}` }); else w.cash += price;
  w.log.push({ day: w.day, t: `${it.name} ${how === 'retail' ? `寄卖，约 ${days} 天回款` : '批发现结'}`, amt: price });
  const s = w.stones.find(x => x.id === it.stone); if (s) { s.proceeds += price; if (!s.closed && stoneDone(w, s)) closeStone(w, s); }
  return price;
}
function closeStone(w, s) {
  if (s.closed || !stoneDone(w, s)) return;
  if (s.share < 1) { const settle = Math.round((s.proceeds - s.costs) * (1 - s.share)); w.cash -= settle; s.settle = settle; w.log.push({ day: w.day, t: `#${s.id} 合伙结账：${settle >= 0 ? '分给合伙人' : '合伙人补给你'}`, amt: -settle }); }
  s.closed = true; s.closeDay = w.day;
  const st = genStone(s.seed, s.origin, s.channel), fresh = bake(st), ev = evalPiece(st, fresh, WHOLE);
  const net0 = s.proceeds - s.buyPrice - s.costs; if (net0 > 0) { w.stat.wins++; achieve(w, 'win', '第一块赚钱的石头'); } if (net0 > s.buyPrice * 2) achieve(w, 'steal', '捡漏：净赚超过买价两倍'); if (net0 < -s.buyPrice * 0.6) achieve(w, 'bust', '交学费：一块亏掉六成以上');
  if (s.guess) { const g = s.guess, gi = gradeIdx(st.w0), cc = colorClass(st), ck = st.cracks.filter(c => c.open > 0.5).length >= 2 ? 'many' : 'few'; const pts = (g.water === gi ? 10 : Math.abs(g.water - gi) === 1 ? 5 : 0) + (g.color === cc ? 8 : 0) + (g.crack === ck ? 4 : 0); w.eye += pts; s.guessResult = { pts, water: gi, color: cc, crack: ck }; if (pts >= 22) achieve(w, 'sharp', '火眼金睛：种、色、裂全部判断对'); }
  s.review = { fake: s.fake ? FAKE_NAME[s.fake.type] : '', truth: Math.round(ev.truth), water: waterName(st.w0), hue: st.feats.length ? st.hue : '无色', cracks: st.cracks.filter(c => c.open > 0.5).length, feats: st.feats.map(f => ({ ribbon: '色带', pinch: '收尖色带', skin: '靠皮色', blob: '团块色', float: '飘花', full: '满色' })[f.type]), shift: st.shift ? (st.shift.drop > 0 ? '有变种（一侧种水变差）' : '有变种（一侧种水变好）') : '' };
}
function nextDay(w) {
  const notes = []; w.news = [];
  for (const k in w.markets) for (const L of w.markets[k]) if (L.auction && L.bid && !L.sold) { const nm = `${L.origin}·${L.info.skin}`; w.cash += L.bid; if (L.bid >= L.top) { buy(w, L, L.bid); notes.push(`${nm} 中标，成交 ${fmt(L.bid)}（对手最高出到 ${fmt(L.top)}）`); achieve(w, 'bid', '公盘中标'); } else notes.push(`${nm} 未中标，中标价 ${fmt(L.top)}，标款退回`); }
  w.day++; w.watchLeft = 3; const living = lifeTick(w, notes), pay = w.staff.clerk * STAFF.clerk.pay + w.staff.master * STAFF.master.pay + w.staff.host * STAFF.host.pay, rent = SHOPLV[w.shop].rent + w.branches * BRANCH_RENT; w.cash -= rent + pay; notes.push(`开销 ${living + rent + pay}`);
  if (pay) w.log.push({ day: w.day, t: '员工工资', amt: -pay });
  if (rent) w.log.push({ day: w.day, t: `${SHOPLV[w.shop].name}租金`, amt: -rent });
  w.after = w.after.filter(a => { if (a.day > w.day) return true;
    if (a.kind === 'boom') { relAdd(w, a.buyer, 8); w.fame += 2; notes.push(`${a.buyer}切涨了你卖的料，记你的好，以后出价会高些`); }
    else if (a.kind === 'bust') { relAdd(w, a.buyer, -10); w.fame -= 1; notes.push(`${a.buyer}把你卖的料切垮了，以后会压你的价`); }
    else if (a.kind === 'fake') { relAdd(w, a.buyer, -35); w.fame -= 8; w.cash -= a.amt; const s = w.stones.find(x => x.id === a.stone); if (s) s.proceeds -= a.amt; w.log.push({ day: w.day, t: `${a.buyer}发现是假料，上门退货`, amt: -a.amt }); notes.push(`${a.buyer}发现你卖的是做过手脚的料，上门退了 ${fmt(a.amt)}，口碑大跌`); }
    else relAdd(w, a.buyer, 2);
    return false; });
  { const S = SHOPLV[w.shop]; for (const s of w.stones) if (!s.closed) for (const p of s.pieces) if (p.shelf && !p.sold) { const r = new Rng(seedOf(w.seed, 'pshelf', s.seed, p.id, w.day));
      if (r.u() < (S.p + w.branches * 0.06 + w.staff.clerk * 0.04) * 0.8 * clamp(1 + w.fame / 100, 0.5, 1.6)) { const q = quotes(w, s, p), price = Math.round(q.best * 1.12 * S.mult * r.range(0.95, 1.08) / 10) * 10; if (price < 50) continue; p.sold = true; p.shelf = false; p.soldPrice = price; p.buyer = '铺面散客'; s.proceeds += price; w.cash += price; w.log.push({ day: w.day, t: `铺面卖出 #${s.id} ${p.name}`, amt: price }); notes.push(`铺面卖出料头 #${s.id} ${p.name} ${fmt(price)}`); closeStone(w, s); } }
    for (const it of w.items) if (it.state === 'shelf') { const r = new Rng(seedOf(w.seed, 'shelf', it.id, w.day)), dm = productDemand(w, it.type);
      if (r.u() < (S.p + w.branches * 0.06 + w.staff.clerk * 0.04 + famEff(w, 'manager') * 0.12) * dm * clamp(1 + w.fame / 100, 0.5, 1.6)) { w.stat.shelfSold++; const price = Math.round(it.value * S.mult * dm * r.range(0.94, 1.06) / 10) * 10; it.state = 'sold'; it.price = price; w.cash += price; w.fame += 0.5; w.log.push({ day: w.day, t: `铺面卖出 ${it.name}`, amt: price }); notes.push(`铺面卖出 ${it.name} ${fmt(price)}`); const s = w.stones.find(x => x.id === it.stone); if (s) { s.proceeds += price; if (!s.closed && stoneDone(w, s)) closeStone(w, s); } } } }

  w.recv = w.recv.filter(r => { if (r.day <= w.day) { w.cash += r.amt; notes.push(`${r.from} 到账 ${fmt(r.amt)}`); return false; } return true; });
  w.works = w.works.filter(k => { if (k.issue && !k.issue.done) { if (w.day >= k.issue.day && !k.issue.told) { k.issue.told = true; notes.push(`${k.from}：师傅做到一半停了手，等你拿主意`); } return true; } if (k.ready > w.day) return true; for (const it of k.items) { it.state = 'ready'; w.items.push(it); if (it.type === 'bracelet') achieve(w, 'bangle', '第一只手镯'); if (it.w >= 0.62) achieve(w, 'ice', '做出冰种以上的成品'); if (it.value >= 1e5) achieve(w, 'big', '单件成品过十万'); if (it.type === 'cab' && it.lv > 0.6) achieve(w, 'cab', '一粒满色蛋面'); } notes.push(`${k.from} 做好了：${k.items.length} 件${k.lost ? `，压坏 ${k.lost} 只镯子` : ''}`); return false; });
  if ((w.staff.host || famEff(w, 'host') > 0.15) && can(w, 'live') && w.liveDay !== w.day - 1) { const d = w.day; w.day = d - 1; const lr = liveRun(w); w.day = d; if (lr.ok) notes.push(`主播替你播了一场：成交 ${lr.sold} 件 ${fmt(lr.income)}，涨粉 ${lr.gain}`); } // 昨天你没播，主播替你播
  genMarket(w); fillOrders(w); rollEvent(w); if (w.event) notes.push('行情：' + w.event.t); for (const x of w.news) notes.push(x);
  const open = w.stones.some(s => !s.closed);
  if (w.cash < -20000 && !open && !w.recv.length && !w.items.some(i => i.state === 'ready')) w.over = true;
  return notes;
}
function serialize(w) { return JSON.stringify(w); }

const api = { Rng, seedOf, ORIGINS, CHANNELS, SKINS, HUES, BODIES, BUYERS, TOOLS, ECON, WHOLE, waterName, qWater, vd, genStone, bake, truthAt, crackG, sampleG, planeD, pick, carve, pieceInfo, slabOf, evalPiece, estimate, betOf, fmt, getVol, volCache, newWorld, genMarket, makeListing, negotiate, buy, quotes, explain, grind, peelAt, cutPreview, cut, sawPreview, saw, sell, pieceShelf, pieceKeep, CAB_SIZES, cabGame, FOODS, HOMES, CARS, SCHOOLS, JOBS, LOANS, TRAIN, FAMC, SKILLS, skillsOf, learnSkill, masterOf, mastersFor, ownMaster, proposals, issueOf, resolveIssue, trainKid, haveBaby, divorce, marry, startAffair, endAffair, kidAge, schoolsFor, traitWord, famEff, lifeCost, loanRoom, borrow, repay, buyAsset, setSchool, setJob, restDay, lifeEvent, applyEvent, UNLOCK, can, watch, liveRun, STAFF, BRANCH_COST, BRANCH_RENT, openBranch, hire, slotsOf, SCENE_CH, CHAPTERS, DEBT, ACH_ALL, netWorth, goalDone, checkStory, payDebt, FAKE_NAME, callOut, relOf, relWord, SHOPLV, upgradeShop, shelfCount, toShelf, SHOP, applyTools, buyTool, appraise, appraiseFee, productDemand, SCENES, RANKS, GRADES, rankOf, sceneOpen, enterScene, achieve, gradeIdx, colorClass, fillOrders, orderMatch, orderText, sellToOrder, keepItem, placeBid, ROUTES, MASTERS, THEMES, themeDemand, demandWord, workPlan, sendWork, sellItem, stoneDone, closeStone, nextDay, serialize };
if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Core = api;
})(typeof window !== 'undefined' ? window : globalThis);
