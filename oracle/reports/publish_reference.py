"""Render docs/mechanics-reference-galaxy-sovereign.md as a self-contained HTML page for the artifact.
Small purpose-built Markdown subset: headings, paragraphs, nested bullet/numbered lists, tables,
**bold**, `code`, horizontal rules. Status marks become styled chips."""
import html, re, sys
from pathlib import Path

SRC = Path(sys.argv[1])
OUT = Path(sys.argv[2])
CHIPS = {"✅": ("ok", "Confirmed"), "⏳": ("wait", "Pending"), "❓": ("open", "Open")}


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    for mark, (cls, label) in CHIPS.items():
        t = t.replace(mark, f'<span class="chip {cls}" title="{label}">{label}</span>')
    return t


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def render(md):
    lines = md.splitlines()
    out, toc = [], []
    i = 0
    stack = []  # open lists: (indent, tag)

    def close_lists(to_indent=-1):
        while stack and stack[-1][0] > to_indent:
            out.append(f"</li></{stack.pop()[1]}>")

    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,4}) (.*)", ln)
        if m:
            close_lists()
            lvl, text = len(m.group(1)), m.group(2)
            sid = slug(re.sub(r"[✅⏳❓]", "", text))
            if lvl == 2:
                toc.append((sid, re.sub(r"[✅⏳❓]|\(.*?\)|/", "", text).strip()))
            out.append(f'<h{lvl} id="{sid}">{inline(text)}</h{lvl}>')
            i += 1
            continue
        if ln.strip() == "---":
            close_lists()
            out.append("<hr>")
            i += 1
            continue
        if ln.lstrip().startswith("|"):
            close_lists() if not stack else None
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
            t = ['<div class="tbl"><table><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"]
            for r in body:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
            continue
        m = re.match(r"^(\s*)([-*]|\d+\.) (.*)", ln)
        if m:
            ind = len(m.group(1))
            tag = "ol" if m.group(2)[0].isdigit() else "ul"
            if stack and stack[-1][0] == ind:
                out.append("</li>")
            elif stack and stack[-1][0] > ind:
                close_lists(ind)
                out.append("</li>")
            if not stack or stack[-1][0] < ind:
                out.append(f"<{tag}>")
                stack.append((ind, tag))
            out.append(f"<li>{inline(m.group(3))}")
            i += 1
            continue
        if stack and ln.startswith(" "):  # continuation inside a list item
            out.append(" " + inline(ln.strip()))
            i += 1
            continue
        close_lists()
        para = [ln.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\s*[-*] |\s*\d+\. |\||---)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
    close_lists()
    return "\n".join(out), toc


md = SRC.read_text()
title_line = md.splitlines()[0].lstrip("# ").strip()
body_md = "\n".join(md.splitlines()[1:])
body, toc = render(body_md)
nav = "".join(f'<a href="#{s}">{html.escape(t)}</a>' for s, t in toc)

page = f"""<title>BC Combat Mechanics</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: a technical-manual page; sticky section index on wide screens, single column on phones. */
:root {{
  --bg: #f6f7f9; --panel: #ffffff; --fg: #1b2230; --muted: #5b6577; --rule: #d9dee6;
  --accent: #b36b00; --accent-soft: #fbefdc;
  --ok: #1f7a4d; --ok-bg: #e2f3ea; --wait: #8a5a00; --wait-bg: #fcefd6; --open: #4a55a2; --open-bg: #e7e9f7;
  --display: "IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
  --body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #11151c; --panel: #171c25; --fg: #e3e7ee; --muted: #9aa4b5; --rule: #2a3240;
  --accent: #f0a640; --accent-soft: #2c2214;
  --ok: #6fd3a0; --ok-bg: #16301f; --wait: #f2c46b; --wait-bg: #33270f; --open: #a8b1f0; --open-bg: #22264a; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #11151c; --panel: #171c25; --fg: #e3e7ee; --muted: #9aa4b5; --rule: #2a3240;
  --accent: #f0a640; --accent-soft: #2c2214;
  --ok: #6fd3a0; --ok-bg: #16301f; --wait: #f2c46b; --wait-bg: #33270f; --open: #a8b1f0; --open-bg: #22264a; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--fg); font: 15px/1.6 var(--body); }}
.wrap {{ max-width: 1180px; margin: 0 auto; padding-inline: 16px; padding-block: 28px 64px;
  display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 40px; }}
header.top {{ grid-column: 1 / -1; border-bottom: 2px solid var(--accent); padding-bottom: 18px; }}
header.top .eyebrow {{ font: 600 12px/1 var(--display); letter-spacing: .14em; text-transform: uppercase; color: var(--accent); }}
header.top h1 {{ font: 600 clamp(28px, 4vw, 40px)/1.1 var(--display); margin: 8px 0 6px; text-wrap: balance; }}
header.top p {{ color: var(--muted); margin: 0; max-width: 70ch; }}
nav.toc {{ position: sticky; top: calc(env(safe-area-inset-top, 0px) + 20px); align-self: start;
  display: flex; flex-direction: column; gap: 2px; font: 500 13.5px/1.35 var(--display); }}
nav.toc .lbl {{ font-size: 11px; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); margin-bottom: 6px; }}
nav.toc a {{ color: var(--fg); text-decoration: none; padding: 5px 8px; border-radius: 4px; }}
nav.toc a:hover, nav.toc a:focus-visible {{ background: var(--accent-soft); color: var(--accent); outline: none; }}
main {{ min-width: 0; max-width: 820px; }}
h2 {{ font: 600 24px/1.25 var(--display); margin: 44px 0 12px; padding-top: 10px; border-top: 1px solid var(--rule); text-wrap: balance; scroll-margin-top: 16px; }}
h3 {{ font: 600 17px/1.3 var(--display); margin: 26px 0 8px; color: var(--fg); scroll-margin-top: 16px; }}
h4 {{ font: 600 15px/1.3 var(--display); margin: 28px 0 8px; color: var(--accent); letter-spacing: .02em; }}
p, li {{ max-width: 72ch; }}
ul, ol {{ padding-left: 1.3em; margin: 6px 0 12px; }}
li {{ margin: 3px 0; }}
li > ul, li > ol {{ margin: 4px 0; }}
strong {{ font-weight: 600; }}
code {{ font: 13px var(--mono); background: var(--accent-soft); padding: 1px 5px; border-radius: 3px; overflow-wrap: anywhere; }}
hr {{ border: 0; border-top: 1px solid var(--rule); margin: 28px 0; }}
.tbl {{ overflow-x: auto; margin: 10px 0 18px; border: 1px solid var(--rule); border-radius: 6px; background: var(--panel); }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; font-variant-numeric: tabular-nums; }}
th {{ font: 600 12px/1.3 var(--display); letter-spacing: .04em; text-transform: uppercase; color: var(--muted);
  text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--rule); white-space: nowrap; }}
td {{ padding: 7px 10px; border-bottom: 1px solid var(--rule); vertical-align: top; }}
tr:last-child td {{ border-bottom: 0; }}
.chip {{ display: inline-block; font: 600 10.5px/1 var(--display); letter-spacing: .08em; text-transform: uppercase;
  padding: 4px 7px 3px; border-radius: 3px; vertical-align: 2px; white-space: nowrap; }}
.chip.ok {{ color: var(--ok); background: var(--ok-bg); }}
.chip.wait {{ color: var(--wait); background: var(--wait-bg); }}
.chip.open {{ color: var(--open); background: var(--open-bg); }}
@media (max-width: 860px) {{
  .wrap {{ grid-template-columns: minmax(0, 1fr); gap: 20px; }}
  nav.toc {{ position: static; flex-direction: row; flex-wrap: wrap; }}
  nav.toc .lbl {{ width: 100%; }}
}}
@media (prefers-reduced-motion: no-preference) {{ html {{ scroll-behavior: smooth; }} }}
</style>
<div class="wrap">
  <header class="top">
    <div class="eyebrow">Star Trek: Bridge Commander · measured from the original engine</div>
    <h1>{html.escape(title_line)}</h1>
    <p>Every rule below comes from instrumented runs of the original game. <span class="chip ok">Confirmed</span> measured; <span class="chip open">Open</span> not yet answered.</p>
  </header>
  <nav class="toc" aria-label="Sections"><div class="lbl">Sections</div>{nav}</nav>
  <main>
{body}
  </main>
</div>
"""
OUT.write_text(page)
print(f"wrote {OUT} ({len(page)} bytes, {len(toc)} sections)")
