"""Build the presentation PDF from the deck files in this folder.

The deck is edited in the private Claude Slides artifact "개발팀 업무 과제"; this folder keeps a copy of
its files (deck.json, deck.css, slides/<id>.html) and the pictures (images/<blob id>.png) so the PDF can
be rebuilt on any computer with Microsoft Edge:

    venv\\Scripts\\python.exe docs\\presentation\\deck\\build_pdf.py

Writes docs/presentation/개발팀_업무_과제.pdf (16:9, one slide per page, speaker notes left out).
Edge draws the slides close to the Slides viewer, but connector arrows are approximated.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "개발팀_업무_과제.pdf"
EDGE_PATHS = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
              Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]

BASE_CSS = """
@page { size: 1920px 1080px; margin: 0 }
* { margin: 0 }
html, body { padding: 0; background: #fff }
body { font: 32px/1.2 sans-serif; counter-reset: page; -webkit-print-color-adjust: exact; print-color-adjust: exact }
body > section { width: 1920px; height: 1080px; overflow: hidden; box-sizing: border-box; position: relative;
  isolation: isolate; break-after: page; display: block }
aside { display: none !important }
h1 { font-size: 96px; font-weight: 600 } h2 { font-size: 64px; font-weight: 600 } h3 { font-size: 44px; font-weight: 600 }
p, li, h1, h2, h3, td, th { overflow-wrap: break-word; text-wrap: pretty }
table { width: 100%; border-collapse: separate; border-spacing: 0; border: solid #0003; border-width: 2px 0 0 2px }
th, td { padding: .35em .6em; text-align: left; border: solid #0003; border-width: 0 2px 2px 0 }
x-shape, x-icon, x-embed { display: block }
x-connector { display: block; flex: none; position: relative; border-top: 4px solid currentColor; height: 0 !important }
x-connector::after { content: ""; position: absolute; right: -4px; top: -13px; border: 11px solid transparent;
  border-left: 16px solid currentColor; border-right: 0 }
"""


def build_html() -> str:
    deck = json.loads((HERE / "deck.json").read_text(encoding="utf-8"))
    fonts = "".join(f'<link rel="stylesheet" href="{f["href"]}">' for f in deck["faces"].values() if "href" in f)
    slides = []
    for sid in deck["order"]:
        html = (HERE / "slides" / f"{sid}.html").read_text(encoding="utf-8")
        html = re.sub(r'/_blob/([0-9a-f]{32})', lambda m: (HERE / "images" / f"{m.group(1)}.png").as_uri(), html)
        slides.append(html)
    css = (HERE / "deck.css").read_text(encoding="utf-8")
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">{fonts}'
            f'<style>{BASE_CSS}</style><style>{css}</style></head><body>{"".join(slides)}</body></html>')


def main() -> None:
    edge = next((p for p in EDGE_PATHS if p.exists()), None)
    if edge is None:
        sys.exit("Microsoft Edge를 찾을 수 없습니다")
    page = HERE / "_build.html"
    page.write_text(build_html(), encoding="utf-8")
    try:
        subprocess.run([str(edge), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=15000", f"--print-to-pdf={OUT}", page.as_uri()],
                       check=True, timeout=180)
    finally:
        page.unlink(missing_ok=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
