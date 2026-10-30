"""
s3io.py — S³-Slicer 배포 결과물 읽기 (자유도 사다리 실험의 '천장' 데이터).

S³-Slicer (Zhang et al. 2022, github.com/zhangty019/S3_DeformFDM) 본체는 Windows GUI
+ Intel oneMKL 이라 이 환경에서 돌릴 수 없다. 대신 저장소가 **결과물을 통째로
배포**한다:

  · `DataSet/TET_MODEL/<model>.tet`                   입력 사면체 메시
  · `DataSet/fabricationSource/<model>/waypoint/*.txt` 곡면 레이어 툴패스 점
        한 줄 = `x y z nx ny nz` (점, 그 점의 국소 빌드 방향 — 부호는 아래 ⚠)

그래서 S³ 를 돌리지 않고도 "S³ 가 이 모델에 준 국소 빌드 방향장"을 읽어, 우리와
**같은 자**(면 법선 vs 국소 빌드 방향, 45°)로 남은 서포트 % 를 잴 수 있다.

좌표 규약 (S³ 소스 `DeformTet.cpp` 에서 확인):
  · **Y 가 위다.** `_detectBottomTet` 가 `pp[1] < minHeight + threshold` 로 바닥을
    잡는다. 우리 파이프라인은 Z 가 위이므로 `y_up_to_z_up` 으로 돌린다.
  · 자기지지 각 `m_supportFreeAngle = 45.0` (`DeformTet.cpp:1099`), 판정은
    `_detectOverhangFace`: `-n·printDir < -sin(45°)`. 우리 `analytic.needs_support`
    의 `g < -sin(threshold)` 와 같은 규칙이다 — 자가 같다.
  · **바닥 사면체(`isBottomTet`)의 면은 오버행에서 뺀다.** 우리 해석식은 그런
    예외가 없어 평평한 바닥면을 서포트로 센다. 공정하게 비교하려면 양쪽 다
    같은 규칙을 써야 하므로 `bed_contact_mask` 로 **양쪽에서 같이 뺀다.**

⚠ 웨이포인트 법선의 부호. ring 첫 층의 법선 평균이 ≈ −Y 다. Y 가 위이므로 이것은
  빌드 방향(위)이 아니라 **노즐 방향(아래)** 이거나 레이어의 아래쪽 법선이다.
  `load_waypoints` 는 첫 층 법선 평균이 +위 가 되도록 전체 부호를 맞추고, 그
  판정 근거(첫 층 평균의 위 성분)를 함께 돌려준다 — 가정이 깨지면 숫자로 보인다.

.tet 형식 (실제 파일로 확인, ring.tet):
    줄1  "<N> vertices"
    줄2  "<M> tets"
    N 줄  x y z
    M 줄  "4 i j k l"   (0 기반 정점 인덱스)
"""

import os
import re

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from .config import THRESHOLD_DEG


# ─────────────────────────────────────────────────────────────
# .tet 읽기 + 경계면 추출
# ─────────────────────────────────────────────────────────────
def load_tet(path):
    """`.tet` → (vertices[N,3] float, tets[M,4] int, 0 기반)."""
    with open(path) as f:
        n_v = int(f.readline().split()[0])
        n_t = int(f.readline().split()[0])
        verts = np.loadtxt(f, max_rows=n_v, dtype=float)
        tets = np.loadtxt(f, max_rows=n_t, dtype=int)
    if verts.shape != (n_v, 3):
        raise ValueError(f"{path}: 정점 {verts.shape} ≠ ({n_v}, 3)")
    if tets.shape != (n_t, 5) or not np.all(tets[:, 0] == 4):
        raise ValueError(f"{path}: 사면체 줄 형식이 '4 i j k l' 이 아니다")
    tets = tets[:, 1:]
    if tets.min() < 0 or tets.max() >= n_v:
        raise ValueError(f"{path}: 인덱스 범위 밖 ({tets.min()}..{tets.max()})")
    return verts, tets


