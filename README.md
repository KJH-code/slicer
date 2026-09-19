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
python3 conical_slice.py model.stl --machine-profile profiles/machine.example.ini
python3 conical_slice.py model.stl \
  --slicer-cmd "prusa-slicer -g --load profiles/conical_pipeline.ini --dont-arrange -o {gcode} {stl}"
```

### ⚠ 실물로 뽑으려면 기계 프로파일이 필요하다

`--machine-profile` 없이 나온 G-code 에는 **예열·호밍·프라임·냉각이 없다.**
이 저장소의 내장 슬라이서는 연구용이라 `G21/G90/M82` 와 경로만 내보낸다 —
그 파일을 그대로 프린터에 넣으면 안 된다. 기계 설정은 경로 생성과 성질이 다르므로
INI 파일로 분리했다(`conical/machine.py`).

```ini
[machine]
name = Open5x (Prusa 개조)
bed_temp = 60
start_gcode =
    M140 S{bed_temp}
    G28
end_gcode =
    M84
```

치환은 `{key}` 하나뿐이다 — 프로파일 자신의 키와 슬라이싱이 정한
`{layer_height} {angle} {direction} {mode} {source_stl}`. 채울 값이 없으면
조용히 비우지 않고 **멈춘다**(기계로 나가는 파일이므로).

`profiles/machine.example.ini` 는 **템플릿이고 우리 기계에서 확인된 값이 아니다.**
온도·호밍·프라임 좌표를 반드시 확인하고, 5축 U/V 호밍은 제원을 받기 전까지
비워 뒀다(TODO 표시).

가변각 프로필은 tanθ 를 Z′에 조각별 선형으로 보간하고(가역성 조건
`c·r_max·s < 1`, 블렌드 최소 폭 `w_min = c·r_max·Δtanθ` 자동 검증),
상수 프로필은 기존 고정각과 수치적으로 동일하다(회귀 테스트로 강제).

블렌드에는 **층간격 제약**도 걸린다: 변환공간에서 층고 간격으로 자른 레이어가
실공간에서 `m = 1 − c·r·s` 배로 벌어지므로, 배율을 `MAX_SPACING_FACTOR`
(기본 1.5) 이내로 두는 최소 폭 `w ≥ r_b·|Δtanθ|/(limit−1)` 을 강제한다.
반경 `r_b` 는 **그 높이의 최대 반경**이라(`meshio.RadiusProfile`) 경계를 반경이
작은 높이로 옮기면 블렌드가 싸진다 — 자동으로 그렇게 옮긴다(`--spacing-limit 0`
으로 끄면 옛 동작). 이 제약은 툴패스 검사기가 실측으로 잡아낸 결함에서 나왔다.

### 툴패스 가상 검증기 (하드웨어 없이)

```
python3 toolpath_check.py out.gcode              # 검사기 A: 압출 지지 (미지지 %, 산점 PNG)
python3 toolpath_check.py out.gcode --nozzle     # + 검사기 B: 3축 노즐 간섭
python3 find_max_safe_angle.py [model.stl]       # 각도 스윕 → 이 모델·기계의 3축 MAX_ANGLE
python3 compare_prediction_vs_toolpath.py        # 본편 실험: 메시 예측 vs 툴패스 (순위상관)
python3 compare_waist.py                         # 핵심 실험: 밴드 vs 균일 — '허리'가 있어야 이긴다
python3 analyze_blend_k.py                       # J의 블렌드 비용 가중치 k_blend 창 분석
python3 compare_bands.py                         # 복잡도(밴드 수 N=1~6) vs 성능, 툴패스 실측
python3 compare_bands.py --waist-sweep            # + 허리 깊이 축으로 모델 표본 확대
python3 compare_kappa_rules.py                   # 임계 κ 규칙(고정 45° vs 형상 의존) 실측 판정
python3 compare_with_teammate.py --teammate ./find_conical_angle   # 팀메 독립 구현과 면 단위 대조
```

### 검사기 C: Open5x 기계좌표 사전 점검 (5축)

```
python3 open5x_check.py out_open5x.gcode --bed-radius 90
```

검사기 A/B 는 **3축 가정**(노즐 수직, 베드 고정)이라 5축 출력에는 맞지 않는다.
검사기 C 는 기계좌표 자체를 본다 — 틸트 한계, **회전 V 누적(배선 감김)**,
축 근처 **V 급회전**, 기계 Z 음수(소프트리밋), 베드 이탈, 피드 한계.

실제 출력(funnel, 20°)에서 셋이 걸린다. 고쳐야 할 버그가 아니라 **실기 전에
사람이 알아야 할 사실**이다:

| 걸린 것 | 값 | 뜻 |
|---|---|---|
| 회전 누적 | **175회전** | 슬립링이 없으면 배선이 감긴다. 되감기나 레이어별 방향 교대가 필요 |
| V 한 걸음 | **179°** | 축 근처 방위각 반전. 베드가 급회전하며 출력물을 흔든다 |
| 기계 Z 최소 | **−2.45mm** | 틸트로 베드가 내려간 쪽이라 음수가 정상일 수 있다. 펌웨어 소프트리밋이 0 이면 잘려서 노즐이 파고든다 — Z 오프셋 확인 |

⚠ 축 가속도 한계와 실제 기구 충돌은 **보지 못한다.** 통과해도 첫 출력은 사람이
지켜봐야 한다.

### 그림 라벨 언어 (발표 자료용)

실험 스크립트의 그림은 **한글 폰트가 설치돼 있으면 한글, 없으면 영문**으로 나온다
(`conical/plotstyle.py`). 개발용 리눅스 컨테이너엔 한글 폰트가 없어 두부(□)로 깨지기
때문이고, 발표 자료를 만들 때 라벨을 손으로 고치지 않으려는 것이다.

```
python3 -m conical.plotstyle       # 이 환경에서 한글이 되는지 + 쓸 폰트 확인
python3 compare_waist.py           # 폰트가 있으면 그대로 한글 그림이 나온다
CONICAL_PLOT_FONT="Malgun Gothic" python3 compare_bands.py   # 폰트 직접 지정
                                   # (matplotlib 이름이라 "맑은 고딕"이 아니라 영문명)
