"""gapdata.py — gap_sample_results.json 읽기 + docs/gap_audit.md §9.3 표와의 대조.

그림 7·8 이 쓰는 값(모델별 미지지 길이 mm 세 가지, 평균|θ|)이 문서 표와 0.1mm·0.1° 안에서
같은지 확인한다. 다르면 AssertionError 로 멈춘다.
"""

import json
import re

from tools.report_figs.style import ROOT

JSON = "gap_sample_results.json"
DOC = "docs/gap_audit.md"


def load():
    d = json.loads((ROOT / JSON).read_text(encoding="utf-8"))
    out = {}
    for lh, rows in d["by_layer_height"].items():
        out[lh] = [{
            "model": r["model"],
            "uJ_angle": r["uniform"][0], "band2": r["band2"],
            "uJ_mm": r["uniform_J"]["mm"], "b2_mm": r["band2_measured"]["mm"],
            "ub_mm": r["uniform_bottom_angle"]["mm"],
            "uJ_mean": r["uniform_J"]["angle"], "b2_mean": r["band2_measured"]["angle"],
            "ub_mean": r["uniform_bottom_angle"]["angle"],
        } for r in rows]
    return out


def _doc_tables():
    text = (ROOT / DOC).read_text(encoding="utf-8")
    sec = text.split("### 9.3", 1)[1].split("### 9.4", 1)[0]
    tabs = {}
    for lh, head in (("0.4", "**층고 0.4mm**"), ("0.3", "**층고 0.3mm**")):
        part = sec.split(head, 1)[1]
        rows = []
        for line in part.splitlines()[1:]:
            if not line.startswith("|"):
                if rows:
                    break
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells[0] in ("모델",) or set(cells[0]) <= set("-"):
                continue
            mm = [float(c.split("/")[1]) for c in cells[3:6]]
            th = [float(x) for x in re.findall(r"([\d.]+)°", cells[6])]
            rows.append({"model": cells[0], "uJ_mm": mm[0], "b2_mm": mm[1], "ub_mm": mm[2],
                         "uJ_mean": th[0], "b2_mean": th[1]})
        tabs[lh] = rows
    return tabs


def check(data):
    tabs = _doc_tables()
    n = 0
    for lh in ("0.4", "0.3"):
        js = {r["model"]: r for r in data[lh]}
        assert len(tabs[lh]) == len(js) == 17, (lh, len(tabs[lh]), len(js))
        for t in tabs[lh]:
            j = js[t["model"]]
            for k in ("uJ_mm", "b2_mm", "ub_mm"):
                assert abs(round(j[k], 1) - t[k]) < 0.051, (lh, t["model"], k, j[k], t[k])
            for k in ("uJ_mean", "b2_mean"):
                assert abs(round(j[k], 1) - t[k]) < 0.051, (lh, t["model"], k, j[k], t[k])
            n += 1
    return n
