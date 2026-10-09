# Rep5x 3D 부품 모델 — 출처와 변환 절차

이 폴더의 STL 파일은 **우리가 설계한 것이 아니다.** 오픈소스 5축 레트로핏 프로젝트
[Rep5x](https://github.com/dennisklappe/Rep5x)(제작: Dennis Klappe, **GPL v3**)의 3MF 파일을
발표 화면에 띄우기 위해 STL로 변환한 것이다. 저작권은 원저작자에게 있다.

발표 자료(9쪽)와 `assets/images/rep5x/`의 조립 사진도 같은 저장소에서 가져왔다.

## 원본 위치

| STL | 원본 3MF |
|---|---|
| `b-arm.stl` | `build-guide/universal-parts/3d-printed-parts/current/3mf/b-arm_v1.1.0.3mf` |
| `c-driven-pulley.stl` | `.../universal-parts/.../C-driven-pulley_v1.1.0.3mf` |
| `b-driven-pulley.stl` | `.../universal-parts/.../b-driven-pulley_v1.1.0.3mf` |
| `slip-ring-holder.stl` | `.../universal-parts/.../slip-ring-holder_v1.1.1.3mf` |
| `hotend-spacer.stl` | `.../universal-parts/.../hotend-spacer_v1.0.0.3mf` |
| `spacer-3mm.stl` | `.../universal-parts/.../spacer-3mm_v1.0.0.3mf` |
| `e3v3se-carriage-mount.stl` | `build-guide/printer-specific/ender-3-v3-se/3d-printed-parts/current/3mf/carriage-mount_v1.1.1.3mf` |
| `e3v3se-extruder-mount.stl` | `.../ender-3-v3-se/.../extruder-mount_v1.1.0.3mf` |
| `e3v3se-x-endstop.stl` | `.../ender-3-v3-se/.../x-endstop_v1.1.0.3mf` |
| `e3v3se-z-endstop.stl` | `.../ender-3-v3-se/.../z-endstop_v1.1.0.3mf` |

## 변환 절차

3MF는 zip 안에 `3D/3dmodel.model`(XML)이 들어 있는 형식이다. 다음을 그대로 옮겼다.

1. `<vertices>` / `<triangles>` 를 읽는다 (단위는 밀리미터).
2. `<build><item>` 과 `<components>` 의 `transform`(열우선 4×3)을 정점에 적용한다.
3. 삼각형마다 법선을 `(v2−v1) × (v3−v1)` 로 계산해 이진 STL로 쓴다.

**형상은 바꾸지 않았다** — 스케일·회전·단순화 없이 삼각형을 그대로 옮긴 것이므로,
뷰어에 표시되는 치수는 원본 CAD 치수와 같다.

| 파일 | 삼각형 수 | 바운딩박스 (mm) |
|---|---|---|
| `b-arm` | 10,268 | 48.0 × 91.8 × 51.4 |
| `c-driven-pulley` | 40,812 | 41.0 × 41.0 × 31.4 |
| `b-driven-pulley` | 23,124 | 41.0 × 41.0 × 25.4 |
| `slip-ring-holder` | 2,840 | 3.8 × 15.8 × 14.0 |
| `hotend-spacer` | 692 | 20.0 × 4.0 × 6.0 |
| `spacer-3mm` | 684 | 21.0 × 7.0 × 3.0 |
| `e3v3se-carriage-mount` | 16,534 | 119.9 × 56.5 × 58.0 |
| `e3v3se-extruder-mount` | 4,412 | 46.5 × 97.5 × 65.0 |
| `e3v3se-x-endstop` | 6,538 | 27.0 × 25.5 × 7.6 |
| `e3v3se-z-endstop` | 1,442 | 21.0 × 22.0 × 19.0 |

## 실제 출력에는 원본을 쓸 것

이 STL은 **발표 표시용**이다. 부품을 실제로 출력할 때는 저장소의 3MF(출력 설정이 함께
들어 있다)나 STEP 파일을 쓰는 것이 맞다. 버전도 저장소의 `current/`를 다시 확인할 것.

## 사진 (`assets/images/rep5x/`)

같은 저장소의 `build-guide/images/` 와
`build-guide/printer-specific/ender-3-v3-se/images/` 에서 가져와, 발표 용량을 줄이려고
가로 1,100~1,600 px, JPEG 품질 80으로 축소만 했다. 내용은 손대지 않았다.
