# -*- coding: utf-8 -*-
r"""把特刊内容 JSON 导出成可直接粘贴的纯文本（发群/存档用）。支持 head/mini/line/rule/credit。

用法： python 导出纯文本.py <期号> [日期] [时段]
       期号必填；日期/时段不给就整行省略。
"""
import json
import pathlib

# ── dsh-qqdaily 注入：路径与浏览器由环境变量决定，默认值保持向后兼容 ──
import os as _os
def _qd(name, default):
    return _os.environ.get(name) or default
QD_BASE = pathlib.Path(_qd("QQDAILY_BASE", r"C:\\Users\\Administrator\\Desktop\\QQ日报"))
QD_OUT = pathlib.Path(_qd("QQDAILY_OUT", str(QD_BASE / "5-报纸成品")))
QD_TMP = pathlib.Path(_qd("QQDAILY_TMP", r"D:\ai\out"))
QD_EDGE = _qd("QQDAILY_EDGE", "")
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = QD_BASE
if len(sys.argv) > 1:
    NO = sys.argv[1]
else:
    _avail = sorted({re.search(r"第(\d+)期", p.name).group(1)
                     for p in (BASE / "4-出报素材和日志").glob("特刊内容_第*期.json")})
    sys.exit("用法：python 导出纯文本.py <期号> [日期] [时段]（如 python 导出纯文本.py 011）\n"
             "可用期号（按 特刊内容_第*.json）：" + "、".join(_avail))
DATE = sys.argv[2] if len(sys.argv) > 2 else ""
SPAN = sys.argv[3] if len(sys.argv) > 3 else ""

c = json.loads((BASE / "4-出报素材和日志" / f"特刊内容_第{NO}期.json").read_text(encoding="utf-8"))
L = []
hr = "─" * 34


def emit(block):
    """输出一个块（小章节/一句话/分隔/标题）。"""
    k = block.get("kind", "mini")
    if k == "rule":
        L.append("· · · · · · · · · ·")
    elif k == "head":
        L.append(f"── {block.get('title','')} ──")
    elif k == "line":
        who = f"　——{block['who']}" if block.get("who") else ""
        if block.get("credit"):
            L.append(f"{block['text']}{who}")
        else:
            L.append(f"「{block['text']}」{who}")
    else:
        L.extend([f"◇ {block.get('title','')}", block.get("text", "")])


hl = c["headline"]
ch = c["chapters"]
_meta = "　".join(x for x in (DATE, f"统计时段 {SPAN}" if SPAN else "") if x)
L += [f"四号食堂日报　第 {NO} 期"] + ([_meta] if _meta else []) + ["群友内部发行（非卖品）"]
moe = c.get("masthead") or {}
if moe:
    L.append(f"本报立场　{moe.get('stance','')} {moe.get('face','')}　·　{moe.get('tip','')}")
L += [hr, ""]
L += [f"【要闻 · {hl.get('kicker','')}】{hl['title']}", hl.get("subtitle", ""), hr]
L += hl["body"] + ["", hr, ""]
L += [f"【{ch[0].get('kicker','')}】{ch[0]['title']}", ch[0].get("deck", ""), hr]
L += ch[0]["body"] + [""]
if c.get("quotes"):
    L += ["【群友语录】"]
    for q in c["quotes"]:
        L.append(f"「{q['text']}」　——{q.get('who','')} {q.get('when','')}")
    L += ["", hr, ""]
for m in (c.get("p1_minis") or []):
    emit(m)
L.append("")
for x in ch[1:]:
    L += [hr, f"【{x.get('kicker','')}】{x['title']}", x.get("deck", ""), hr]
    L += x["body"] + [""]

# 第 3 版手工版位的块（按 p3_plan 顺序）
plan = c.get("p3_plan") or {}
order = (plan.get("left", []) + plan.get("left_mid", []) + plan.get("left_bottom", [])
         + plan.get("right_seq", []))
index = {m.get("title"): m for m in c.get("minis", [])}
for x in ch:
    index[x.get("title")] = x
rest = [t for t in order if t in index]
L += [hr, "【第 3 版 · 左右对开】", hr]
for t in rest:
    b = index[t]
    if "body" in b:      # 大章节
        L += [f"【{b.get('kicker','')}】{b['title']}", b.get("deck", ""), ""] + b["body"] + [""]
    else:
        emit(b)

# 留在源池里、没被手工版位抽走的短刊 = 第 5 版短刊
leftover = [m for m in c.get("minis", []) if m.get("title") not in order]
if leftover:
    L += [hr, "【短刊】", hr]
    for m in leftover:
        emit(m)
for key, name in (("p2_minis", "第 2 版版底"), ("p2_side_minis", "第 2 版侧栏"),
                  ("p4_mid", "第 4 版中部"), ("p4_minis", "第 4 版版底")):
    if c.get(key):
        L += [hr, f"【{name}】", ""]
        for m in c[key]:
            emit(m)
            L.append("")
if c.get("p5_minis"):
    L += [hr, f"【第 5 版版底】", ""]
    for m in c["p5_minis"]:
        emit(m)
L.append("")
out = QD_OUT / f"{_qd('QQDAILY_PAPER', '四号食堂日报')}_第{NO}期.txt"
out.write_text("\n".join(L), encoding="utf-8")
print(f"已写出 {out}（{len(L)} 行，{len(''.join(L))} 字符）")