def boundary_mesh(verts, tets):
    """사면체 메시의 경계 삼각형 → trimesh (법선이 바깥을 향하도록 정렬).

    경계면 = 정확히 **한** 사면체에만 속한 면. 각 면의 바깥 방향은 그 사면체의
    나머지 정점(안쪽)이 법선의 반대쪽에 오도록 정한다 — 메시 전체를 다시
    orient 하지 않아도 면마다 국소적으로 정해지므로 비다양체여도 안전하다.
    """
    # 사면체 (a,b,c,d) 의 네 면: 반대 정점을 함께 기억
    opp = np.array([[3, 2, 1, 0]])
    face_idx = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])
    faces = tets[:, face_idx].reshape(-1, 3)                  # (4M, 3)
    opposite = tets[:, opp[0]].reshape(-1)                    # (4M,)
    key = np.sort(faces, axis=1)
    _, first, counts = np.unique(key, axis=0, return_index=True,
                                 return_counts=True)
    sel = first[counts == 1]
    b_faces = faces[sel]
    b_opp = opposite[sel]
    # 바깥 정렬: 법선·(반대정점 − 면중심) > 0 이면 뒤집는다
    p = verts[b_faces]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    inward = np.einsum("ij,ij->i", n, verts[b_opp] - p.mean(axis=1)) > 0
    b_faces[inward] = b_faces[inward][:, [0, 2, 1]]
    m = trimesh.Trimesh(vertices=verts.copy(), faces=b_faces, process=False)
    return m


def y_up_to_z_up(mesh):
    """S³ 의 Y-위 좌표를 우리 Z-위 좌표로: (x, y, z) → (x, −z, y). det = +1."""
    v = mesh.vertices
    nv = np.column_stack([v[:, 0], -v[:, 2], v[:, 1]])
    return trimesh.Trimesh(vertices=nv, faces=mesh.faces.copy(), process=False)


def y_up_to_z_up_points(pts):
    pts = np.asarray(pts, dtype=float)
    return np.column_stack([pts[:, 0], -pts[:, 2], pts[:, 1]])


def load_s3_model(tet_path):
    """`.tet` → Z-위로 돌린 경계 trimesh (XY 는 그대로, 바닥을 z=0 으로)."""
    verts, tets = load_tet(tet_path)
    m = y_up_to_z_up(boundary_mesh(verts, tets))
    m.apply_translation([0.0, 0.0, -m.bounds[0][2]])
    return m


# ─────────────────────────────────────────────────────────────
# 웨이포인트 (S³ 가 준 국소 빌드 방향장)
# ─────────────────────────────────────────────────────────────
_NUM = re.compile(r"(\d+)")


def _layer_key(name):
    mo = _NUM.search(os.path.basename(name))
    return int(mo.group(1)) if mo else -1


def load_waypoints(wp_dir, to_z_up=True):
    """`waypoint/*.txt` 전부 → dict(points[K,3], dirs[K,3], layer[K], sign_evidence).

    `dirs` 는 **위를 향하는 빌드 방향**으로 부호를 맞춘 단위벡터다. 기준은 첫 층
    (파일 번호 최소) 법선 평균의 위 성분 부호. `sign_evidence` 는 그 평균의 위
    성분(부호 맞추기 전) — |값| 이 1 에 가까워야 첫 층이 평면이라는 가정이 선다.
    """
    files = sorted((f for f in os.listdir(wp_dir) if f.endswith(".txt")),
                   key=_layer_key)
    if not files:
        raise FileNotFoundError(f"{wp_dir}: 웨이포인트 파일이 없다")
    pts, dirs, lay = [], [], []
    for f in files:
        if os.path.getsize(os.path.join(wp_dir, f)) == 0:
            continue                       # 빈 레이어 파일 (topopt 65.txt 등)
        a = np.loadtxt(os.path.join(wp_dir, f), dtype=float, ndmin=2)
        if a.shape[1] < 6:
            raise ValueError(f"{f}: 열이 6개 미만 ({a.shape[1]})")
        pts.append(a[:, :3])
        dirs.append(a[:, 3:6])
        lay.append(np.full(len(a), _layer_key(f)))
    pts = np.vstack(pts)
    dirs = np.vstack(dirs)
    lay = np.concatenate(lay)
    if to_z_up:
        pts = y_up_to_z_up_points(pts)
        dirs = y_up_to_z_up_points(dirs)
    nrm = np.linalg.norm(dirs, axis=1, keepdims=True)
    dirs = dirs / np.where(nrm > 1e-12, nrm, 1.0)
    first = lay == lay.min()
    up = float(dirs[first, 2].mean())
    if up < 0:
        dirs = -dirs
    return {"points": pts, "dirs": dirs, "layer": lay, "sign_evidence": up,
            "n_layers": int(len(np.unique(lay)))}


