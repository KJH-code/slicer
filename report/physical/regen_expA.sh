#!/usr/bin/env bash
# 실험 4 G-code 를 **우리 기계 프로파일로** 다시 뽑고 사전 점검까지 돌린다.
#
#   bash report/physical/regen_expA.sh profiles/our_machine.ini [rep5x|xyz]
#
# 템플릿 프로파일(name 에 TEMPLATE)이면 멈춘다 — 예열·호밍·프라임 값이 실기 값이 아니다.
# 경로 자체는 examples/lamp_expA_*.gcode 와 같다(템플릿으로 돌리면 바이트 단위로 같음을 확인).
set -euo pipefail
PROFILE=${1:?기계 프로파일 INI 경로를 주세요}
MODE=${2:-rep5x}
# 되감기 피드(F, 회전만 하는 이동). 기본 1200 = 20 deg/s 로 해석되면 1 회전 18 초.
# 기계에서 빠르게 돌려 보고 안전한 값을 확인한 뒤에만 올린다. **두 전략에 같은 값.**
REWIND_FEED=${REWIND_FEED:-1200}
cd "$(dirname "$0")/../.."
export PYTHONPATH=. MPLBACKEND=Agg
if grep -q "TEMPLATE" "$PROFILE"; then
  echo "✗ $PROFILE 은 템플릿이다. name/온도/호밍/프라임을 실기 값으로 바꾼 뒤 다시." >&2
  exit 1
fi
OUT=report/physical/gcode
mkdir -p "$OUT"
for LH in 0.3 0.4; do
  T=${LH/./}
  SUF=""; [ "$MODE" = rep5x ] && SUF="_rep5x"
  python3 conical_slice.py examples/lamp.stl --angle 24 --direction outward \
    --layer-height "$LH" --mode "$MODE" --machine-profile "$PROFILE" --v-rewind-feed "$REWIND_FEED" \
    -o "$OUT/lamp_expA_uniform24_lh${T}${SUF}.gcode"
  python3 conical_slice.py examples/lamp.stl --auto-bands 2 \
    --layer-height "$LH" --mode "$MODE" --machine-profile "$PROFILE" --v-rewind-feed "$REWIND_FEED" \
    -o "$OUT/lamp_expA_band2_lh${T}${SUF}.gcode"
done
if [ "$MODE" = rep5x ]; then
  for G in "$OUT"/*_rep5x.gcode; do
    echo "== $G"
    python3 rep5x_check.py "$G" --stride 4   # 최종 판정은 --stride 1, --arm-radius 실측값으로
  done
else
  for G in "$OUT"/*.gcode; do
    echo "== $G"
    python3 toolpath_check.py "$G" --nozzle
  done
fi
md5sum "$OUT"/*.gcode
