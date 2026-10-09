"""A 항목 에이전트 결과 파싱 + 코드 수치 대조.

- 재유도 3건: g_expr / kappa_expr / theta_star_expr 를 analytic.py 와 무작위 입력으로 대조
- 회의론자 3건: 숫자 failure_cases 를 코드에 돌려 formula_says 와 비교
- derivation_ko 원문은 파일로 떨군다 (docs/review 에 붙이기 위해)
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, "/home/user/slicer")
from conical import analytic  # noqa: E402
from conical.config import MAX_ANGLE_DEG, THRESHOLD_DEG  # noqa: E402

OUT = "/tmp/claude-0/-home-user/1f47eca2-dd3b-5dff-881a-936e8fb49377/tasks/wlmgisc6e.output"
SCRATCH = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(OUT))
res = data["result"]
print("logs:", data["logs"])
print("violators:", res.get("violators"))


class FakeMesh:
    """analytic.py 가 쓰는 속성만 흉내: face_normals, vertices, faces, area_faces.
    면 i 의 세 꼭짓점을 모두 중심점 c_i 에 두면 centroid = c_i 가 된다."""

    def __init__(self, normals, centroids):
        n = len(normals)
        self.face_normals = normals
        self.vertices = np.repeat(centroids, 3, axis=0)
        self.faces = np.arange(3 * n).reshape(n, 3)
        self.area_faces = np.ones(n)


rng = np.random.default_rng(20261008)
N = 20000
v = rng.normal(size=(N, 3))
normals = v / np.linalg.norm(v, axis=1, keepdims=True)
# 중심점: r 을 넓게 (0.01~50), 방위각 무작위, z 무작위. 축 위(r=0) 면도 몇 개 섞는다.
r = rng.uniform(0.01, 50.0, N)
phi = rng.uniform(0, 2 * math.pi, N)
cent = np.stack([r * np.cos(phi), r * np.sin(phi), rng.uniform(0, 30, N)], axis=1)
cent[:50, :2] = 0.0  # 축 위
mesh = FakeMesh(normals, cent)
nz = normals[:, 2]
nr = analytic.radial_normal(mesh)
kappa_code = -math.sin(math.radians(THRESHOLD_DEG))
theta_max = math.radians(MAX_ANGLE_DEG)

SAFE = {"np": np, "math": math, "__builtins__": {}}


def ev(expr, **kw):
    return eval(expr, SAFE, kw)


print("\n" + "=" * 70)
print("재유도 3건 — 코드 대조 (무작위 면 %d개, 축 위 50개 포함)" % N)
print("=" * 70)
for d in res["derivations"]:
    print(f"\n### {d['framing']}")
    print("tools_used:", d["tools_used"])
    print("prior_formula_seen:", d["prior_formula_seen"][:300])
    print("g_expr:", d["g_expr"])
    print("kappa_expr:", d["kappa_expr"], "| support:", d["support_condition"])
    print("theta_star_expr:", d["theta_star_expr"])
    # kappa
    try:
        k = float(ev(d["kappa_expr"], threshold_deg=THRESHOLD_DEG))
        print(f"  kappa: agent {k:.10f} vs code {kappa_code:.10f} diff {abs(k-kappa_code):.2e}")
    except Exception as e:  # noqa: BLE001
        print("  kappa eval 실패:", e)
    # g, 여러 각도·방향
    worst = 0.0
    for direction, c in (("outward", 1.0), ("inward", -1.0)):
        for deg in (0.0, 5.0, 12.5, 24.0, 30.0, 44.0):
            th = np.full(N, math.radians(deg))
            try:
                g_agent = ev(d["g_expr"], nz=nz, nr=nr, c=c, theta=th)
            except Exception as e:  # noqa: BLE001
                print("  g eval 실패:", e)
                worst = float("nan")
                break
            g_code = analytic.overhang_score(mesh, deg, direction)
            worst = max(worst, float(np.max(np.abs(g_agent - g_code))))
    print(f"  g: 최대 |차이| = {worst:.3e}  (12 각도·방향 조합)")
    # theta*
    for direction, c in (("outward", 1.0), ("inward", -1.0)):
        try:
            ts_agent = ev(d["theta_star_expr"], nz=nz, nr=nr, c=c, kappa=kappa_code,
                          theta_max=theta_max)
        except Exception as e:  # noqa: BLE001
            print(f"  theta* eval 실패 ({direction}):", e)
            continue
        ts_agent = np.asarray(ts_agent, dtype=float)
        with np.errstate(invalid="ignore"):
            ts_code = np.radians(analytic.critical_angle(mesh, direction, THRESHOLD_DEG,
                                                        MAX_ANGLE_DEG))
        both = ~np.isnan(ts_agent) & ~np.isnan(ts_code)
        only_agent = ~np.isnan(ts_agent) & np.isnan(ts_code)
        only_code = np.isnan(ts_agent) & ~np.isnan(ts_code)
        diff = float(np.max(np.abs(ts_agent[both] - ts_code[both]))) if both.any() else float("nan")
        print(f"  theta* [{direction}]: 둘 다 값 {both.sum()}개 최대|차이| {np.degrees(diff):.3e}° | "
              f"에이전트만 값 {only_agent.sum()} | 코드만 값 {only_code.sum()} | 둘 다 NaN {(np.isnan(ts_agent)&np.isnan(ts_code)).sum()}")
        if only_agent.any():
            idx = np.where(only_agent)[0][:4]
            for i in idx:
                b = c * nr[i]
                print(f"     예) nz={nz[i]:+.3f} c·nr={b:+.3f} → 에이전트 θ*={math.degrees(ts_agent[i]):.2f}°, 코드 NaN; "
                      f"g(θ*)={nz[i]*math.cos(ts_agent[i])+b*math.sin(ts_agent[i]):+.4f}, g(44°)={nz[i]*math.cos(theta_max)+b*math.sin(theta_max):+.4f}")
        if only_code.any():
            idx = np.where(only_code)[0][:4]
            for i in idx:
                print(f"     예) nz={nz[i]:+.3f} c·nr={c*nr[i]:+.3f} → 코드 θ*={math.degrees(ts_code[i]):.2f}°, 에이전트 NaN")
    # 원문 저장
    with open(os.path.join(SCRATCH, f"A_derivation_{d['framing']}.md"), "w") as f:
        f.write(f"# 재유도 — {d['framing']}\n\n")
        f.write(f"tools_used: {d['tools_used']}\n\nprior_formula_seen: {d['prior_formula_seen']}\n\n")
        f.write("## 가정\n" + "\n".join("- " + a for a in d["assumptions"]) + "\n\n")
        f.write("## 유도\n" + d["derivation_ko"] + "\n\n")
        f.write("## 못 고치는 조건\n" + d["unreachable_condition_ko"] + "\n\n")
        f.write("## 단조성\n" + d["monotonic_ko"] + "\n")

# 코드의 '못 고침' 게이트 자체를 정확 조건과 대조 (에이전트 식과 무관하게)
print("\n--- 코드 게이트 vs 정확 조건 (g(θ_max) ≥ κ) ---")
for direction, c in (("outward", 1.0), ("inward", -1.0)):
    with np.errstate(invalid="ignore"):
        ts_code = analytic.critical_angle(mesh, direction, THRESHOLD_DEG, MAX_ANGLE_DEG)
    need0 = nz < kappa_code
    fixable_exact = need0 & (nz * math.cos(theta_max) + c * nr * math.sin(theta_max) >= kappa_code)
    fixable_code = need0 & ~np.isnan(ts_code)
    print(f"  [{direction}] θ=0 서포트 필요 {need0.sum()} | 정확히 고칠 수 있음 {fixable_exact.sum()} | "
          f"코드가 고칠 수 있다 함 {fixable_code.sum()} | 코드가 놓친 것 {(fixable_exact & ~fixable_code).sum()} | "
          f"코드가 잘못 고칠 수 있다 함 {(~fixable_exact & fixable_code).sum()}")

print("\n" + "=" * 70)
print("회의론자 3건")
print("=" * 70)
for a in res["attacks"]:
    print(f"\n### {a['lens_key']}  ({a['lens']})")
    print("tools_used:", a["tools_used"], "| prior:", a["prior_formula_seen"][:200])
    print("숨은 가정:")
    for h in a["hidden_assumptions"]:
        print("  -", h["assumption"])
    print("실패 사례:")
    for fc in a["failure_cases"]:
        line = f"  - {fc['description'][:110]}"
        if not fc.get("needs_mesh") and all(k in fc for k in ("nz", "nr", "c", "theta_deg")):
            m1 = FakeMesh(np.array([[math.sqrt(max(0.0, 1 - fc['nz']**2 - fc['nr']**2)) * 0, fc['nr'], fc['nz']]]),
                          np.array([[1.0, 0.0, 0.0]]))  # x축 위 중심점 → r̂ = x̂, 법선 (0, nr, nz)? 아니다
            # r̂ = x̂ 이므로 법선의 x 성분이 n_r 이어야 한다. (n_r, n_t, n_z) 로 놓는다.
            nt = math.sqrt(max(0.0, 1 - fc['nz']**2 - fc['nr']**2))
            m1 = FakeMesh(np.array([[fc['nr'], nt, fc['nz']]]), np.array([[1.0, 0.0, 0.0]]))
            direction = "outward" if fc["c"] > 0 else "inward"
            code_need = bool(analytic.needs_support(m1, fc["theta_deg"], direction, THRESHOLD_DEG)[0])
            g = float(analytic.overhang_score(m1, fc["theta_deg"], direction)[0])
            line += (f"\n      입력 nz={fc['nz']} nr={fc['nr']} c={fc['c']:+.0f} θ={fc['theta_deg']}° → 코드 g={g:+.4f}, "
                     f"코드 서포트={code_need} | 에이전트가 말한 식의 답={fc['formula_says_needs_support']} | 물리={fc['physically_needs_support']}")
            if code_need != fc["formula_says_needs_support"]:
                line += "   ⚠ 에이전트의 '식의 답'이 코드와 다름"
        else:
            line += f"\n      [메시 필요] {fc.get('mesh_construction', '')[:200]}"
        line += f"\n      이유: {fc['reason'][:220]}"
        print(line)
    print("정답 아는 시험:")
    for t in a["known_answer_tests"]:
        print(f"  - {t['name']}: {t['construction'][:120]} → 기대 {t['expected'][:80]}")
    print("지표가 못 보는 것:")
    for w in a["what_metric_cannot_see"]:
        print("  -", w[:140])
    with open(os.path.join(SCRATCH, f"A_attack_{a['lens_key']}.json"), "w") as f:
        json.dump(a, f, ensure_ascii=False, indent=1)
