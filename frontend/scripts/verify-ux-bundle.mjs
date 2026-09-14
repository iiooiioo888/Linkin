#!/usr/bin/env node
/**
 * 建置後 UX 迴歸掃描 — 防止任務看板／metrics %%／MediaCrawler 標籤回退。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), '../dist/assets');
if (!fs.existsSync(dist)) {
  console.error('verify-ux-bundle: dist/assets 不存在，請先 npm run build');
  process.exit(1);
}

const files = fs.readdirSync(dist).filter((f) => f.endsWith('.js'));
const all = files.map((f) => fs.readFileSync(path.join(dist, f), 'utf8')).join('\n');

const errors = [];

// 任務看板：已完成欄不可再含 failed/cancelled/interrupted
const taskColMatch = all.match(
  /key:`done`,label:`已完成`,statuses:\[`completed`(?:,`failed`|`cancelled`|`interrupted`)+\]/,
);
if (taskColMatch) {
  errors.push('TASK_COLUMNS done 欄仍包含失敗／取消／中斷狀態');
}
if (!all.includes('key:`failed`,label:`失敗`,statuses:[`failed`,`cancelled`,`interrupted`]')) {
  errors.push('缺少 TASK_COLUMNS 失敗欄定義');
}

// Metrics KPI：不可同時在 value 內含 % 又對任務成功率傳 unit:"%"
if (/任務成功率`,value:`\$\{[^}]+\}%`,unit:`%`/.test(all)) {
  errors.push('任務成功率 KPI 仍可能渲染雙重 %（value 與 unit 重複）');
}

if (!all.includes('乾跑啟動')) {
  errors.push('MediaCrawler 乾跑啟動標籤未出現在 bundle');
}

if (errors.length) {
  console.error('verify-ux-bundle FAILED:\n' + errors.map((e) => `  - ${e}`).join('\n'));
  process.exit(1);
}

console.log('verify-ux-bundle OK');
