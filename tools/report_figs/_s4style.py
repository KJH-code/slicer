"""보고서 그림 공통 양식: NanumGothic 9pt, 300 dpi, 폭 16 cm(전폭)/7.8 cm(반폭), tab10,
그림 안 제목 없음, 패널 라벨 (a)(b)…, 축 단위 표기. 데이터는 저장소의 결과 파일에서만."""

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
FULL = 16 * CM
HALF = 7.8 * CM
TAB10 = plt.get_cmap("tab10").colors


def setup():
    for f in font_manager.findSystemFonts():
        if os.path.basename(f) in ("NanumGothic.ttf", "NanumGothicBold.ttf"):
            font_manager.fontManager.addfont(f)
    plt.rcParams.update({
        "font.family": "NanumGothic", "font.size": 9, "axes.titlesize": 9,
        "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "legend.fontsize": 7.5, "axes.unicode_minus": False, "savefig.dpi": 300,
        "axes.prop_cycle": plt.cycler(color=TAB10),
    })


def panel(ax, label):
    """패널 라벨. label 이 'a' 면 '(a)', 'a) 구' 처럼 이미 괄호가 있으면 '(a) 구'."""
    text = f"({label})" if ")" not in label else f"({label}"
    ax.text(0.0, 1.02, text, transform=ax.transAxes, ha="left", va="bottom",
            fontsize=9, fontweight="bold")


def save(fig, slug, script, data_sources, description, key_numbers):
    os.makedirs(FIG_DIR, exist_ok=True)
    png = os.path.join(FIG_DIR, f"{slug}.png")
    fig.savefig(png, dpi=300)
    rel = lambda p: os.path.relpath(p, ROOT)  # noqa: E731
    entries = json.load(open(MANIFEST, encoding="utf-8")) if os.path.exists(MANIFEST) else []
    entries = [e for e in entries if e.get("slug") != slug]
    entries.append({"slug": slug, "png": rel(png), "script": rel(script),
                    "data_sources": data_sources, "description": description,
                    "key_numbers": key_numbers})
    entries.sort(key=lambda e: e["slug"])
    json.dump(entries, open(MANIFEST, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("saved", rel(png))
