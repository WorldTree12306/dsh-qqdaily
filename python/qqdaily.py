#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""qqdaily — 配置驱动的群日报流水线（dsh-qqdaily 插件的 Python 内核）

用法：
    qqdaily.py config                      # 打印生效配置
    qqdaily.py init [--force]              # 写一份样例配置到 ~/.dsh/qqdaily.json
    qqdaily.py stats  --since "YYYY-MM-DD HH:MM" [--window 窗口.jsonl]
    qqdaily.py fetch  --since "... " [--out 窗口.jsonl] [--label 012]
    qqdaily.py typeset --内容 内容.json --期号 012 [--日期 ...] [--时段 ...]
    qqdaily.py check  --期号 012
    qqdaily.py send   --期号 012 [--images-only]
    qqdaily.py templates                   # 列出可用模板

配置解析顺序：--config > $QQDAILY_CONFIG > ~/.dsh/qqdaily.json > 内置默认值
所有路径类键都支持 ~ 与相对本文件的位置；留空的键会用合理默认值补齐。
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PLUGIN = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = pathlib.Path(os.environ.get("DSH_HOME", pathlib.Path.home() / ".dsh")) / "qqdaily.json"

DEFAULTS = {
    "base": "",                 # 素材基目录：内容 JSON 里 吉祥物/素材库/xxx.png 这类相对路径按它解析
    "out": "",                  # 成品目录（HTML/PDF/版图）
    "tmp": "",                  # 临时目录（无头浏览器 profile）
    "archive": "",              # 归档目录（可选）
    "paper": "群日报",           # 刊名
    "template": "example",     # 模板名（templates/ 下的目录名）
    "templates_dir": "",        # 模板根目录，默认 <插件>/templates
    "edge": "",                 # 浏览器可执行文件；留空自动探测 Edge/Chrome
    "python": sys.executable,   # 解释器（插件层调用时用）
    "onebot": {"endpoint": "http://127.0.0.1:3001", "token": "", "group_id": 0},
    "send": {"sink": "onebot", "images": True, "text": False},
    "layout": {"capacity": 1010, "byline": "本报记者", "kicker": "群内观察",
               "date": "", "window": ""},
    "limits": {"min_pages": 4, "min_total_hanzi": 3500, "min_page_hanzi": 600,
               "min_gap_px": 6, "max_hole_px": 300},
}


def _expand(p: str) -> pathlib.Path:
    return pathlib.Path(os.path.expanduser(os.path.expandvars(str(p))))


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(explicit: str | None = None) -> dict:
    path = pathlib.Path(explicit) if explicit else pathlib.Path(
        os.environ.get("QQDAILY_CONFIG", DEFAULT_CONFIG))
    user = {}
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"! 配置读取失败（按默认值继续）：{path} — {e}", file=sys.stderr)
    cfg = deep_merge(DEFAULTS, user)
    cfg["_config_path"] = str(path)
    # 路径类键补默认 + 展开
    plug = PLUGIN
    cfg["templates_dir"] = str(_expand(cfg["templates_dir"]) if cfg["templates_dir"] else plug / "templates")
    for key, fallback in (("base", plug / "workspace"), ("out", plug / "out"),
                          ("tmp", plug / "tmp"), ("archive", "")):
        v = cfg.get(key) or ""
        cfg[key] = str(_expand(v)) if v else (str(fallback) if fallback else "")
    cfg["template_dir"] = str(pathlib.Path(cfg["templates_dir"]) / cfg["template"])
    return cfg


def env_for_typesetter(cfg: dict) -> dict:
    env = dict(os.environ)
    env["QQDAILY_BASE"] = cfg["base"]
    env["QQDAILY_OUT"] = cfg["out"]
    env["QQDAILY_TMP"] = cfg["tmp"]
    env["QQDAILY_PAPER"] = cfg.get("paper") or "群日报"
    ban = pathlib.Path(cfg["template_dir"]) / "禁用词.txt"
    if ban.exists():
        env["QQDAILY_BAN"] = str(ban)
    corpus_dir = pathlib.Path(cfg["base"]) / "1-聊天记录"
    if corpus_dir.exists():
        env["QQDAILY_CORPUS_DIR"] = str(corpus_dir)
    if cfg.get("edge"):
        env["QQDAILY_EDGE"] = cfg["edge"]
    tpl = pathlib.Path(cfg["template_dir"]) / "程序" / "报纸版面模板.html"
    if tpl.exists():
        env["QQDAILY_TPL"] = str(tpl)
    return env


def run(cmd: list[str], env: dict | None = None) -> int:
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.call([str(c) for c in cmd], env=env)


