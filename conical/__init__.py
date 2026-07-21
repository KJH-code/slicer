"""
conical — 형상 적응형 원뿔(conical) 슬라이싱 알고리즘 패키지.

이 패키지 하나로 주요 기능을 바로 가져다 쓸 수 있다:

    from conical import analyze_overhangs, support_fraction, select_cone

각 단계별 모듈:
    config    : 설정값(임계각, 최대 각도, 탐색 간격) 한 곳에 모음
    transform : 원뿔 좌표 변환식 (RotBot 방식)
    overhang  : Stage 1 — 오버행 분석
    sweep     : Stage 2 — 각도별 남은 서포트 계산
    selector  : Stage 3 — 평가함수 J로 각도/방향 자동 결정
    meshio    : STL 로드 / 데모 구 생성 도우미
"""

from . import config
from .transform import transform_cone
from .overhang import analyze_overhangs, support_area_fraction, summarize
from .sweep import support_fraction, sweep_table
from .selector import evaluate_J, select_cone, k_sensitivity
from .meshio import load_mesh_or_demo
from .metrics import face_support_and_staircase
from .varangle import select_uniform, select_banded, select_fine
from .strength import face_strength, part_strength

__all__ = [
    "config",
    "transform_cone",
    "analyze_overhangs", "support_area_fraction", "summarize",
    "support_fraction", "sweep_table",
    "evaluate_J", "select_cone", "k_sensitivity",
    "load_mesh_or_demo",
    "face_support_and_staircase",
    "select_uniform", "select_banded", "select_fine",
    "face_strength", "part_strength",
]
