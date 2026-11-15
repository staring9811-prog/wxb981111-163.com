// 用法：node 截图.js（在本目录运行），把 成功率判定_画像.html 截成整页 PNG
const { chromium } = require('playwright'); const path = require('path');
(async () => { const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
  await p.goto('file://' + path.join(__dirname, '成功率判定_画像.html'));
  await p.screenshot({ path: path.join(__dirname, '成功率判定_画像.png'), fullPage: true }); await b.close(); })();
