#!/usr/bin/env bash
# fetch_s3_dataset.sh — S³-Slicer 저장소에서 사다리 실험에 필요한 결과물만 받는다.
#
#   bash tools/fetch_s3_dataset.sh <목적지 디렉토리>
#
# 받는 것 (모델당 수 MB, 전체 수십 MB):
#   <dst>/<model>.tet            입력 사면체 메시 (DataSet/TET_MODEL)
#   <dst>/wp_<model>/*.txt       곡면 레이어 웨이포인트 x y z nx ny nz (DataSet/fabricationSource)
#
# 저장소 전체(수백 MB, G-code·FEM 결과 포함)를 받지 않으려고 blob 필터 클론 뒤
# 필요한 파일만 `git show` 로 꺼낸다. 받은 것은 외부 데이터다 — 저장소에 커밋하지 않는다.
set -euo pipefail
DST="${1:?목적지 디렉토리를 주세요}"
REPO=https://github.com/zhangty019/S3_DeformFDM
REV=a77ef04115b1383a58f228a7f67ce4434c9d09f3     # 2025-04-24 main. 고정해 재현 가능하게.

mkdir -p "$DST"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone -q --filter=blob:none --no-checkout "$REPO" "$TMP/s3"
cd "$TMP/s3"
git -c advice.detachedHead=false checkout -q "$REV" -- . 2>/dev/null || true

# (tet 파일명, fabricationSource 폴더명)
PAIRS="ring:ring teapot:teapot bunny_cut6:bunny topopt_new4:topopt armadillo4:armadillo AnkleBaseV1:ankleBase"
for pair in $PAIRS; do
  tet="${pair%%:*}"; wp="${pair##*:}"
  git show "$REV:DataSet/TET_MODEL/$tet.tet" > "$DST/$tet.tet"
  mkdir -p "$DST/wp_$tet"
  for f in $(git ls-tree -r --name-only "$REV" -- "DataSet/fabricationSource/$wp/waypoint"); do
    git show "$REV:$f" > "$DST/wp_$tet/$(basename "$f")"
  done
  echo "$tet: $(head -1 "$DST/$tet.tet"), waypoint $(ls "$DST/wp_$tet" | wc -l) files"
done
