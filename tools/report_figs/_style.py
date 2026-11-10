"""보고서 그림 공통 스타일 — NanumGothic 9pt, 300 dpi, 폭 16cm(전폭)/7.8cm(반폭), tab10,
그림 안 제목 없음, 패널 라벨 (a)(b). 그림은 이 저장소의 결과 JSON 에서만 그린다.

manifest: docs/report/figures/manifest.json 에 {slug, png, script, data_sources, 설명, 핵심 수치}.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "docs" / "report" / "figures"
MANIFEST = FIG_DIR / "manifest.json"
CM = 1 / 2.54
FULL, HALF = 16 * CM, 7.8 * CM
TAB10 = plt.get_cmap("tab10").colors

_FONT = Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf")


def setup():
    if not _FONT.exists():
        raise SystemExit("NanumGothic 없음: apt-get install -y fonts-nanum")
    font_manager.fontManager.addfont(str(_FONT))
    bold = _FONT.with_name("NanumGothicBold.ttf")
    if bold.exists():
        font_manager.fontManager.addfont(str(bold))
    plt.rcParams.update({
        "font.family": "NanumGothic", "font.size": 9, "axes.titlesize": 9,
        "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
        "legend.fontsize": 7, "axes.unicode_minus": False, "savefig.dpi": 300,
        "axes.prop_cycle": plt.cycler(color=TAB10)})


def panel_label(ax, text):
    ax.text(-0.02, 1.02, text, transform=ax.transAxes, ha="right", va="bottom",
            fontsize=9, fontweight="bold")


def family(name):
    """모델 이름 → (계열 번호, 계열 이름) — 21 모델을 tab10 색 다섯 개로 묶는다."""
    if name.startswith("허리3 로브"):
        return 3, "허리3 로브"
    if name.startswith("허리3 ×"):
        return 2, "허리3 ×λ"
    if name.startswith("허리 r="):
        return 1, "허리 r"
    if name == "구":
        return 0, "구"
    return 4, "데모"


def save(fig, slug, script, sources, desc, key_numbers):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    png = FIG_DIR / f"{slug}.png"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    items = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    items = [i for i in items if i.get("slug") != slug]
    items.append({"slug": slug, "png": str(png.relative_to(ROOT)),
                  "script": str(Path(script).resolve().relative_to(ROOT)),
                  "data_sources": sources, "설명": desc, "핵심 수치": key_numbers})
    items.sort(key=lambda i: i["slug"])
    MANIFEST.write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n")
    print(f"저장: {png.relative_to(ROOT)}")