```

`requirements.txt` 에 `koreanize-matplotlib`(나눔고딕 번들)이 들어 있어서
`pip install -r requirements.txt` 만 하면 어느 환경에서든 한글로 나온다.
윈도우(`Malgun Gothic`)·macOS(`AppleGothic`)는 시스템 폰트가 먼저 잡힌다.
한글 폰트에 없는 기호(⟨ ⟩ 등)는 폰트 폴백으로 DejaVu Sans 가 대신 그린다.

`find_max_safe_angle.py` 는 config 의 전역 상수 `MAX_ANGLE_DEG` 를 모델별
계산값으로 대체할 수 있게 한다 (HotendProfile 은 실측 전 추정값 — 캘리퍼스 필수).

**검증 계층**: 단위테스트 → 툴패스 검증(검사기 A/B) → 브라우저 독립 재구현 →
사람 손계산 → **팀메 독립 구현 대조**. 각 층이 아래층의 가정을 검사한다 —
실제로 툴패스 검사기가 메시 예측의 순위를 재현(ρ=1.0)하면서, 동시에 가변각
블렌드의 층간격 팽창이라는 "이상적 추정"의 결함을 실측으로 잡아냈다.

⚠ **실물 출력은 지금까지 불가능했다**(장비·여건). 그래서 마지막 층은
'프린트해 봤다'가 아니라 '같은 수식을 다른 사람이 따로 구현한 코드와 맞다'이다
(22,000면, 최대 차이 1.42e-14°). 물리(브리징·수축·접착)는 계산으로 검증되지 않으므로
모든 결론을 '증명'이 아니라 '시뮬레이션 경향'으로만 쓴다.

**2026-09-19: 다음 달 프린터를 직접 제작해 물리 실험이 가능해진다.** 위 제약이
풀리므로 `--machine-profile` 로 실물용 G-code 를 낼 수 있게 해뒀다. 첫 실물
실험의 질문은 '예측대로 나오나'가 아니라 **'어느 지표가 실물과 맞나'** 다 —
옛 지표('페리미터 미지지')와 진짜 오버행이 순위를 다르게 매기는 **램프**가
그 판정 모델이다.

출력 G-code는 `tools/slicing_simulator.html`(브라우저)에서 재생·확인할 수 있다.
시뮬레이터의 **검증 탭**은 Python 과 독립적으로 수식을 재구현해 점 단위로
대조한다(오프라인 동작): G-code + (선택) `toolpath_check.py --export-json`
정답지를 로드 → 층간격 히트맵·프로필 인스펙터·손계산 검산·자체테스트 4종.
자세한 검증 계층은 [`docs/verification.md`](docs/verification.md) 참고.
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
  varangle.py        높이 구간별 변수각 θ(z) 전략 + 프로필 단위 J(블렌드 비용 포함)
  clusters.py        오버행 클러스터 진단 + 적응 천장(ceiling)
  bandplan.py        실현 가능한 밴드 계획 (팀메 bands.py 미러)
  strength.py        이론 강도 (Hankinson)
  gcode.py           G-code 데이터 모델 (파싱/쓰기)
  planar_slicer.py   내장 미니 평면 슬라이서 (연구용)
  backtransform.py   역변환 + 적응 현 분할 L=2√(2rε)
  open5x.py          Open5x 5축 기계좌표 변환 [실험적]
  meshio.py          STL 로드 / 축 센터링 / 높이별 반경 프로필 / 데모 구
  plotstyle.py       그림 라벨 한글/영문 자동 선택 (한글 폰트 감지)
  kappa.py           임계 κ 규칙 둘 (고정 45° / 팀메 형상 의존) — 실측 비교용
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
구간별은 '각도 예산'을 오버행 심한 구간에만 몰아써서 **더 적은 왜곡으로 오버행을
더 줄인다** — 단 허리가 있을 때만 (아래 표). `compare_complexity.py`가 균일/구간2/구간3/세밀을 **서포트·강도proxy·
평균각·계산시간**으로 비교한다(복잡도 vs 성능 가성비 곡선).

**단, 툴패스로 실측해 보니 조건부다** (`compare_waist.py`):

> ⚠ **'페리미터 미지지' 열은 오버행이 아닌 몫을 섞어 센다.** 위로 좁아지는 형상은
> 페리미터가 아랫층 단면 **안**에 놓이는데(희소 인필을 건너뛰는 평범한 브리징)
> 검사기가 그걸 미지지로 셌다. 섞인 비율이 행마다 0~67% 로 달라 **순위를 바꾼다.**
> 갈라낸 수치가 '진짜 오버행' 열이고, **결론은 이쪽으로만 읽는다.**
> → [`docs/verification.md`](docs/verification.md) 2026-09-19 절

| 모델 | 전략 | (페리미터 미지지) | **진짜 오버행** | 평균 왜곡각 |
|---|---|---|---|---|
| 구 (허리 없음) | 평면 0° | 7.51% | 4.90%p | 0° |
| | 균일 28° (J) | 1.08% | **0.51%p** | 28° |
| | 밴드2 (J) | 1.08% | 0.51%p | 28° ← 균일로 수렴 |
| | 밴드2 (선택에 블렌드비용 없음) | 4.93% | 0.48%p | 18.9° ← 아래 ⚠ |
| 램프 (허리 있음) | 평면 0° | 4.49% | 2.71%p | 0° |
| | 균일 24° (J) | 3.01% | 1.01%p | 24° |
| | **밴드2 (J)** | 0.83% | **0.33%p** | **18.6°** |

읽는 법 둘.

**① 원뿔이 평면을 크게 이긴다.** 구 4.90 → 0.51%p (9.6배), 램프 2.71 → 1.01%p (2.7배).

**② 허리가 있으면 밴드가 균일각을 두 축에서 지배한다.** 램프에서 오버행 1.01 →
**0.33%p** (3.1배)이면서 왜곡도 24.0° → **18.6°** 로 줄었다. 파레토 우세다.
허리가 없는 구에서는 밴드가 스스로 균일로 수렴한다 — 블렌드가 비싸서다.

> ⚠ **열린 질문**: 구에서 선택에 블렌드 비용을 아예 안 넣은 해(`select_banded`)가
> 0.48%p / 18.9° 로 균일(0.51%p / 28.0°)을 두 축 모두에서 약간 이긴다. "구에서는
> 균일이 정답"이라는 전제 자체를 다시 봐야 한다. 지금 J 는 그 해를 못 고른다.

각도를 바꾸려면 블렌드가 필요하고 그 폭은 **그 높이의 반경에 비례**한다
(층간격 제약). 그래서 각도 변경은 '가는 곳에서 싸고 뚱뚱한 곳에서 비싸다' —
구처럼 어디나 뚱뚱하면 블렌드가 모델 높이의 73%를 잡아먹어 균일각이 낫다.
이 조건은 우리가 가정한 게 아니라 검사기가 실측으로 알려준 것이다.

그래서 밴드 선택을 **프로필 단위 J** 로 바꿨다(`select_banded_j`): 후보 각도로
실제 프로필을 만들어(층간격 제약 포함) J 를 재고, 여기에 해석식이 못 보는
블렌드 비용을 명시적으로 더한다.

```
J = (서포트 감소 %p) − k×평균|θ| − k_blend × Σ(블렌드 구간 표면적 %)×(m−1)/(limit−1)
```

탐색 이웃은 '연속한 밴드 덩어리'다 — 블렌드 비용이 '이웃 밴드의 각도가 다른
자리'에 붙으므로 한 칸씩 바꾸는 이웃으로는 두 밴드를 함께 내리는 수를 못 둔다.
균일 후보를 전수 평가해 섞으므로 **결과가 최선 균일 원뿔보다 나쁠 수 없다**
(회귀 테스트로 강제).

**`k_blend` 기본값은 0.5 → 0.1 로 낮췄다** (2026-09-19). 0.5 는
`analyze_blend_k.py` 가 낸 창(0.1~1.5)의 한가운데였는데, 그 창의 '정답'
("구=균일, 램프=부위별")이 **오염된 지표**로 정의돼 있었다. 진짜 오버행으로
다시 재니 0.5 는 과하다 — 램프 밴드2 에서 `k_blend=0.5` 는 1.12%p/16.3°,
`0.1` 은 **0.33%p**/18.6° 로 3.4배 낫고, 구에서는 둘이 같다(균일로 수렴).
0 으로 두면 여전히 병리적이다(구에서 `[36°, −44°]`, 블렌드 19.9mm, 1.81%p).

밴드 수를 늘렸을 때의 곡선은 `compare_bands.py` 가 그린다 (진짜 오버행 %p /
평균 왜곡각). 표본 7개 × N=1~6 으로 재측정한 결과:

**밴드 수 N 을 늘릴 이유가 없다.** 다만 이유는 "J 가 포화해서"가 **아니다** —
`k_blend=0.1` 에서 J 는 N=6 까지 계속 오른다. 그런데 **진짜 오버행은 거기서
나빠진다**: 7개 중 6개에서 J 최대 N 의 오버행이 달성 가능한 최소보다 나쁘다
(구 N=5 → 1.84%p vs 최소 0.51%p, 허리 r=3 N=6 → 1.39%p vs 최소 0.32%p).

결함이 아니라 구조다. J 는 경계가 겹치는 짝에서 N 에 대해 비감소이므로 N 을 J 로
고르면 항상 커지는 쪽으로 가고, 각도 비용 k 때문에 '밴드 많고 각도 낮은' 해를
선호한다. **그래서 N 은 사람이 준다**(`--auto-bands N`, 기본 2). 자동화하려면
N 자체에 대한 비용이 따로 필요하다.

**J 가 N 에 대해 비감소인지**가 이 실험의 자체 점검이다. 처음엔 위반했고, 그걸
따라가 계획기 결함 셋을 찾았다 (docs/verification.md). 다만 그 점검의 원래 논거
("N개는 이웃을 같은 각도로 두면 N−1개를 흉내낼 수 있다")는 **틀렸다**: 밴드 경계가
`linspace` 라 N=3 의 경계(33.3%, 66.7%)는 N=4 의 경계(25/50/75%)에 하나도 없다.
흉내내기가 보장되는 짝은 **n 이 m 을 나눌 때뿐**이고(1→2, 2→4, 3→6 …), 그 짝에서만
감소가 결함이다. 이웃한 N 사이의 감소는 격자 비정합이다
(`tests/test_band_nesting.py` 가 고정).

모델 표본은 `--waist-sweep` 으로 늘린다. 목 반경을 7→1 로 바꾸면 허리 두드러짐
(`conical.meshio.waist_prominence`) 이 0.00→0.86 으로 움직인다. **허리 문턱이
선명하다** — 밴드2 기준 오버행 감소 배수:

| 허리 두드러짐 | 0.00 | 0.00 | 0.29 | 0.57 | 0.71 | 0.86 |
|---|---|---|---|---|---|---|
| 오버행 감소 | ×1.0 | ×0.9 | ×0.9 | **×3.3** | **×3.1** | **×4.1** |

문턱은 0.29 와 0.57 사이다. 얕은 허리에서는 밴드가 이득이 없고(오히려 약간 손해),
깊어지면 3~4배가 된다.

```
python3 compare_bands.py --waist-sweep --n-max 6     # 허리 깊이 × 밴드 수
python3 compare_bands.py sphere waist:3 model.stl    # 모델 직접 지정
python3 compare_bands.py --replay compare_bands_results.json   # 그림만 다시 그리기
```

전체 스윕은 수십 분 걸린다(선택 비용이 N 에 2차). 측정값은
`compare_bands_results.json` 에 저장되므로, 라벨·축만 손볼 때는 `--replay` 로
다시 그린다 — 같은 입력이면 그림이 바이트 단위로 같다.

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
- `MAX_SPACING_FACTOR` : 블렌드 층간격 배율 상한 (기본 1.5)
- `BLEND_SHIFT_RATIO`  : 밴드 경계를 '허리'로 옮겨보는 최대 거리 (모델 높이 × 이 값, 기본 0.25)
- `BLEND_COST_K`       : J의 블렌드 비용 가중치 (기본 0.5, 창 0.1~1.5)

## 참고 (선행연구, 인용 전제)

RotBot/ZHAW, slicer4rtn, Open5x, S³ DeformFDM, S4, Fractal Cortex.
팀메 저장소: `26037-arch/find_conical_angle`(성분 분석·κ 규칙),
`conical-slice-viewer`(교선 시각화) — 대조 결과는
[`docs/teammate_comparison.md`](docs/teammate_comparison.md).
현재 결과는 **시뮬레이션 경향**이며 '증명'이 아니다.
