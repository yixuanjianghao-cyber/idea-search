// 配置：token 从环境变量或 ~/.github-finder.json 读
import { readFileSync, writeFileSync, existsSync, mkdirSync, renameSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, dirname } from 'node:path';

const FILE = join(process.env.GHF_DATA_DIR || homedir(), '.github-finder.json');

export function load() {
  try {
    if (!existsSync(FILE)) return {};
    return JSON.parse(readFileSync(FILE, 'utf8'));
  } catch {
    return {};
  }
}

export function save(patch) {
  const cur = load();
  const next = { ...cur, ...patch };
  try {
    mkdirSync(dirname(FILE), { recursive: true });
    const tmp = FILE + '.tmp';
    writeFileSync(tmp, JSON.stringify(next, null, 2), { mode: 0o600 });
    renameSync(tmp, FILE);
  } catch (e) {
    throw new Error(`写配置失败：${e.message}`);
  }
  return next;
}

export function token() {
  return process.env.GITHUB_TOKEN || process.env.GH_TOKEN || load().token || '';
}

export function maskedToken() {
  const t = token();
  if (!t) return '';
  if (t.length <= 8) return '****';
  return `${t.slice(0, 4)}…${t.slice(-4)}`;
}

export const configPath = FILE;
