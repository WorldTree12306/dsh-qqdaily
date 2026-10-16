// dsh-qqdaily 挂载测试：用假的 cordis ctx 跑一遍 apply()，
// 验证「宿主入口 → ctx.effect → ctx.tools.register」这条路径真的能注册出工具。
//
// 用法： node lib/mount.test.mjs
import { apply, buildTools, inject, name } from './index.js'
import { loadConfig } from './config.js'

const problems = []
const registered = []
let effectRan = 0
let disposed = 0

const ctx = {
  effect(fn, label) {
    effectRan += 1
    const dispose = fn()
    return () => {
      disposed += 1
      dispose?.()
    }
  },
  tools: {
    register(tool) {
      if (!tool || typeof tool !== 'object') throw new Error('register 收到非法定义')
      registered.push(tool.name)
      return () => { /* 单个工具的卸载句柄 */ }
    },
  },
}

apply(ctx, { configPath: process.argv[2] || undefined })

const expected = buildTools({}).map((t) => t.name)
if (effectRan !== 1) problems.push(`ctx.effect 调用次数应为 1，实际 ${effectRan}`)
if (registered.length !== expected.length) {
  problems.push(`注册工具数 ${registered.length} ≠ 期望 ${expected.length}`)
}
for (const n of expected) if (!registered.includes(n)) problems.push(`未注册：${n}`)
if (inject.includes('tools') === false) problems.push('inject 未声明 tools')
if (name !== 'qqdaily') problems.push(`插件名应为 qqdaily，实际 ${name}`)

// 配置能否加载（含路径默认值补齐）
const cfg = loadConfig(process.argv[2])
for (const key of ['base', 'out', 'tmp', 'templates_dir', 'template_dir', 'paper', 'python']) {
  if (!cfg[key]) problems.push(`配置缺键：${key}`)
}

console.log(JSON.stringify({
  plugin: name,
  effectRan,
  registered,
  expected,
  configOk: { paper: cfg.paper, out: cfg.out, template_dir: cfg.template_dir, python: cfg.python },
}, null, 1))

if (problems.length) {
  console.log('--- 问题 ---')
  for (const p of problems) console.log('  ✗', p)
  process.exit(1)
}
console.log('--- 挂载测试通过 ---')