def face_build_dirs(mesh, wp, k=1):
    """면 중심마다 가장 가까운 웨이포인트 k 개의 빌드 방향 평균 → [F,3] 단위벡터.

    ⚠ 최근접 매핑이다. 얇은 벽에서는 반대편 면의 툴패스가 잡힐 수 있고, 그
      거리(`dist`)를 함께 돌려주므로 중앙값·최대값을 보고 판단할 것.
    """
    cent = mesh.vertices[mesh.faces].mean(axis=1)
    tree = cKDTree(wp["points"])
    dist, idx = tree.query(cent, k=k)
    if k == 1:
        d = wp["dirs"][idx]
    else:
        d = wp["dirs"][idx].mean(axis=1)
        dist = dist[:, 0]
    nrm = np.linalg.norm(d, axis=1, keepdims=True)
    return d / np.where(nrm > 1e-12, nrm, 1.0), dist


# ─────────────────────────────────────────────────────────────
# 공통 자 — 면 법선 vs 국소 빌드 방향
# ─────────────────────────────────────────────────────────────
def bed_contact_mask(mesh, height=0.3, nz_max=-0.9):
    """바닥 접촉 면: 중심 z ≤ z_min + height 이고 아래를 보는(n_z < nz_max) 면.

    S³ 가 `isBottomTet` 의 면을 오버행에서 빼므로 우리도 같은 것을 뺀다.
    우리 데모 모델(구·램프·funnel)은 바닥이 점이라 약 1% 안쪽만 걸린다.
    """
    cz = mesh.vertices[mesh.faces].mean(axis=1)[:, 2]
    return (cz <= mesh.bounds[0][2] + height) & (mesh.face_normals[:, 2] < nz_max)


def support_fraction_dirs(mesh, dirs, threshold_deg=THRESHOLD_DEG,
                          exclude=None):
    """면별 빌드 방향 `dirs[F,3]` 에 대한 남은 서포트 넓이 % — `analytic` 과 같은 자.

    g = n̂·b̂ (b̂ = 국소 빌드 방향, 위를 향함) < κ = −sin(threshold) 이면 서포트.
    균일 원뿔에서 b̂ = (sinθ·r̂, cosθ) 를 넣으면 `analytic.overhang_score` 의
    `n_z·cosθ + n_r·sinθ` 와 정확히 같다 (테스트가 강제).
    `exclude` 가 주어지면 그 면들은 분모·분자에서 모두 뺀다.
    """
    g = np.einsum("ij,ij->i", mesh.face_normals, dirs)
    need = g < -np.sin(np.radians(threshold_deg))
    areas = mesh.area_faces
    keep = np.ones(len(areas), dtype=bool) if exclude is None else ~exclude
    tot = areas[keep].sum()
    return float(areas[keep & need].sum() / tot * 100.0) if tot > 0 else 0.0


def profile_dirs(mesh, profile, direction="outward"):
    """가변각 프로필 θ(Z′) 의 면별 빌드 방향 — `analytic.support_fraction_profile`
    과 같은 '축상 근사'(면 중심 z 로 θ 조회). 같은 자로 프로필 칸을 재기 위한 것."""
    cent = mesh.vertices[mesh.faces].mean(axis=1)
    th = np.radians(np.asarray(profile.theta_at(cent[:, 2]), dtype=float))
    c = 1.0 if direction == "outward" else -1.0
    r = np.hypot(cent[:, 0], cent[:, 1])
    safe = np.where(r > 1e-9, r, 1.0)
    rx = np.where(r > 1e-9, cent[:, 0] / safe, 0.0)
    ry = np.where(r > 1e-9, cent[:, 1] / safe, 0.0)
    d = np.column_stack([c * np.sin(th) * rx, c * np.sin(th) * ry, np.cos(th)])
    return d / np.linalg.norm(d, axis=1, keepdims=True)


def cone_dirs(mesh, theta_deg, direction="outward"):
    """균일 원뿔각의 면별 빌드 방향 (strength.layer_normals 와 같은 식, 위 향함)."""
    th = np.radians(float(theta_deg))
    c = 1.0 if direction == "outward" else -1.0
    cent = mesh.vertices[mesh.faces].mean(axis=1)
    r = np.hypot(cent[:, 0], cent[:, 1])
    safe = np.where(r > 1e-9, r, 1.0)
    rx = np.where(r > 1e-9, cent[:, 0] / safe, 0.0)
    ry = np.where(r > 1e-9, cent[:, 1] / safe, 0.0)
    d = np.column_stack([c * np.sin(th) * rx, c * np.sin(th) * ry,
                         np.full(len(r), np.cos(th))])
    return d / np.linalg.norm(d, axis=1, keepdims=True)
