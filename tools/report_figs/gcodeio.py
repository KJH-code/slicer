"""gcodeio.py — 보고서 그림용 G-code 읽기 (압출 이동만, 층 주석 기준).

`; layer k z=Z′` 주석 뒤의 G0/G1 을 읽어, E 가 늘어난 이동을 압출 선분으로 모은다.
기계 시작 G-code(프라임 선 등)는 첫 `; layer` 앞이라 들어가지 않는다.
"""

import json
import re

import numpy as np

_LAYER = re.compile(r"^;\s*layer\s+(\d+)\s+z=([-\d.]+)")
_WORD = re.compile(r"([XYZEFBC])([-+]?\d*\.?\d+)")


def read(path):
    """→ meta(dict|None), layers: dict k → {"zp": Z′, "seg": (N,2,3) 압출 선분, "b": (N,) B각, "de": (N,) E 증가}."""
    meta = None
    layers = {}
    cur = None
    pos = {"X": None, "Y": None, "Z": None, "B": 0.0, "C": 0.0}
    e = 0.0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if s.startswith(";CONICAL_META"):
                meta = json.loads(s.split(";CONICAL_META", 1)[1])
                continue
            mo = _LAYER.match(s)
            if mo:
                cur = int(mo.group(1))
                layers[cur] = {"zp": float(mo.group(2)), "seg": [], "b": [], "de": []}
                continue
            code = s.split(";", 1)[0].strip()
            if code.startswith("G92"):
                for k, v in _WORD.findall(code):
                    if k == "E":
                        e = float(v)
                    elif k in pos:
                        pos[k] = float(v)
                continue
            if not (code.startswith("G1 ") or code.startswith("G0 ")):
                continue
            w = dict(_WORD.findall(code))
            prev = (pos["X"], pos["Y"], pos["Z"])
            for k in ("X", "Y", "Z", "B", "C"):
                if k in w:
                    pos[k] = float(w[k])
            e_new = float(w["E"]) if "E" in w else e
            extr = e_new > e + 1e-9 and any(k in w for k in "XYZ")
            de = e_new - e
            e = e_new
            if extr and cur is not None and None not in prev:
                layers[cur]["seg"].append((prev, (pos["X"], pos["Y"], pos["Z"])))
                layers[cur]["b"].append(pos["B"])
                layers[cur]["de"].append(de)
    out = {}
    for k, d in layers.items():
        if d["seg"]:
            out[k] = {"zp": d["zp"], "seg": np.array(d["seg"], dtype=float),
                      "b": np.array(d["b"], dtype=float),
                      "de": np.array(d["de"], dtype=float)}
    return meta, out
