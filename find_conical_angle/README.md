# STL 원뿔 방향·각도 분석기

STL 하나에서 원래 winding 기준으로 아래쪽을 향하는 삼각형을 찾고, 공유 변으로
연결된 오버행 성분별 지지 경계를 계산하고, 각 면의 최소 허용 원뿔각을
역삼각함수로 직접 구한 뒤 면적 가중 평균하여 모델 전체의 `inward`/`outward`
방향과 각도를 선택하는 독립 Python 프로그램입니다. 메시를
자동 수리하거나 뒤집지 않으며, 외부 슬라이서·GUI·subprocess를 사용하지 않습니다.

Python 3.11 이상, NumPy, trimesh가 필요합니다. 테스트에는 pytest를 사용합니다.

## 설치와 실행

```bash
python -m pip install -r requirements.txt
python analyze_stl.py model.stl
python analyze_stl.py model.stl --config config.json
```

Windows PowerShell 한 줄 예시:

```powershell
python .\analyze_stl.py .\models\model.stl --axis-x 100 --axis-y 100 --angle-min 0 --angle-max 60 --angle-step 1 --kappa-max 0.3 --q0 1.0 --output .\result.json
```

기본 출력은 입력 파일 옆의 `<STL 파일명>_analysis.json`입니다. `--output`으로
바꿀 수 있습니다. 다음 설정은 모두 CLI에서 덮어쓸 수 있습니다.

```text
--axis-x --axis-y
--angle-min --angle-max --angle-step
--kappa-max --q0 --bed-z
--bed-tolerance --vertex-tolerance --cross-z-epsilon --radial-epsilon
```

`axis_x`와 `axis_y`는 반드시 둘 다 지정하거나 둘 다 생략해야 합니다. 생략하면
메시 바운딩 박스의 XY 중심을 사용합니다. 잘못된 파일, 빈 메시, 로딩 실패 또는
설정 오류는 간단한 오류 메시지와 종료 코드 2로 보고합니다.

외부 코드에서는 CLI 없이 공개 함수를 직접 호출할 수 있습니다.

```python
from conical_slicing import analyze_stl

result = analyze_stl("model.stl", {"angle_min": 0.0, "angle_max": 60.0})
```

두 번째 인자는 부분 설정도 허용하며 나머지는 루트 `config.json`에서 읽습니다.
반환값은 표준 JSON으로 바로 직렬화할 수 있는 딕셔너리입니다.

## 구현 구조

- `analyze_stl.py`: 얇은 명령행 진입점이며 공개 `analyze_stl`도 다시 노출합니다.
- `conical_slicing/config.py`: JSON 로딩, 부분 설정 병합과 검증. `angle_step`은 기존 설정 호환용으로만 유지됩니다.
- `conical_slicing/mesh.py`: STL 로딩, 면 분류, 허용오차 기반 변 키, topology 경고,
  BFS 성분 탐색과 BFS 도중의 지지 경계 누적.
- `conical_slicing/evaluation.py`: `asin`·`atan2` 기반 면별 최소각 계산, 면적 가중 평균,
  모델 손실 및 최종 방향 선택.
- `conical_slicing/analysis.py`: 위 단계를 조합하는 공개 API와 strict JSON 변환/저장.
- `tests/`: 수식·설정 단위 테스트, 합성 topology 테스트, STL/CLI 통합 테스트.

STL은 좌표가 같아도 서로 다른 vertex index를 가질 수 있으므로, 꼭짓점 좌표를
`vertex_tolerance` 격자로 정규화하고 정렬된 양 끝점으로 변 키를 만듭니다. 변별
연결 면이 1개면 열린 변, 3개 이상이면 non-manifold 변으로 기록합니다. manifold
공유 변에서 두 면의 진행 방향이 같으면 winding 불일치 경고를 냅니다. 이 검사는
진단 전용이며 입력 메시를 변경하지 않습니다.

분류 순서는 바닥면, 퇴화면, 아래쪽 면, 비오버행 면입니다. 바닥면이 아니고
`c_z < -cross_z_epsilon`인 면만 BFS에 들어갑니다. BFS가 면을 방문할 때 면적,
단위법선, 중심점과 방사 법선 성분을 계산합니다. 같은 BFS 안에서 이웃 분류를
검사하여 bed/surface 경계를 누적하고, 성분별 변 집합으로 중복을 막습니다.
non-manifold 변에 여러 분류가 겹치면 bed, surface, 내부 overhang 순으로 우선하며
길이는 한 번만 셉니다. 열린 변은 경고에만 기록하고 지지 경계에는 넣지 않습니다.

## 수식과 코드 대응

