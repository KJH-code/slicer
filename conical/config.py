"""
config.py — 알고리즘 '손잡이(설정값)'를 한 곳에 모아둔 파일.

여기 값만 바꾸면 전체 동작이 바뀐다. 코드 여기저기를 고칠 필요가 없다.
발표 때 이렇게 말할 수 있게 하려는 것: "튜닝할 값은 전부 config.py 한 곳에 있습니다."
"""

# 오버행 판정 임계각(도).
#   이 각도보다 심하게 '아래를 보는' 면은 서포트가 필요하다고 본다.
#   보통 FDM 프린터는 45°까지는 서포트 없이 출력되므로 기본값 45.
THRESHOLD_DEG = 45.0

# 하드웨어가 허용하는 최대 원뿔 각도(도). 각도 탐색은 여기까지만 한다.
#   · 3축 프린터만 사용   → 25 정도
#   · Open5x/Rep5x 사용   → U축 실제 구동 범위로 교체할 것 (아직 확인 필요!)
#   ⚠ 하드코딩하지 말고 반드시 이 설정값을 쓸 것.
MAX_ANGLE_DEG = 44

# 각도 탐색 간격(도). 2면 0,2,4,...44 를 훑는다. 작을수록 촘촘하지만 느리다.
ANGLE_STEP = 2


# ─────────────────────────────────────────────────────────────
# 각도 관례 — 실제 슬라이서와의 정합 (발표/논문 인용용)
# ─────────────────────────────────────────────────────────────
# 이 코드의 오버행 각도 정의: overhang_angle = arcsin(-n_z)
#   0° = 수직 벽,  90° = 수평 천장,  임계각을 '초과'하면 서포트 필요.
# 실제 슬라이서 관례와의 대응(오픈소스 소스코드 기준으로 확인):
#   · Cura "Support Overhang Angle"  : 완전히 동일. '수직 기준' 각도이고
#       임계각 '초과' 시 서포트. Cura 기본값 50°(과거 45°). → 우리와 1:1.
#   · PrusaSlicer / SuperSlicer / OrcaSlicer : '여집합'.
#       이들은 '수평 기준' 경사각을 쓰고, 경사각이 임계각 '미만'일 때 서포트.
#       따라서  prusa_threshold ≈ 90 − (우리 임계각).  Orca 기본값 30°.
#   (출처: CuraEngine src/support.cpp, PrusaSlicer PrintConfig.cpp /
#          Support/SupportMaterial.cpp, OrcaSlicer PrintConfig.cpp. docs/slicer_conventions.md 참고)

def ours_to_prusa(threshold_deg):
    """우리(=Cura) 임계각을 PrusaSlicer/Orca 관례(수평 기준)로 변환."""
    return 90.0 - threshold_deg


def prusa_to_ours(prusa_threshold_deg):
    """PrusaSlicer/Orca 관례(수평 기준) 임계각을 우리(=Cura) 관례로 변환."""
    return 90.0 - prusa_threshold_deg