# ── 子命令 ────────────────────────────────────────────────────────────

def cmd_init(cfg, args):
    p = pathlib.Path(cfg["_config_path"])
    if p.exists() and not args.force:
        print(f"配置已存在：{p}（要覆盖加 --force）")
        return 0
    p.parent.mkdir(parents=True, exist_ok=True)
    sample = {
        "paper": "四号食堂日报",
        "base": str(pathlib.Path.home() / "QQ日报"),
        "out": str(pathlib.Path.home() / "QQ日报" / "5-报纸成品"),
        "archive": str(pathlib.Path.home() / "QQ日报" / "6-报纸仓库" / "四号食堂日报"),
        "template": "template1",
        "edge": "",
        "onebot": {"endpoint": "http://127.0.0.1:3001", "token": "", "group_id": 0},
        "send": {"sink": "onebot", "images": True, "text": False},
        "layout": {"capacity": 1010, "byline": "本报记者 蓝色大肥鱼", "kicker": "群内观察"},
    }
    p.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入样例配置：{p}\n改完再跑：qqdaily.py config")
    return 0


def cmd_config(cfg, args):
    printable = {k: v for k, v in cfg.items() if not k.startswith("_")}
    print(f"配置文件：{cfg['_config_path']}")
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0


def cmd_templates(cfg, args):
    root = pathlib.Path(cfg["templates_dir"])
    print(f"模板目录：{root}")
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        ts = d / "程序" / "排特刊v3.py"
        print(f"  {'*' if d.name == cfg['template'] else ' '} {d.name}"
              f"　排版器：{'有' if ts.exists() else '缺'}"
              f"　槽位表：{'有' if (d / '模板.json').exists() else '缺'}")
    return 0


def _window_rows(path: pathlib.Path, since: str) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not since or r.get("time", "") >= since:
                rows.append(r)
    return rows


