# -*- coding: utf-8 -*-
r"""特刊排版 v3 —— 量高后贪心装箱，让小章节/一句话自动填进大章节之间的空隙。

流程：
  ① 把每个「块」（大章节 / 小章节 / 一句话）渲成一段 HTML
  ② 用无头浏览器量出每块实际高度
  ③ 按版心容量贪心装箱（--容量 只定初始切分，之后不再动）
  ④ 逐版回流：实量各版溢出，哪版超了就把该版最后一块推到下一版（必要时新增一版）；
     首版装不下则从底条 → 语录栏尾推块。循环到全部装下，不降容量、不改字号
  ⑤ 出最终 HTML → Edge 打印 PDF → pypdfium2 出各版 PNG

块类型：
  chapter  大章节：栏目名 + 居中标题 + 副题 + 两栏正文
  mini     小章节：小标题 + 一段（带左边线，窄栏处理）
  line     一句话：● 前缀单行

内容 JSON 可选字段（第 2 版版式，主编 2026-10-15 要求）：
  vlead_chapter  章节标题。写了它，第 2 版首章强制走竖排题栏（左竖排主标题/副题/栏名框
                 + 中两栏正文），回流阶段不再自动降级、不推块
  vlead_mini     短刊标题（通常在 p2_side_minis 里）。竖排后钉在第 2 版右上角，与左侧
                 竖排题栏并列；首章之后的章节整体下移到竖排区之下按常规排

用法：
  python 程序\排特刊v3.py --内容 4-出报素材和日志\特刊内容_第009期.json \
     --刊名 群日报 --期号 001 --日期 "2026 年 10 月 10 日　星期六" \
     --时段 "10-08 20:00 — 10-10 22:00"
"""
import argparse
import json
import pathlib

# ── dsh-qqdaily 注入：路径与浏览器由环境变量决定，默认值保持向后兼容 ──
import os as _os
def _qd(name, default):
    return _os.environ.get(name) or default
QD_BASE = pathlib.Path(_qd("QQDAILY_BASE", r"C:\Users\Administrator\Desktop\QQ日报"))
QD_OUT = pathlib.Path(_qd("QQDAILY_OUT", str(QD_BASE / "5-报纸成品")))
QD_TMP = pathlib.Path(_qd("QQDAILY_TMP", r"D:\ai\out"))
QD_EDGE = _qd("QQDAILY_EDGE", "")
QD_TPL = _qd("QQDAILY_TPL", "")
# ── 品牌串：从 <模板>/模板.json 的「品牌」段读取，缺省回落到中性文案 ──
def _brand():
    d = {}
    try:
        import json as _json
        cfg = _json.loads((pathlib.Path(__file__).resolve().parent.parent / "模板.json")
                          .read_text(encoding="utf-8"))
        d = cfg.get("品牌") or {}
    except Exception:
        d = {}
    return d


BRAND = _brand()


def brand(key, default=""):
    return str(BRAND.get(key) or default)


import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = pathlib.Path(__file__).resolve().parent
BASE = QD_BASE   # dsh-qqdaily：由配置/环境变量决定
TPL = pathlib.Path(QD_TPL) if QD_TPL else (HERE / "报纸版面模板.html")
# 探测列表与 出报主程序.py 的 BROWSERS 一致：Edge 更新换目录时不会整条出报链路静默断链
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
EDGE = QD_EDGE if QD_EDGE else next((b for b in BROWSERS if pathlib.Path(b).exists()), None)
if EDGE is None:
    sys.exit("找不到 Edge/Chrome，无法量高/出 PDF。探测过：" + "；".join(BROWSERS))

