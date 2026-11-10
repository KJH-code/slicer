# CLAUDE.md — slicer

형상 적응형 원뿔(conical) 슬라이싱 알고리즘. 고등학교 R&E.

STL 을 분석해 **부위별로** 원뿔 슬라이싱 각도·방향을 자동 결정한다. 무거운
연구용 최적화 슬라이서와 단순 고정각 원뿔 슬라이서(RotBot 등) 사이의 빈 자리를 노린다.

---

## ⏱ 지금 국면 (2026-11-10)

**프린터가 있다**: Ender-3 V3 SE + REP5X 키트, REP5X Marlin. 확정된 건 이것뿐이고, 나머지 기계
규약은 `docs/rep5x_machine_facts.md`(REP5X 소스에서 읽음, 출처·신뢰도 표기)를 믿는다.
실험은 **10~20분짜리 싼 출력을 반복**하는 방식이다 (PLA, 노즐 0.4, 210/60).

- 지금 할 것: `docs/experiment_plan.md` 「R」 사다리 (`examples/rep5x_ladder/`)
- 연구 현황: `docs/research_summary.md` · 허점: `docs/gap_audit.md` (J1~J11은 연구자 판단)
- ⚠ `examples/lamp_expA_*_rep5x.gcode`는 **치명 결함이 있는 옛 파일**이다. 프린터에 넣지 말 것
  (테스트의 회귀 표본으로만 남김)
- 실물 G-code는 `--machine-profile profiles/rep5x_ender3v3se.ini`로만 뽑는다. 뽑고 나면
  `rep5x_check.py`와 `tools/fibr3d_crosscheck.py`(팀 가상 프린터 IK, `../FIBR3DEmul-Rep5x`)를 둘 다 돌린다
- 베드 충돌 때문에 바닥 쪽 각도가 B_safe(약 22.8°, 공식 뷰어 핫엔드 모델 기준)로 깎인다.
  균일 대조군은 `--strict`로 뽑아야 몰래 균일이 아니게 되지 않는다

DevVault: Projects/Conical Slicer

---

## 환경

Python 3.11. 가상환경 없이 시스템 파이썬을 쓴다.

```
pip install -r requirements.txt      # 실행 의존성
pip install pytest ruff              # 개발 의존성 (requirements.txt 에 없음)
export PYTHONPATH=.                  # tests/ 가 루트의 conical 패키지를 찾게
export MPLBACKEND=Agg                # 헤드리스. 없으면 그림 스크립트가 죽는다
```

Claude Code on the web 세션은 `.claude/hooks/session-start.sh` 가 위를 자동으로 한다.
훅은 `main` 에 있으므로 새 세션에서 그냥 돈다 — 직접 설치할 필요 없다.

## 테스트 · 린트

```
pytest tests/ -q      # 203개, 약 170초. 전부 통과가 기준선이다
ruff check .          # 0건이 기준선이다. 설정은 ruff.toml 에 고정
```

`ruff.toml` 은 규칙을 **명시적으로** 고정한다 — ruff 기본값이 버전마다 바뀌기 때문이다.
켜 둔 것은 F(미정의 이름·안 쓰는 import)·E4·E7·E9·B(bugbear)·I(import 정렬)뿐이고,
스타일 취향 규칙(SIM, C4, FURB 등)은 일부러 껐다.

`zip()` 에는 `strict=` 를 반드시 쓴다. 길이가 같아야 하면 `strict=True`,
슬라이딩 윈도처럼 의도적으로 짧은 쪽에 맞추면 `strict=False`.
둘 다 안 쓰면 길이가 어긋날 때 **조용히 잘린다.**

---

## 구조

```
conical/                  로직 (25 모듈)
├── config.py             모든 손잡이 (임계각, MAX_ANGLE, k, k_blend, 층간격 상한)
├── transform.py          원뿔 변환식 — RotBot 것, 차용
├── analytic.py         ★ 판정 기준(해석식). 저장소 전체가 이거 하나를 쓴다
├── profile.py          ★ θ(Z') 가변각 프로필 — 가역성·층간격 제약의 닫힌 해
├── varangle.py         ★ 밴드 전략 + 프로필 단위 J (블렌드 비용 포함)
├── meshio.py             STL 로드 / 축 센터링 / 높이별 반경 프로필
├── backtransform.py      역변환 + 적응 현 분할 L=2√(2rε)
├── planar_slicer.py      내장 미니 평면 슬라이서 (연구용)
├── toolpath.py           툴패스 가상 검사기 A(지지)·B(노즐 간섭)
├── open5x.py rep5x.py    5축 기계좌표 변환 [실험적] + 검사기 C
├── envelope.py motion.py sync.py quality.py   5축 하드웨어 분석
└── sweep.py metrics.py   ⚠ 레거시 — 아래 금지 항목 참조

conical_slice.py          슬라이싱 CLI (STL → 원뿔 G-code)
toolpath_check.py         검사기 CLI
open5x_check.py           5축 기계좌표 사전 점검 CLI
analyze_*.py compare_*.py 실험 스크립트 (테스트 없음)
tests/                    단위·회귀 테스트
docs/                     검증 계층·선행연구·슬라이서 관례·실험 계획
examples/                 funnel.stl, lamp.stl + 출력 G-code
profiles/                 기계 프로파일 INI
```

