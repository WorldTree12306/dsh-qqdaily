# dsh-qqdaily

把**群聊变成一份报纸**的 DeepSeek Harness 插件：OneBot（NapCat）采集 → 话题统计 → 模板化排版 →
逐字校验 → 版图发群。全部行为由配置文件决定，版式模板可换。

- 采集：从 OneBot 11 的 `get_group_msg_history` 抓群消息，按时间窗口落成 JSONL
- 统计：总条数 / 参与人数 / 人均 / 发言榜 / 按天 / 最热闹时段
- 排版：内容 JSON + 模板 → HTML → **PDF**（无头 Edge/Chrome）→ 每版一张 PNG
- 校验：正文引语逐字命中率、禁用词、每版溢出与页脚间距、字数硬指标
- 发群：只发版图（默认不发文字），走 OneBot `send_group_msg`

## 依赖

| 依赖 | 说明 |
|---|---|
| Node.js ≥ 20 | 宿主插件（`lib/`） |
| Python ≥ 3.10 | 内核（`python/qqdaily.py`）；需 `pypdfium2` 才能出 PDF/版图 |
| Edge 或 Chrome | 无头渲染 HTML→PDF；路径可配置（`edge`），留空自动探测 |
| OneBot 11 实现 | 如 NapCat，提供 HTTP 接口（默认 `http://127.0.0.1:3001`） |

```bash
pip install pypdfium2          # 唯一的 Python 三方依赖
```

## 安装

```bash
dsh plugin --profile desktop add <本目录或包名>
```

安装后插件会以 `qqdaily` 之名挂载（`cordis.patch.yml` 里的 insert），并注册这些工具：

| 工具 | 作用 |
|---|---|
| `qqdaily_status` | 查看生效配置与已装模板 |
| `qqdaily_fetch` | 抓群消息窗口 |
| `qqdaily_stats` | 窗口统计 |
| `qqdaily_typeset` | 内容 JSON → HTML/PDF/版图 |
| `qqdaily_check` | 引语逐字 / 禁用词 / 版心与字数 |
| `qqdaily_send` | 发版图到群 |
| `qqdaily_templates` | 列出版式模板 |

## 配置

首次使用：

```bash
python python/qqdaily.py init      # 写出样例到 ~/.dsh/qqdaily.json
python python/qqdaily.py config    # 看生效值
```

关键键（`~/.dsh/qqdaily.json`，全部可选）：

```jsonc
{
  "paper": "群日报",                  // 刊名，进报头与文件名
  "base": "~/QQ日报",                 // 素材基目录：内容 JSON 里 吉祥物/素材库/x.png 按它解析
  "out": "~/QQ日报/5-报纸成品",        // 成品目录（HTML/PDF/版图）
  "tmp": "~/QQ日报/tmp",              // 临时目录（无头浏览器 profile）
  "archive": "",                      // 归档目录，可空
  "template": "template1",            // 用哪个版式模板
  "edge": "",                         // 浏览器可执行文件；空=自动探测
  "python": "python",                 // 解释器路径
  "onebot": { "endpoint": "http://127.0.0.1:3001", "token": "", "group_id": 123456 },
  "send": { "images": true, "text": false },
  "layout": { "capacity": 1010, "byline": "本报记者", "kicker": "群内观察" },
  "limits": { "min_pages": 4, "min_total_hanzi": 3500, "min_page_hanzi": 600,
              "min_gap_px": 6, "max_hole_px": 300 }
}
```

配置解析顺序：**工具参数 `config_path` > `$QQDAILY_CONFIG` > `~/.dsh/qqdaily.json` > 内置默认值**。
路径类键支持 `~` 与 `$VAR` 展开；留空的键自动补默认值（默认落在插件目录下）。

## 命令行用法（不装插件也能用）

```bash
P=D:\\Python313\\python.exe
$P python/qqdaily.py config
$P python/qqdaily.py stats  --since "2026-10-14 21:00"
$P python/qqdaily.py fetch  --since "2026-10-14 21:00" --label 012
$P python/qqdaily.py typeset --内容 内容_第012期.json --期号 012 \
    --日期 "2026 年 10 月 16 日　星期五" --时段 "10-14 21:00 — 10-16 19:20"
$P python/qqdaily.py check  --期号 012
$P python/qqdaily.py send   --期号 012
```

## 内容 JSON 与版式模板

一期报纸的**内容**与**版式**是分开的：

- 内容 JSON（你自己写）：`headline`（头条）／`chapters`（章节）／`minis`（短刊）／
  `quotes`（语录）／各版槽位（`p1_minis`、`p2_side_minis`、`p3_plan`、`p4_mid`、`p5_mid`…）／
  `masthead`（报头）。
- 模板目录（可复制改名换风格）：

```
templates/template1/
  模板.json              槽位表说明（各版放什么、有哪些开关）
  禁用词.txt             命中即不登（可换成你自己的表）
  程序/排特刊v3.py       排版器：JSON → HTML → PDF → 版图
  程序/报纸版面模板.html  版面 CSS/结构
```

换模板：把 `templates/template1` 复制成 `template2`，改 CSS 与槽位表，然后把配置里的
`template` 改成 `template2` 即可（`qqdaily_templates` 会列出所有模板与是否齐全）。

## 输出

```
<out>/
  <刊名>_第<期号>期.html     排版源
  <刊名>_第<期号>期.pdf      A4 成品（每版一页）
  <日报/刊名缩写>_第N版.png   每版一张，用于发群
```

## 设计说明

- **路径全配置化**：排版器与校验脚本读环境变量（`QQDAILY_BASE/OUT/TMP/EDGE/TPL/PAPER/BAN`），
  这些由 `lib/config.js` 与 `python/qqdaily.py` 按同一套配置注入，两边行为一致。
- **不碰内容**：插件只做「采集→统计→排版→校验→发布」，写稿交给 agent（内容 JSON 由你或
  你的模型产出）。
- **诚实校验**：`qqdaily_check` 会把每条引语回查语料，未逐字命中的会点名列出，不做静默放过。

## 已知限制

- 需要本机有 Edge/Chrome（不打包浏览器内核）。
- 只支持 OneBot 11 系（NapCat 等）；其它聊天源需另写 `fetch`。
- 版式以中文报刊为默认（竖排题栏、左右对开、版底横板）；改西文/横排需改模板 CSS。
- 发图走本机 HTTP，不代理图片上传；大图频率过高可能触发平台风控。

## 许可

MIT。模板里的字体依赖系统字体（宋体/黑体/楷体），分发前请确认你对所选用字体的授权。