EXTRA_CSS = """
/* 大章节 */
.chap { break-inside: avoid; }
.chap-kicker { font-family:"SimHei","黑体",sans-serif; font-size:11pt; letter-spacing:2px;
  border-left:5px solid #b3261e; padding-left:6px; margin:9px 0 4px; }
.chap-kicker small { font-family:Georgia,serif; font-size:7.6pt; color:#999; letter-spacing:2px;
  margin-left:6px; }
.chap-title { text-align:center; font-family:"SimHei","黑体",sans-serif; font-weight:900;
  font-size:17pt; line-height:1.24; margin:2px 0 2px; }
.chap-deck { text-align:center; font-family:"KaiTi","楷体",serif; font-size:10.2pt;
  color:#444; margin-bottom:4px; }
.chap-body { column-count:2; column-gap:12px; column-rule:.5px solid #d5d5d5; }
.chap-body p { margin:0 0 4px; text-indent:2em; }
.chap .sign { text-align:right; font-family:"KaiTi","楷体",serif; font-size:10.4pt;
  color:#333; margin:6px 2px 0; text-indent:0; }
.chap .credit { border-top:1px solid #17181a; margin-top:9px; padding-top:5px;
  font-size:8.6pt; line-height:1.6; color:#444; }
.chap .credit div:first-child { font-family:"SimHei","黑体",sans-serif; }
/* 次条改单栏：右半栏内容流到左栏下方（豹饼干 2026-10-10 要求） */
.chap-body.one { column-count:1; }
.chap-body.one p { margin-bottom:3px; }
.rail .mini { margin:5px 0 0; padding:4px 7px; }
.rail .mini-t { font-size:10.6pt; }
.rail .mini p { font-size:9.1pt; line-height:1.44; }
/* 小章节：填空用，带左边线、窄一号字 */
.mini { border-left:3px solid #b3261e; background:#fbf9f6; padding:5px 8px; margin:7px 0;
  break-inside:avoid; }
.mini-t { font-family:"SimHei","黑体",sans-serif; font-size:11.4pt; letter-spacing:1px;
  margin-bottom:2px; }
.mini-deck { font-family:"KaiTi","楷体",serif; font-size:9.2pt; color:#555;
  margin-bottom:3px; }
.mini p { margin:0; font-size:9.9pt; line-height:1.52; }
/* 一句话：单行，圆点前缀 */
.line { margin:5px 0; padding-left:13px; position:relative; font-size:10pt; line-height:1.5;
  break-inside:avoid; }
.line::before { content:"●"; position:absolute; left:0; top:1px; color:#b3261e; font-size:7pt; }
.line .w { color:#888; font-size:8.6pt; }

/* 左右半版：整版劈成左右两半，各成一路读下来（仿人民日报三版，豹饼干指定） */
.page.has-pin { display:flex; flex-direction:column; }
.page.has-pin .pinbottom { margin-top:auto; }
.page.has-pin .halves { flex:1 1 auto; }        /* 撑满剩余高度，左半的沉底才生效 */
.halves { display:flex; gap:0; align-items:stretch; }
.halves .half { flex:1 1 0; min-width:0; padding:0 9px; }
.halves .half:first-child { padding-left:0; }
.halves .half.halfcol { display:flex; flex-direction:column; }
.halves .half .sink { margin-top:auto; }
.halves .half .mid { margin:auto 0; }      /* 上下自动留白 = 垂直居中（豹饼干指定） */
.halves .half.spread { justify-content:space-between; }   /* 顶/中/底三分 */
.halves .half.spread .mid, .halves .half.spread .sink { margin:0; }
.halves .half:last-child { border-left:1px solid #17181a; padding-right:0; }
.halves .chap-title { font-size:13.6pt; line-height:1.26; }
.halves .chap-deck { font-size:9.4pt; }
.halves .chap-body { column-count:1; }
.halves .chap-body p { font-size:10.2pt; line-height:1.5; }
.halves .chap-kicker { font-size:10pt; margin:7px 0 3px; }

 /* 首版底部横条：两条小章节**上下排列**、各占整行（豹饼干 2026-10-10 指定） */
 .miniband { display:block; margin-top:4px; }
 .miniband .mini { margin:0 0 5px; }
 .miniband .mini:last-child { margin-bottom:0; }
 .miniband .mini p { font-size:9.3pt; line-height:1.44; }

 /* 首版语录栏：次条回流到第 2 版后改通栏双列（豹饼干 2026-10-14 放开首版版式） */
 .p1quotes h3 { font-family:"SimHei","黑体",sans-serif; font-size:10pt; letter-spacing:1.5px;
   border-bottom:2px solid #17181a; padding-bottom:2px; margin:6px 0 5px; }
 .p1quotes .qcols { column-count:2; column-gap:12px; }
 .p1quotes .qcard2 { break-inside:avoid; }
 .p1quotes .mini { margin:6px 0 0; }

/* ---------- 竖排标题版式（仿人民日报「思想纵横」那一版，豹饼干 2026-10-10 指定）----------
   左：一条竖排大标题（自上而下）＋栏名装饰；中：三栏正文；右：一块横标题短文。 */
.vlead { display:flex; gap:10px; align-items:stretch; break-inside:avoid; }
.vlead .vcol { flex:0 0 76px; border-left:1px solid #17181a; border-right:1px solid #17181a;
  padding:0 5px; display:flex; flex-direction:column; align-items:center; }
/* 第 2 版：题栏列拉到竖排区底，竖线顶住下面的分隔符（主编 2026-10-15）*/
.vlead.v2 .vcol { align-self:stretch; width:86px; flex:0 0 86px; }
.vlead .vstack { display:flex; flex-direction:row; gap:5px; align-items:flex-start;
  justify-content:center; width:100%; }
.vlead .vdeck { writing-mode:vertical-rl; text-orientation:upright;
  font-family:"KaiTi","楷体",serif; font-size:9.6pt; line-height:1.15; color:#333;
  letter-spacing:1px; margin-top:6px; }
.vlead .vtitle { writing-mode:vertical-rl; text-orientation:upright;
  font-family:"SimHei","黑体",sans-serif; font-weight:400; font-size:17pt; line-height:1.06;
  letter-spacing:2px; margin:2px auto 5px; }
/* 字号由页面脚本按「与正文等高」自动缩放（豹饼干要求） */
.vlead .vkicker { writing-mode:vertical-rl; text-orientation:upright; color:#b3261e;
  font-family:"SimHei","黑体",sans-serif; font-size:9.2pt; letter-spacing:2px; margin-top:auto;
  border:1px solid #b3261e; padding:3px 2px; background:#fdf7f5; }
.vlead .vmain { flex:1 1 0; min-width:0; }
.vlead .vmain .deck { font-family:"KaiTi","楷体",serif; font-size:9.8pt; color:#444;
  text-align:center; border-bottom:.5px solid #bbb; padding-bottom:3px; margin-bottom:5px; }
.vlead .vmain .vbody { column-count:2; column-gap:12px; column-rule:.5px solid #d5d5d5; }
.vlead .vmain .vbody p { margin:0 0 4px; text-indent:2em; }
.vlead .vpic { margin:7px 0 0; text-align:center; }
.vlead .vpic img { width:190px; max-width:92%; height:auto; display:block; margin:0 auto; }
.vlead .vpic .cap { font-family:"KaiTi","楷体",serif; font-size:8.8pt; color:#555;
  margin-top:2px; }
/* 版中报花条（p{N}_mid 里 kind:"pic"，主编 2026-10-15 要求第 2 版竖排后仍要有报花） */
.picband { margin:9px 0 2px; text-align:center; }
.picband img { height:104px; width:auto; display:inline-block; }
.picband .cap { font-family:"KaiTi","楷体",serif; font-size:8.4pt; color:#555; margin-top:2px; }
/* 答群友问（p{N}_mid 里 kind:"qa"） */
.qabox { border:1.5px solid #17181a; background:#fbf9f6; padding:6px 9px 7px; margin:9px 0 0; }
.qabox .qa-h { font-family:"SimHei","黑体",sans-serif; font-size:11.4pt; letter-spacing:1.5px;
  margin:0 0 4px; }
.qabox .qa-q, .qabox .qa-a { font-size:9.6pt; line-height:1.6; text-align:justify; }
.qabox .qa-q b, .qabox .qa-a b { font-family:"SimHei","黑体",sans-serif; font-weight:400;
  margin-right:2px; }
.qabox .qa-a { margin-top:3px; }
/* 统计框（p{N}_mid 里 kind:"statbox"）：带边框的数据栏 */
.statbox { border:1.5px solid #17181a; background:#fbf9f6; padding:5px 8px 6px; margin:7px 0 0; }
.statbox h4 { font-family:"SimHei","黑体",sans-serif; font-size:11.4pt; font-weight:400;
  letter-spacing:1.5px; margin:0 0 3px; }
.statbox .srow { display:flex; justify-content:space-between; gap:8px; font-size:9pt;
  line-height:1.38; padding:.5px 0; border-top:.5px dotted #dcdcdc; }
.statbox .srow:first-of-type { border-top:0; }
.statbox .srow b { font-weight:400; font-family:"SimHei","黑体",sans-serif; }
.statbox .snote { font-size:8pt; color:#666; margin-top:4px; line-height:1.35; }
/* 第 2 版中栏报花：固定高度（图片未加载时也要占位，否则量高按 0 算、会和下一章叠住） */
.vlead .vpic.small { margin:4px 0 0; }
.vlead .vpic.small img { width:auto; height:72px; max-width:100%; }
.vlead .vpic.small .cap { font-size:7.8pt; margin-top:1px; }
.vlead .vside { flex:0 0 37%; border-left:1px solid #17181a; padding-left:10px; }
.vlead .vside .sub-title { font-size:13.6pt; margin-top:0; }
.vlead .vside .vbody2 { column-count:1; }
.vlead .vside .vbody2 p { margin:0 0 4px; text-indent:2em; font-size:10.6pt; line-height:1.52; }
/* 头条区（第 1 版）沿用 v2 */
.lead-kicker { text-align:center; font-family:"SimHei","黑体",sans-serif; font-size:11pt;
  letter-spacing:3px; color:#b3261e; margin:2px 0 3px; }
.lead-kicker span { border-bottom:1.5px solid #b3261e; padding-bottom:1px; }
.lead-title { text-align:center; font-family:"SimHei","黑体",sans-serif; font-weight:900;
  font-size:25pt; line-height:1.16; letter-spacing:1px; margin:3px 0 4px; }
.lead-deck { text-align:center; font-family:"KaiTi","楷体",serif; font-size:11.6pt; color:#333;
  margin-bottom:3px; }
.lead-byline { text-align:center; font-size:8.8pt; color:#666; border-bottom:.5px solid #bbb;
  padding-bottom:4px; margin-bottom:7px; }
.cols3 { column-count:3; column-gap:12px; column-rule:.5px solid #d5d5d5; }
.cols3 p { margin:0 0 4px; text-indent:2em; }
.cols3 p.lead-p { text-indent:0; }
.cols3 p.lead-p::first-letter { font-size:1.9em; font-family:"SimHei","黑体",sans-serif; line-height:1; }
.split { display:flex; gap:11px; align-items:flex-start; }
.split .main { flex:1 1 0; min-width:0; }
.split .rail { flex:0 0 31%; border-left:1px solid #17181a; padding-left:9px; }
.sub-title { text-align:center; font-family:"SimHei","黑体",sans-serif; font-weight:900;
  font-size:15pt; line-height:1.24; margin:2px 0 3px; }
.sub-deck { text-align:center; font-family:"KaiTi","楷体",serif; font-size:10.4pt; color:#444;
  margin-bottom:3px; }
.rail h3 { font-family:"SimHei","黑体",sans-serif; font-size:10pt; letter-spacing:1.5px;
  border-bottom:2px solid #17181a; padding-bottom:2px; margin:0 0 5px; }
.qcard2 { border-left:3px solid #b3261e; background:#faf7f4; padding:1px 6px; margin-bottom:2px; }
.qcard2 .t { font-size:9.1pt; line-height:1.42; }
.qcard2 .b { font-size:8.4pt; color:#777; text-align:right; margin-top:2px; }

/* ---------- 第 2 版强制竖排（内容 JSON vlead_chapter 指定，主编 2026-10-15 要求）----------
   左：竖排题栏（栏名框 + 竖排主标题 + 竖排副题）；中：两栏正文；右：竖排短刊（vlead_mini
   指定）。其余章节下移到竖排区之下常规排。竖排区不放 vpic 报花图：正稿 011 的量高预算里
   图一加就顶破版心，强制竖排时不再渲染 vlead_image。 */
/* 用 grid 而不是 flex 排三列：行高天然等于最高的一列，
   否则 flex 会把中栏拉伸/压缩，报花从盒子里漏出来压住下一章（2026-10-15 修） */
/* 第 2 版：竖排区吃掉本版余量，使其下的章节贴住版底分隔线（主编 2026-10-15）*/
.page.has-pin > .vlead.v2 { flex:1 0 auto; }
.vlead.v2 { min-height:300px; display:grid; flex:0 0 auto;
  grid-template-columns:76px minmax(0,1fr) 205px; gap:10px; align-items:start; }  /* 保竖排短刊列高（首章两栏正文实测约 270-290px，取整 300） */
.vlead.v2 .vmini { border-left:1px solid #17181a; padding:2px 6px 2px 8px;
  writing-mode:vertical-rl; background:#fbf9f6; height:430px; flex:0 0 auto; }
.vlead.v2 .vmini .vmini-t { font-family:"SimHei","黑体",sans-serif; font-size:11pt;
  letter-spacing:2px; color:#b3261e; margin-left:5px; }
.vlead.v2 .vmini p { margin:0; font-size:8.2pt; line-height:1.5; letter-spacing:0; }
.vlead.v2 .vdeck { font-size:11pt; letter-spacing:1.2px; }
/* 竖排短刊：给显式高度，竖排文字按高度折列（宽度随列数自动长）*/
/* 竖排区吸收本版余量：群像章贴住版底分隔线（主编 2026-10-15）*/
.vlead.v2 .vmini:not(.vmini-h) { flex:0 0 auto; height:430px; }
/* 横板变体（半横板）：右列定宽、高度自适应 */
/* 横板右列：拉到底（左边线顶住分隔符），高度由竖排区決定，不影响其他块（主编 2026-10-15）*/
.vlead.v2 .vmini-h { flex:0 0 232px; align-self:stretch; height:auto; }
/* 半横板：右列位置不变，字改横排（主编 2026-10-15：天堂改半横板） */
.vlead.v2 .vmini-h { writing-mode:horizontal-tb; }
.vlead.v2 .vmini-h .vmini-t { writing-mode:horizontal-tb; font-size:14pt; letter-spacing:1px;
  margin:0 0 4px; }
.vlead.v2 .vmini-h p { writing-mode:horizontal-tb; font-size:11pt; line-height:1.55;
  letter-spacing:0; text-align:justify; }
/* 右列里再挂的短刊（.mini 块）同步放大 */
.vlead.v2 .vmini-h .mini { padding:5px 7px; margin-top:8px; }
.vlead.v2 .vmini-h .mini .mini-t { font-size:13pt; margin-bottom:3px; }
.vlead.v2 .vmini-h .mini p { font-size:11pt; line-height:1.55; }
/* 右列「群友语录」：小字、细虚线分隔，只留名字不留时间戳 */
.vlead.v2 .qband { margin-top:6px; border-top:.5px solid #c9c9c9; padding-top:4px; }
.vlead.v2 .qband-t { font-family:"SimHei","黑体",sans-serif; font-size:9.6pt; color:#b3261e;
  letter-spacing:1px; margin-bottom:3px; }
.vlead.v2 .qline { font-size:8.6pt; line-height:1.42; padding:1px 0; }
.vlead.v2 .qline + .qline { border-top:.5px dashed #d8d8d8; }
.vlead.v2 .qline .w { color:#777; font-size:8pt; }
"""


