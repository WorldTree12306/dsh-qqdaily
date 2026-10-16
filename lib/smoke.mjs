// dsh-qqdaily 冒烟测试：不依赖 DSH 宿主，验证配置加载 + 工具清单 + 一次真实内核调用。
//
// 用法： node lib/smoke.mjs [配置文件路径]
import { loadConfig, pythonEntry } from './config.js'
import { buildTools, inject, name } from './index.js'

const cfg = loadConfig(process.argv[2])
const tools = buildTools({ configPath: cfg.configPath })
const summary = {
  plugin: name,
  inject,
  configPath: cfg.configPath,
  configError: cfg.configError,
  paper: cfg.paper,
  template: cfg.template,
  template_dir: cfg.template_dir,
  out: cfg.out,
  tmp: cfg.tmp,
  python: cfg.python,
  onebot_group: cfg.onebot.group_id,
  pythonEntry: pythonEntry(),
  tools: tools.map((t) => t.name),
}
console.log(JSON.stringify(summary, null, 1))

const problems = []
if (cfg.configError) problems.push(`配置读取失败：${cfg.configError}`)
if (!tools.length) problems.push('没有注册任何工具')
for (const t of tools) {
  if (!t.name.startsWith('qqdaily_')) problems.push(`工具名不带前缀：${t.name}`)
  if (typeof t.handler !== 'function') problems.push(`工具缺 handler：${t.name}`)
  if (!t.description) problems.push(`工具缺描述：${t.name}`)
}

// 真跑一次内核：templates（列出模板，不写盘）
const status = tools.find((t) => t.name === 'qqdaily_templates')
const result = await status.handler({})
console.log('--- qqdaily_templates 输出 ---')
console.log(result.content?.[0]?.text ?? '(空)')

if (result.isError) problems.push('内核调用失败')
if (problems.length) {
  console.log('--- 问题 ---')
  for (const p of problems) console.log('  ✗', p)
  process.exit(1)
}
console.log('--- 冒烟通过 ---')
