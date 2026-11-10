"""analyze_gap_pipeline.py — 역변환 파이프라인에서 '실제로 틀리게 찍히는' 것.

`analyze_gap_flow.py` 가 낸 유량 오차의 **원인**을 코드 수준에서 분리하고,
경로 기하(현 분할)와 표면 덮임을 잰다. 저장소 코드는 고치지 않는다 — 고친 판을
이 스크립트 안에 따로 두고(`backtransform_fixed`) 차이만 잰다.

## 재는 것

① **E 회계** — `backtransform` 은 `dE = mv.e − e_prev` 로 입력 ΔE 를 구하는데,
   `e_prev` 가 **출력(보정된) 누적 E** 다. 입력 절대 E 에서 출력 절대 E 를 빼므로
   앞 이동에서 줄인 양이 다음 이동에 도로 붙는다. → 보정이 누적으로는 상쇄된다.
   입력 E / 의도한 E(ΔE·L/L′) / 실제 출력 E 를 나란히 낸다.
② **`G92 E0`** — 외부 슬라이서(PrusaSlicer 절대 E)는 리트랙션·층 전환마다 낸다.
   raw 줄이라 그대로 통과하고 `e_prev` 는 안 바뀐다. 합성 입력으로 직후 E 를 본다.
③ **현 오차** — 허용 현 길이 L = 2√(2·r·ε) 의 r 은 **끝점 반경의 평균**이다.
   그런데 변환공간 직선의 실공간 곡률은 '축까지의 최근접 거리' 가 정한다
   (z(t) = Z′ − c·sinθ·√(d²+t²)). 축 근처를 지나는 긴 직선(인필·트래블)에서는
   r_mid ≫ d 라 허용 길이가 과대하다. 정확 곡선과 실제 폴리라인의 최대 편차를 잰다.
④ **표면 덮임** — 내장 슬라이서에는 솔리드 상/하면이 없다. 이웃한 두 층의 바깥
   페리미터가 층 면을 따라 `페리미터 수 × w` 보다 멀리 떨어지면 그 사이 표면은
   희소 인필뿐이다. 어느 높이에서 얼마나 비는지 낸다.

    python3 analyze_gap_pipeline.py
"""

import json
import math
import sys

import numpy as np
import trimesh

from conical import gcode as gc
from conical.backtransform import _crosses_blend, _inv_point, backtransform
from conical.gcode import Move
from conical.meshio import center_on_axis
from conical.planar_slicer import slice_mesh
from conical.profile import AngleProfile
from conical.toolpath import sample_extrusions
from conical.transform import transform_cone_profile

W, PERIMS = 0.45, 2
CASES = [
    ("lamp 균일 24°", "examples/lamp.stl", [(0.0, 24.0)], 0.3),
    ("lamp 밴드2 30→0", "examples/lamp.stl",
     [(0.006392146150271098, 30.0), (16.34849550315555, 30.0),
      (18.657896642994718, 0.0), (30.0, 0.0)], 0.3),
    ("funnel 균일 26°", "examples/funnel.stl", [(0.0, 26.0)], 0.3),
]


def warped_items(stl, bps, h):
    mesh = center_on_axis(trimesh.load(stl, force="mesh"))
    prof = AngleProfile(bps)
    v, f = trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces, max_edge=1.5)
    warped = trimesh.Trimesh(vertices=transform_cone_profile(v, prof, "outward"),
                             faces=f, process=False)
    return slice_mesh(warped, layer_height=h), prof


def inv_many(P, prof, c=1.0):
    th = np.radians(prof.theta_at(P[:, 2]))
    return np.column_stack([P[:, 0] * np.cos(th), P[:, 1] * np.cos(th),
                            P[:, 2] - c * np.hypot(P[:, 0], P[:, 1]) * np.sin(th)])


def slope_at(prof, zw):
    for i in range(len(prof.zs) - 1):
        if prof.zs[i] <= zw <= prof.zs[i + 1]:
            return (prof.tans[i + 1] - prof.tans[i]) / (prof.zs[i + 1] - prof.zs[i])
    return 0.0