def cmd_stats(cfg, args):
    path = pathlib.Path(args.window) if args.window else None
    if path is None:
        cand = sorted(pathlib.Path(cfg["tmp"]).glob("窗口_*.jsonl"))
        if not cand:
            print("没找到窗口文件，用 --window 指定，或先跑 fetch", file=sys.stderr)
            return 2
        path = cand[-1]
    rows = _window_rows(path, args.since or "")
    cnt = Counter(r.get("sender", "?") for r in rows)
    byday = Counter(r.get("time", "")[:10] for r in rows)
    byhour = Counter(r.get("time", "")[11:13] for r in rows)
    out = {
        "window": str(path), "since": args.since, "total": len(rows), "people": len(cnt),
        "per": round(len(rows) / max(1, len(cnt)), 1), "top": cnt.most_common(8),
        "byday": byday.most_common(), "byhour": byhour.most_common(3),
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if args.save:
        pathlib.Path(args.save).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def _import_rows(src: pathlib.Path) -> list[dict]:
    """把任意聊天导出转成窗口格式：[{time, sender, content}]。
       支持：窗口 JSONL（time/sender/content）、Telegram 导出 JSON（messages[].date/from/text）。"""
    import datetime as _dt
    text = src.read_text(encoding="utf-8", errors="replace")
    rows = []
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(text)
        except Exception:
            data = None
        if isinstance(data, dict) and isinstance(data.get("messages"), list):
            for m in data["messages"]:
                if not isinstance(m, dict):
                    continue
                ts = m.get("date") or ""
                if isinstance(ts, (int, float)):
                    ts = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    ts = str(ts).replace("T", " ")[:19]
                who = m.get("from") or (m.get("from_id") if isinstance(m.get("from_id"), str) else "") or "?"
                body = m.get("text")
                if isinstance(body, list):
                    body = "".join(b if isinstance(b, str) else str(b.get("text", "")) for b in body)
                rows.append({"time": ts, "sender": str(who), "content": str(body or "")})
            return rows
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if not isinstance(r, dict):
            continue
        ts = r.get("time") or r.get("date") or ""
        if isinstance(ts, (int, float)):
            ts = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        who = r.get("sender") or r.get("from") or r.get("nickname") or "?"
        body = r.get("content") or r.get("text") or ""
        if isinstance(body, list):
            body = "".join(b if isinstance(b, str) else str(b.get("text", "")) for b in body)
        rows.append({"time": str(ts)[:19].replace("T", " "), "sender": str(who),
                     "content": str(body)})
    return rows


def cmd_fetch(cfg, args):
    import urllib.request
    if getattr(args, "from_file", ""):
        src = pathlib.Path(args.from_file)
        if not src.exists():
            print(f"找不到导入文件：{src}", file=sys.stderr)
            return 2
        rows = _import_rows(src)
        dest = pathlib.Path(args.out) if getattr(args, "out", "") else \
            pathlib.Path(cfg["tmp"]) / f"窗口_{getattr(args, 'label', '') or src.stem}.jsonl"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"从文件导入 {len(rows)} 条 → {dest}")
        return 0
    ob = cfg["onebot"]
    if not ob.get("group_id"):
        print("配置里没写 onebot.group_id", file=sys.stderr)
        return 2
    hdr = {"Content-Type": "application/json",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if ob.get("token"):
        hdr["Authorization"] = f"Bearer {ob['token']}"
    # NapCat 的 get_group_msg_history 返回不稳定（同样的 count 每次给的结果集不同），
    # 所以连拉几轮、按 message_id 取并集，避免漏消息。
    passes = max(1, int(getattr(args, "passes", 3) or 3))
    merged = {}
    for i in range(passes):
        body = json.dumps({"group_id": ob["group_id"], "count": args.count}).encode()
        req = urllib.request.Request(ob["endpoint"].rstrip("/") + "/get_group_msg_history",
                                     data=body, headers=hdr, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == 0:
                raise
            print(f"  第 {i+1} 轮回捞失败（忽略）：{e}", file=sys.stderr)
            continue
        got = (data.get("data") or {}).get("messages") or []
        for m in got:
            merged[m.get("message_id")] = m
        if len(got) == 0:
            break
    msgs = list(merged.values())
    rows = []
    for m in msgs:
        text = "".join(seg.get("data", {}).get("text", "") for seg in m.get("message", [])
                       if seg.get("type") == "text")
        ts = m.get("time")
        import datetime as _dt
        t = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
        if args.since and t < args.since:
            continue
        rows.append({"time": t, "sender": (m.get("sender") or {}).get("nickname", ""),
                     "content": text, "message_id": m.get("message_id")})
    dest = pathlib.Path(args.out) if args.out else pathlib.Path(cfg["tmp"]) / f"窗口_{args.label or 'new'}.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"抓到 {len(rows)} 条（原始 {len(msgs)} 条）→ {dest}")
    return 0


KNOWN_KEYS = {
    "headline", "chapters", "minis", "quotes", "notice", "masthead",
    "p1_minis", "p2_minis", "p2_side_minis", "p2_mid", "p3_plan", "p4_minis", "p4_mid",
    "p5_mid", "p6_mid", "vlead_chapter", "vlead_mini", "vlead_mini_horiz",
    "vlead_image", "vlead_image_in_region", "_说明",
}


def _contract_check(content_path: pathlib.Path) -> list[str]:
    """轻量契约自检：拼错的槽位名会被点名（不会静默丢版）。"""
    try:
        doc = json.loads(pathlib.Path(content_path).read_text(encoding="utf-8"))
    except Exception as e:
        return [f"内容 JSON 读不出来：{e}"]
    warn = []
    unknown = sorted(set(doc) - KNOWN_KEYS)
    if unknown:
        warn.append("未知槽位（拼错了？会被忽略）：" + "、".join(unknown))
    if not doc.get("headline"):
        warn.append("缺 headline（头条）")
    if not doc.get("chapters"):
        warn.append("缺 chapters（章节）")
    empty = [k for k in ("p1_minis", "p2_minis", "p2_side_minis", "p4_mid", "p5_mid")
             if k in doc and not doc.get(k)]
    if empty:
        warn.append("这些版位是空的：" + "、".join(empty))
    return warn


def cmd_typeset(cfg, args):
    for w in _contract_check(args.内容):
        print(f"  ! {w}")
    ts = pathlib.Path(cfg["template_dir"]) / "程序" / "排特刊v3.py"
    if not ts.exists():
        print(f"模板里没有排版器：{ts}", file=sys.stderr)
        return 2
    pathlib.Path(cfg["out"]).mkdir(parents=True, exist_ok=True)
    pathlib.Path(cfg["tmp"]).mkdir(parents=True, exist_ok=True)
    cmd = [cfg.get("python") or sys.executable, str(ts),
           "--内容", args.内容, "--期号", args.期号,
           "--刊名", cfg["paper"],
           "--容量", str(args.capacity or cfg["layout"]["capacity"])]
    date = args.日期 or cfg["layout"].get("date") or auto_date()
    window = args.时段 or cfg["layout"].get("window")
    if date:
        cmd += ["--日期", date]
    if window:
        cmd += ["--时段", window]
    if args.署名 or cfg["layout"].get("byline"):
        cmd += ["--署名", args.署名 or cfg["layout"]["byline"]]
    if args.引题 or cfg["layout"].get("kicker"):
        cmd += ["--引题", args.引题 or cfg["layout"]["kicker"]]
    if args.量块:
        cmd += ["--量块", str(args.量块)]
    return run(cmd, env=env_for_typesetter(cfg))


def cmd_check(cfg, args):
    tools = PLUGIN / "python" / "tools"
    env = env_for_typesetter(cfg)
    content = getattr(args, "内容", "") or ""
    if content:
        env["QQDAILY_CONTENT"] = str(pathlib.Path(content))
    # 语料：显式 --语料（可多次）→ 否则「项目语料 + tmp 里最新的窗口文件」
    corpus = [c for c in (getattr(args, "语料", None) or []) if c]
    if not corpus:
        corpus_dir = pathlib.Path(cfg["base"]) / "1-聊天记录"
        corpus += [str(p) for p in sorted(corpus_dir.glob("messages_*.jsonl"))]
        for w in sorted(pathlib.Path(cfg["tmp"]).glob("窗口_*.jsonl"))[-3:]:
            corpus.append(str(w))
    if corpus:
        env["QQDAILY_CORPUS"] = ";".join(corpus)
    rc = run([cfg.get("python") or sys.executable, str(tools / "校验.py"), args.期号], env=env)
    rc2 = run([cfg.get("python") or sys.executable, str(tools / "版心与字数.py"), args.期号], env=env)
    return rc or rc2


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    """向 OneBot 发一个 JSON POST。urllib 被拦时自动退回本机 PowerShell / curl。"""
    import json as _json
    import platform
    import subprocess as _sp
    import tempfile
    import urllib.request

    body = _json.dumps(payload, ensure_ascii=False)
    try:
        req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return _json.loads(r.read().decode("utf-8"))
    except Exception as first:
        tmp = pathlib.Path(tempfile.gettempdir()) / "qqdaily_payload.json"
        tmp.write_text(body, encoding="utf-8")
        if platform.system() == "Windows":
            ps = (
                "$h=@{"
                + ";".join(f"'{k}'='{v}'" for k, v in headers.items())
                + "}; "
                f"Invoke-RestMethod -Method Post -Uri '{url}' -Headers $h "
                f"-ContentType 'application/json; charset=utf-8' -InFile '{tmp}' -TimeoutSec {timeout} "
                "| ConvertTo-Json -Depth 8 -Compress"
            )
            try:
                out = _sp.run(["powershell", "-NoProfile", "-Command", ps],
                              capture_output=True, text=True, encoding="utf-8", timeout=timeout + 30)
                if out.returncode == 0 and out.stdout.strip():
                    return _json.loads(out.stdout)
            except Exception:
                pass
        try:
            out = _sp.run(["curl", "-sS", "-X", "POST", url,
                           "-H", "Content-Type: application/json",
                           *sum((["-H", f"{k}: {v}"] for k, v in headers.items() if k != "Content-Type"), []),
                           "--data-binary", "@" + str(tmp)],
                          capture_output=True, text=True, encoding="utf-8", timeout=timeout + 30)
            if out.returncode == 0 and out.stdout.strip():
                return _json.loads(out.stdout)
        except Exception:
            pass
        raise first


def _issue_pages(cfg, issue: str) -> list[pathlib.Path]:
    out = pathlib.Path(cfg["out"])
    pages = [p for p in out.glob(f"*{issue}*第*版.png")]
    if not pages:   # demo 等成品在子目录里
        pages = [p for p in out.glob(f"**/*{issue}*第*版.png")]
    if not pages:
        pages = list(out.glob("第*版.png"))
    return sorted(pages, key=lambda p: int(re.search(r"第(\d+)版", p.name).group(1)))


def cmd_send(cfg, args):
    """发群。sink=onebot（默认，只发版图）或 file（只把版图归档到 <out>/sent/）。"""
    send_cfg = cfg.get("send") or {}
    sink = str(send_cfg.get("sink") or "onebot").lower()
    pages = _issue_pages(cfg, args.期号)
    if not pages:
        print(f"{cfg['out']} 下没找到该期版图（先 typeset）", file=sys.stderr)
        return 2
    print(f"版图 {len(pages)} 张：{', '.join(p.name for p in pages)}")

    if sink == "file":
        dest = pathlib.Path(cfg["out"]) / "sent" / str(args.期号)
        dest.mkdir(parents=True, exist_ok=True)
        for p in pages:
            (dest / p.name).write_bytes(p.read_bytes())
        print(f"已归档到 {dest}（sink=file：没有发到任何群）")
        return 0

    ob = cfg.get("onebot") or {}
    if not ob.get("group_id"):
        print("配置里没写 onebot.group_id（或把 send.sink 设为 file 只归档）", file=sys.stderr)
        return 2
    hdr = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if ob.get("token"):
        hdr["Authorization"] = f"Bearer {ob['token']}"
    endpoint = ob["endpoint"].rstrip("/")

    # 真 OneBot 对中文路径的图片会 403：先复制成纯 ASCII 名再发
    slug = re.sub(r"[^0-9A-Za-z_-]", "", str(args.期号)) or "issue"
    safe_dir = pathlib.Path(cfg["tmp"]) / "send" / slug
    safe_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for idx, p in enumerate(pages, 1):
        safe = safe_dir / f"p{idx:02d}{p.suffix.lower()}"
        safe.write_bytes(p.read_bytes())
        payload = {"group_id": ob["group_id"],
                   "message": [{"type": "image",
                                "data": {"file": "file:///" + str(safe).replace("\\", "/")}}]}
        try:
            res = _post_json(endpoint + "/send_group_msg", payload, hdr)
            mid = (res.get("data") or {}).get("message_id")
            print(f"  {p.name} → {res.get('status')} {mid or ''}（发送用 {safe.name}）")
            ok += 1
        except Exception as e:
            print(f"  {p.name} → 失败：{e}", file=sys.stderr)

    # send.text=true 时再补一条文字（默认关：本项目习惯只发图）
    if send_cfg.get("text") and ok:
        tip = f"{cfg.get('paper') or '群日报'} 第 {args.期号} 期，共 {len(pages)} 版。"
        try:
            res = _post_json(endpoint + "/send_group_msg",
                             {"group_id": ob["group_id"],
                              "message": [{"type": "text", "data": {"text": tip}}]}, hdr)
            print(f"  文字：{res.get('status')}")
        except Exception as e:
            print(f"  文字发送失败：{e}", file=sys.stderr)
    return 0 if ok == len(pages) else 1


def auto_date() -> str:
    """按本地日期生成中文日期串：「2026 年 10 月 18 日　星期日」（全角空格分隔）。"""
    import datetime as _dt
    wd = "一二三四五六日"[_dt.date.today().weekday()]
    d = _dt.date.today()
    return f"{d.year} 年 {d.month} 月 {d.day} 日　星期{wd}"


def cmd_demo(cfg, args):
    """离线示例：不碰 OneBot，直接用随包样例排一期，验证安装是否成功。"""
    samples = PLUGIN / "samples"
    content = samples / "内容_示例.json"
    window = samples / "窗口_示例.jsonl"
    if not content.exists():
        print(f"找不到示例素材：{content}", file=sys.stderr)
        return 2
    demo_out = pathlib.Path(cfg["out"]) / "demo"
    demo_tmp = pathlib.Path(cfg["tmp"]) / "demo"
    demo_out.mkdir(parents=True, exist_ok=True)
    demo_tmp.mkdir(parents=True, exist_ok=True)
    env = env_for_typesetter(cfg)
    env["QQDAILY_OUT"] = str(demo_out)
    env["QQDAILY_TMP"] = str(demo_tmp)
    ts = pathlib.Path(cfg["template_dir"]) / "程序" / "排特刊v3.py"
    if not ts.exists():
        print(f"模板里没有排版器：{ts}", file=sys.stderr)
        return 2
    cmd = [cfg.get("python") or sys.executable, str(ts),
           "--内容", str(content), "--期号", "示例",
           "--刊名", cfg.get("paper") or "示例日报",
           "--日期", auto_date(),
           "--署名", "示例编辑", "--引题", "示例",
           "--容量", str(cfg["layout"]["capacity"])]
    rc = run(cmd, env=env)
    if rc != 0:
        return rc
    # 示例只做结构自检（引语与示例窗口逐字核对）
    env2 = dict(env)
    env2["QQDAILY_CONTENT"] = str(content)
    env2["QQDAILY_CORPUS"] = str(window)
    rc2 = run([cfg.get("python") or sys.executable,
               str(PLUGIN / "python" / "tools" / "校验.py"), "示例"], env=env2)
    print(f"\n示例成品：{demo_out}")
    print("  提示：把配置里的 onebot.endpoint/token/group_id 填好，就能出自己群的真报了。")
    return rc2


def cmd_doctor(cfg, args):
    """体检：环境依赖、模板完整性、配置可写、OneBot 可达与群列表。"""
    import importlib.util
    import urllib.request

    rows = []
    def check(name, fn):
        try:
            ok, detail = fn()
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        rows.append((name, bool(ok), detail))

    check("Python ≥ 3.10", lambda: (sys.version_info >= (3, 10), sys.version.split()[0]))
    def _pdfium():
        spec = importlib.util.find_spec("pypdfium2")
        return (spec is not None, "已安装" if spec else "缺失：pip install pypdfium2")
    check("pypdfium2（出 PDF/版图）", _pdfium)

    def _edge():
        import shutil as _sh
        cands = ([cfg["edge"]] if cfg.get("edge") else []) + [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/usr/bin/microsoft-edge", "/usr/bin/google-chrome", "/usr/bin/chromium",
        ]
        for c in cands:
            if c and pathlib.Path(c).exists():
                return True, c
        for exe in ("msedge", "google-chrome", "chromium", "chrome"):
            p = _sh.which(exe)
            if p:
                return True, p
        return False, "未找到 Edge/Chrome（可在配置里写 edge 路径）"
    check("浏览器（无头打印 PDF）", _edge)

    def _tpl():
        d = pathlib.Path(cfg["template_dir"])
        need = {"模板.json": d / "模板.json",
                "排版器": d / "程序" / "排特刊v3.py",
                "版面模板": d / "程序" / "报纸版面模板.html",
                "禁用词表": d / "禁用词.txt"}
        miss = [k for k, p in need.items() if not p.exists()]
        return (not miss, f"{d.name}：{'齐全' if not miss else '缺 ' + '/'.join(miss)}")
    check("版式模板", _tpl)

    def _cfg():
        p = pathlib.Path(cfg["_config_path"])
        if p.exists():
            return True, str(p)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            return True, f"{p}（可创建，建议先跑 init）"
        except Exception as e:
            return False, f"不可写：{e}"
    check("配置文件", _cfg)
    check("输出目录", lambda: (pathlib.Path(cfg["out"]).parent.exists(), cfg["out"]))

    ob = cfg.get("onebot") or {}
    def _onebot():
        if not ob.get("group_id"):
            return False, "未配置 onebot.group_id"
        hdr = {"User-Agent": "Mozilla/5.0"}
        if ob.get("token"):
            hdr["Authorization"] = f"Bearer {ob['token']}"
        url = ob["endpoint"].rstrip("/") + "/get_login_info"
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=8) as r:
            d = json.loads(r.read().decode("utf-8"))
        who = (d.get("data") or {})
        return True, f"在线：{who.get('nickname')}（{who.get('user_id')}）"
    check("OneBot 在线", _onebot)

    print("=== qqdaily 体检 ===")
    for name, ok, detail in rows:
        print(f"  {'✓' if ok else '✗'} {name}：{detail}")

    # 群列表（可选，方便挑群号）
    if args.groups and ob.get("group_id") is not None:
        try:
            hdr = {"User-Agent": "Mozilla/5.0"}
            if ob.get("token"):
                hdr["Authorization"] = f"Bearer {ob['token']}"
            url = ob["endpoint"].rstrip("/") + "/get_group_list"
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=10) as r:
                gl = json.loads(r.read().decode("utf-8")).get("data") or []
            print(f"\n=== 群列表（{len(gl)} 个，把 id 填进配置的 onebot.group_id）===")
            for g in gl[:40]:
                print(f"  {g.get('group_id')}  {g.get('group_name')}")
        except Exception as e:
            print(f"群列表读取失败：{e}")

    bad = [r for r in rows if not r[1]]
    if bad:
        print(f"\n{len(bad)} 项待处理。")
        if args.fix:
            print("尝试 --fix：写一份样例配置（不覆盖已有文件）…")
            cmd_init(cfg, type("A", (), {"force": False})())
        return 1
    print("\n全部就绪。下一步：python/qqdaily.py demo（离线看效果）或 fetch（拉自己的群）")
    return 0



