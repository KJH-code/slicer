"""analyze_gap_frame.py — 실험 A 의 사전등록 수치는 어느 '아래' 를 기준으로 했나.

## 왜

지지 판정이 저장소에 두 개 있고 **기준 프레임이 다르다.**

| | '아래' 의 정의 | 문턱 |
|---|---|---|
| `analytic.py` (예측) | **층 법선** b = sinθ·r̂ + cosθ·ẑ | 45° 고정, 층고 무관 |
| `toolpath.check_support` (검사기 A) | **연직(중력)** — 수평 ≤ w, 수직 (0, 1.5h] | 평면에서 atan(w/h): 0.3mm 56°, 0.4mm 48° |

REP5X 는 헤드 틸트식이다. 노즐 축이 층 법선이고 부품은 중력에 대해 고정이다.
비드가 눌리는 방향은 **노즐 축**(= 층 법선)이므로, 실험 A 를 REP5X 로 뽑으면
검사기 A 의 연직 창은 실제 기계와 다른 프레임에서 잰 것이 된다. 검사기 B 는
2026-09-19 에 공구 프레임으로 일반화됐지만(`tool_up`) 검사기 A 는 그대로다.

연직 창이 원뿔 층에서 만드는 인공물 하나: outward 원뿔에서 안쪽 페리미터는 같은 층
바깥 페리미터보다 `w·sinθ` 높다 → 수평 0.45mm·수직 창 안에 들어와 **같은 층 이웃이
'아래 지지' 로 세어진다.** 평면(θ=0)에서는 dz=0 이라 안 생긴다.

## 무엇을 재나

실험 A 의 네 파일(`examples/lamp_expA_*`)을 그대로 읽어, 같은 점 표본에 대해

* 프레임: 연직(현행) / 공구(층 법선)
* 수평 창: w(현행, 겹침 0 허용) / w/2(반 겹침) / t_n·tan45°(예측식과 같은 문턱, 공구 프레임만)
* 지지 모형: 낙관 / 비관(연쇄)

으로 '진짜 오버행 %p' 를 다시 낸다. 연직·w·1.5h 는 `toolpath.check_support` 와
점 단위로 같아야 한다(검산).

그리고 **표본 잡음**: 램프를 Z 축 둘레로 돌려(인필 격자·면 분할 위상이 바뀐다)
같은 프로필로 다시 뽑아 수치의 흩어짐을 잰다 — 지금 표는 전부 표본 1 개다.
좌표를 파일처럼 소수 3 자리로 적느냐(0.001mm)만 바꿔도 값이 얼마나 움직이는지도 본다.

**대조 프로필 둘** (판정 모델의 교란을 가르기 위한 것 — 채택 제안이 아니다):

* 균일 30° — 밴드2 의 아랫밴드와 같은 각. '밴드라서' 와 '아래가 30° 라서' 를 가른다
* 밴드2′ — 같은 [30°, 0°] 인데 블렌드를 Z′ 17.25~19.56 으로 올린 것. 현행 블렌드
  (16.35~18.66)의 원뿔 층은 큰 반경에서 구의 어깨까지 내려가 실제 층간격 배율이
  2.6 배가 된다(`analyze_gap_flow.py`). 17.25 부터는 원뿔이 구를 비켜 가 1.5 배로 지켜진다

판정 기준은 `docs/experiment_plan.md` 그대로다(오버행 %p 가 작은 쪽이 승). 이
스크립트는 새 기준을 만들지 않고 **프레임·창을 바꿨을 때 그 판정이 유지되는지**만 본다.

    python3 analyze_gap_frame.py            # 파일 4 개 + 대조 프로필 + 회전 표본 5 개 (약 10 분)
    python3 analyze_gap_frame.py --no-seeds
"""

import argparse
import json
import math
import sys

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from shapely.geometry import Point

from conical import gcode as gc
from conical.backtransform import backtransform
from conical.meshio import center_on_axis
from conical.planar_slicer import slice_mesh
from conical.profile import AngleProfile
from conical.toolpath import check_support, layer_cross_sections, sample_extrusions
from conical.transform import transform_cone_profile

