// 端到端回归：通过插件的 JS 工具（而非直接跑 Python）排一期并校验，
// 用真实配置（~/.dsh/qqdaily.json）+ 第 012 期内容 JSON。
//
// 用法： node lib/e2e.test.mjs
import { readFileSync } from 'node:fs'
import { loadConfig } from './config.js'
import { buildTools } from './index.js'

const tools = Object.fromEntries(buildTools({}).map((t) => [t.name, t]))
const cfg = loadConfig()
const CONTENT = process.argv[2]
  || 'C:/Users/Administrator/Desktop/QQ日报/4-出报素材和日志/特刊内容_第012期.json'

console.log('配置：', cfg.configPath, '｜刊名：', cfg.paper, '｜输出：', cfg.out)

const ts = await tools.qqdaily_typeset.handler({
  content: CONTENT, issue: '012',
  date: '2026 年 10 月 16 日　星期五',
  window: '10-14 21:00 — 10-16 19:20',
})
const tsText = ts.content?.[0]?.text ?? ''
console.log('--- typeset ---')
console.log(tsText.split('\n').slice(-6).join('\n'))

const ck = await tools.qqdaily_check.handler({ issue: '012' })
const ckText = ck.content?.[0]?.text ?? ''
console.log('--- check ---')
console.log(ckText)

// 断言：版数、溢出、页脚间距、字数、引语未命中、禁用词
const problems = []
if (!/回流结果：\d+ 版/.test(tsText)) problems.push('排版未产出回流结果')
if (/溢出 \[(?!0(, 0)*\])/.test(tsText)) problems.push('存在溢出页')
if (/压页脚/.test(ckText)) problems.push('压页脚')
if (!/正文引语（「」）\d+ 条　未命中 0/.test(ckText)) problems.push('引语未全部逐字命中')
if (!/禁用词命中 0/.test(ckText)) problems.push('命中禁用词')
const total = Number((ckText.match(/全期汉字[^：]*：(\d+)/) || [])[1] || 0)
if (total < cfg.limits.min_total_hanzi) problems.push(`全期汉字 ${total} 低于下限 ${cfg.limits.min_total_hanzi}`)

console.log('--- 结论 ---')
if (problems.length) {
  for (const p of problems) console.log('  ✗', p)
  process.exit(1)
}
console.log(`  端到端通过：全期汉字 ${total}，引语逐字 100%，禁用词 0，无溢出`)
