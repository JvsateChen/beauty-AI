#!/usr/bin/env node
/**
 * 守卫脚本：禁止在 UI 代码中出现 emoji。
 *
 * 原因：emoji 在不同系统字体下形状/线宽/颜色不一致，无法继承 currentColor
 * 做 hover / 激活态染色。全站图标统一走 components/Icons.tsx 的内联 SVG。
 *
 * 允许的范围：注释里的排版符号（→ 等）与 Markdown 之外的文案标点。
 * 检查范围：app/ 与 components/ 下的 .tsx/.ts（不含 node_modules）。
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = process.cwd();
const TARGETS = ['app', 'components', 'lib'];

/** emoji 与「像图标的符号」范围（不含中文标点与常见排版符） */
const BANNED = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{2705}\u{274C}\u{2714}\u{2716}]/u;

/** 行内允许的例外（正则字面量里可能包含的字符，以及注释里的排版符号） */
const LINE_ALLOW = /^\s*(\/\/|\*|\/\*)/;

function walk(dir, out = []) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const name of entries) {
    if (name === 'node_modules' || name === '.next') continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (/\.(tsx?|jsx?|css)$/.test(name)) out.push(full);
  }
  return out;
}

const violations = [];

for (const target of TARGETS) {
  for (const file of walk(join(ROOT, target))) {
    const lines = readFileSync(file, 'utf8').split(/\r?\n/);
    lines.forEach((line, i) => {
      if (LINE_ALLOW.test(line)) return;            // 注释里的排版符号可接受
      if (!BANNED.test(line)) return;
      // 排除 JS 正则 / 字符类里为了写校验规则而出现的 emoji 范围
      const m = line.match(BANNED);
      violations.push({
        file: relative(ROOT, file),
        line: i + 1,
        char: m[0],
        text: line.trim().slice(0, 100),
      });
    });
  }
}

if (violations.length === 0) {
  console.log('emoji 检查通过：UI 代码中未发现 emoji 图标。');
  process.exit(0);
}

console.error(`发现 ${violations.length} 处 emoji，请改用 components/Icons.tsx 的 <Icon />：\n`);
for (const v of violations) {
  console.error(`  ${v.file}:${v.line}  「${v.char}」  ${v.text}`);
}
process.exit(1);
