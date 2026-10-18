#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""qqdaily 的编辑部流水线（draft / assemble / publish）。

设计原则：
- **素材由代码机械生成**（逐字复制窗口消息，模型不参与）——稿件的全部事实来源天生逐字；
- **写稿交给宿主里的 agent**：插件只产出「素材 + 骨架 + 任务单」，不自己调模型；
- **拼版是确定性的**：按模板声明的槽位把 稿/*.json 填进内容 JSON，同样输入必得同样输出；
- **门禁**：check 不过就不许 send。

工作目录（默认 <tmp>/工作_<label>/）：
  窗口.jsonl       本窗口消息（机器可读）
  素材/*.md        各栏目素材 digest（逐字）
  统计.json        条数/人数/榜/按天按小时
  骨架.json        带全部槽位的内容骨架（空值），agent 只往里填稿
  任务单.md        各栏目的写作任务单（含硬规矩），可直接派给 agent
  稿/*.json        agent 产出（栏名/标题/副题/正文；短刊另存 短刊.json）
  内容.json        assemble 的确定性产物
  状态.json        publish 的状态机快照
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 默认栏目（模板没声明「栏目」时用这套；关键词是粗聚类，只为切素材，不追求精确）
DEFAULT_COLUMNS = {
    "饮食": ["吃", "饭", "外卖", "酒", "奶茶", "火锅", "菜", "饿", "早饭", "午饭", "晚饭", "烧烤", "零食"],
    "生活": ["买", "快递", "打车", "地铁", "通勤", "医院", "体检", "装修", "天气", "冷", "热", "睡", "租房"],
    "职场": ["加班", "上班", "下班", "公司", "领导", "老板", "工位", "打卡", "调休", "工资", "请假", "会议"],
    "玩乐": ["游戏", "打野", "排位", "开黑", "追剧", "电影", "音乐", "球", "跑步", "健身"],
    "人际": ["生日", "相亲", "随礼", "红包", "请客", "送礼", "分手", "吵架", "和好"],
}

# 槽位分配计划：短刊按顺序进这些版位；语录按顺序进这些位置
MINI_PLAN = [("p2_side_minis", 2), ("p1_minis", 3), ("p2_minis", 2),
             ("p4_mid", 2), ("p5_mid", 2), ("p3_plan", 3), ("minis", 2)]
LINE_PLAN = [("quotes", 4), ("p4_minis", 4), ("p5_mid", 4), ("p3_right", 2)]

TAIL_PUNCT = "。！？，、；：…~～!?,;:"


# ── 读窗口 ──────────────────────────────────────────────────────────
def read_window(path: pathlib.Path) -> list[dict]:
    rows = []
    for line in path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if not r.get("time"):
            continue
        rows.append({"time": str(r["time"]), "sender": str(r.get("sender") or "?"),
                     "content": str(r.get("content") or "")})
    return rows


def stats_of(rows: list[dict]) -> dict:
    cnt = Counter(r["sender"] for r in rows)
    return {
        "total": len(rows),
        "people": len(cnt),
        "per": round(len(rows) / max(1, len(cnt)), 1),
        "top": cnt.most_common(6),
        "byday": Counter(r["time"][:10] for r in rows).most_common(),
        "busiest_hour": (Counter(r["time"][11:13] for r in rows).most_common(1) or [("0", 0)])[0],
        "from": rows[0]["time"] if rows else "",
        "to": rows[-1]["time"] if rows else "",
    }


# ── 栏目聚类 ────────────────────────────────────────────────────────
def columns_of(cfg: dict, template_dir: pathlib.Path) -> dict:
    """栏目的定义优先取 <模板>/模板.json 的「栏目」段，缺省用内置。"""
    cols = None
    try:
        spec = json.loads((template_dir / "模板.json").read_text(encoding="utf-8"))
        cols = spec.get("栏目")
    except Exception:
        cols = None
    if not cols:
        cols = DEFAULT_COLUMNS
    return {str(k): [str(w) for w in v] for k, v in cols.items()}


def cluster(rows: list[dict], columns: dict) -> dict:
    """按关键词把消息切进栏目；一条消息可进多个栏目（素材宁可重叠，写稿再取舍）。"""
    out = {c: [] for c in columns}
    for r in rows:
        text = r["content"]
        for c, kws in columns.items():
            if any(k in text for k in kws):
                out[c].append(r)
    return out


def people_of(rows: list[dict], columns: dict) -> dict:
    return {c: len({r["sender"] for r in rows if any(k in r["content"] for k in kws)})
            for c, kws in columns.items()}


# ── 素材 digest（逐字）──────────────────────────────────────────────
def write_digests(work: pathlib.Path, rows: list[dict], columns: dict) -> dict:
    d = work / "素材"
    d.mkdir(parents=True, exist_ok=True)
    files = {}
    for c in columns:
        hits = [r for r in rows if any(k in r["content"] for k in columns[c])]
        p = d / f"{c}.md"
        p.write_text("\n".join(f"[{r['time'][5:16]}] {r['sender']}: {r['content']}" for r in hits),
                     encoding="utf-8")
        files[c] = {"path": str(p), "rows": len(hits)}
    return files


# ── 骨架（槽位从模板来）────────────────────────────────────────────
def skeleton(template_dir: pathlib.Path) -> dict:
    """产出一份带全部槽位的内容骨架：agent 只往里填，不用背槽位名。"""
    return {
        "headline": {"kicker": "要闻", "title": "", "subtitle": "——", "body": []},
        "chapters": [],
        "minis": [],
        "quotes": [],
        "notice": "本报内容全部来自群内公开聊天，仅记原话与时间，不作评价。",
        "p1_minis": [],
        "p2_minis": [],
        "p2_side_minis": [],
        "p2_mid": [],
        "p4_minis": [],
        "p4_mid": [],
        "p5_mid": [],
        "p3_plan": {"left": [], "left_mid": [], "left_bottom": [], "right_seq": [],
                    "right_lines": [], "right_align": "bottom"},
        "vlead_chapter": "",
        "vlead_mini": "",
        "vlead_mini_horiz": True,
        "masthead": {"stance": "头条谁聊得凶谁上", "face": "🐋", "tip": "", "editor": "", "editor_note": ""},
        "_说明": "把 稿/*.json 交给 assemble 自动填充；手工改也行，改完直接 typeset。",
    }


TASK_TPL = """# 第 {label} 期 · 写作任务单

窗口：{frm} → {to}，共 {total} 条 / {people} 人。
素材在 `素材/`（每行 = [时间] 发言人: 原话，**逐字**，未做任何改写）。

## 硬规矩（违反即作废）

1. **只用素材里的内容**：一个人名、一个时间、一句对话都不许编；
2. **引用原话必须逐字**（照抄标点与错别字），前后加「」；引号里一个字都不能改；
   非原话不许加引号；
3. 不许出现采集过程、统计数字、方法论、编者按；
4. 报刊体：栏名两个字；标题 ≤14 个汉字（不带日期与阿拉伯数字）；副题 ≤22 字、以「——」开头；
   正文 **300～450 个汉字**；倒金字塔——导语先写最抓人的事实或冲突；
5. 时间写法：{date_example}；发言人用群昵称；不抄 [回复]/[图片]/@数字 这类噪声。

## 各栏目

{columns}

## 产出

每个栏目写一个 `稿/<栏目>.json`：

```json
{{"栏名": "<栏目>", "标题": "…", "副题": "——…", "正文": "…（引号用「」，段落之间空一行）"}}
```

短刊与一句话另存 `稿/短刊.json`：

```json
{{"短刊": [{{"标题": "≤10 字", "正文": "40～90 字"}}],
 "一句话": [{{"文本": "≤22 字", "作者": "群昵称", "时间": "MM-DD HH:MM"}}]}}
```

写完跑：`python python/qqdaily.py publish --label {label} --resume`
"""


def write_task(work: pathlib.Path, label: str, stats: dict, columns: dict,
               digests: dict, date_example: str) -> pathlib.Path:
    cols = "\n".join(
        f"- **{c}**：素材 {digests[c]['rows']} 条 → `素材/{c}.md`"
        for c in columns
    )
    p = work / "任务单.md"
    p.write_text(TASK_TPL.format(
        label=label, frm=stats["from"], to=stats["to"], total=stats["total"],
        people=stats["people"], columns=cols, date_example=date_example,
    ), encoding="utf-8")
    return p


# ── 拼版（确定性）──────────────────────────────────────────────────
def _load_drafts(work: pathlib.Path, columns: dict) -> tuple[list[dict], dict]:
    d = work / "稿"
    chaps = []
    for c in columns:
        f = d / f"{c}.json"
        if not f.exists():
            continue
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ! 稿 {c} 解析失败：{e}")
            continue
        body = raw.get("正文") or raw.get("body") or ""
        if isinstance(body, str):
            body = [p for p in body.split("\n\n") if p.strip()]
        chaps.append({"col": c,
                      "kicker": raw.get("栏名") or raw.get("kicker") or c,
                      "title": raw.get("标题") or raw.get("title") or "",
                      "deck": raw.get("副题") or raw.get("deck") or "",
                      "body": body})
    short = {"短刊": [], "一句话": []}
    f = d / "短刊.json"
    if f.exists():
        try:
            short = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ! 短刊解析失败：{e}")
    return chaps, short


def assemble(work: pathlib.Path, columns: dict, stats: dict, masthead: dict | None = None) -> dict:
    """把 稿/*.json 填进槽位，产出 内容.json（同样输入必得同样输出）。"""
    chaps, short = _load_drafts(work, columns)
    if not chaps:
        raise SystemExit("稿/ 里还没有任何栏目稿，先按 任务单.md 写稿")
    M = [{"title": m.get("标题") or m.get("title") or "",
          "text": m.get("正文") or m.get("text") or ""} for m in short.get("短刊") or []]
    L = [{"text": (m.get("文本") or m.get("text") or "").strip().strip("「」"),
          "who": m.get("作者") or m.get("谁") or m.get("who") or "",
          "when": m.get("时间") or m.get("when") or ""} for m in short.get("一句话") or []]

    # 头条 = 参与人数最多的栏目（人数相同时取素材多的）
    people = people_of(read_window(work / "窗口.jsonl"), columns) if (work / "窗口.jsonl").exists() else {}
    order = sorted(range(len(chaps)),
                   key=lambda i: (-people.get(chaps[i].get("col", ""), 0),
                                  -sum(len(p) for p in chaps[i]["body"])))
    head = dict(chaps[order[0]])
    rest = [dict(chaps[i]) for i in order[1:]]
    for c in [head] + rest:
        c.pop("col", None)

    # 短刊按计划逐段切
    cur, slots = 0, {}
    for slot, n in MINI_PLAN:
        slots[slot] = M[cur:cur + n]
        cur += n
    # 语录按计划切
    lcur, lslots = 0, {}
    for slot, n in LINE_PLAN:
        lslots[slot] = L[lcur:lcur + n]
        lcur += n

    def mini(m):
        return {"kind": "mini", "title": m["title"], "text": m["text"]}

    def line(m):
        who = f"{m['who']}　{m['when']}" if m["when"] else m["who"]
        return {"kind": "line", "text": m["text"], "who": who}

    data = {
        "headline": {"kicker": head["kicker"], "title": head["title"],
                     "subtitle": head["deck"], "body": head["body"]},
        "chapters": rest,
        "minis": [mini(m) for m in lslots.get("minis", [])] if False else [mini(m) for m in slots.get("minis", [])],
        "quotes": lslots.get("quotes", []),
        "notice": "本报内容全部来自群内公开聊天，仅记原话与时间，不作评价。",
        "p1_minis": [mini(m) for m in slots.get("p1_minis", [])],
        "p2_minis": [mini(m) for m in slots.get("p2_minis", [])],
        "p2_side_minis": [mini(m) for m in slots.get("p2_side_minis", [])],
        "p4_minis": [line(m) for m in lslots.get("p4_minis", [])],
        "p4_mid": ([{"kind": "head", "title": "短刊"}] + [mini(m) for m in slots.get("p4_mid", [])]
                   + [{"kind": "statbox", "title": "本期发言统计", "rows": [
                       ["总发言", f"{stats['total']:,} 条"], ["参与人数", f"{stats['people']} 人"],
                       ["人均发言", f"{stats['per']} 条"],
                       ["发言冠军", f"{stats['top'][0][0]}　{stats['top'][0][1]} 条" if stats["top"] else "—"],
                       ["最热闹的时段", f"{int(stats['busiest_hour'][0])} 时　{stats['busiest_hour'][1]} 条"],
                   ], "note": f"统计口径：{stats['from'][:16]} — {stats['to'][:16]}，按群消息去重后计数。"}]
                  + [{"kind": "rule"}]
                  + [{"kind": "line", "text": "主编　（在此署名）", "credit": True},
                     {"kind": "line", "text": "撰稿　（在此署名）｜编排·终检　（在此署名）", "credit": True},
                     {"kind": "rule"},
                     {"kind": "line", "text": "—— 编辑部", "credit": True}]),
        "p5_mid": ([mini(m) for m in slots.get("p5_mid", [])]
                   + [line(m) for m in lslots.get("p5_mid", [])]),
        "vlead_chapter": rest[0]["title"] if rest else "",
        "vlead_mini": (slots.get("p2_side_minis") or [{}])[0].get("title", ""),
        "vlead_mini_horiz": True,
        "p3_plan": {
            "left": [rest[1]["title"]] if len(rest) > 1 else [],
            "left_mid": [m["title"] for m in slots.get("p3_plan", [])[:1]],
            "left_bottom": [m["title"] for m in slots.get("p3_plan", [])[1:2]],
            "right_seq": (["rule"] + ([rest[2]["title"]] if len(rest) > 2 else [])
                          + [m["title"] for m in slots.get("p3_plan", [])[2:3]]),
            "right_lines": [{"text": m["text"], "who": m["who"]} for m in lslots.get("p3_right", [])],
            "right_align": "bottom",
        },
        "masthead": masthead or {"stance": "头条谁聊得凶谁上", "face": "🐋",
                                 "tip": f"本期素材：{stats['from'][:10]} 至 {stats['to'][:10]}，{stats['total']:,} 条。",
                                 "editor": "（主编）", "editor_note": "qqdaily"},
    }
    # 源池只放「未被 p3_plan 引用」的短刊，避免重复刊出（模板1 的坑）
    referenced = set()
    for k in ("left_mid", "left_bottom", "right_seq"):
        referenced.update(data["p3_plan"][k])
    data["minis"] = [m for m in data["minis"] if m["title"] not in referenced]

    (work / "内容.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def stage_file(work: pathlib.Path) -> pathlib.Path:
    return work / "状态.json"


def read_stage(work: pathlib.Path) -> dict:
    p = stage_file(work)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"stage": "new"}


def write_stage(work: pathlib.Path, **kw) -> None:
    st = read_stage(work)
    st.update(kw)
    stage_file(work).write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
