# slicer — 형상 적응형 원뿔(conical) 슬라이싱 알고리즘

STL 모델을 분석해 부위별로 원뿔 슬라이싱 각도/방향을 **자동으로, 가볍고
투명하게** 결정하는 알고리즘 (고등학교 R&E). 무거운 연구용 최적화 슬라이서와
단순 고정각 원뿔 슬라이서(RotBot 등) 사이의 빈 자리를 노린다.

> "연구실의 성능을 메이커의 손에."

## 설치

```
pip install -r requirements.txt
```

## 실행

```
python3 overhang_analysis.py [model.stl]        # Stage 1: 오버행 분석 (면 법선)
python3 angle_sweep.py                           # Stage 2: 각도별 남은 서포트 곡선 -> angle_sweep.png
python3 cone_selector.py [model.stl]             # Stage 3: 각도/방향 자동 결정 + 이유
python3 region_selector.py [model.stl]           # Stage 4: 부위별(오버행 심한 정도) 각도 결정
python3 compare_overhang_methods.py [model.stl]  # 검증: 면법선 vs 레이어별 2D 판정 비교
python3 compare_complexity.py [model.stl]        # 핵심: '복잡도 vs 성능' 균일/구간별/세밀 비교
python3 analyze_k.py [model.stl]                  # 구간별 이득이 k에 어떻게 의존하나 -> analyze_k.png
python3 compare_ceiling.py [model.stl]            # 실현 가능한 밴드 계획 vs 이상적 천장
```

STL 경로를 안 주면 데모용 구(sphere)로 실행된다.

### 슬라이싱 파이프라인 (STL → 원뿔 G-code)

```
python3 conical_slice.py model.stl                       # 각도 자동 (J 기준, --k 로 조정)
python3 conical_slice.py model.stl --angle 30 --direction outward   # 수동 지정
python3 conical_slice.py model.stl --profile "0:15,10:15,14:35,30:35"  # 가변각 θ(Z′) 수동
python3 conical_slice.py model.stl --auto-bands 2        # 밴드 자동 탐색 → 가변각 프로필
python3 conical_slice.py model.stl --mode open5x         # Open5x 5축 기계좌표 [실험적]
python3 conical_slice.py model.stl \
  --slicer-cmd "prusa-slicer -g --load profiles/conical_pipeline.ini --dont-arrange -o {gcode} {stl}"
```

가변각 프로필은 tanθ 를 Z′에 조각별 선형으로 보간하고(가역성 조건
`c·r_max·s < 1`, 블렌드 최소 폭 `w_min = c·r_max·Δtanθ` 자동 검증),
상수 프로필은 기존 고정각과 수치적으로 동일하다(회귀 테스트로 강제).

### 툴패스 가상 검증기 (하드웨어 없이)

```
python3 toolpath_check.py out.gcode              # 검사기 A: 압출 지지 (미지지 %, 산점 PNG)
python3 toolpath_check.py out.gcode --nozzle     # + 검사기 B: 3축 노즐 간섭
python3 find_max_safe_angle.py [model.stl]       # 각도 스윕 → 이 모델·기계의 3축 MAX_ANGLE
python3 compare_prediction_vs_toolpath.py        # 본편 실험: 메시 예측 vs 툴패스 (순위상관)
```

`find_max_safe_angle.py` 는 config 의 전역 상수 `MAX_ANGLE_DEG` 를 모델별
계산값으로 대체할 수 있게 한다 (HotendProfile 은 실측 전 추정값 — 캘리퍼스 필수).

**검증 계층**: 메시 예측(해석식, 초 단위) → 툴패스 검증(검사기 A/B, 분 단위)
→ (향후) 실물 출력. 각 층이 아래층의 가정을 검사한다 — 실제로 툴패스 검사기가
메시 예측의 순위를 재현(스피어만 ρ=1.0)하면서, 동시에 가변각 블렌드의 층간격
팽창이라는 "이상적 추정"의 결함을 실측으로 잡아냈다.

출력 G-code는 `tools/slicing_simulator.html`(브라우저)에서 재생·확인할 수 있다.
예시 입력/출력은 `examples/` 참고.

## 구조

로직은 `conical/` 패키지 한 곳에 모여 있고, 위 3개 파일은 '실행 방법'만
담당하는 얇은 스크립트다.

