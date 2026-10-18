# -*- coding: utf-8 -*-
r"""按版统计汉字数，并量每版"最深内容底边 vs 页脚顶边"的间距。

每版汉字按**版面实际归属**统计：直接数生成 HTML 里每一版 DOM 上的汉字，
不再按内容 JSON 的章节下标推算 —— 推算法只在"7 个大章节＋固定版位"时成立，
011 期就数错过（第 3 版把整池 minis 都算进去、第 4 版漏了 chapters[6]）。
口径：含标题/题花/署名，不含页脚 folio 与报头 masthead（要目与正文标题重复）。

用法： python 版心与字数.py 011    （期号必填）
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
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = QD_BASE
EDGE = QD_EDGE or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not pathlib.Path(EDGE).exists():
    EDGE = EDGE or r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

if len(sys.argv) > 1:
    NO = sys.argv[1]
else:
    avail = sorted({re.search(r"第(\d+)期", p.name).group(1)
                    for p in (BASE / "4-出报素材和日志").glob("特刊内容_第*期.json")})
    sys.exit("用法：python 版心与字数.py <期号>（如 011）\n"
             "可用期号（按 特刊内容_第*.json）：" + "、".join(avail))

PAPER = _qd("QQDAILY_PAPER", "四号食堂日报")
hp = QD_OUT / ("%s_第%s期.html" % (PAPER, NO))
if not hp.exists():
    sys.exit(f"找不到 {hp}")

js = ("<script>window.addEventListener('load',function(){var o=[];"
      "document.querySelectorAll('.page').forEach(function(p,idx){"
      "var f=p.querySelector('.folio');var ft=f?f.getBoundingClientRect().top:1e9;"
      "var deep=0;Array.prototype.forEach.call(p.children,function(e){"
      "if(e===f)return;var r=e.getBoundingClientRect();"
      "if(r.height>0&&r.bottom>deep)deep=r.bottom;});"
      "var t=p.cloneNode(true);"
      "t.querySelectorAll('.folio,.masthead').forEach(function(e){e.remove();});"
      "var han=(t.textContent.match(/[\\u4e00-\\u9fff]/g)||[]).length;"
      "o.push([idx+1,Math.round(ft-deep),Math.round(p.scrollHeight-p.clientHeight),han]);});"
      "var d=document.createElement('div');d.id='__O';d.textContent=JSON.stringify(o);"
      "document.body.appendChild(d);});</script>")
tmp = hp.with_name("_gap.html")
tmp.write_text(hp.read_text(encoding="utf-8").replace("</body>", js + "</body>"), encoding="utf-8")
r = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-sandbox",
                    "--virtual-time-budget=12000",
                    f"--user-data-dir={pathlib.Path(r'D:\ai\out')/'ep_gap'}",
                    "--dump-dom", "file:///" + str(tmp).replace("\\", "/")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
tmp.unlink(missing_ok=True)
m = re.search(r'id="__O"[^>]*>(.*?)</div>', r.stdout or "", re.S)
if not m:
    sys.exit("量不到版心数据（Edge 没跑起来或输出异常），报错退出。")
try:
    rows = json.loads(m.group(1).replace("&quot;", '"'))
except Exception:
    sys.exit("版心数据解析失败（Edge 输出异常），报错退出。")
print("版 | 最深内容距页脚 | 溢出 | 版面汉字")
for pg, gap, ovf, han in rows:
    flag = "" if gap >= 6 else "  ← 压页脚！"
    print(f" {pg}  |   {gap:5d}px      | {ovf:+4d}px | {han:5d}{flag}")
print(f"\n全期汉字（版面实际，含标题题花，不含页脚与报头）：{sum(r[3] for r in rows)}")