W = 0.45
FILES = {
    (0.3, "균일 24°"): "examples/lamp_expA_uniform24_lh03.gcode",
    (0.3, "밴드2"): "examples/lamp_expA_band2_lh03.gcode",
    (0.4, "균일 24°"): "examples/lamp_expA_uniform24_lh04.gcode",
    (0.4, "밴드2"): "examples/lamp_expA_band2_lh04.gcode",
}
SEED_ROT_DEG = (0.0, 7.0, 13.0, 21.0, 33.0)
ZONES = (("아랫반구 z<8", -1e9, 8.0), ("윗반구 8~16.35", 8.0, 16.35),
         ("목 16.35~20", 16.35, 20.0), ("나팔 z>20", 20.0, 1e9))
BAND2_BPS = [(0.006392146150271098, 30.0), (16.34849550315555, 30.0),
             (18.657896642994718, 0.0), (30.0, 0.0)]
CONTROLS = {
    "균일 30°": [(0.0, 30.0)],
    "밴드2′ (블렌드 17.25~19.56)": [(0.0, 30.0), (17.25, 30.0), (19.56, 0.0),
                                    (30.0, 0.0)],
}


def load(path):
    with open(path) as fh:
        lines = fh.readlines()
    meta, start, end = None, 0, len(lines)
    for i, ln in enumerate(lines):
        if ln.startswith(";CONICAL_META"):
            meta = json.loads(ln.split(" ", 1)[1])
        if ln.startswith("; conical built-in planar slicer"):
            start = i
        if ln.startswith("; end"):
            end = i
    return meta, gc.parse(lines[start:end])


def frames(pts, prof, direction, h):
    """점마다 층 법선 b 와 실공간 층 두께 t_n = h·m·cosθ."""
    c = 1.0 if direction == "outward" else -1.0
    r = np.hypot(pts[:, 0], pts[:, 1])
    zw = prof.solve_forward(pts[:, 2], r, direction)
    th = np.radians(prof.theta_at(zw))
    safe = np.where(r > 1e-9, r, 1.0)
    rx, ry = pts[:, 0] / safe, pts[:, 1] / safe
    up = np.column_stack([c * np.sin(th) * rx, c * np.sin(th) * ry, np.cos(th)])
    m = prof.spacing_factor(zw, r, direction)
    return up, h * m * np.cos(th), th


def check_frame(pts, up, hwin, vwin, bed_h, chained):
    """`toolpath.check_support` 와 같은 판정을 임의 프레임에서.

    up[i] = 점 i 의 '위' 단위벡터. (0,0,1) 이면 현행 연직 판정과 같다.
    hwin/vwin 은 점별 배열(mm). G-code 순서상 앞선 점만 후보로 쓴다.
    """
    n = len(pts)
    sup = pts[:, 2] <= bed_h + 1e-9
    rad = float(np.sqrt(hwin.max() ** 2 + vwin.max() ** 2)) + 1e-6
    nbrs = cKDTree(pts).query_ball_point(pts, r=rad)
    for i in range(n):
        if sup[i]:
            continue
        nb = np.asarray(nbrs[i], dtype=int)
        nb = nb[nb < i]
        if chained and len(nb):
            nb = nb[sup[nb]]
        if not len(nb):
            continue
        d = pts[i] - pts[nb]
        dz = d @ up[i]
        lat = np.sqrt(np.maximum((d * d).sum(axis=1) - dz * dz, 0.0))
        sup[i] = bool(np.any((dz > 1e-9) & (dz <= vwin[i] + 1e-9)
                             & (lat <= hwin[i] + 1e-9)))
    return sup


