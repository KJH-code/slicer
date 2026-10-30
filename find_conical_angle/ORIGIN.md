# find_conical_angle — 출처와 이 폴더의 규칙

이 폴더는 팀메 저장소 **26037-arch/find_conical_angle** 의 사본 위에 우리 검증 도구를
잇는 다리와 수정 이력을 얹은 것이다. 바깥의 `conical/` 패키지와 실험 스크립트는
**그대로 두고**, 원뿔각 탐색 알고리즘만 여기서 팀메 것을 쓰고 고쳐 간다 (2026-10-30 결정).

| | |
|---|---|
| 원본 | https://github.com/26037-arch/find_conical_angle |
| 가져온 커밋 | `0d113b265cc242350c2cfc50d18c8bb333965340` (2026-07-26 "밴드 구조 출력") |
| 가져온 날 | 2026-10-30 |
| 원본 라이선스 | 파일 없음. 같은 R&E 팀의 코드이고 저자 표시를 유지한다 |
| 그대로인 것 | `conical_slicing/`, `analyze_stl.py`, `batch_experiment*.py`, `config.json`, `batch_config.json`, `models/`, `single_model/`, `tests/`, `README.md` |
| 우리가 보탠 것 | `ORIGIN.md`(이 파일), `NOTES.md`(예측·결과), `bridge.py`, `evaluate.py`, `tests_bridge/` |

## 가져올 때의 상태

* 원본 `pytest -q`: **27 통과 / 7 실패** (이 환경, numpy 2.5, trimesh 4). 실패는 전부
  원본 테스트가 코드보다 오래된 것이다 — 예: `test_q_and_kappa_use_downward_boundary_area_ratio`
  는 `q = A_down/A` 를 기대하는데 코드는 `q = support_boundary/√A_down` 이다(`mesh.py`
  `find_overhang_components`). README 의 "q = B/√A" 와도 다르다. **문서·테스트·코드 세
  군데가 서로 다르다**는 것을 기록해 둔다. 원본 테스트는 바깥 `pytest tests/` 에 안
  잡히므로 기준선(141개)을 깨지 않는다.
* ruff: 원본 파일은 저장소 규칙(import 정렬 등)에 안 맞는다. `ruff.toml` 에서 원본
  파일만 제외하고 우리가 보탠 파일은 검사한다.

## 알고리즘 요약 (원본, 코드로 확인)

1. `mesh.py prepare_mesh` — 면 분류: 바닥(`z≈bed_z`) / 퇴화 / **아래보기**(외적 z<0) /
   나머지. 허용오차 격자로 변 키를 만들어 공유 변 그래프를 세운다.
2. `find_overhang_components` — 아래보기 면의 BFS 연결성분. 성분마다 바닥·표면 경계
   길이, `B_c^down`(바닥까지 최단 경로가 성분 밖으로 바로 나가는 경계 면), 그리고
   **형상 의존 임계** `κ = −κ_max·q/(q+q₀)`, `q = 지지경계길이/√(B_down 면적)`.
   `κ_max=0.3, q₀=1` 기본 → κ ∈ (−0.3, 0]. 즉 **수직 기준 0~17.5° 까지만** 자기지지로 본다
   (우리 `analytic` 의 고정 κ = −sin45° 보다 훨씬 엄격).
3. `evaluation.py minimum_feasible_angle` — 면마다 `g = n_z cosα + d·n_r sinα ≥ κ` 의
   최소 α 를 `asin` 으로 닫힌 형태로 푼다(주기 구간 교차, 해 없으면 g 최대각으로 대체).
   **우리 `analytic.critical_angle` 과 같은 식**이고 2026-07 에 면 단위로 대조했다
   (`compare_with_teammate.py`, 22,000면 최대 차 1.4e-14°).
4. `evaluate_component_direction` — 성분의 각도 = 면 최소각의 **면적 가중 평균**.
   `evaluate_model` — 모델 각도 = 성분 각도의 면적 가중 평균, 방향은 손실
   `Σ A·max(0, κ−g)` 가 작은 쪽, 동률이면 inward.
5. `bands.py plan_slice_bands` — 성분마다 (방향, 각도) → 변환높이 `h = z + d·r·tanα`
   의 정점 정확 구간 → 겹치는 구간을 BFS 로 병합해 다시 고르기 → 수렴. 결과는
   밴드(h 구간 + 부호 각)와 밴드 사이 전이(중점 h, 각도 차).

원본에 **없는** 것: 블렌드 폭·층간격 제약(우리 `profile.py`), 툴패스 검증, 축 탐색
(축은 설정값), 각도 비용. 밴드 사이 전이는 "중점에서 바뀐다" 만 적고 실현 가능성은
"하류에서 보장할 것"으로 둔다(README 가정 7).

## 변경 로그 (이 폴더 안에서만 고친다. 원본 파일을 건드리면 여기 적는다)

| 날짜 | 무엇 | 왜 | 어디 |
|---|---|---|---|
| 2026-10-30 | 사본 생성, 다리·예측·평가 추가 | 탐색 알고리즘을 팀메 것으로 바꾸고 우리 검증 도구로 잰다 | `bridge.py`, `NOTES.md`, `evaluate.py` |
| 2026-10-30 | **원본 수정 ①** 선택 규칙에 `quantile` 옵션 (None=원본 평균, p=면적 가중 분위수) | 평균이 위반 면적 44~46 % 를 남긴다 (NOTES P1). 기본값 None 이라 원본 동작은 그대로 | `conical_slicing/evaluation.py` (`weighted_quantile`, `_select_angle`), `bands.py` 통과 인자 |
