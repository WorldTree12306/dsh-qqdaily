# dsh-qqdaily

Turn a **group chat into a newspaper** inside DeepSeek Harness: OneBot (NapCat) collection →
topic statistics → template typesetting → verbatim-quote checking → page images posted back to the group.
Everything is configuration-driven, and the page layout is a swappable template.

## What it does

| Step | Detail |
|---|---|
| Collect | `get_group_msg_history` from OneBot 11, filtered by time window, written as JSONL |
| Count | total messages, participants, per-person average, top speakers, daily and hourly peaks |
| Typeset | content JSON + template → HTML → **PDF** (headless Edge/Chrome) → one PNG per page |
| Check | verbatim hit rate for every quoted line, banned words, per-page overflow and footer gap, length floors |
| Publish | page images only by default (no caption text), via `send_group_msg` |

## Requirements

- Node.js ≥ 20 (host plugin in `lib/`)
- Python ≥ 3.10 with `pypdfium2` (the kernel and PDF/PNG rendering)
- Edge or Chrome for headless HTML → PDF (path configurable, auto-detected when empty)
- An OneBot 11 server such as NapCat (default endpoint `http://127.0.0.1:3001`)

```bash
pip install pypdfium2
```

## Quick start

```bash
python python/qqdaily.py doctor --groups   # env / deps / browser / template / config / OneBot
python python/qqdaily.py doctor --fix      # write a sample ~/.dsh/qqdaily.json
python python/qqdaily.py demo              # offline sample paper (no OneBot needed)
```

`demo` renders the bundled synthetic sample into `out/demo/` (PDF + one PNG per page) and
runs the full check, so a green run proves the installation works.

## Install

```bash
dsh plugin --profile desktop add <this-directory-or-package-name>
```

The plugin mounts under the name `qqdaily` and registers:

`qqdaily_doctor` · `qqdaily_demo` · `qqdaily_status` · `qqdaily_fetch` · `qqdaily_stats` ·
`qqdaily_typeset` · `qqdaily_check` · `qqdaily_send` · `qqdaily_templates`

## Configure

```bash
python python/qqdaily.py init      # writes a sample to ~/.dsh/qqdaily.json
python python/qqdaily.py config    # shows the effective configuration
```

Resolution order: tool argument `config_path` > `$QQDAILY_CONFIG` > `~/.dsh/qqdaily.json` > built-in defaults.
Paths accept `~` and `$VAR`. Keys: `paper`, `base`, `out`, `tmp`, `archive`, `template`,
`edge`, `python`, `onebot{endpoint,token,group_id}`, `send{images,text}`,
`layout{capacity,byline,kicker}`, `limits{...}`.

## Command line (works without the plugin)

```bash
python python/qqdaily.py stats   --since "2026-10-14 21:00"
python python/qqdaily.py fetch   --since "2026-10-14 21:00" --label 012
python python/qqdaily.py typeset --content content_012.json --issue 012
python python/qqdaily.py check   --issue 012
python python/qqdaily.py send    --issue 012
```

## One-command publish

A persisted state machine: split material → draft → assemble → typeset → check → send.
Writing itself is the agent's job (the plugin never calls an LLM).

```bash
python python/qqdaily.py draft --label 014 --since "2026-10-17 22:00"
# ... the agent writes 稿/<column>.json and 稿/短刊.json ...
python python/qqdaily.py publish --label 014 --resume [--send]
```

`publish` exits non-zero when the gate fails and lists every unmatched quote / banned word,
then you fix the drafts and re-run with `--resume`. Assembly is deterministic.

## Content vs. layout

- **Content JSON** (yours): `headline`, `chapters`, `minis`, `quotes`, per-page slots
  (`p1_minis`, `p2_side_minis`, `p3_plan`, `p4_mid`, `p5_mid`, …), `masthead`.
- **Template directory** (swappable): `模板.json` (slot spec), `禁用词.txt` (banned words),
  `程序/排特刊v3.py` (typesetter), `程序/报纸版面模板.html` (layout CSS/markup).

Copy `templates/example` to `templates/template2`, restyle it, and point `template` at it.

## Without OneBot

- `fetch --from-file <path>` imports any chat export: window JSONL, or a Telegram export
  (`messages[].date/from/text`).
- `send.sink` selects the output: `onebot` (default, images only unless `send.text=true`) or
  `file` (archive page PNGs to `<out>/sent/<issue>/`, posting nothing).
- Pages are copied to ASCII-only filenames before upload (real OneBot 403s on CJK image paths).
- `typeset` runs a contract check first: misspelled slots (e.g. `p1_mini`), missing headline or
  chapters, and empty page slots are reported by name.

## Tests

```bash
node lib/mount.test.mjs      # host entry → effect → tools.register
node lib/smoke.mjs           # config loading + one real kernel call
```

## Known limits

- Requires a local Edge/Chrome (no bundled browser engine).
- OneBot 11 only; other chat sources need a new `fetch` implementation.
- The default template is tuned for Chinese newspaper typography.

MIT licensed. The bundled template relies on system CJK fonts — verify your font licensing before redistribution.
