#!/usr/bin/env python3
"""Build the static site published on GitHub Pages: one page with the latest report, the
scoreboard from the ledger, the bets waiting for settlement and the archive of all reports.

  python3 build_site.py [--out <project>/site]

Reads <project>/reports/*.html|*.md and <project>/data/ledger.jsonl; writes site/index.html,
copies the reports to site/reports/. The page reuses the report template's CSS so both look
alike; times are shown in Polish local time.
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import ledger
from bk_lib import now_utc, parse_time

PROJECT = ledger.PROJECT
REPORTS = PROJECT / "reports"
TEMPLATE = Path(__file__).resolve().parents[1] / "references" / "report-template.html"
PL = ZoneInfo("Europe/Warsaw")
NAME_RE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})_typy\.(html|md)$")

EXTRA_CSS = """
  .latest { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; }
  .latest h2 { margin-top: 0; }
  .btn { display: inline-block; margin-top: 12px; padding: 8px 16px; border-radius: 8px; background: var(--accent);
         color: var(--bg); text-decoration: none; font-weight: 600; }
  .archive li { margin: 4px 0; }
  .archive .when { font-variant-numeric: tabular-nums; }
"""


def report_time(path: Path) -> datetime | None:
    """Reports are named in Polish local time: 2026-09-24_1851_typy.html."""
    m = NAME_RE.search(path.name)
    if not m:
        return None
    return datetime.strptime(f"{m.group(1)} {m.group(2)}{m.group(3)}", "%Y-%m-%d %H%M").replace(tzinfo=PL)


def extract(path: Path) -> dict:
    """Title, summary paragraph and range chips of an HTML report (empty for Markdown)."""
    if path.suffix != ".html":
        return {"title": path.stem, "summary": "", "chips": ""}
    text = path.read_text(errors="replace")
    title = re.search(r"<h1>(.*?)</h1>", text, re.S)
    summary = re.search(r'<p class="summary">(.*?)</p>', text, re.S)
    nav = re.search(r'<nav class="ranges">(.*?)</nav>', text, re.S)
    chips = ""
    if nav:  # re-point the report's in-page anchors at the copied report
        chips = re.sub(r'href="#', f'href="reports/{path.name}#', nav.group(1))
    return {"title": re.sub(r"<[^>]+>", "", title.group(1)).strip() if title else path.stem,
            "summary": summary.group(1).strip() if summary else "", "chips": chips}


def css() -> str:
    m = re.search(r"<style>(.*?)</style>", TEMPLATE.read_text(), re.S)
    return (m.group(1) if m else "") + EXTRA_CSS


def fmt_pl(dt: datetime | None) -> str:
    return dt.astimezone(PL).strftime("%d.%m.%Y %H:%M") if dt else "—"


def open_bets(entries: list[dict]) -> str:
    rows = sorted((e for e in entries if e["status"] in ("open", "manual")), key=lambda e: e["start_utc"])
    if not rows:
        return '<p class="empty">Brak typów czekających na rozliczenie.</p>'
    out = []
    for e in rows:
        line = "" if e.get("line") is None else f" {e['line']}"
        kind = "" if e["kind"] == "pick" else " <em>(papier)</em>"
        state = "czeka" if e["status"] == "open" else "do ręcznego rozliczenia"
        out.append(f"<tr><td class=\"num\">{fmt_pl(parse_time(e['start_utc']))}</td>"
                   f"<td>{html.escape(e['home'])} – {html.escape(e['away'])}</td>"
                   f"<td>{e['market']} {e['selection']}{line}{kind}</td><td class=\"num\">{e['odds']}</td>"
                   f"<td class=\"num\">{e['p_est']:.2f}</td><td>{state}</td></tr>")
    return ("<div class=\"table-wrap\"><table><thead><tr><th>Start (PL)</th><th>Mecz</th><th>Zakład</th>"
            "<th>Kurs</th><th>p_est</th><th>Status</th></tr></thead><tbody>" + "".join(out) + "</tbody></table></div>")


def build(out_dir: Path) -> Path:
    reports = sorted((p for p in REPORTS.glob("*_typy.*") if report_time(p)), key=report_time, reverse=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "reports").mkdir(exist_ok=True)
    for p in reports:
        shutil.copy2(p, out_dir / "reports" / p.name)
    (out_dir / ".nojekyll").write_text("")

    entries = ledger.load()
    stats = ledger.html_fragment(ledger.build_stats(entries))
    if reports:
        latest, info = reports[0], extract(reports[0])
        latest_html = (f"<section class=\"latest\"><h2>Najnowszy raport — {fmt_pl(report_time(latest))}</h2>"
                       f"<p class=\"meta\">{html.escape(info['title'])}</p>"
                       f"<p class=\"summary\">{info['summary']}</p>"
                       f"<nav class=\"ranges\">{info['chips']}</nav>"
                       f"<a class=\"btn\" href=\"reports/{latest.name}\">Otwórz pełny raport</a></section>")
    else:
        latest_html = '<p class="empty">Nie ma jeszcze żadnego raportu.</p>'
    archive = "".join(f"<li><span class=\"when\">{fmt_pl(report_time(p))}</span> — "
                      f"<a href=\"reports/{p.name}\">{html.escape(extract(p)['title'])}</a></li>" for p in reports)

    page = f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Typy bukmacherskie</title>
<style>{css()}</style>
</head>
<body>
<main>
  <header>
    <h1>Typy bukmacherskie</h1>
    <p class="meta">Raporty generowane automatycznie przez Claude kilka razy dziennie; każdy typ jest później
    rozliczany, a skuteczność liczona poniżej. Ostatnia aktualizacja strony: {fmt_pl(now_utc())}.</p>
    <p class="warn">Kursy się zmieniają — sprawdź je u bukmachera przed postawieniem zakładu. Graj odpowiedzialnie.</p>
  </header>
  {latest_html}
  {stats}
  <section>
    <h2>Czekają na rozliczenie</h2>
    {open_bets(entries)}
  </section>
  <section>
    <h2>Archiwum raportów</h2>
    <ul class="archive">{archive}</ul>
  </section>
</main>
</body>
</html>
"""
    index = out_dir / "index.html"
    index.write_text(page)
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(PROJECT / "site"))
    args = ap.parse_args()
    print(f"[site] {build(Path(args.out))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