# ── 编辑部流水线（draft / assemble / publish）─────────────────────────
def _pipeline():
    import importlib.util
    spec = importlib.util.spec_from_file_location("qqdaily_pipeline", PLUGIN / "python" / "pipeline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _work_dir(cfg, label):
    return pathlib.Path(cfg["tmp"]) / f"工作_{label}"


def _date_example() -> str:
    import datetime as _dt
    d = _dt.date.today()
    return f"{d.month}月{d.day}日{8}时30分"


def cmd_draft(cfg, args):
    """切栏目、出逐字素材 digest、内容骨架、写作任务单；必要时先 fetch。"""
    pipe = _pipeline()
    label = args.label
    work = _work_dir(cfg, label)
    work.mkdir(parents=True, exist_ok=True)
    win = work / "窗口.jsonl"
    if args.window:
        src = pathlib.Path(args.window)
        win.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"用现成窗口：{src}")
    elif win.exists() and not args.since:
        print(f"复用已有窗口：{win}")
    else:
        if not args.since:
            print("需要 --since 或 --window（窗口起点）", file=sys.stderr)
            return 2
        rc = cmd_fetch(cfg, type("A", (), {"since": args.since, "out": str(win),
                                            "label": label, "count": args.count})())
        if rc != 0:
            return rc
    rows = pipe.read_window(win)
    if not rows:
        print("窗口是空的", file=sys.stderr)
        return 2
    stats = pipe.stats_of(rows)
    (work / "统计.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    tpl_dir = pathlib.Path(cfg["template_dir"])
    columns = pipe.columns_of(cfg, tpl_dir)
    digests = pipe.write_digests(work, rows, columns)
    # 素材为 0 的栏目不派稿（写了也是凭空编）
    empty = [c for c in columns if digests[c]["rows"] == 0]
    if empty:
        print(f"  跳过素材为 0 的栏目：{'、'.join(empty)}")
        columns = {c: v for c, v in columns.items() if c not in empty}
    (work / "骨架.json").write_text(json.dumps(pipe.skeleton(tpl_dir), ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    task = pipe.write_task(work, label, stats, columns, digests, _date_example())
    pipe.write_stage(work, stage="drafted", label=label, window=str(win),
                     total=stats["total"], people=stats["people"])
    print(f"\n工作目录：{work}")
    print(f"  窗口 {stats['total']} 条 / {stats['people']} 人　{stats['from']} → {stats['to']}")
    for c in columns:
        print(f"  素材 {c}：{digests[c]['rows']} 条")
    print(f"  任务单：{task}")
    print("\n下一步：按 任务单.md 把 稿/<栏目>.json 与 稿/短刊.json 写出来，再跑 publish --resume")
    return 0


def cmd_assemble(cfg, args):
    """把 稿/*.json 确定性拼成 内容.json。"""
    pipe = _pipeline()
    work = _work_dir(cfg, args.label)
    if not (work / "窗口.jsonl").exists():
        print(f"还没有工作目录：{work}（先跑 draft）", file=sys.stderr)
        return 2
    rows = pipe.read_window(work / "窗口.jsonl")
    stats = pipe.stats_of(rows)
    columns = pipe.columns_of(cfg, pathlib.Path(cfg["template_dir"]))
    data = pipe.assemble(work, columns, stats)
    pipe.write_stage(work, stage="assembled")
    print(f"已拼版：{work / '内容.json'}")
    print(f"  头条：{data['headline']['title']}（{data['headline']['kicker']}）")
    n_mini = sum(1 for k in ("minis", "p1_minis", "p2_minis", "p2_side_minis", "p4_minis")
                 for m in (data.get(k) or []) if isinstance(m, dict) and m.get("kind") == "mini")
    n_mini += sum(1 for k in ("p4_mid", "p5_mid") for m in (data.get(k) or [])
                  if isinstance(m, dict) and m.get("kind") == "mini")
    n_mini += sum(len(data["p3_plan"].get(k) or []) for k in ("left_mid", "left_bottom"))
    n_line = len(data.get("quotes") or []) + sum(1 for k in ("p4_minis", "p5_mid")
                                                 for m in (data.get(k) or [])
                                                 if isinstance(m, dict) and m.get("kind") == "line")
    n_line += len((data.get("p3_plan") or {}).get("right_lines") or [])
    print(f"  章节 {len(data['chapters'])} 篇（＋头条）｜短刊 {n_mini} 条｜语录/一句话 {n_line} 条")
    return 0


def cmd_publish(cfg, args):
    """一条命令走完 排版 → 校验 →（可选）发群；没稿就先出草稿。"""
    import shutil
    pipe = _pipeline()
    label = args.label
    work = _work_dir(cfg, label)
    st = pipe.read_stage(work)

    if not work.exists() or args.since:
        rc = cmd_draft(cfg, type("A", (), {"label": label, "window": args.window or "",
                                            "since": args.since or "", "count": args.count})())
        if rc != 0:
            return rc
        print("\n—— 草稿已就绪，需要先把 稿/ 写出来 ——")
        return 3

    if not (work / "内容.json").exists() or args.assemble:
        rc = cmd_assemble(cfg, type("A", (), {"label": label})())
        if rc != 0:
            return rc

    # 排版
    content = work / "内容.json"
    out_dir = pathlib.Path(cfg["out"])
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = pipe.read_window(work / "窗口.jsonl")
    stats = pipe.stats_of(rows)
    env = env_for_typesetter(cfg)
    ts = pathlib.Path(cfg["template_dir"]) / "程序" / "排特刊v3.py"
    cmd = [cfg.get("python") or sys.executable, str(ts),
           "--内容", str(content), "--期号", label,
           "--刊名", cfg.get("paper") or "群日报",
           "--日期", auto_date(),
           "--时段", f"{stats['from'][5:16]} — {stats['to'][5:16]}",
           "--容量", str(cfg["layout"]["capacity"])]
    rc = run(cmd, env=env)
    if rc != 0:
        pipe.write_stage(work, stage="typeset-failed")
        return rc

    # 校验（门禁）
    env2 = dict(env)
    env2["QQDAILY_CONTENT"] = str(content)
    env2["QQDAILY_CORPUS"] = str(work / "窗口.jsonl")
    rc = run([cfg.get("python") or sys.executable,
              str(PLUGIN / "python" / "tools" / "校验.py"), label], env=env2)
    pipe.write_stage(work, stage="checked" if rc == 0 else "check-failed")
    if rc != 0:
        print("\n校验没过：按上面的清单改 稿/*.json，然后重跑 publish --resume", file=sys.stderr)
        return rc

    if args.send:
        rc = cmd_send(cfg, type("A", (), {"期号": label})())
        pipe.write_stage(work, stage="sent" if rc == 0 else "send-failed")
        return rc
    pipe.write_stage(work, stage="ready")
    print(f"\n就绪（未发群）。核对后发：publish --label {label} --resume --send")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="qqdaily", description="配置驱动的群日报流水线")
    ap.add_argument("--config", help="配置文件路径")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init"); p.add_argument("--force", action="store_true"); p.set_defaults(f=cmd_init)
    sub.add_parser("config").set_defaults(f=cmd_config)
    sub.add_parser("templates").set_defaults(f=cmd_templates)

    p = sub.add_parser("stats")
    p.add_argument("--since", default=""); p.add_argument("--window", default=""); p.add_argument("--save", default="")
    p.set_defaults(f=cmd_stats)

    p = sub.add_parser("fetch")
    p.add_argument("--passes", type=int, default=3, help="回捞轮数（并集去重，默认 3）")
    p.add_argument("--from-file", default="", help="从任意聊天导出导入（JSONL / Telegram JSON）")
    p.add_argument("--since", default=""); p.add_argument("--out", default="")
    p.add_argument("--label", default=""); p.add_argument("--count", type=int, default=500)
    p.set_defaults(f=cmd_fetch)

    p = sub.add_parser("typeset")
    p.add_argument("--内容", required=True); p.add_argument("--期号", required=True)
    p.add_argument("--日期", default=""); p.add_argument("--时段", default="")
    p.add_argument("--署名", default=""); p.add_argument("--引题", default="")
    p.add_argument("--capacity", type=int, default=0); p.add_argument("--量块", type=int, default=0)
    p.set_defaults(f=cmd_typeset)

    p = sub.add_parser("check")
    p.add_argument("--期号", required=True)
    p.add_argument("--内容", default="", help="该期内容 JSON（校验引语用）")
    p.add_argument("--语料", action="append", default=[],
                   help="语料来源（可多次；支持通配）。默认用项目语料 + tmp 里最新几个窗口")
    p.set_defaults(f=cmd_check)
    p = sub.add_parser("send"); p.add_argument("--期号", required=True); p.set_defaults(f=cmd_send)
    sub.add_parser("demo").set_defaults(f=cmd_demo)
    p = sub.add_parser("draft")
    p.add_argument("--label", required=True, help="期号，同时作为工作目录名")
    p.add_argument("--since", default="", help="窗口起点（会自动 fetch）")
    p.add_argument("--window", default="", help="用现成窗口 jsonl，不 fetch")
    p.add_argument("--count", type=int, default=3000)
    p.set_defaults(f=cmd_draft)

    p = sub.add_parser("assemble")
    p.add_argument("--label", required=True)
    p.set_defaults(f=cmd_assemble)

    p = sub.add_parser("publish")
    p.add_argument("--label", required=True)
    p.add_argument("--since", default="")
    p.add_argument("--window", default="")
    p.add_argument("--count", type=int, default=3000)
    p.add_argument("--resume", action="store_true", help="沿用已有工作目录（不重新 draft）")
    p.add_argument("--assemble", action="store_true", help="强制重新拼版")
    p.add_argument("--send", action="store_true", help="校验通过后发群")
    p.set_defaults(f=cmd_publish)

    p = sub.add_parser("doctor")
    p.add_argument("--fix", action="store_true", help="发现问题时写一份样例配置")
    p.add_argument("--groups", action="store_true", help="列出 OneBot 里的群（方便挑群号）")
    p.set_defaults(f=cmd_doctor)

    args = ap.parse_args()
    cfg = load_config(args.config)
    return args.f(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