- 바닥 판정과 빠른 `c_z`: `prepare_mesh`
- 허용오차 기반 꼭짓점·변 키: `_vertex_key`, `_edge_key`, `prepare_mesh`
- BFS, `B_bed`, `B_surface`: `find_overhang_components`
- `A_i`, `n_z`, `r_i`: `_face_geometry`
- `q = B / sqrt(A)`, `kappa = -kappa_max*q/(q+q0)`: `find_overhang_components`
- `g_i = n_z*cos(alpha) + d*r_i*sin(alpha)`: `minimum_feasible_angle`
- `R*sin(alpha+delta)` 변환과 `asin` 경계 계산: `minimum_feasible_angle`
- 면별 최소각의 면적 가중 평균: `weighted_mean`, `evaluate_component_direction`
- 단일 각도에서의 `L_c,d`: `component_loss_at_angle`
- `L_model,d`와 동률 규칙: `evaluate_model`

각 면에서 `a=n_z`, `b=d*r_i`, `R=hypot(a,b)`, `delta=atan2(a,b)`로 두면
`g_i(alpha)=R*sin(alpha+delta)`입니다. `asin(kappa/R)`로 허용 구간 경계를 구하고,
주기적인 사인 해 중 설정 범위와 처음 겹치는 각도를 선택합니다. 따라서 면×후보각
행렬을 만들지 않으며 각도 평가 단계는 오버행 면 수에 대해 선형입니다. 범위 안에
해가 없는 면은 같은 범위에서 `g_i`를 최대화하는 각을 해석적으로 사용하고 JSON에
`feasible=false`로 기록합니다. `angle_step`은 기존 설정 파일 호환용이며 선택 결과에
영향을 주지 않습니다.

## JSON 결과

결과에는 `schema_version`, `input`, `config`, `axis`, `mesh_summary`,
`assumptions`, `warnings`, `components`, `direction_results`, `selected_result`,
`runtime_seconds`가 있습니다. 각 성분은 면 인덱스와 기하 값, bed/surface/support
경계, `q`, `kappa`, 방향별 면 최소각·해 존재 여부·면적 가중 평균각·통과/위반 면적을 포함합니다.
`allow_nan=False`로 검증하고 저장하므로 NaN, Infinity, NumPy 객체가 JSON에
남으면 결과 생성을 실패시킵니다.

## 설정값 조정

루트 `config.json`의 값이 기본값입니다. 특히 `kappa_max`, `q0`,
`bed_tolerance`, `vertex_tolerance`, `cross_z_epsilon`, `radial_epsilon`는 메시의
단위, 정밀도, STL 내보내기 방식과 실험 결과에 맞춰 조정해야 하는 경험적
파라미터입니다. `vertex_tolerance=0`은 좌표의 정확한 일치만 공유 꼭짓점으로
간주합니다.

## 테스트

```bash
python -m pytest -q
```

테스트는 외부 모델에 의존하지 않고 작은 합성 메시를 만들며, 바닥/오버행 분류,
연결·분리 성분, 내부·bed·surface·열린·non-manifold 변, 중복 vertex index,
기본/사용자 축, 방사 방향 예외, `q`/`kappa`/`g`/손실, 역삼각함수 최소각,
면적 가중 평균, 해가 없는 경우의 fallback, 모델 방향 동률 규칙, strict JSON 왕복과 CLI 오류 처리를 검증합니다.

## 알고리즘적 한계

- 원래 winding의 `n_z < 0` 면만 검사합니다. `n_z >= 0`인 면도 큰 원뿔각에서는
  위험해질 수 있지만 이번 경량 근사에서는 제외됩니다.
- winding이 잘못된 입력은 분류 자체가 잘못될 수 있습니다. 경고만 제공하며 자동
  방향 수정이나 메시 수리를 하지 않습니다.
- 지지 경계량은 연결 경계 길이에 기반한 휴리스틱입니다. 구조역학적 안정성,
  실제 하중 경로, 아치 작용 또는 출력 공정 성공을 직접 판정하지 않습니다.
- 허용오차 격자 양자화는 경계 양쪽에 매우 가깝게 놓인 좌표를 서로 다른 키로 만들
  수 있고, 큰 허용오차는 의도하지 않은 꼭짓점을 합칠 수 있습니다.
- 중심점이 축과 `radial_epsilon` 이내이면 방향이 정의되지 않아 `r_i=0`으로 두고
  경고합니다.
- 면별 최소각의 면적 가중 평균은 모든 면이 최종 평균각에서 조건을 만족함을 보장하지 않습니다.
  `selected_angle_allows_all`, `passed_area`, `violating_area`를 함께 확인해야 합니다.
