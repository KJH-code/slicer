"""보고서 그림 공통 스타일 — NanumGothic 9pt, 300 dpi, 전폭 16cm / 반폭 7.8cm, tab10.

그림은 저장소의 실제 결과 JSON 에서만 그린다. manifest.json 은 slug 단위로 갱신한다.
"""

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIG_DIR = os.path.join(ROOT, "docs", "report", "figures")
MANIFEST = os.path.join(FIG_DIR, "manifest.json")
CM = 1 / 2.54
FULL_W = 16.0 * CM
HALF_W = 7.8 * CM
TAB10 = plt.get_cmap("tab10").colors


def setup():
    for path in ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                 "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"):
        if os.path.exists(path):
            font_manager.fontManager.addfont(path)
    plt.rcParams.update({
        "font.family": "NanumGothic", "font.size": 9, "axes.titlesize": 9,
        "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "legend.fontsize": 8, "axes.unicode_minus": False, "savefig.dpi": 300,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
        "axes.linewidth": 0.6, "lines.linewidth": 1.2,
    })


def panel_label(ax, s):
    ax.text(0.0, 1.08, s, transform=ax.transAxes, ha="left", va="bottom",
            fontsize=9, fontweight="bold")


def save(fig, slug, script, data_sources, desc, key_numbers):
    png = os.path.join(FIG_DIR, f"{slug}.png")
    fig.savefig(png, dpi=300, bbox_inches="tight", pad_inches=0.02)
    entries = []
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as fh:
            entries = json.load(fh)
    entries = [e for e in entries if e.get("slug") != slug]
    entries.append({"slug": slug, "png": os.path.relpath(png, ROOT),
                    "script": os.path.relpath(script, ROOT),
                    "data_sources": data_sources, "description": desc,
                    "key_numbers": key_numbers})
    entries.sort(key=lambda e: e["slug"])
    with open(MANIFEST, "w") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=1)
    print(f"저장: {os.path.relpath(png, ROOT)}")