def backtransform_fixed(items, prof, c=1.0, chord_tol=0.05, max_sub=400,
                        jacobian=True):
    """제안하는 E 회계 — 입력 E 와 출력 E 를 **따로** 추적한다.

    jacobian=False: 문서가 말한 보정(ΔE × 실길이/변환길이)을 그대로 구현.
    jacobian=True : 체적 야코비안(ΔE × cos²θ·m, 재분할 구간별)으로 보정.
    `G92 E<n>` 은 두 누적값을 함께 n 으로 맞춘다. 경로 좌표는 현행과 같다.
    """
    blends = prof.blend_intervals()
    out = []
    X = Y = Zw = None
    e_in = e_out = 0.0
    for kind, mv in items:
        if kind != "move":
            if isinstance(mv, str) and mv.strip().upper().startswith("G92"):
                for word in mv.split(";", 1)[0].split()[1:]:
                    if word[0].upper() == "E":
                        e_in = e_out = float(word[1:])
            out.append((kind, mv))
            continue
        nX = mv.x if mv.x is not None else X
        nY = mv.y if mv.y is not None else Y
        nZ = mv.z if mv.z is not None else Zw
        dE = (mv.e - e_in) if mv.e is not None else None
        if None in (nX, nY, nZ) or X is None:
            if None not in (nX, nY, nZ):
                x, y, z = _inv_point(nX, nY, nZ, prof, c)
                out.append(("move", Move(g=mv.g, x=x, y=y, z=z, e=mv.e, f=mv.f)))
            else:
                out.append(("move", mv))
            if mv.e is not None:
                e_in = e_out = mv.e
            X, Y, Zw = nX, nY, nZ
            continue
        warp_len = math.dist((X, Y, Zw), (nX, nY, nZ))
        if dE is not None and warp_len < 1e-9:
            e_in, e_out = mv.e, e_out + dE
            out.append(("move", Move(g=mv.g, e=e_out, f=mv.f, extra=mv.extra)))
            continue
        x0, y0, z0 = _inv_point(X, Y, Zw, prof, c)
        x1, y1, z1 = _inv_point(nX, nY, nZ, prof, c)
        r_mid = 0.5 * (math.hypot(x0, y0) + math.hypot(x1, y1))
        allowed = 2.0 * math.sqrt(max(2.0 * r_mid * chord_tol, 1e-12))
        if blends and _crosses_blend(blends, Zw, nZ):
            allowed *= 0.5
        n = max(1, min(max_sub, math.ceil(
            math.dist((x0, y0, z0), (x1, y1, z1)) / max(allowed, 1e-9))))
        px, py, pz = x0, y0, z0
        for i in range(1, n + 1):
            t = i / n
            wx, wy, wz = X + (nX - X) * t, Y + (nY - Y) * t, Zw + (nZ - Zw) * t
            xi, yi, zi = _inv_point(wx, wy, wz, prof, c)
            e_val = None
            if dE is not None:
                tm = (i - 0.5) / n
                mx, my, mz = (X + (nX - X) * tm, Y + (nY - Y) * tm,
                              Zw + (nZ - Zw) * tm)
                if jacobian:
                    th = math.radians(float(prof.theta_at(mz)))
                    rr = math.hypot(mx, my) * math.cos(th)
                    k = math.cos(th) ** 2 * (1.0 - c * rr * slope_at(prof, mz))
                else:
                    k = math.dist((px, py, pz), (xi, yi, zi)) / (warp_len / n)
                e_out += dE / n * k
                e_val = e_out
            out.append(("move", Move(g=mv.g, x=xi, y=yi, z=zi, e=e_val, f=mv.f,
                                     extra=mv.extra)))
            px, py, pz = xi, yi, zi
        if dE is not None:
            e_in = mv.e
        X, Y, Zw = nX, nY, nZ
    return out


def last_e(items):
    return max((p.e for k, p in items if k == "move" and p.e is not None),
               default=0.0)


def e_accounting(items, prof):
    """입력 E / 의도(L/L′) / 야코비안 / 현행 출력 E."""
    real, _ = backtransform(items, prof, "outward")
    e_in = last_e(items)
    return {"E_in": e_in, "E_out_current": last_e(real),
            "E_intended_len_ratio": last_e(backtransform_fixed(items, prof,
                                                               jacobian=False)),
            "E_jacobian": last_e(backtransform_fixed(items, prof, jacobian=True)),
            "real": real}