def _vtitle_style(title):
    """竖排主标题按字数缩号：标题太长会把竖排栏名框顶出框（主编 2026-10-15 反馈）。"""
    n = len(title or "")
    if n <= 8:
        return "font-size:19pt;letter-spacing:2px"
    if n <= 10:
        return "font-size:17.4pt;letter-spacing:1px"
    if n <= 12:
        return "font-size:16pt;letter-spacing:1px"
    return "font-size:14.4pt;letter-spacing:0"


def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def paras(items, cls="", first_lead=False):
    out = []
    for i, x in enumerate(items):
        c = (cls + (" lead-p" if (first_lead and i == 0) else "")).strip()
        out.append(f'<p class="{c}">{esc(x)}</p>' if c else f"<p>{esc(x)}</p>")
    return "".join(out)


def block_html(blk, half=False):
    """把一块渲成 HTML（不带外层版心）。half=True 时按半版排（标题小一号）。"""
    k = blk["kind"]
    if k == "chapter":
        h = [f'<div class="chap-kicker">{esc(blk.get("kicker") or "要闻")}'
             f'<small>{esc(blk.get("en") or "")}</small></div>',
             f'<div class="chap-title">{esc(blk["title"])}</div>']
        if blk.get("deck"):
            h.append(f'<div class="chap-deck">{esc(blk["deck"])}</div>')
        h.append('<div class="rule-thin"></div>')
        body = blk.get("body") or []
        if blk.get("qa"):
            # 问答体：每组问答之间加一条细分隔线
            seg, first = [], True
            for x in body:
                if x.startswith("问：") and not first:
                    seg.append('<div class="rule-hair" style="margin:6px 0"></div>')
                seg.append(f'<p class="indent">{esc(x)}</p>')
                first = False
            h.append('<div class="chap-body">' + "".join(seg) + '</div>')
        else:
            h.append(f'<div class="chap-body">{paras(body)}</div>')
        if blk.get("credit"):
            h.append('<div class="credit">' + "".join(
                f'<div>{esc(x)}</div>' for x in blk["credit"]) + '</div>')
        if blk.get("sign"):
            h.append(f'<div class="sign">{esc(blk["sign"])}</div>')
        return f'<div class="chap">{"".join(h)}</div>'
    if k == "mini":
        d = (f'<div class="mini-deck">{esc(blk["deck"])}</div>'
             if blk.get("deck") else '')
        return (f'<div class="mini"><div class="mini-t">{esc(blk["title"])}</div>'
                f'{d}<p>{esc(blk["text"])}</p></div>')
    if k == "line":
        w = f'　<span class="w">——{esc(blk["who"])}</span>' if blk.get("who") else ""
        return f'<div class="line">{esc(blk["text"])}{w}</div>'
    if k == "rule":
        return '<div class="rule-double"></div>'
    return ""


def measure(blocks, css):
    """用无头浏览器量每块真实高度（结果写进 <title>，比解析 DOM 稳）。"""
    body = "".join(f'<div id="b{i}">{block_html(b)}</div>' for i, b in enumerate(blocks))
    html = (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>0</title>'
            f'<style>{css}</style></head><body>'
            f'<div style="width:188mm">{body}</div>'
            f'<script>window.addEventListener("load",function(){{'
            f'var o=[];document.querySelectorAll("[id^=b]").forEach(function(e){{'
            f'o.push(Math.round(e.getBoundingClientRect().height));}});'
            f'document.title=o.join(",");}});</script></body></html>')
    tmp = QD_OUT / "_measure.html"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(html, encoding="utf-8")
    try:
        r = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                            "--virtual-time-budget=12000",
                            f"--user-data-dir={QD_TMP/'ep_auto'}",
                            "--dump-dom", "file:///" + str(tmp).replace("\\", "/")],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=240)
    finally:
        tmp.unlink(missing_ok=True)
    m = re.search(r"<title>([\d,]+)</title>", r.stdout or "")
    if not m or m.group(1) == "0":
        print("  ! 量高失败，退回估算")
        return None
    return [float(x) for x in m.group(1).split(",")]


def page_overflow(hp):
    """量每版溢出 px（列表，索引 0 是第 1 版）。量不到返回 None。"""
    js = ("<script>window.addEventListener('load',function(){var o=[];"
          "document.querySelectorAll('.page').forEach(function(p){"
          "o.push(p.scrollHeight-p.clientHeight);});"
          "var d=document.createElement('div');d.id='__O';d.textContent=JSON.stringify(o);"
          "document.body.appendChild(d);});</script>")
    tmp = hp.with_name("_chk.html")
    tmp.write_text(hp.read_text(encoding="utf-8").replace("</body>", js + "</body>"),
                   encoding="utf-8")
    try:
        r = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                            "--virtual-time-budget=12000",
                            f"--user-data-dir={QD_TMP/'ep_auto'}",
                            "--dump-dom", "file:///" + str(tmp).replace("\\", "/")],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=240)
    finally:
        tmp.unlink(missing_ok=True)
    m = re.search(r'id="__O"[^>]*>(.*?)</div>', r.stdout or "", re.S)
    if not m or not m.group(1).strip():
        return None
    try:
        return [float(x) for x in json.loads(m.group(1).replace("&quot;", '"'))]
    except Exception:
        return None


