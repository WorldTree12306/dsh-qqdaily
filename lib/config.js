// dsh-qqdaily — 配置读取（与 python/qqdaily.py 的解析顺序保持一致）
//
// 顺序：显式路径 > $QQDAILY_CONFIG > ~/.dsh/qqdaily.json > 内置默认值
// 路径类键支持 ~ 展开；留空的键补默认值（默认落在插件目录下的 workspace/out/tmp）。
import { readFileSync, existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
/** 插件根目录（lib/ 的上一级）。 */
export const PLUGIN_ROOT = resolve(HERE, '..')

/** 内置默认值——与 Python 端 DEFAULTS 一一对应。 */
export const DEFAULTS = {
  base: '',
  out: '',
  tmp: '',
  archive: '',
  paper: '群日报',
  template: 'example',
  templates_dir: '',
  edge: '',
  python: '',
  onebot: { endpoint: 'http://127.0.0.1:3001', token: '', group_id: 0 },
  send: { images: true, text: false },
  layout: {
    capacity: 1010,
    byline: '本报记者',
    kicker: '群内观察',
    date: '',
    window: '',
  },
  limits: {
    min_pages: 4,
    min_total_hanzi: 3500,
    min_page_hanzi: 600,
    min_gap_px: 6,
    max_hole_px: 300,
  },
}

/** ~ 与 $VAR 展开（只做最常见的两种）。 */
export function expand(p) {
  let s = String(p ?? '')
  if (s.startsWith('~')) s = join(homedir(), s.slice(1))
  s = s.replace(/\$(\w+)|\$\{(\w+)\}/g, (_, a, b) => process.env[a || b] ?? '')
  return s
}

function deepMerge(base, over) {
  const out = { ...base }
  for (const [k, v] of Object.entries(over ?? {})) {
    out[k] = v && typeof v === 'object' && !Array.isArray(v) && typeof out[k] === 'object'
      ? deepMerge(out[k], v)
      : v
  }
  return out
}

/** 默认配置文件路径。 */
export function defaultConfigPath() {
  const home = process.env.DSH_HOME || join(homedir(), '.dsh')
  return join(home, 'qqdaily.json')
}

/**
 * 读取并规范化配置。
 * @param {string} [explicit] 显式配置路径（工具参数优先）
 */
export function loadConfig(explicit) {
  const path = explicit ? expand(explicit) : (process.env.QQDAILY_CONFIG || defaultConfigPath())
  let user = {}
  let readError = null
  if (existsSync(path)) {
    try {
      user = JSON.parse(readFileSync(path, 'utf8'))
    } catch (error) {
      readError = `${path}: ${error instanceof Error ? error.message : String(error)}`
    }
  }
  const cfg = deepMerge(DEFAULTS, user)
  cfg.configPath = path
  cfg.configError = readError
  cfg.templates_dir = cfg.templates_dir ? expand(cfg.templates_dir) : join(PLUGIN_ROOT, 'templates')
  cfg.template_dir = join(cfg.templates_dir, cfg.template)
  cfg.base = cfg.base ? expand(cfg.base) : join(PLUGIN_ROOT, 'workspace')
  cfg.out = cfg.out ? expand(cfg.out) : join(PLUGIN_ROOT, 'out')
  cfg.tmp = cfg.tmp ? expand(cfg.tmp) : join(PLUGIN_ROOT, 'tmp')
  cfg.archive = cfg.archive ? expand(cfg.archive) : ''
  cfg.python = cfg.python || process.env.QQDAILY_PYTHON || 'python'
  return cfg
}

/** 传给 Python 内核的环境变量（与 qqdaily.py 的 env_for_typesetter 对齐）。 */
export function pythonEnv(cfg) {
  const env = { ...process.env }
  env.QQDAILY_BASE = cfg.base
  env.QQDAILY_OUT = cfg.out
  env.QQDAILY_TMP = cfg.tmp
  env.QQDAILY_PAPER = cfg.paper
  if (cfg.edge) env.QQDAILY_EDGE = cfg.edge
  const ban = join(cfg.template_dir, '禁用词.txt')
  if (existsSync(ban)) env.QQDAILY_BAN = ban
  const tpl = join(cfg.template_dir, '程序', '报纸版面模板.html')
  if (existsSync(tpl)) env.QQDAILY_TPL = tpl
  return env
}

/** Python 内核入口路径。 */
export function pythonEntry() {
  return join(PLUGIN_ROOT, 'python', 'qqdaily.py')
}