def overhang_pct(pts, mid, kinds, lay, sup, wts, shift_xy=None):
    """미지지 페리미터 중 '아랫층 단면 밖' 의 무게 비율(%) = 진짜 오버행.

    shift_xy 를 주면 단면 포함 판정을 그만큼 옮긴 XY 로 한다 — 공구 프레임에서는
    '아랫층에 내린 발' 이 연직 투영이 아니라 −b 방향 투영이기 때문이다.
    """
    peri = kinds == 0
    tot = wts[peri].sum()
    sections = layer_cross_sections(pts, mid, kinds, lay, W)
    xy = pts[:, :2] if shift_xy is None else pts[:, :2] + shift_xy
    is_over = np.zeros(len(pts), dtype=bool)
    for i in np.where(peri & ~sup)[0]:
        below = sections.get(int(lay[i]) - 1)
        if below is None or not below.contains(Point(xy[i, 0], xy[i, 1])):
            is_over[i] = True
    zones = {name: float(wts[is_over & (pts[:, 2] >= lo) & (pts[:, 2] < hi)].sum()
                         / tot * 100.0) for name, lo, hi in ZONES}
    return (float(wts[is_over].sum() / tot * 100.0),
            float(wts[peri & ~sup].sum() / tot * 100.0), zones,
            float(wts[is_over].sum()), float(tot))


CONFIGS = [  # (이름, 프레임, 수평 창)
    ("연직·w (현행)", "vert", "w"),
    ("연직·w/2", "vert", "w2"),
    ("공구·w", "tool", "w"),
    ("공구·w/2", "tool", "w2"),
    ("공구·t_n (=예측식 45°)", "tool", "tn"),
]


def evaluate(items, meta, verify=False, configs=None):
    h = meta["layer_height"]
    prof = AngleProfile([tuple(b) for b in meta["profile"]])
    pts, mid, wts, kinds, lay = sample_extrusions(items, return_types=True,
                                                  return_layers=True)
    up_t, tn, th = frames(pts, prof, meta["direction"], h)
    n = len(pts)
    up_v = np.tile([0.0, 0.0, 1.0], (n, 1))
    # 공구 프레임에서 아랫층에 내린 발의 XY 이동 (−t_n·b 의 수평 성분)
    foot = -(tn[:, None]) * up_t[:, :2]
    out = {}
    for name, frame, hw in (configs or CONFIGS):
        up = up_v if frame == "vert" else up_t
        vwin = np.full(n, 1.5 * h)
        hwin = {"w": np.full(n, W), "w2": np.full(n, W / 2), "tn": tn}[hw]
        if hw == "tn":
            vwin = 1.5 * tn
        for label, chained in (("낙관", False), ("비관", True)):
            sup = check_frame(pts, up, hwin, vwin, h, chained)
            if verify and name.startswith("연직·w ("):
                ref, _ = check_support(pts, mid, wts, layer_height=h,
                                       require_supported_below=chained)
                diff = int((ref != sup).sum())
                assert diff == 0, f"검산 실패: check_support 와 {diff}점 다름"
            ov, un, zones, mm, tot = overhang_pct(
                pts, mid, kinds, lay, sup, wts, None if frame == "vert" else foot)
            out[f"{name}|{label}"] = {"overhang": ov, "peri_unsupported": un,
                                      "zones": zones, "overhang_mm": mm,
                                      "perimeter_mm": tot}
    out["m_range"] = [float((tn / (h * np.cos(th))).min()),
                      float((tn / (h * np.cos(th))).max())]
    if configs is None:
        # 연직 창의 인공물: 같은 층 이웃이 '아래 지지' 로 세어지는 비율
        out["same_layer_artifact"] = same_layer_share(pts, lay, kinds, wts, h)
    return out


def same_layer_share(pts, lay, kinds, wts, h):
    """연직·w·낙관에서, **같은 층 점만 빼면** 미지지가 되는 페리미터 비율(%)."""
    n = len(pts)
    peri = kinds == 0
    nbrs = cKDTree(pts).query_ball_point(pts, r=math.hypot(W, 1.5 * h) + 1e-6)
    only_same = np.zeros(n, dtype=bool)
    for i in np.where(peri & (pts[:, 2] > h + 1e-9))[0]:
        nb = np.asarray(nbrs[i], dtype=int)
        nb = nb[nb < i]
        if not len(nb):
            continue
        dz = pts[i, 2] - pts[nb, 2]
        hz = np.hypot(pts[i, 0] - pts[nb, 0], pts[i, 1] - pts[nb, 1])
        ok = (dz > 1e-9) & (dz <= 1.5 * h + 1e-9) & (hz <= W + 1e-9)
        if ok.any() and not (ok & (lay[nb] != lay[i])).any():
            only_same[i] = True
    return float(wts[only_same].sum() / wts[peri].sum() * 100.0)


