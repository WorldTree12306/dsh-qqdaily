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
    "template": "template1",    # 模板名（templates/ 下的目录名）
    "templates_dir": "",        # 模板根目录，默认 <插件>/templates
    "edge": "",                 # 浏览器可执行文件；留空自动探测 Edge/Chrome
    "python": sys.executable,   # 解释器（插件层调用时用）
    "onebot": {"endpoint": "http://127.0.0.1:3001", "token": "", "group_id": 0},
    "send": {"images": True, "text": False},
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
        "send": {"images": True, "text": False},
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


def cmd_fetch(cfg, args):
    import urllib.request
    ob = cfg["onebot"]
    if not ob.get("group_id"):
        print("配置里没写 onebot.group_id", file=sys.stderr)
        return 2
    hdr = {"Content-Type": "application/json",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if ob.get("token"):
        hdr["Authorization"] = f"Bearer {ob['token']}"
    body = json.dumps({"group_id": ob["group_id"], "count": args.count}).encode()
    req = urllib.request.Request(ob["endpoint"].rstrip("/") + "/get_group_msg_history",
                                 data=body, headers=hdr, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    msgs = (data.get("data") or {}).get("messages") or []
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


def cmd_typeset(cfg, args):
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
    date = args.日期 or cfg["layout"].get("date")
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
    rc = run([cfg.get("python") or sys.executable, str(tools / "校验.py"), args.期号], env=env)
    rc2 = run([cfg.get("python") or sys.executable, str(tools / "版心与字数.py"), args.期号], env=env)
    return rc or rc2


def cmd_send(cfg, args):
    import urllib.request
    ob = cfg["onebot"]
    if not ob.get("group_id"):
        print("配置里没写 onebot.group_id", file=sys.stderr)
        return 2
    hdr = {"Content-Type": "application/json",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if ob.get("token"):
        hdr["Authorization"] = f"Bearer {ob['token']}"
    out = pathlib.Path(cfg["out"])
    pages = sorted(out.glob(f"*{args.期号}*第*版.png"),
                   key=lambda p: int(re.search(r"第(\d+)版", p.name).group(1)))
    if not pages:
        pages = sorted(out.glob("第*版.png"))
    if not pages:
        print(f"{out} 下没找到该期版图", file=sys.stderr)
        return 2
    sent = []
    for p in pages:
        payload = {"group_id": ob["group_id"],
                   "message": [{"type": "image", "data": {"file": "file:///" + str(p).replace('\\', '/')}}]}
        req = urllib.request.Request(ob["endpoint"].rstrip("/") + "/send_group_msg",
                                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers=hdr, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                res = json.loads(r.read().decode("utf-8"))
            sent.append((p.name, res.get("status"), (res.get("data") or {}).get("message_id")))
        except Exception as e:
            sent.append((p.name, f"FAILED: {e}", None))
    for name, st, mid in sent:
        print(f"  {name} → {st} {mid or ''}")
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
    p.set_defaults(f=cmd_check)
    p = sub.add_parser("send"); p.add_argument("--期号", required=True); p.set_defaults(f=cmd_send)

    args = ap.parse_args()
    cfg = load_config(args.config)
    return args.f(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