def page_stats(hp):
    """量每版（溢出 px, 最深内容距页脚 px）。量法同 程序\\版心与字数.py，只读不改。"""
    js = ("<script>window.addEventListener('load',function(){var o=[];"
          "document.querySelectorAll('.page').forEach(function(p){"
          "var f=p.querySelector('.folio');var ft=f?f.getBoundingClientRect().top:1e9;"
          "var deep=0;Array.prototype.forEach.call(p.children,function(e){"
          "if(e===f)return;var r=e.getBoundingClientRect();"
          "if(r.height>0&&r.bottom>deep)deep=r.bottom;});"
          "o.push([Math.round(p.scrollHeight-p.clientHeight),Math.round(ft-deep)]);});"
          "var d=document.createElement('div');d.id='__O';d.textContent=JSON.stringify(o);"
          "document.body.appendChild(d);});</script>")
    tmp = hp.with_name("_stats.html")
    tmp.write_text(hp.read_text(encoding="utf-8").replace("</body>", js + "</body>"),
                   encoding="utf-8")
    try:
        r = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                            "--virtual-time-budget=12000",
                            f"--user-data-dir={QD_TMP/'ep_auto'}",
                            "--dump-dom", "file:///" + str(tmp).replace("\\", "/")],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=240)
    finally:
        tmp.unlink(missing_ok=True)
    m = re.search(r'id="__O"[^>]*>(.*?)</div>', r.stdout or "", re.S)
    if not m or not m.group(1).strip():
        return None
    try:
        return json.loads(m.group(1).replace("&quot;", '"'))
    except Exception:
        return None