def g92_demo():
    src = ["G1 X10 Y0 Z0.3 F1800", "G1 X10 Y10 E0.5", "G1 X0 Y10 E1.0",
           "G92 E0", "G1 X0 Y0 E0.5", "G1 X10 Y0 E1.0"]
    cur, _ = backtransform(gc.parse(src), 24.0, "outward")
    fix = backtransform_fixed(gc.parse(src), AngleProfile.constant(24.0),
                              jacobian=False)

    def after_reset(items):
        seen, es = False, []
        for k, p in items:
            if k == "raw" and p.startswith("G92"):
                seen = True
            elif seen and k == "move" and p.e is not None:
                es.append(round(p.e, 4))
        return es
    return after_reset(cur), after_reset(fix)


def chord_errors(items, prof, eps=0.05, dense=24):
    """이동마다: 실제 폴리라인(현행 분할 수 그대로)과 정확 곡선의 최대 편차."""
    rows = []
    X = Y = Zw = None
    e_prev = 0.0
    kind_now = 2
    for kind, mv in items:
        if kind != "move":
            if isinstance(mv, str) and mv.upper().startswith(";TYPE:"):
                kind_now = 0 if "PERIMETER" in mv.upper() else 1
            continue
        nX = mv.x if mv.x is not None else X
        nY = mv.y if mv.y is not None else Y
        nZ = mv.z if mv.z is not None else Zw
        if X is not None and None not in (nX, nY, nZ):
            A, B = np.array([X, Y, Zw]), np.array([nX, nY, nZ])
            if np.linalg.norm(B - A) > 1e-9:
                # 현행 함수가 이 이동을 몇 조각으로 쪼개는지 그대로 받아 온다
                two = [("move", Move(g=0, x=X, y=Y, z=Zw)),
                       ("move", Move(g=1, x=nX, y=nY, z=nZ))]
                n = len(backtransform(two, prof, "outward", chord_tol=eps)[0]) - 1
                t = np.linspace(0.0, 1.0, n * dense + 1)
                exact = inv_many(A + (B - A) * t[:, None], prof)
                knots = exact[::dense]
                j = np.minimum(np.arange(len(t)) // dense, n - 1)
                a, b = knots[j], knots[j + 1]
                ab = b - a
                u = np.clip(((exact - a) * ab).sum(1)
                            / np.maximum((ab * ab).sum(1), 1e-18), 0.0, 1.0)
                foot = a + ab * u[:, None]
                dev = np.linalg.norm(exact - foot, axis=1)
                i = int(dev.argmax())
                # 축까지의 최근접 거리(변환공간 XY)
                dxy = (B - A)[:2]
                tt = np.clip(-(A[:2] @ dxy) / max(dxy @ dxy, 1e-18), 0.0, 1.0)
                d_axis = float(np.linalg.norm(A[:2] + dxy * tt))
                extr = mv.e is not None and mv.e > e_prev + 1e-12
                rows.append((0 if not extr else 1 + kind_now, float(dev[i]),
                             float(foot[i, 2] - exact[i, 2]), d_axis,
                             float(np.linalg.norm(exact[-1] - exact[0])), n))
        if mv.e is not None:
            e_prev = mv.e
        X, Y, Zw = nX, nY, nZ
    return np.array(rows)


def skin_gaps(real, prof, h):
    """이웃 층 바깥 페리미터 사이의 '층 면 방향 거리' 가 벽 두께를 넘는 곳."""
    pts, _mid, _w, kinds, lay = sample_extrusions(real, return_types=True,
                                                  return_layers=True)
    r = np.hypot(pts[:, 0], pts[:, 1])
    ring = []
    for L in np.unique(lay[lay >= 0]):
        sel = np.where((lay == L) & (kinds == 0))[0]
        if len(sel) < 5:
            continue
        i = sel[np.argmax(r[sel])]
        ring.append((int(L), float(r[i]), float(pts[i, 2])))
    ring = np.array(ring)
    zw = prof.solve_forward(ring[:, 2], ring[:, 1], "outward")
    th = np.radians(prof.theta_at(zw))
    out = []
    for k in range(len(ring) - 1):
        if ring[k + 1, 0] != ring[k, 0] + 1:
            continue
        dr, dz = ring[k + 1, 1] - ring[k, 1], ring[k + 1, 2] - ring[k, 2]
        tk = 0.5 * (th[k] + th[k + 1])
        u = abs(dr * math.cos(tk) - dz * math.sin(tk))       # 층 면 방향
        if u > PERIMS * W + 1e-9:
            out.append({"layer": int(ring[k + 1, 0]), "z": float(ring[k + 1, 2]),
                        "r_from": float(ring[k, 1]), "r_to": float(ring[k + 1, 1]),
                        "in_layer_step_mm": float(u),
                        "open_mm": float(u - PERIMS * W)})
    return out, len(ring)


def main():
    res = {}
    cur, fix = g92_demo()
    res["g92"] = {"current": cur, "fixed": fix}
    print("② G92 E0 직후의 E (입력: 리셋 뒤 E0.5, E1.0 두 이동)")
    print(f"   현행 : {cur[:3]} … {cur[-1]}   ← 0 에서 {cur[0]} 로 튄 뒤 감소(리트랙트)")
    print(f"   고친 판: {fix[:3]} … {fix[-1]}")

    for name, stl, bps, h in CASES:
        items, prof = warped_items(stl, bps, h)
        acc = e_accounting(items, prof)
        real = acc.pop("real")
        ce = chord_errors(items, prof)
        gaps, nlay = skin_gaps(real, prof, h)
        res[name] = {"e": acc, "skin_gaps": gaps, "layers": nlay}
        print(f"\n[{name}]  층고 {h}")
        print("  ① E 합계(mm 필라멘트): "
              f"입력 {acc['E_in']:.2f} | 현행 출력 {acc['E_out_current']:.2f} "
              f"({acc['E_out_current'] / acc['E_in']:.3f}×) | 의도한 L/L′ 보정 "
              f"{acc['E_intended_len_ratio']:.2f} "
              f"({acc['E_intended_len_ratio'] / acc['E_in']:.3f}×) | 야코비안 "
              f"{acc['E_jacobian']:.2f} ({acc['E_jacobian'] / acc['E_in']:.3f}×)")
        print(f"     → 현행 출력은 필요량(야코비안)의 "
              f"{acc['E_out_current'] / acc['E_jacobian']:.3f} 배")
        print("  ③ 현 오차 (정확 곡선 − 실제 폴리라인, mm; ε=0.05)")
        res[name]["chord"] = {}
        for code, label in ((0, "트래블"), (1, "페리미터"), (2, "인필")):
            s = ce[ce[:, 0] == code]
            if not len(s):
                continue
            worst = s[s[:, 1].argmax()]
            row = {"moves": int(len(s)), "max": float(s[:, 1].max()),
                   "p99": float(np.percentile(s[:, 1], 99)),
                   "share_over_eps": float((s[:, 1] > 0.05).mean()),
                   "share_over_half_layer": float((s[:, 1] > h / 2).mean()),
                   "worst_axis_dist": float(worst[3]),
                   "worst_dz": float(worst[2]), "worst_len": float(worst[4]),
                   "worst_n": int(worst[5])}
            res[name]["chord"][label] = row
            print(f"     {label:<6} {row['moves']:>6}개  최대 {row['max']:.3f}  p99 "
                  f"{row['p99']:.3f}  ε 초과 {row['share_over_eps'] * 100:.2f}%  "
                  f"층고/2 초과 {row['share_over_half_layer'] * 100:.2f}%  "
                  f"| 최악: 축거리 {row['worst_axis_dist']:.2f}mm, 길이 "
                  f"{row['worst_len']:.1f}mm 를 {row['worst_n']}조각, "
                  f"수직 {row['worst_dz']:+.3f}mm")
        tot = sum(g["open_mm"] for g in gaps)
        print(f"  ④ 표면 덮임: {nlay} 층 중 {len(gaps)} 곳에서 이웃 층 바깥 "
              f"페리미터가 벽 두께({PERIMS}×{W}mm)보다 멀다 (열린 폭 합 {tot:.1f}mm)")
        for g in sorted(gaps, key=lambda d: -d["open_mm"])[:5]:
            print(f"     층 {g['layer']:>3} z={g['z']:.2f}  r {g['r_from']:.2f}→"
                  f"{g['r_to']:.2f}  층 면 방향 {g['in_layer_step_mm']:.2f}mm "
                  f"(열린 폭 {g['open_mm']:.2f})")

    with open("gap_pipeline_results.json", "w") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print("\n저장: gap_pipeline_results.json")


if __name__ == "__main__":
    sys.exit(main())