```
conical/
  config.py          설정값 한 곳에 모음 (임계각, 최대 각도, DEFAULT_K) + 슬라이서 관례 변환
  transform.py       원뿔 좌표 변환식 (RotBot 방식)
  analytic.py        ★ 판정 기준(해석식): 실공간 국소 레이어 각 + 면별 임계각
  overhang.py        Stage 1 — 면별 오버행 분석 (빠른 면 법선 방식)
  overhang_layers.py 레이어별 2D 오버행 판정 (실제 슬라이서 방식)
  sweep.py           (레거시) 변환공간 근사 — 비교·재현용
  metrics.py         (레거시) 변환공간 지표 — 비교·재현용
  selector.py        Stage 3 — 평가함수 J 로 각도/방향 자동 결정 (해석식)
  regions.py         Stage 4 — 부위별(오버행 심한 정도) 각도 결정 (해석식)
  varangle.py        높이 구간별 변수각 θ(z) 전략 (균일/구간별/세밀, 해석식)
  clusters.py        오버행 클러스터 진단 + 적응 천장(ceiling)
  bandplan.py        실현 가능한 밴드 계획 (팀메 bands.py 미러)
  strength.py        이론 강도 (Hankinson)
  gcode.py           G-code 데이터 모델 (파싱/쓰기)
  planar_slicer.py   내장 미니 평면 슬라이서 (연구용)
  backtransform.py   역변환 + 적응 현 분할 L=2√(2rε)
  open5x.py          Open5x 5축 기계좌표 변환 [실험적]
  meshio.py          STL 로드 / 축 센터링 / 데모 구
profiles/            외부 슬라이서(PrusaSlicer) 파이프라인 프리셋
tools/               시뮬레이터(html)·G-code 진단·엑셀 생성기
examples/            예시 입력(STL)과 출력(G-code)
tests/               회귀 테스트
```

### 판정 기준 (통일됨)

오버행/서포트 판정은 **해석식**(`analytic.py`: 면이 실공간 국소 원뿔 레이어와
이루는 각, `g = n_z·cosθ + d·n_r·sinθ`)으로 통일했다. 변환공간 방식
(`sweep.py`/`metrics.py`)은 α>0에서 물리와 어긋나(비등각 왜곡,
`docs/warped_threshold_finding.md`) 레거시 비교용으로만 유지한다.

의존성 참고: `rtree`가 없으면 내장 슬라이서/레이어별 판정이 죽는다
(`requirements.txt`에 포함).

### 연구 논지: 균일 원뿔 vs 부위별 각도

비교 대상은 RotBot식 **균일 원뿔(모델 전체 각도 1개)**. 우리 방법은 모델을
**높이 구간으로 나눠 각 구간에 최적 각도**를 준다(= 변수각 원뿔 θ(z), RotBot의
`var_angle` 방식이라 실제로 프린트 가능). 균일각은 전체 타협값이라 손해고,
구간별은 '각도 예산'을 오버행 심한 구간에만 몰아써서 더 적은 왜곡으로 서포트를
더 줄인다. `compare_complexity.py`가 균일/구간2/구간3/세밀을 **서포트·강도proxy·
평균각·계산시간**으로 비교한다(복잡도 vs 성능 가성비 곡선).

> 강도는 실측이 아니라 '레이어-표면 정렬' 기반 가벼운 proxy다 (증명 아닌 경향).
> '세밀(면마다)'은 이론적 바닥일 뿐 물리적으로 못 찍는다(유효한 θ(z) 아님).

### 오버행 판정 두 가지 (조사 반영)

- **면 법선 방식**(`overhang.py`): 아래를 보는 면을 오버행으로 본다. 빠르지만
  '밑에서 받쳐주는 면/바닥면'도 세므로 과대평가한다(정육면체 밑면 오판).
- **레이어별 2D 방식**(`overhang_layers.py`): 실제 슬라이서(Cura/PrusaSlicer/
  OrcaSlicer)처럼 각 레이어를 아래층과 비교해 '튀어나온 부분'만 센다.

우리 각도 관례는 **Cura와 동일**하고 Prusa/Orca와는 여집합(90−θ)이다. 근거와
출처는 [`docs/slicer_conventions.md`](docs/slicer_conventions.md) 참고.

패키지에서 바로 가져다 쓸 수도 있다:

```python
from conical import analyze_overhangs, support_fraction, select_cone, config
```

## 튜닝

바꿀 값은 전부 `conical/config.py` 한 곳에 있다.
- `THRESHOLD_DEG` : 오버행 판정 임계각 (기본 45°)
- `MAX_ANGLE_DEG` : 하드웨어가 허용하는 최대 원뿔 각도 (하드코딩 금지, 여기서 조정)
- `ANGLE_STEP`   : 각도 탐색 간격

## 참고 (선행연구, 인용 전제)

RotBot/ZHAW, slicer4rtn, Open5x, S³ DeformFDM, S4, Fractal Cortex.
현재 결과는 **시뮬레이션 경향**이며 '증명'이 아니다.