def measure_blocks(hp, page_no):
    r"""量第 page_no 版每个子块的高度与整版溢出（--量块 用，只读诊断）。
    量法与 程序\量版面块.py 完全一致：往临时副本注入一段 JS，无头浏览器
    dump-dom 取数；正式 HTML 只读不动，临时文件量完即删，不改任何版式参数。"""
    js = ("<script>window.addEventListener('load',function(){var o=[];"
          "var ps=document.querySelectorAll('.page');"
          "o.push(['__pages',ps.length]);"
          "var p=ps[" + str(page_no - 1) + "];"
          "if(p){o.push(['__overflow',p.scrollHeight-p.clientHeight]);"
          "Array.prototype.forEach.call(p.children,function(e){"
          "o.push([e.className||e.tagName,Math.round(e.getBoundingClientRect().height)]);});}"
          "var d=document.createElement('div');d.id='__O';d.textContent=JSON.stringify(o);"
          "document.body.appendChild(d);});</script>")
    tmp = hp.with_name("_量块.html")
    tmp.write_text(hp.read_text(encoding="utf-8").replace("</body>", js + "</body>"),
                   encoding="utf-8")
    try:
        r = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                            "--virtual-time-budget=12000",
                            f"--user-data-dir={QD_TMP/'ep_auto'}",
                            "--dump-dom", "file:///" + str(tmp).replace("\\", "/")],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=240)
    finally:
        tmp.unlink(missing_ok=True)
    m = re.search(r'id="__O"[^>]*>(.*?)</div>', r.stdout or "", re.S)
    if not m or not m.group(1).strip():
        return None
    try:
        return json.loads(m.group(1).replace("&quot;", '"'))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--内容", required=True)
    ap.add_argument("--刊名", default=brand("默认刊名", "群日报"))
    ap.add_argument("--期号", required=True)
    ap.add_argument("--日期", default="")
    ap.add_argument("--时段", default="")
    ap.add_argument("--署名", default=brand("默认署名", "本报记者"))
    ap.add_argument("--引题", default="群内观察")
    ap.add_argument("--容量", type=int, default=1010,
                    help="每版初始装箱容量 px（只定初始切分，回流阶段不再调整）")
    ap.add_argument("--量块", nargs="?", const=1, default=None, type=int, metavar="版号",
                    help="可选：排版出报完成后，量第 N 版（不给 N 则第 1 版）逐块高度与"
                         "溢出，只打印不改版式；不带本参数时输出与从前完全一致")
    o = ap.parse_args()

    c = json.loads(pathlib.Path(o.内容).read_text(encoding="utf-8-sig"))
    css = TPL.read_text(encoding="utf-8").split("<style>", 1)[1].split("</style>", 1)[0]

    # 第 1 版：报头 + 头条 + 群友语录栏 + p1_minis 底条。次条(chapters[0])不再钉首版，
    # 交给下面的装箱流当第 2 版开头（豹饼干 2026-10-14：首版改自然回流，不再人工削）
    hl = c["headline"]
    chap = c.get("chapters") or []
    minis = c.get("minis") or []
    lines = c.get("oneliners") or []
    p1_quotes = list(c.get("quotes") or [])       # 语录栏（尾部可推到后面的版）
    p1_minis = list(c.get("p1_minis") or [])      # 首版底条（尾部可推到后面的版）

    # 「本报立场」右耳：立场 / 萌点 / 提示 / 编辑部，均可按期覆盖（内容 JSON 的 masthead 字段）
    moe = c.get("masthead") or {}
    stance = esc(moe.get("stance") or "头条谁聊得凶谁上")
    face = esc(moe.get("face") or "(*^▽^*)")
    tip = esc(moe.get("tip") or "排错了请骂排版机，别骂鱼。")
    ed = esc(moe.get("editor") or brand("默认编辑", "编辑部"))
    note = esc(moe.get("editor_note") or "DSH 驱动 · 不吃饭不睡觉")
    ear2 = (f'<div class="ear"><b>本报立场</b>{stance} <b>{face}</b><br>{tip}'
            f'<br><b>编辑部</b>{ed}<span style="font-size:7.4pt">（{note}）</span></div>')

    masthead = f'''<div class="masthead">
 <div class="mh-top"><span>第 {o.期号} 期</span><span>{brand("报头中文", o.刊名 + " · 群友内部发行（非卖品）")}</span><span>定价：免费</span></div>
 <div class="mh-row">
  <div class="ear"><b>本期要目</b>{esc("　".join([hl.get("title")] + [x.get("title") for x in chap[:4]]))}</div>
  <div class="mh-title"><h1 class="title">{esc(o.刊名)}</h1>
   <div class="mh-en">{brand("报头英文", "COMMUNITY DAILY")}</div></div>
  {ear2}
 </div>
 <div class="mh-top" style="margin-top:3px"><span>{esc(o.日期)}</span>
  <span>统计时段 {esc(o.时段)}</span><span>本期共 {{PAGES}} 版</span></div>
</div>'''

    def build_p1():
        """首版 = 报头 + 头条 + 群友语录栏 + p1_minis 底条。
        p1_quotes / p1_minis 是活列表：回流阶段从尾部推块后这里自动少排。"""
        p1 = ['<div class="page">', masthead, '<h2 class="sec">要闻 <small>TOP NEWS</small></h2>']
        if o.引题:
            p1.append(f'<div class="lead-kicker"><span>{esc(o.引题)}</span></div>')
        p1.append(f'<div class="lead-title">{esc(hl["title"])}</div>')
        if hl.get("subtitle"):
            p1.append(f'<div class="lead-deck">{esc(hl["subtitle"])}</div>')
        p1.append(f'<div class="lead-byline">{esc(o.署名)}　·　{esc(o.日期)}</div>')
        p1.append(f'<div class="cols3">{paras(hl.get("body") or [], first_lead=True)}</div>')
        # 群友语录栏：次条回流走后改通栏双列；rail_minis 仍随语录栏排（版位语义不变）
        if p1_quotes or (c.get("rail_minis") or []):
            p1.append('<div class="rule-thick"></div><div class="p1quotes">')
            if p1_quotes:
                p1.append('<h3>群友语录</h3><div class="qcols">')
                p1 += [f'<div class="qcard2"><div class="t">「{esc(q["text"])}」</div>'
                       f'<div class="b">{esc(q.get("who"))}　{esc(q.get("when"))}</div></div>'
                       for q in p1_quotes]
                p1.append('</div>')
            for m in (c.get("rail_minis") or []):
                p1.append(f'<div class="mini"><div class="mini-t">{esc(m["title"])}</div>'
                          f'<p>{esc(m["text"])}</p></div>')
            p1.append('</div>')
        # 首版底条：p1_minis 钉首版底；装不下时回流阶段从尾往前推到后面的版
        if p1_minis:
            p1.append('<div class="rule-thick"></div><div class="miniband">')
            p1 += [f'<div class="mini"><div class="mini-t">{esc(m["title"])}</div>'
                   f'<p>{esc(m["text"])}</p></div>' for m in p1_minis]
            p1.append('</div>')
        p1.append(f'<div class="folio">{esc(o.刊名)}　第 {o.期号} 期　{esc(o.日期)}　第 1 版</div></div>')
        return p1

    # 后续版：贪心装箱。次条(chapters[0])也进流，作为第 2 版内容的开头
    rest = [{"kind": "chapter", **x} for x in chap]
    rest += [{"kind": "mini", **x} for x in minis]
    rest += [{"kind": "line", **x} for x in lines]

    # 第 3 版若手工指定了版位，就把这些块抽出来，并把第 3 版整版留空（None 占位）
    plan = c.get("p3_plan") or None
    plan_blocks = {}
    if plan:
        want = set(plan.get("left", []) + plan.get("left_bottom", [])
                   + plan.get("left_mid", [])
                   + plan.get("right", []) + plan.get("right_bottom", []) + plan.get("right_seq", []) + plan.get("right_center", [])
                   + plan.get("defer", []))
        for b in rest:
            if b.get("title") and b["title"] in want:      # 一句话块没有 title，要防
                plan_blocks[b["title"]] = b
        rest = [b for b in rest if not (b.get("title") and b["title"] in want)]
        print(f"  第 3 版手工版位：{[x['title'] for x in plan_blocks.values()]}")
    # 第 2 版强制竖排：vlead_chapter 指定首章标题后，回流阶段不再自动降级（主编要求）
    force_lead = (c.get("vlead_chapter") or "").strip()
    force_mini = (c.get("vlead_mini") or "").strip()
    if force_lead:
        ok = bool(rest) and rest[0].get("kind") == "chapter" and rest[0].get("title") == force_lead
        print(f"  vlead_chapter「{force_lead}」→ 第 2 版强制竖排（不自动降级）"
              + ("" if ok else "　! 装箱流首块与该标题不符，指定可能不生效"))
    # 量高必须用**和渲染同一套样式**：EXTRA_CSS 里有竖排区、报花等规则，
    # 漏掉它会让这些块的实测高度偏小（图片按 0 算），装版后互相压字（2026-10-15 修）
    heights = measure(rest, css + "\n" + EXTRA_CSS)
    if not heights or len(heights) != len(rest):
        # 量高失败才退回估算：两栏正文每行约 52 字，行高 15.5px
        heights = [84 + (sum(len(x) for x in (b.get("body") or [])) / 52.0) * 15.5
                   if b["kind"] == "chapter" else
                   (44 + (len(b.get("text") or "") / 62.0) * 15.0 if b["kind"] == "mini" else 24.0)
                   for b in rest]
    print(f"  量高：{len(heights)} 块　合计 {int(sum(heights))}px")

    out = QD_OUT

    # ── 首版自然回流：实量首版溢出，超了就从后往前推块（p1_minis 尾 → 语录栏尾），
    #    推出的块插进装箱流的小章节段开头，落到后面的版。不改字号、不改全局容量。──
    p1_pushed = []

    def p1_shell(parts):
        body = "\n".join(parts).replace("{PAGES}", "—")
        return (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
                f'<title>首版试排</title><style>{css}\n{EXTRA_CSS}</style>'
                f'</head><body>' + body + '</body></html>')

    p1fit = out / "_p1fit.html"
    for _ in range(len(p1_minis) + len(p1_quotes) + 1):
        p1fit.write_text(p1_shell(build_p1()), encoding="utf-8")
        ovf = page_overflow(p1fit)
        if ovf is None:
            print("  ! 首版量不到溢出，按当前首版出（不推块）")
            break
        if ovf[0] <= 2:
            break
        if p1_minis:
            m = p1_minis.pop()
            p1_pushed.append({"kind": "mini", **m})
            print(f"  首版溢出 {int(ovf[0])}px → 推出小章节「{m['title']}」，随流排到后面的版")
            continue
        if p1_quotes:
            q = p1_quotes.pop()
            who = f'{q.get("who") or ""}　{q.get("when") or ""}'.strip("　")
            p1_pushed.append({"kind": "line", "text": q["text"], "who": who})
            print(f"  首版溢出 {int(ovf[0])}px → 推出语录「{q['text']}」，随流排到后面的版")
            continue
        print(f"  ! 首版仍溢出 {int(ovf[0])}px，已无可推块（报头/头条固定，需人工微调）")
        break
    p1fit.unlink(missing_ok=True)
    if p1_pushed:
        # 插在小章节段开头（紧跟最后一个大章节），保持这些块在后面的版里靠前出现
        first_small = next((i for i, b in enumerate(rest) if b["kind"] != "chapter"), len(rest))
        est = lambda b: (44 + (len(b.get("text") or "") / 62.0) * 15.0
                         if b["kind"] == "mini" else 24.0)
        rest = rest[:first_small] + p1_pushed + rest[first_small:]
        heights = (heights[:first_small] + [est(b) for b in p1_pushed]
                   + heights[first_small:])

    def pack(capacity):
        """装箱：先排大章节，再排小章节/一句话（顺延，不回填）。
        第 1 个续版要给「钉版底」的块预留高度，否则内容会压到页脚。"""
        # 钉在版底的块：第 2 版右栏底(p2_side_minis) + 第 2 版版底(p2_minis)
        pinned = 0.0
        for m in (c.get("p2_minis") or []):
            pinned += 44 + (len(m.get("text") or "") / 62.0) * 15.0     # 第 2 版通栏
        pinned_later = 0.0                                              # 第 3 版及以后钉的
        for k, v in c.items():
            if k.startswith("p") and k.endswith("_minis") and k not in ("p2_minis",):
                for m in (v or []):
                    pinned_later += 44 + (len(m.get("text") or "") / 62.0) * 15.0
        big = [(b, h) for b, h in zip(rest, heights) if b["kind"] == "chapter"]
        small = [(b, h) for b, h in zip(rest, heights) if b["kind"] != "chapter"]
        pg, cur, used = [], [], 0.0
        for b, h in big:
            cap = capacity - (pinned if not pg else 0)   # 只给第 2 版预留；后续版靠实测纠偏
            if used + h + 8 > cap and cur:
                pg.append(cur)
                cur, used = [], 0.0
            cur.append(b)
            used += h + 8
        if cur:
            pg.append(cur)
        # 各版已用量
        useds = []
        for p in pg:
            useds.append(sum(h + 8 for b, h in zip(rest, heights) if b in p))
        # 小章节不再回填空隙，一律顺序排在大章节之后（= 顺延到后面的版，豹饼干要求）
        cur, used = [], 0.0
        for b, h in small:
            if used + h + 8 > capacity and cur:
                pg.append(cur)
                cur, used = [], 0.0
            cur.append(b)
            used += h + 8
        if cur:
            pg.append(cur)
        return pg

    pages = pack(o.容量)
    if plan:
        # 保留位要插在「第 2 版之后」= 索引 1；被 defer 的章另起一版跟在其后
        deferred = [plan_blocks[x] for x in plan.get("defer", []) if x in plan_blocks]
        pages = pages[:1] + [None] + ([deferred] if deferred else []) + pages[1:]
    print(f"  装箱结果：{len(pages)} 个续版" + ("（含第 3 版手工版位）" if plan else ""))

    hp = out / f"{o.刊名}_第{o.期号}期.html"
    folio = (lambda i: f'<div class="folio">{esc(o.刊名)}　第 {o.期号} 期　第 {i} 版　'
                       f'{brand("页脚", o.刊名 + "　内部发行")}</div>')

    def build(pg_list):
        parts = build_p1()
        for i, pg in enumerate(pg_list, start=2):
            cls = "page has-pin" if (c.get(f"p{i}_minis") or []) else "page"
            parts.append(f'<div class="{cls}">')
            # 第 3 版：按 p3_plan 手工摆位（左半上/左半底/右半），空白一律不填
            if i == 3 and plan and pg is None:
                def one(title):
                    b = plan_blocks.get(title)
                    return block_html(b) if b else ''

                def kind_of(title):
                    return (plan_blocks.get(title) or {}).get("kind", "mini")

                RULE = '<div class="rule-thin" style="margin:6px 0"></div>'

                def seq(items):
                    """顺序输出若干块；相邻两块类型不同（大章节 ↔ 小章节）时插一条分隔线。
                    序列里写字符串 "rule" 就是**显式插一条分隔线**（主编 2026-10-15）。"""
                    out, prev = [], None
                    for x in items:
                        if x == "rule":
                            out.append(RULE)
                            prev = None
                            continue
                        k = kind_of(x)
                        if prev and prev != k:
                            out.append(RULE)
                        out.append(one(x))
                        prev = k
                    return out
                parts.append('<div class="halves">')
                lcls = "half halfcol" if (plan.get("left_mid") or plan.get("left_bottom")) else "half"
                parts.append(f'<div class="{lcls}">')
                L1 = plan.get("left", [])
                L2 = plan.get("left_mid", [])
                L3 = plan.get("left_bottom", [])
                parts += seq(L1)
                if L2:
                    if L1 and kind_of(L1[-1]) != kind_of(L2[0]):
                        parts.append(RULE)
                    parts.append('<div class="mid">')
                    parts += seq(L2)
                    parts.append('</div>')
                if L3:
                    last = (L2 or L1)
                    if last and kind_of(last[-1]) != kind_of(L3[0]):
                        parts.append(RULE)
                    parts.append('<div class="sink">')
                    parts += seq(L3)
                    parts.append('</div>')
                parts.append('</div>')
                useq = plan.get("right_seq") or []
                bottom_align = (plan.get("right_align") == "bottom")
                rcls = ("half halfcol" if bottom_align else
                        ("half halfcol spread" if useq else
                         ("half halfcol" if (plan.get("right_bottom") or plan.get("right_center"))
                          else "half")))
                if (not bottom_align and not useq and plan.get("right_center")
                        and plan.get("right_bottom")):
                    rcls += " spread"      # 顶/中/底三分，中段才真正居中
                _rstyle = ' style="justify-content:flex-end"' if bottom_align else ''
                parts.append(f'<div class="{rcls}"{_rstyle}>')
                # 右半顶部的「群友语录」：p3_plan.right_lines（只留名字、不带时间戳）
                _rl = plan.get("right_lines") or []
                if _rl:
                    parts.append('<div class="kicker" style="margin:2px 0 4px">群友语录</div>'
                                 '<div class="rule-thin"></div>')
                    for _ln in _rl:
                        _w = (f'　<span class="w">——{esc(_ln.get("who"))}</span>'
                              if _ln.get("who") else '')
                        parts.append(f'<div class="line">{esc(_ln.get("text"))}{_w}</div>')
                    parts.append('<div class="rule-thin" style="margin:6px 0 0"></div>')
                if useq:
                    parts += seq(useq)
                parts += [one(x) for x in ([] if useq else plan.get("right", []))]
                if plan.get("right_center") and not useq:
                    parts.append('<div class="mid">')
                    parts += [one(x) for x in plan["right_center"]]
                    parts.append('</div>')
                if plan.get("right_bottom") and not useq:
                    parts.append('<div class="sink">')
                    parts += [one(x) for x in plan["right_bottom"]]
                    parts.append('</div>')
                parts.append('</div>')
                parts.append('</div>')
                for m in (c.get("p3_minis") or []):
                    parts.append('<div class="pinbottom"><div class="rule-thick"></div>'
                                 '<div class="miniband">'
                                 f'<div class="mini"><div class="mini-t">{esc(m["title"])}</div>'
                                 f'<p>{esc(m["text"])}</p></div></div></div>')
                parts.append(folio(i) + '</div>')
                continue
            rest_blocks = list(pg) if pg else []
            vlead_pair = False
            # 第 2 版强制竖排（内容 JSON vlead_chapter 指定，主编 2026-10-15 要求）：
            # 左竖排题栏（栏名框 + 竖排主标题 + 竖排副题）+ 中两栏正文 + 右上竖排短刊
            # （vlead_mini 指定，取自 p2_side_minis），其余块（下一章节等）下移到
            # 竖排区之下按常规排。指定后回流阶段不自动降级（见文末回流循环）。
            # 第 1 版溢出的块会被推到本版最前面，指定的竖排章可能不在首位：
            # 先在本版头几块里把它找出来并提到最前（2026-10-15 修）
            if i == 2 and force_lead:
                for _bi, _b in enumerate(rest_blocks[:5]):
                    if (_b.get("kind") == "chapter" and _b.get("title") == force_lead
                            and _bi > 0):
                        rest_blocks.insert(0, rest_blocks.pop(_bi))
                        break
            if (i == 2 and force_lead and rest_blocks
                    and rest_blocks[0].get("kind") == "chapter"
                    and rest_blocks[0].get("title") == force_lead):
                lead = rest_blocks[0]
                below = rest_blocks[1:]
                vlead_pair = True
                vm = None
                side_rest = list(c.get("p2_side_minis") or [])
                if force_mini:
                    vm = next((m for m in side_rest if m.get("title") == force_mini), None)
                    if vm is not None:
                        side_rest = [m for m in side_rest if m is not vm]
                    else:
                        # 防内容 JSON 把这条短刊写进了 minis 装箱流：在第 2 版流里按标题找
                        for bi, b in enumerate(below):
                            if b.get("kind") == "mini" and b.get("title") == force_mini:
                                vm = below.pop(bi)
                                break
                        if vm is None:
                            print(f"  ! vlead_mini「{force_mini}」在 p2_side_minis 和第 2 版流里"
                                  f"都找不到，右上竖排短刊留空")
                parts.append('<div class="vlead v2">')
                dk = (f'<div class="vdeck">{esc(lead["deck"])}</div>'
                      if lead.get("deck") else '')
                parts.append(f'<div class="vcol"><div class="vstack">'
                             f'<div class="vtitle" style="{_vtitle_style(lead["title"])}">'
                             f'{esc(lead["title"])}</div>{dk}</div>'
                             f'<div class="vkicker">{esc(lead.get("kicker") or "")}</div></div>')
                parts.append('<div class="vmain">'
                             f'<div class="vbody">{paras(lead.get("body") or [])}</div>')
                # 报花落在中栏正文之下（照第 010 期第 2 版的样子）——须显式开启
                # `vlead_image_in_region: true`；默认不开（报花改由 p{N}_mid 的 pic 块排）
                im = c.get("vlead_image") or {}
                if c.get("vlead_image_in_region") and im.get("file"):
                    src = "file:///" + str(BASE / im["file"]).replace("\\", "/")
                    cap = (f'<div class="cap">{esc(im.get("caption"))}</div>'
                           if im.get("caption") else '')
                    parts.append(f'<div class="vpic small"><img src="{src}">{cap}</div>')
                parts.append('</div>')
                hm = bool(c.get("vlead_mini_horiz"))   # 主编 2026-10-15：天堂改「半横板」（右列横排字）
                if vm is not None:
                    inner = f'<div class="vmini-t">{esc(vm["title"])}</div><p>{esc(vm["text"])}</p>'
                    if hm:
                        # 右列：天堂之下接**侧栏短刊**（横板；主编 2026-10-15 改）
                        for _m in (c.get("p2_side_minis") or []):
                            if _m.get("title") == force_mini:
                                continue
                            inner += (f'<div class="mini" style="margin:7px 0 0">'
                                      f'<div class="mini-t">{esc(_m["title"])}</div>'
                                      f'<p>{esc(_m["text"])}</p></div>')
                        plines = c.get("p2_lines") or []
                        if plines:
                            rows = []
                            for ln in plines:
                                if ln.get("kind") == "rule":
                                    continue
                                who = (ln.get("who") or "").split("　")[0].strip()
                                w = f'<span class="w">——{esc(who)}</span>' if who else ''
                                rows.append(f'<div class="qline">{esc(ln.get("text"))}{w}</div>')
                            inner += (f'<div class="qband"><div class="qband-t">群友语录</div>'
                                      + "".join(rows) + '</div>')
                    parts.append(f'<div class="vmini{" vmini-h" if hm else ""}">{inner}</div>')
                parts.append('</div><div class="rule-thick"></div>')
                for q in (c.get("p2_quote") or []):
                    parts.append('<div class="line" style="margin:6px 0 8px">'
                                 f'{esc(q["text"])}　'
                                 f'<span class="w">——{esc(q.get("who"))}</span></div>'
                                 '<div class="rule-double"></div>')
                for m in ([] if hm else side_rest):   # 横板时它们已排进右列，这里不再补排（防重复）
                    parts.append(f'<div class="mini"><div class="mini-t">{esc(m["title"])}</div>'
                                 f'<p>{esc(m["text"])}</p></div>')
                # 竖排区之下的章节**留在流里**（不在这里渲染，也不清空 rest_blocks）：
                # 这样第 2 版装不下时，回流循环能把它们推到后面的版，而不是整版压页脚。
                rest_blocks = list(below)
            # 第 2 版首块走「竖排大标题 + 三栏正文 + 右侧横标题短文」（豹饼干指定版式）。
            # 回流阶段若整版只剩这一对仍溢出，会把 vlead_mode 关掉改常规排版（见文末回流循环）
            if (i == 2 and vlead_mode and len(rest_blocks) >= 2
                    and rest_blocks[0]["kind"] == "chapter" and rest_blocks[1]["kind"] == "chapter"):
                lead, side = rest_blocks[0], rest_blocks[1]
                vlead_pair = True
                parts.append('<div class="vlead">')
                dk = (f'<div class="vdeck">{esc(lead["deck"])}</div>'
                      if lead.get("deck") else '')
                parts.append(f'<div class="vcol"><div class="vstack">'
                             f'<div class="vtitle">{esc(lead["title"])}</div>{dk}</div>'
                             f'<div class="vkicker">{esc(lead.get("kicker") or "")}</div></div>')
                parts.append('<div class="vmain">')
                parts.append(f'<div class="vbody">{paras(lead.get("body") or [])}</div>')
                im = c.get("vlead_image") or {}
                if im.get("file"):
                    src = "file:///" + str(BASE / im["file"]).replace("\\", "/")
                    cap = (f'<div class="cap">{esc(im.get("caption"))}</div>'
                           if im.get("caption") else '')
                    parts.append(f'<div class="vpic"><img src="{src}">{cap}</div>')
                parts.append('</div>')
                parts.append('<div class="vside">')
                parts.append(f'<div class="sub-title">{esc(side["title"])}</div>')
                if side.get("deck"):
                    parts.append(f'<div class="sub-deck">{esc(side["deck"])}</div>')
                parts.append(f'<div class="vbody2">{paras(side.get("body") or [])}</div>')
                for m in (c.get("p2_side_minis") or []):
                    # 不是完整小章节：不加红杠，只用细分隔线 + 比正文大一号的标题
                    # 底色与「感情课堂」等小章节一致（#fbf9f6），但不加红杠、不做成完整小章节
                    parts.append('<div class="rule-thin" style="margin:6px 0 5px"></div>'
                                 '<div style="background:#fbf9f6;padding:5px 7px">'
                                 f'<div style="font-family:\'SimHei\',\'黑体\',sans-serif;'
                                 f'font-size:11.6pt;font-weight:400;margin-bottom:3px">'
                                 f'{esc(m["title"])}</div>'
                                 f'<div style="font-size:10.6pt;line-height:1.52">'
                                 f'{esc(m["text"])}</div></div>')
                parts.append('</div>')
                parts.append('</div><div class="rule-thick"></div>')
                for q in (c.get("p2_quote") or []):
                    parts.append('<div class="line" style="margin:6px 0 8px">'
                                 f'{esc(q["text"])}　'
                                 f'<span class="w">——{esc(q.get("who"))}</span></div>'
                                 '<div class="rule-double"></div>')
                rest_blocks = list(pg[2:])
            # 第 3 版：左右半版（左半一路、右半一路），豹饼干指定
            if i == 3 and len(rest_blocks) >= 2:
                cut = (len(rest_blocks) + 1) // 2
                parts.append('<div class="halves">')
                for grp in (rest_blocks[:cut], rest_blocks[cut:]):
                    parts.append('<div class="half">')
                    parts += [block_html(b) for b in grp]
                    parts.append('</div>')
                parts.append('</div>')
            else:
                parts += [block_html(b) for b in rest_blocks]
            # 第 2 版未走竖排版式（装不下被回流关掉，或块型不配）时：
            # p2_side_minis / p2_quote 仍属第 2 版，按常规块补排，内容一个不丢
            if i == 2 and not vlead_pair:
                for m in (c.get("p2_side_minis") or []):
                    parts.append(f'<div class="mini"><div class="mini-t">{esc(m["title"])}</div>'
                                 f'<p>{esc(m["text"])}</p></div>')
                for q in (c.get("p2_quote") or []):
                    parts.append('<div class="line" style="margin:6px 0 8px">'
                                 f'{esc(q["text"])}　'
                                 f'<span class="w">——{esc(q.get("who"))}</span></div>'
                                 '<div class="rule-double"></div>')
            # 指定版底：第 N 版最下面钉若干条（key = p{N}_minis，豹饼干要求）
            # 版中补充块（p{i}_mid）：排在本版章节之后、钉版底之前
            mid_rows = c.get(f"p{i}_mid") or []
            if mid_rows:
                prev_kind = None
                last_rule = False          # 刚出过分隔线就不再出（防两三连）
                for m in mid_rows:
                    mk = m.get("kind", "mini")
                    if mk == "rule":
                        if not last_rule:
                            parts.append('<div class="rule-thin" style="margin:6px 0"></div>')
                            last_rule = True
                        prev_kind = mk
                        continue
                    if prev_kind and prev_kind != mk and not last_rule:
                        parts.append('<div class="rule-thin" style="margin:6px 0"></div>')
                    last_rule = False
                    if mk == "head":
                        parts.append(f'<div class="kicker" style="margin:8px 0 4px">'
                                     f'{esc(m.get("title"))}</div><div class="rule-thin"></div>')
                    elif mk == "line":
                        w = (f'　<span class="w">——{esc(m.get("who"))}</span>'
                             if m.get("who") else '')
                        parts.append(f'<div class="line">{esc(m.get("text"))}{w}</div>')
                    elif mk == "qa":
                        # 两行制：提问人：问题 ／ 答话人：答案（主编 2026-10-15）
                        parts.append(
                            f'<div class="qabox"><div class="qa-h">'
                            f'{esc(m.get("title") or "答群友问")}</div>'
                            f'<div class="qa-q">{esc(m.get("asker"))}：'
                            f'{esc(m.get("question"))}</div>'
                            f'<div class="qa-a">{esc(m.get("answerer") or brand("默认答主", "编辑"))}：'
                            f'{esc(m.get("answer"))}</div></div>')
                    elif mk == "statbox":
                        _r = "".join(
                            f'<div class="srow"><span>{esc(a)}</span><b>{esc(b)}</b></div>'
                            for a, b in (m.get("rows") or []))
                        _n = (f'<div class="snote">{esc(m.get("note"))}</div>'
                              if m.get("note") else '')
                        parts.append(f'<div class="statbox"><h4>{esc(m.get("title"))}</h4>'
                                     f'{_r}{_n}</div>')
                    elif mk == "pic":
                        fp = m.get("file") or ""
                        if fp:
                            src = "file:///" + str(BASE / fp).replace("\\", "/")
                            cap = (f'<div class="cap">{esc(m.get("caption"))}</div>'
                                   if m.get("caption") else '')
                            parts.append(f'<div class="picband"><img src="{src}">{cap}</div>')
                    else:
                        parts.append(f'<div class="mini"><div class="mini-t">'
                                     f'{esc(m.get("title"))}</div>'
                                     f'<p>{esc(m.get("text"))}</p></div>')
                    prev_kind = mk
            pinned_rows = c.get(f"p{i}_minis") or []
            if pinned_rows:
                parts.append('<div class="pinbottom"><div class="rule-thick"></div>'
                             '<div class="miniband">')
                for m in pinned_rows:
                    k = m.get("kind", "mini")
                    if k == "rule":
                        parts.append('<div class="rule-thin" style="margin:6px 0"></div>')
                    elif k == "head":
                        parts.append(f'<div class="kicker" style="margin:8px 0 4px">{esc(m.get("title"))}</div>'
                                     '<div class="rule-thin"></div>')
                    elif k == "line":
                        w = (f'　<span class="w">——{esc(m.get("who"))}</span>'
                             if m.get("who") else '')
                        parts.append(f'<div class="line">{esc(m.get("text"))}{w}</div>')
                    else:
                        parts.append(f'<div class="mini"><div class="mini-t">{esc(m.get("title"))}</div>'
                                     f'<p>{esc(m.get("text"))}</p></div>')
                parts.append('</div></div>')
            parts.append(folio(i) + '</div>')
        body = "\n".join(parts).replace("{PAGES}", str(len(pg_list) + 1))
        # 竖排标题按豹饼干要求用固定字号（缩一号、不加粗），不再自动等高
        return (f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
                f'<title>{esc(o.刊名)} · 第{o.期号}期</title><style>{css}\n{EXTRA_CSS}</style>'
                f'</head><body>' + body + '</body></html>')

    # ── 逐版回流（取代旧的"全局降容量"纠偏）：渲染 → 量各版溢出 → 哪版超了就把
    #    该版最后一块推到下一版（手工版位 p3_plan 不让位，推到它后面；没有下一版
    #    就新增一版）→ 再量，直到全部装下。全程不改 --容量 基准值、不改字号。──
    vlead_mode = True
    for rnd in range(1, 31):
        hp.write_text(build(pages), encoding="utf-8")
        ovf = page_overflow(hp)
        if ovf is None:
            print("  ! 量不到溢出，按当前版式出")
            break
        hot = [k for k, v in enumerate(ovf) if v > 2]
        if not hot:
            print(f"  回流通过（共 {rnd-1} 轮推移）：各版溢出 {[int(x) for x in ovf]}")
            break
        moved = False
        for k in hot:
            no = k + 1                                    # 物理版号（ovf[0]=第 1 版）
            if k == 0:
                print(f"  ! 首版仍溢出 {int(ovf[k])}px（首版已无可推块，需人工微调）")
                continue
            idx = k - 1                                   # pages 下标
            if idx >= len(pages) or pages[idx] is None:
                print(f"  ! 第 {no} 版（p3_plan 手工版位）溢出 {int(ovf[k])}px，"
                      f"手工版位不回流，请调 p3_plan")
                continue
            if not pages[idx]:
                print(f"  ! 第 {no} 版没有可推的流式块（只剩钉版底/版中块）仍溢出 {int(ovf[k])}px")
                continue
            # 强制竖排（vlead_chapter）：竖排区本身不降级；但竖排区**之下**的流式块
            # （下一章节等，已留在 pages 里）仍按通用规则推走 —— 否则整版压页脚。
            if (idx == 0 and force_lead and not (pages[idx] or [])):
                print(f"  ! 第 {no} 版强制竖排仍溢出 {int(ovf[k])}px（vlead_chapter 指定、"
                      f"竖排区之下已无可推块），请人工调第 2 版内容或版位字段")
                continue
            blocks = pages[idx]
            # 第 2 版整版只剩竖排那一对章节仍溢出 → 放弃竖排版式改常规排版，再量一次
            # （vlead_chapter 强制指定时不走这条自动降级）
            if (idx == 0 and vlead_mode and not force_lead and len(blocks) == 2
                    and blocks[0]["kind"] == "chapter" and blocks[1]["kind"] == "chapter"):
                vlead_mode = False
                print(f"  第 2 版只剩竖排一对章节仍超 {int(ovf[k])}px → 放弃竖排版式，"
                      f"改常规章节排版重试（p2_side_minis/p2_quote 改平排补上）")
                moved = True
                continue
            b = blocks.pop()
            name = (b.get("title") or b.get("text") or b["kind"])[:14]
            nxt = idx + 1
            while nxt < len(pages) and pages[nxt] is None:
                nxt += 1                                  # 越过手工版位，推到其后
            if nxt < len(pages):
                pages[nxt].insert(0, b)
                print(f"  第 {no} 版推出 1 块「{name}」→ 第 {nxt + 2} 版")
            else:
                pages.append([b])
                print(f"  第 {no} 版推出 1 块「{name}」→ 新增第 {len(pages) + 1} 版")
            moved = True
        if not moved:
            print("  ! 溢出的版已无可推块，回流停止（请按上面各行警告处理）")
            break
    else:
        print("  ! 回流 30 轮仍未收敛，按当前版式出（请检查内容是否异常超长）")

    # ── 回填（rebalance）：推移只会往后推，会把版面越推越空（第 2 版空 308px、
    #    末版整页空 812px 都这么来的）。收敛后从后往前，把「后一版的首块」拉回
    #    前面还有余量的那一版，装得下就拉走；装不下就撤回。手工版位(占位 None)跳过。──
    for _ in range(30):
        hp.write_text(build(pages), encoding="utf-8")
        ovf = page_overflow(hp)
        if ovf is None:
            break
        pulled = False
        for k in range(len(pages) - 1, 0, -1):
            if pages[k] is None or not pages[k]:
                continue
            prev = k - 1
            while prev >= 0 and pages[prev] is None:
                prev -= 1
            if prev < 0:
                continue
            blk = pages[k][0]
            pages[prev].append(blk)
            pages[k].pop(0)
            hp.write_text(build(pages), encoding="utf-8")
            ovf2 = page_overflow(hp)
            if ovf2 is not None and max(ovf2) <= 2:
                while len(pages) > 1 and not pages[-1] and pages[-1] is not None:
                    pages.pop()
                name = (blk.get("title") or blk.get("text") or blk["kind"])[:14]
                print(f"  回填：第 {k + 2} 版首块「{name}」→ 第 {prev + 2} 版")
                pulled = True
                break
            pages[k].insert(0, blk)
            pages[prev].pop()
        if not pulled:
            break

    # p{N}_minis / p{N}_mid 的 N 超出实际版数时补空版兜底，别让钉版底内容（含报尾）落空
    need = 1
    for key in c:
        m = re.match(r"^p(\d+)_(minis|mid)$", key)
        if m and c.get(key):
            need = max(need, int(m.group(1)))
    while len(pages) + 1 < need:
        pages.append([])
        print(f"  新增第 {len(pages) + 1} 版：承载 p{len(pages) + 1}_minis/_mid 版位字段")

    hp.write_text(build(pages), encoding="utf-8")
    stats = page_stats(hp)
    if stats:
        gaps = [int(s[1]) for s in stats]
        print(f"  回流结果：{len(pages) + 1} 版　各版溢出 {[int(s[0]) for s in stats]}"
              f"　距页脚 {gaps}")
        if any(g < 6 for g in gaps):
            print("  ! 有版距页脚不足 6px，请看上表")
        for gi, g in enumerate(gaps):
            if g > 300:
                print(f"  ! 第 {gi + 1} 版底部空白 {g}px（>300px，版面偏空，请过目）")
    print(f"  HTML：{hp.name}（{len(pages)+1} 版）")

    tmp = QD_TMP / f"{o.刊名}_{o.期号}.pdf"
    tmp.unlink(missing_ok=True)
    kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--run-all-compositor-stages-before-draw", "--virtual-time-budget=12000",
                    f"--user-data-dir={QD_TMP/'ep_auto'}",
                    f"--print-to-pdf={tmp}", "file:///" + str(hp).replace("\\", "/")],
                   capture_output=True, text=True, timeout=300, **kw)
    QD_OUT.mkdir(parents=True, exist_ok=True)
    pdf = QD_OUT / f"{o.刊名}_第{o.期号}期.pdf"   # dsh-qqdaily：成品进配置的输出目录
    pdf.write_bytes(tmp.read_bytes())
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf))
    print(f"  PDF：{pdf.name}  {pdf.stat().st_size//1024}KB　{len(doc)} 版")
    for i in range(len(doc)):
        img = doc[i].render(scale=1.5).to_pil()
        f = out / f"日报{o.期号}_第{i+1}版.png"
        img.save(f)
    doc.close()

    # --量块：排版、出 PDF、出 PNG 都完成后才跑（只打印，不改任何版式参数）
    if o.量块 is not None:
        print(f"  ── 量块：第 {o.量块} 版（量法同 程序\\量版面块.py，只打印不改版式）──")
        rows = measure_blocks(hp, o.量块)
        if not rows:
            print("  ! 量不到版面数据（重跑一次，或改用外部 程序\\量版面块.py）")
        else:
            npages = next((h for n, h in rows if n == "__pages"), 0)
            if o.量块 > npages:
                print(f"  没有第 {o.量块} 版（本期共 {npages} 版）")
            else:
                tot = 0
                for name, h in rows:
                    if name == "__overflow":
                        print(f"  溢出 = {h:+.0f}px")
                    elif name != "__pages":
                        tot += h
                        print(f"    {h:5.0f}px  {name}")
                print(f"  内容合计 {tot:.0f}px（版心 279mm≈1054px）")


if __name__ == "__main__":
    sys.exit(main())
