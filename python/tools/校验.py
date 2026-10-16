# -*- coding: utf-8 -*-
r"""通用校验：引语逐字（正文「」＋语录栏＋一句话块）／禁用词／字数／结构。

用法： python 校验.py 011
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
NO = sys.argv[1] if len(sys.argv) > 1 else "011"
SRC = pathlib.Path(_qd("QQDAILY_CONTENT",
        str(BASE / "4-出报素材和日志" / f"特刊内容_第{NO}期.json")))
def _corpus_files():
    """语料来源：QQDAILY_CORPUS（; 分隔的路径或通配）→ 否则 <BASE>/1-聊天记录/messages_*.jsonl。"""
    spec = _qd("QQDAILY_CORPUS", "")
    if spec:
        out = []
        for part in str(spec).split(";"):
            part = part.strip()
            if not part:
                continue
            p = pathlib.Path(part)
            if any(ch in part for ch in "*?["):
                out += sorted(p.parent.glob(p.name))
            elif p.is_file():
                out.append(p)
        return out
    return sorted((BASE / "1-聊天记录").glob("messages_*.jsonl"))


CORPUS_FILES = _corpus_files()
CORPUS = CORPUS_FILES[0] if CORPUS_FILES else BASE
BAN = pathlib.Path(_qd("QQDAILY_BAN", str(BASE / "4-出报素材和日志" / "禁用词.txt")))

raw = SRC.read_text(encoding="utf-8")
c = json.loads(raw)

lines = []
for f in CORPUS_FILES:
    if not f.is_file():
        continue
    for line in f.open("r", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            lines.append(json.loads(line).get("content") or "")
        except Exception:
            pass
blob = "\n".join(lines)
print(f"语料：{len(CORPUS_FILES)} 个文件，{len(lines)} 条消息" +
      ("　（可用 QQDAILY_CORPUS 指定，或用 check --语料 <路径>）" if not _qd("QQDAILY_CORPUS", "") else ""))
if not lines:
    print("！语料为空：无法逐字核对引语（用 QQDAILY_CORPUS 指定语料，或 check --语料 <路径>）")

# 1) 正文「」引语
quotes = re.findall(r"「([^」]{1,400})」", raw)
# 1b) 语录栏 + 一句话块（一句话在版面上不带「」，最易漏检）
extra = [("语录栏", q.get("text", "")) for q in (c.get("quotes") or [])]
for v in c.values():
    if isinstance(v, list):
        for m in v:
            if (isinstance(m, dict) and m.get("kind") == "line"
                    and m.get("text") and not m.get("credit")):
                extra.append(("一句话", m["text"]))

bad = [q for q in quotes if q not in blob]
bad2 = [(t, s) for t, s in extra if s not in blob]
print(f"正文引语（「」）{len(quotes)} 条　未命中 {len(bad)}")
for q in bad:
    print(f"  ✗ 「{q}」")
print(f"语录栏/一句话 {len(extra)} 条　未命中 {len(bad2)}")
for t, s in bad2:
    print(f"  ✗ [{t}] {s}")

# 2) 禁用词
words = [l.strip() for l in BAN.read_text(encoding="utf-8").splitlines()
         if l.strip() and not l.strip().startswith("#")]
hit = [w for w in words if w in raw]
print(f"\n禁用词命中 {len(hit)}：{hit if hit else '——'}")
for w in hit:
    for ln, text in enumerate(raw.splitlines(), 1):
        if w in text:
            print(f"   第{ln}行: {text.strip()[:90]}")

# 3) 字数与结构
han = lambda s: len(re.findall(r"[\u4e00-\u9fff]", s or ""))
main = sum(han(p) for p in c["headline"]["body"])
for ch in c["chapters"]:
    main += han(ch.get("title", "")) + han(ch.get("deck", "")) + han(ch.get("kicker", ""))
    main += sum(han(p) for p in ch.get("body", []))
    main += sum(han(x) for x in (ch.get("credit") or [])) + han(ch.get("sign", ""))
def mini_slots(doc):
    """所有短刊版位：minis + 任意 p{N}_minis / p{N}_mid（含 p1/p2/p3/p4/p5/p6…）。"""
    keys = ["minis"]
    keys += [k for k in doc
             if re.fullmatch(r"p\d+_(minis|mid)", k)]
    out = []
    for k in keys:
        for m in (doc.get(k) or []):
            if isinstance(m, dict) and m.get("kind", "mini") == "mini":
                out.append(m)
    return out


MINIS = mini_slots(c)
mini = 0
for k in ("minis", "oneliners", "p1_minis", "p2_minis", "p2_side_minis", "p3_minis",
          "p4_mid", "p4_minis", "p5_minis"):
    for m in (c.get(k) or []):
        mini += han(m.get("title", "")) + han(m.get("text", ""))
mini += sum(han(q.get("text", "")) for q in (c.get("quotes") or [])) + han(c.get("notice", ""))
print(f"\n正文汉字 {main}　小章节/语录汉字 {mini}　合计 {main + mini}")
print(f"大章节 {len(c['chapters'])}（含头条共 {len(c['chapters']) + 1}）"
      f"　小章节 {len(MINIS)}"
      f"　语录 {len(c.get('quotes') or [])}")