실행 명령 전체 목록은 `README.md` 에 있다. 여기 중복해 두지 않는다.

---

## 반드시 지킬 것

### 1. `sweep.py` / `metrics.py` 를 쓰지 말 것

⚠ **레거시다.** 왜곡공간에서 45°로 판정하던 옛 방식인데, 원뿔 변환이 등각(conformal)이
아니라서 **왜곡한 메시에서 잰 각도는 실제 물리 각도가 아니다.** θ=0 에서만 두 정의가
일치하고 θ가 커질수록 벌어진다.

그 방식으로 얻었던 "funnel 은 inward 가 유리" 결론은 **철회됐다.** 두 모듈은 비교·재현용으로만
남겨둔 것이다. 새 판정에 갖다 쓰면 결론이 조용히 틀어진다.

판정은 **언제나 `analytic.py` 의 해석식 하나**를 쓴다:

```
g(θ) = n_z·cosθ + d·n_r·sinθ        서포트 필요 ⟺ g < κ = −sin(임계각)
면별 임계각                          θ* = asin(κ/R) − atan2(n_z, d·n_r)
```

### 2. 비교 기준은 균일 원뿔이다 — 평면이 아니다

"평면 슬라이싱 대비 서포트 X% 감소"는 **원뿔 슬라이싱의 성과지 이 연구의 성과가 아니다.**
RotBot 이 이미 하는 일이다.

넘어야 할 선은 **균일 원뿔**(모델 전체에 각도 하나)이다. 모든 실험 표에 균일각 행을 넣고,
균일각을 못 이기면 **진 것으로 적는다.** 이 기준을 세우고 나서야 구(sphere)에서 밴드가
지고 있다는 걸 발견했다.

### 3. 기계 프로파일 없이 나온 G-code 를 프린터에 넣지 말 것

`--machine-profile` 없이 나온 G-code 에는 **예열·호밍·프라임·냉각이 없다.** 내장 슬라이서는
연구용이라 `G21/G90/M82` 와 경로만 내보낸다. `profiles/machine.example.ini` 는 템플릿이고
**우리 기계에서 확인된 값이 아니다.**

---

## 설계상 알아둘 것

- **슬라이서를 재발명하지 않는다.** 외부 슬라이서(PrusaSlicer CLI)를 감싼다 — 왜곡한 STL 을
  넘겨 평면 G-code 를 받고 역변환한다. 우리가 만드는 건 앞뒤(왜곡·역변환·각도 결정)뿐이다.
  프리셋에 못박은 것: 서포트 끄기, arc fitting 끄기(G2/G3 는 역변환 불가), 자동 배치 끄기
  (모델이 축에서 밀리면 원뿔 변환이 망가진다), 절대 E
- **오버행 판정이 두 가지다.** `overhang.py`(면 법선, 빠름, 영역 분할·미리보기용)와
  `overhang_layers.py`(레이어별 2D, 실제 슬라이서 방식, 서포트 넓이 추정용). 면 법선 방식은
  '아래에 받쳐주는 게 있는지'를 몰라서 아래보기 면을 과대평가한다. 용도를 섞지 말 것
- **가변각은 θ 가 아니라 tanθ 를 선형 보간한다.** 변환에 실제로 들어가는 양이 tanθ 라서
  가역성(`c·r_max·s < 1`)과 층간격 제약이 정확한 닫힌 식으로 떨어진다
- **실험 스크립트(`analyze_*.py`, `compare_*.py`)에는 테스트가 없다.** 고칠 때는
  `ruff check .` 와 직접 실행으로 확인한다

## source of truth

| 대상 | 어디를 믿나 |
|---|---|
| 현재 코드 | 이 저장소 |
| 실행 명령 전체 | `README.md` |
| 실험 계획·판정 기준 | `docs/experiment_plan.md` |
| 설계 결정과 그 이유 | DevVault `Projects/Conical Slicer/Decisions.md` |
| 일정·우선순위 | DevVault `Projects/Conical Slicer/TODO.md` |
| 알려진 결함 | DevVault `Projects/Conical Slicer/Bugs.md` |
| 최신 라이브러리 API | Context7 또는 공식 문서 (볼트의 옛 노트보다 우선) |
