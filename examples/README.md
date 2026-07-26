# examples — 예시 입력/출력

| 파일 | 내용 |
|---|---|
| `funnel.stl` | 데모 모델: 팁이 아래인 깔때기 (벽 오버행 70.3° — 평면 슬라이싱 시 서포트 51.5%) |
| `funnel_conical.gcode` | `python3 conical_slice.py examples/funnel.stl` 출력 (자동 outward 26°, 서포트 0%) |
| `funnel_open5x.gcode` | `--mode open5x` 출력 (U=26° 고정, V 방위각 추적) [실험적] |

`tools/slicing_simulator.html` 의 "G-code 실행" 탭에서 STL과 G-code를 함께
로드하면 분석(빨간 오버행) → 왜곡 → 출력 재생을 한 화면에서 볼 수 있다.
| `funnel_profile2band.gcode` | 가변각 2밴드(`--profile "0:26,2.5:26,3.5:10,5:10"`) 출력 — θ(Z′) 파이프라인 예시 |
