// dsh-qqdaily — host half.
//
// 把「群聊 → 报纸」的流水线暴露成 DSH 工具；真正的活由 Python 内核
// （python/qqdaily.py）干，这里只做参数整理、超时与错误包装。
//
// 工具：
//   qqdaily_status    查看生效配置与模板
//   qqdaily_fetch     从 OneBot 抓群消息窗口
//   qqdaily_stats     窗口统计（条数/人数/冠军/按天按小时）
//   qqdaily_typeset   内容 JSON → HTML → PDF → 每版 PNG
//   qqdaily_check     引语逐字 / 禁用词 / 版心与字数
//   qqdaily_send      只发版图到群（默认不发文字）
//   qqdaily_templates 列出可用版式模板
import { execFile } from 'node:child_process'
import { appendFileSync, existsSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { PLUGIN_ROOT, loadConfig, pythonEntry, pythonEnv } from './config.js'

/** Stable cordis plugin name（与 cordis.patch.yml 的 insert id 对应）。 */
export const name = 'qqdaily'
/** 需要 tools 服务来注册工具。 */
export const inject = ['tools']

const DEFAULT_TIMEOUT_MS = 1_800_000

/** 跑一次 Python 内核；返回 {code, stdout, stderr}。 */
function runPython(cfg, args, timeoutMs = DEFAULT_TIMEOUT_MS) {
  return new Promise((resolveResult) => {
    const entry = pythonEntry()
    if (!existsSync(entry)) {
      resolveResult({ code: 127, stdout: '', stderr: `找不到内核：${entry}` })
      return
    }
    const argv = [entry, '--config', cfg.configPath, ...args]
    execFile(cfg.python, argv, {
      env: pythonEnv(cfg),
      timeout: timeoutMs,
      maxBuffer: 8 * 1024 * 1024,
      windowsHide: true,
    }, (error, stdout, stderr) => {
      const code = error && typeof error.code === 'number' ? error.code : error ? 1 : 0
      resolveResult({ code, stdout: String(stdout ?? ''), stderr: String(stderr ?? '') })
    })
  })
}

/** 统一的工具结果包装：命令失败也算「已观测到的结果」，不抛给宿主。 */
function toolResult(r, note = '') {
  const body = [note, r.stdout.trim(), r.stderr.trim()].filter(Boolean).join('\n')
  return { content: [{ type: 'text', text: body || `(无输出，退出码 ${r.code})` }], isError: r.code !== 0 }
}

/** 组装工具列表；cfgOverride 来自插件 config。 */
export function buildTools(cfgOverride = {}) {
  const cfgOf = (params = {}) => loadConfig(params.config_path || cfgOverride.configPath || undefined)

  return [
    {
      name: 'qqdaily_status',
      description: '查看 qqdaily 的生效配置（刊名、模板、目录、OneBot 群号、硬指标）与已装模板。',
      parameters: { type: 'object', properties: { config_path: { type: 'string' } } },
      handler: async (params) => {
        const cfg = cfgOf(params)
        const r = await runPython(cfg, ['config'], 30_000)
        const t = await runPython(cfg, ['templates'], 30_000)
        return toolResult(r, r.code === 0 ? `配置文件：${cfg.configPath}\n` + t.stdout.trim() : '')
      },
    },
    {
      name: 'qqdaily_fetch',
      description: '从 OneBot（NapCat）抓取指定群的历史消息，按时间过滤后写成窗口 JSONL。',
      parameters: {
        type: 'object',
        properties: {
          since: { type: 'string', description: '起始时间 YYYY-MM-DD HH:MM（含）' },
          label: { type: 'string', description: '窗口标签，写进文件名，如 012' },
          out: { type: 'string', description: '输出路径；省略则写到配置的 tmp 目录' },
          count: { type: 'number', description: '最多抓多少条，默认 500' },
          config_path: { type: 'string' },
        },
        required: ['since'],
      },
      handler: async (params) => {
        const args = ['fetch', '--since', params.since]
        if (params.label) args.push('--label', params.label)
        if (params.out) args.push('--out', params.out)
        if (params.count) args.push('--count', String(params.count))
        return toolResult(await runPython(cfgOf(params), args))
      },
    },
    {
      name: 'qqdaily_stats',
      description: '统计窗口：总条数、参与人数、人均、发言榜、按天与最热闹时段。',
      parameters: {
        type: 'object',
        properties: {
          since: { type: 'string' }, window: { type: 'string' },
          save: { type: 'string', description: '把统计 JSON 存到该路径' },
          config_path: { type: 'string' },
        },
      },
      handler: async (params) => {
        const args = ['stats', '--since', params.since ?? '']
        if (params.window) args.push('--window', params.window)
        if (params.save) args.push('--save', params.save)
        return toolResult(await runPython(cfgOf(params), args))
      },
    },
    {
      name: 'qqdaily_typeset',
      description: '按模板排版一期：内容 JSON → HTML → PDF → 每版 PNG，并回报每版溢出与页脚间距。',
      parameters: {
        type: 'object',
        properties: {
          content: { type: 'string', description: '内容 JSON 路径' },
          issue: { type: 'string', description: '期号，如 012' },
          date: { type: 'string', description: '如「2026 年 10 月 16 日　星期五」' },
          window: { type: 'string', description: '统计时段，如「10-14 21:00 — 10-16 19:20」' },
          byline: { type: 'string' }, kicker: { type: 'string' },
          capacity: { type: 'number', description: '每版容量像素，默认取配置' },
          config_path: { type: 'string' },
        },
        required: ['content', 'issue'],
      },
      handler: async (params) => {
        const args = ['typeset', '--内容', params.content, '--期号', params.issue]
        if (params.date) args.push('--日期', params.date)
        if (params.window) args.push('--时段', params.window)
        if (params.byline) args.push('--署名', params.byline)
        if (params.kicker) args.push('--引题', params.kicker)
        if (params.capacity) args.push('--capacity', String(params.capacity))
        return toolResult(await runPython(cfgOf(params), args))
      },
    },
    {
      name: 'qqdaily_check',
      description: '校验一期：正文引语逐字命中率、语录栏、禁用词、每版溢出与页脚间距、字数硬指标。',
      parameters: {
        type: 'object',
        properties: { issue: { type: 'string' }, config_path: { type: 'string' } },
        required: ['issue'],
      },
      handler: async (params) => toolResult(
        await runPython(cfgOf(params), ['check', '--期号', params.issue]),
      ),
    },
    {
      name: 'qqdaily_send',
      description: '把某期版图发到群（默认只发图；配置 send.text=true 才会带文字）。',
      parameters: {
        type: 'object',
        properties: { issue: { type: 'string' }, config_path: { type: 'string' } },
        required: ['issue'],
      },
      handler: async (params) => toolResult(
        await runPython(cfgOf(params), ['send', '--期号', params.issue], 300_000),
      ),
    },
    {
      name: 'qqdaily_templates',
      description: '列出可用版式模板（含排版器与槽位表是否齐全）。',
      parameters: { type: 'object', properties: { config_path: { type: 'string' } } },
      handler: async (params) => toolResult(await runPython(cfgOf(params), ['templates'], 30_000)),
    },
  ]
}

/** cordis 挂载点。 */
export function apply(ctx, config = {}) {
  const tools = buildTools(config)
  writeMountReceipt(tools, config)
  try {
    ctx.effect(() => {
      const disposers = tools.map((tool) => ctx.tools.register(tool))
      return () => {
        for (const dispose of disposers.reverse()) {
          try { dispose?.() } catch { /* 卸载失败不阻塞 */ }
        }
      }
    }, 'qqdaily: tools')
  } catch (error) {
    console.error('[qqdaily] tool registration failed:', error)
  }
}

/**
 * 写一张挂载回执（<插件>/tmp/mount.log，一行一条）。
 *
 * 用途：宿主应用装载本插件时，会把「什么时候、挂了几件工具、配置从哪来」记在本地，
 * 便于安装后确认真的挂上了（不需要开日志窗口）。失败不影响挂载。
 */
function writeMountReceipt(tools, config) {
  try {
    const dir = join(PLUGIN_ROOT, 'tmp')
    mkdirSync(dir, { recursive: true })
    const line = JSON.stringify({
      at: new Date().toISOString(),
      pid: process.pid,
      plugin: name,
      tools: tools.map((t) => t.name),
      configPath: config?.configPath || process.env.QQDAILY_CONFIG || '',
    })
    appendFileSync(join(dir, 'mount.log'), line + '\n', 'utf8')
  } catch {
    /* 回执只是诊断，不影响挂载 */
  }
}
