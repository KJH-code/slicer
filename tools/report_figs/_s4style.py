"""보고서 그림 공통 양식: NanumGothic 9pt, 300 dpi, 폭 16cm(전폭)/7.8cm(반폭), tab10, 제목 없음."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "report" / "figures"
CM = 1 / 2.54
FULL, HALF = 16.0 * CM, 7.8 * CM
TAB = plt.get_cmap("tab10").colors


def setup():
    for f in font_manager.findSystemFonts():
        if Path(f).name in ("NanumGothic.ttf", "NanumGothicBold.ttf"):
            font_manager.fontManager.addfont(f)
    plt.rcParams.update({
        "font.family": ["NanumGothic", "DejaVu Sans"], "font.size": 9, "axes.titlesize": 9,
        "axes.labelsize": 9, "legend.fontsize": 8, "xtick.labelsize": 8,
        "ytick.labelsize": 8, "axes.unicode_minus": False, "mathtext.fontset": "dejavusans", "savefig.dpi": 300,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.prop_cycle": matplotlib.cycler(color=TAB),
    })


def panel(ax, label):
    ax.text(-0.14, 1.03, label, transform=ax.transAxes, fontsize=9, fontweight="semibold",
            va="bottom", ha="left")


def log_ticks(ax):
    """로그 축 눈금을 10^n 으로 — 기본 형식(\\mathdefault)은 본문 글꼴을 써서 NanumGothic 에 없는
    마이너스 기호가 빠진다. mathtext(dejavusans) 로 직접 쓴다."""
    import math

    from matplotlib.ticker import FuncFormatter, LogLocator

    def fmt(v, _pos):
        if v <= 0:
            return ""
        e = math.log10(v)
        return f"$10^{{{int(round(e))}}}$" if abs(e - round(e)) < 1e-9 else ""
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(LogLocator(base=10))
        axis.set_major_formatter(FuncFormatter(fmt))


def save(fig, slug):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{slug}.png"
    fig.savefig(p, dpi=300, facecolor="white")
    return p
