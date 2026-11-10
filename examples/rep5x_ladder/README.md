# REP5X 시험 출력 사다리

Ender-3 V3 SE + REP5X 키트(REP5X Marlin)에서 **처음 돌릴** 파일들. 순서·예측·판정 기준은
[`docs/experiment_plan.md`](../../docs/experiment_plan.md) 「R」절, 기계 규약은
[`docs/rep5x_machine_facts.md`](../../docs/rep5x_machine_facts.md).

PLA, 노즐 0.4, 210/60, 층고 0.3, 최소 층 시간 8초, 팬 없음(M106 이 무엇을 켜는지 [실기 확인] — 파트 냉각 팬이면 `--fan` 을 붙여 다시 뽑는다). 전부 두 검사기에서 치명 0:

- 검사기 C: `rep5x_check.py`
- 팀 가상 프린터의 역기구학·축 한계: `tools/fibr3d_crosscheck.py`

| 순서 | 파일 | 모델 | 조건 |
|---|---|---|---|
| 1 | `L0_dry_run.gcode` | — | 공중 시운전. 히터·압출 없음 |
| 2 | `L1_cylinder_b0.gcode` | `cylinder.stl` (r10 × 8) | B=0 |
| 3 | `L2p_flare_planar.gcode` | `flare.stl` (아래 r5, 벽 60°, 높이 6) | B=0 대조 (실패해야 정상) |
| 4 | `L2_flare_u15.gcode` | `flare.stl` | 균일 15° |
| 5 | `L3a_lamp_u22.gcode` | `lamp_small.stl` (램프 0.6배) | 균일 22° (기준선) |
| 6 | `L3b_lamp_band22to0.gcode` | `lamp_small.stl` | 밴드2 22° → 0° |
| + | `L4a_wall_b0.gcode` / `L4b_wall_u22.gcode` | `cylinder.stl`, 둘레 1줄·인필 없음 | 단벽 B=0 / 22° — 압출 배율 판정 |
| + | `L5_overhang_steps_planar.gcode` | `overhang_steps.stl` (40~65° 단 6개) | 평면 — 이 기계의 오버행 한계 |

## ⚠ 넣기 전에

1. 펌웨어 값을 읽어 `docs/rep5x_machine_facts.md`와 대조한다. `M503`(전체), `M665`(LC/LB), `M211`(소프트 엔드스톱)
2. **베드 중앙 native 좌표가 (100, 100)인지** 확인한다. 아니면 `profiles/rep5x_ender3v3se.ini`의 `part_origin_x/y`를 고치고 아래 명령으로 다시 뽑는다
3. 이 파일들은 **라이브 TCP**(G43.4, 소프트 엔드스톱 켬)로 돈다. SD로 넣어도 USB로 보내도 같다. 끊김(stutter)은 라이브 IK 때문이라 SD로 바꿔도 안 사라진다. L0이나 첫 출력에서 끊기면 `profiles/rep5x_ender3v3se_m668.ini`로 다시 뽑아 **SD로** 출력한다. M668이 파일을 joint 좌표로 미리 바꿔 두기 때문인데, 대신 `M211 S0`이라 보호 장치가 없다. 그 프로파일 머리말을 먼저 읽을 것
4. 핫엔드 충돌 모델은 공식 G-code 뷰어의 것(실측 전 추정)이다. 교체 핫엔드면 실측 후 다시 뽑는다

## 다시 뽑기

```bash
export PYTHONPATH=. MPLBACKEND=Agg
```

```bash
python3 tools/make_ladder_models.py && python3 tools/make_dry_run.py
```

```bash
D=examples/rep5x_ladder; MP=profiles/rep5x_ender3v3se.ini
python3 conical_slice.py $D/cylinder.stl --angle 0 --min-layer-time 8 --mode rep5x --layer-height 0.3 --machine-profile $MP -o $D/L1_cylinder_b0.gcode
python3 conical_slice.py $D/flare.stl --angle 0 --min-layer-time 8 --mode rep5x --layer-height 0.3 --machine-profile $MP -o $D/L2p_flare_planar.gcode
python3 conical_slice.py $D/flare.stl --angle 15 --direction outward --omega-max 180 --strict --min-layer-time 8 --mode rep5x --layer-height 0.3 --machine-profile $MP -o $D/L2_flare_u15.gcode
python3 conical_slice.py $D/lamp_small.stl --angle 22 --direction outward --omega-max 180 --strict --min-layer-time 8 --mode rep5x --layer-height 0.3 --machine-profile $MP -o $D/L3a_lamp_u22.gcode
python3 conical_slice.py $D/lamp_small.stl --profile "0:22,10.27:22,11.34:0,18:0" --omega-max 180 --strict --min-layer-time 8 --mode rep5x --layer-height 0.3 --machine-profile $MP -o $D/L3b_lamp_band22to0.gcode
python3 conical_slice.py $D/cylinder.stl --angle 0 --perimeters 1 --infill-spacing 0 --min-layer-time 8 --mode rep5x --layer-height 0.3 --machine-profile $MP -o $D/L4a_wall_b0.gcode
python3 conical_slice.py $D/cylinder.stl --angle 22 --direction outward --perimeters 1 --infill-spacing 0 --omega-max 180 --strict --min-layer-time 8 --mode rep5x --layer-height 0.3 --machine-profile $MP -o $D/L4b_wall_u22.gcode
python3 conical_slice.py $D/overhang_steps.stl --angle 0 --min-layer-time 8 --mode rep5x --layer-height 0.3 --machine-profile $MP -o $D/L5_overhang_steps_planar.gcode
```

검사:

```bash
python3 rep5x_check.py examples/rep5x_ladder/L2_flare_u15.gcode --omega-max 180
```

```bash
python3 tools/fibr3d_crosscheck.py examples/rep5x_ladder/L2_flare_u15.gcode --emu ../FIBR3DEmul-Rep5x
```

`--strict`는 베드 충돌 때문에 각도를 낮춰야 하면 멈추게 한다. L3의 균일 대조군이 몰래 균일이 아니게 되는 것을 막는다.