def regenerate(mesh, prof, h, rot_deg, file_precision=True):
    """CLI 와 같은 경로(세분화 1.5mm → 정변환 → 내장 슬라이서 → 역변환).

    file_precision=True 면 G-code 줄로 적었다가 다시 읽는다(좌표 소수 3 자리) —
    실제로 프린터에 들어가는 것과 같은 수다.
    """
    m = mesh.copy()
    a = math.radians(rot_deg)
    R = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0],
                  [0, 0, 1]])
    m.vertices = m.vertices @ R.T
    v, f = trimesh.remesh.subdivide_to_size(m.vertices, m.faces, max_edge=1.5)
    warped = trimesh.Trimesh(vertices=transform_cone_profile(v, prof, "outward"),
                             faces=f, process=False)
    real, _ = backtransform(slice_mesh(warped, layer_height=h), prof, "outward")
    if file_precision:
        real = gc.parse([p.to_line() if k == "move" else p for k, p in real])
    return real


def meta_for(bps, h):
    return {"layer_height": h, "direction": "outward",
            "profile": [list(b) for b in bps]}


def verdict(u, b):
    return "밴드2" if b < u - 1e-9 else ("균일" if u < b - 1e-9 else "무승부")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-seeds", action="store_true")
    args = ap.parse_args()
    res = {"files": {}, "controls": {}, "precision": {}, "seeds": {}}
    metas = {}

    for (h, strat), path in FILES.items():
        meta, items = load(path)
        metas[(h, strat)] = meta
        res["files"][f"{h}|{strat}"] = evaluate(items, meta, verify=True)
    print("검산: 연직·w·1.5h 가 toolpath.check_support 와 점 단위로 일치 (낙관·비관, 4 파일)")

    # 대조 프로필 — 실험 A 파일과 같은 경로·같은 정밀도로 뽑는다
    mesh = center_on_axis(trimesh.load("examples/lamp.stl", force="mesh"))
    for h in (0.3, 0.4):
        for cname, bps in CONTROLS.items():
            items = regenerate(mesh, AngleProfile(bps), h, 0.0)
            res["controls"][f"{h}|{cname}"] = evaluate(items, meta_for(bps, h))

    names = ["균일 24°", "밴드2", *CONTROLS]

    def cell(h, strat, key):
        src = res["files"] if (h, strat) in FILES else res["controls"]
        return src[f"{h}|{strat}"][key]

    print("\n[실험 A + 대조] 진짜 오버행 %p — 프레임·수평 창을 바꿨을 때")
    print("  열: 균일 24° (기준) | 밴드2 (실험 A 파일) | 균일 30° | 밴드2′ ;  "
          "판정 = 밴드2 대 균일 24°")
    for h in (0.3, 0.4):
        print(f"  층고 {h}  실제 층간격 배율 m: "
              + ", ".join(f"{n} {cell(h, n, 'm_range')[0]:.2f}~"
                          f"{cell(h, n, 'm_range')[1]:.2f}" for n in names))
        for name, _f, _hw in CONFIGS:
            for label in ("낙관", "비관"):
                v = [cell(h, n, f"{name}|{label}")["overhang"] for n in names]
                print(f"   {name:<22}{label}  " + "  ".join(f"{x:7.3f}" for x in v)
                      + f"   {verdict(v[0], v[1])}")

    print("\n[분모] 같은 미지지 길이가 전략마다 다른 %p 가 된다 — 미지지 페리미터 mm "
          "/ 페리미터 총 길이 mm")
    for h in (0.3, 0.4):
        for key in ("연직·w (현행)|낙관", "공구·w/2|낙관"):
            cells = [cell(h, n, key) for n in names]
            print(f"  층고 {h} {key:<18} " + "   ".join(
                f"{n.split(' (')[0]} {c['overhang_mm']:5.1f} / {c['perimeter_mm']:.0f}"
                for n, c in zip(names, cells, strict=True)))

    print("\n[어디서 생기나] 현행(연직·w) 진짜 오버행 %p 의 높이 구역별 몫")
    for h in (0.3, 0.4):
        for label in ("낙관", "비관"):
            for n in names:
                c = cell(h, n, f"연직·w (현행)|{label}")
                print(f"  층고 {h} {label} {n:<26} 합 {c['overhang']:6.3f} = "
                      + " + ".join(f"{c['zones'][z[0]]:.3f}" for z in ZONES)
                      + f"   (페리미터 미지지 전체 {c['peri_unsupported']:.1f}%)")
    print("   구역 순서: " + " | ".join(z[0] for z in ZONES))

    print("\n[연직 창 인공물] 같은 층 이웃만으로 '지지' 가 된 페리미터 비율 (%)")
    for (h, strat) in FILES:
        print(f"  층고 {h} {strat:<8} "
              f"{res['files'][f'{h}|{strat}']['same_layer_artifact']:.1f}%")

    # 좌표 정밀도 — 같은 경로를 반올림 없이 판정하면
    print("\n[좌표 정밀도] 균일 24° 를 다시 뽑아 반올림 없이 판정 (연직·w, 낙관)")
    for h in (0.3, 0.4):
        meta = metas[(h, "균일 24°")]
        prof = AngleProfile([tuple(b) for b in meta["profile"]])
        vals = {}
        for fp in (True, False):
            items = regenerate(mesh, prof, h, 0.0, file_precision=fp)
            vals[fp] = evaluate(items, meta, configs=[CONFIGS[0]])[
                "연직·w (현행)|낙관"]["overhang"]
        ref = res["files"][f"{h}|균일 24°"]["연직·w (현행)|낙관"]["overhang"]
        assert abs(vals[True] - ref) < 1e-9, "파일 정밀도 재현 실패"
        res["precision"][str(h)] = {"3dp": vals[True], "full": vals[False]}
        print(f"  층고 {h}: 소수 3 자리(파일) {vals[True]:.3f}  →  반올림 없음 "
              f"{vals[False]:.3f}   ({vals[True] / max(vals[False], 1e-12):.2f} 배)")

    if not args.no_seeds:
        keys = ["연직·w (현행)|낙관", "연직·w (현행)|비관", "공구·w|낙관", "공구·w|비관"]
        print("\n[표본 잡음] 램프를 Z 둘레로 돌려 다시 뽑음 "
              f"(회전 {SEED_ROT_DEG}°, 파일 정밀도) — 진짜 오버행 %p, "
              "평균 ± 표준편차 [최소, 최대]")
        for h in (0.3, 0.4):
            store = {}
            for strat in ("균일 24°", "밴드2"):
                meta = metas[(h, strat)]
                prof = AngleProfile([tuple(b) for b in meta["profile"]])
                runs = []
                for rot in SEED_ROT_DEG:
                    items = regenerate(mesh, prof, h, rot)
                    r = evaluate(items, meta, configs=[CONFIGS[0], CONFIGS[2]])
                    runs.append({k: r[k]["overhang"] for k in keys})
                store[strat] = runs
                res["seeds"][f"{h}|{strat}"] = runs
            for k in keys:
                u = np.array([r[k] for r in store["균일 24°"]])
                b = np.array([r[k] for r in store["밴드2"]])
                wins = int((b < u - 1e-9).sum())
                print(f"  층고 {h} {k:<20} 균일24 {u.mean():6.3f} ± {u.std():5.3f} "
                      f"[{u.min():.3f}, {u.max():.3f}]   밴드2 {b.mean():6.3f} ± "
                      f"{b.std():5.3f} [{b.min():.3f}, {b.max():.3f}]   "
                      f"밴드2 승 {wins}/{len(u)}")

    with open("gap_frame_results.json", "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print("\n저장: gap_frame_results.json")


if __name__ == "__main__":
    sys.exit(main())
