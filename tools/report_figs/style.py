"""style.py — 보고서 그림 공통 스타일 · 저장 · manifest 기록.

규칙: NanumGothic 9pt, 300 dpi, 폭 16cm(전폭) / 7.8cm(반폭), 그림 안 제목 없음,
축 이름에 단위, tab10 색, 선 1.2pt, 옅은 격자, 패널 라벨 (a)(b).

    from tools.report_figs.style import setup, figure, panel_label, save
"""

import json
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
FIG_DIR = ROOT / "docs" / "report" / "figures"
MANIFEST = FIG_DIR / "manifest.json"

CM = 1 / 2.54
FULL = 16.0 * CM
HALF = 7.8 * CM
COLORS = plt.get_cmap("tab10").colors


def setup():
    names = {f.name for f in font_manager.fontManager.ttflist}
    if "NanumGothic" not in names:
        raise RuntimeError("NanumGothic 없음 — apt-get install -y fonts-nanum 후 "
                           "rm -rf ~/.cache/matplotlib")
    plt.rcParams.update({
        "font.family": "NanumGothic",
        "font.size": 9, "axes.labelsize": 9, "xtick.labelsize": 8,
        "ytick.labelsize": 8, "legend.fontsize": 8,
        "axes.unicode_minus": False,
        "lines.linewidth": 1.2,
        "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
        "axes.prop_cycle": plt.cycler(color=COLORS),
        "savefig.dpi": 300, "figure.dpi": 100,
        "legend.frameon": False,
        "mathtext.fontset": "dejavusans",
    })


def figure(width="full", height_cm=7.0, **kw):
    w = FULL if width == "full" else HALF
    return plt.subplots(figsize=(w, height_cm * CM), constrained_layout=True, **kw)


def panel_label(ax, letter):
    ax.text(0.0, 1.02, f"({letter})", transform=ax.transAxes, ha="left",
            va="bottom", fontsize=10, fontweight="normal")


def git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def file_commit(path):
    """그 파일을 마지막으로 바꾼 커밋 (데이터 출처 표기용)."""
    try:
        out = subprocess.check_output(["git", "log", "-1", "--format=%h", "--", str(path)],
                                      cwd=ROOT, text=True).strip()
        return out or "uncommitted"
    except Exception:
        return "unknown"


def save(fig, slug, script, sources, desc, key_numbers, extra=None):
    """PNG 저장 + manifest.json 항목 갱신(같은 slug 는 덮어씀, 나머지 항목은 그대로)."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    png = FIG_DIR / f"{slug}.png"
    fig.savefig(png, dpi=300)
    plt.close(fig)
    entries = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else []
    entry = {
        "slug": slug,
        "png": str(png.relative_to(ROOT)),
        "script": str(Path(script).resolve().relative_to(ROOT)),
        "data_sources": [{"path": s, "commit": file_commit(ROOT / s)
                          if (ROOT / s).exists() else "external"} if isinstance(s, str) else s
                         for s in sources],
        "description": desc,
        "key_numbers": key_numbers,
        "generated_at_commit": git_head(),
    }
    if extra:
        entry.update(extra)
    idx = [i for i, e in enumerate(entries) if e["slug"] == slug]
    if idx:                       # 같은 slug 는 제자리에서 바꾸고, 다른 세션의 항목 순서는 건드리지 않는다
        entries[idx[0]] = entry
    else:
        entries.append(entry)
    MANIFEST.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(f"saved {png.relative_to(ROOT)}")
    return png
