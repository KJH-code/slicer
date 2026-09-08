# 4축 3D 프린터의 적응형 원뿔 슬라이싱 — 발표 자료

이 저장소에는 발표 자료가 **두 개** 들어 있습니다. 둘 다 `styles.css` 와
`assets/` 를 공유하고, 별도 빌드 없이 Chrome 또는 Edge에서 바로 열립니다.

| 파일 | 무엇 | 장수 |
|---|---|---|
| `index.html` | **2026 R&E 중간 성과공유회** (현재 발표) — 저번 문제를 어떻게 해결했나 → 지금 무엇을 하나(5축 프린터 설계) → 다음에 무엇을 하나 | 13 |
| `2026-07-27-midterm.html` | 지난 온라인 멘토링 발표(2026-07-27) — 연구 배경, 알고리즘, 시각화 도구 | 17 |

```text
STL 입력 → 축 센터링 → 원뿔각 결정(J) → 정변환 → 평면 슬라이싱
        → 역변환 → G-code → 툴패스 검사·시각화
```

Reveal.js, Three.js, OrbitControls, STLLoader, KaTeX가 로컬 파일로 들어 있어
인터넷 없이도 동작합니다.

> **9쪽(부품 3D 모델)은 로컬 HTTP 서버로 열어야 합니다.** `file://` 로 열면 브라우저
> 보안 정책 때문에 STL을 경로로 읽지 못하고 안내 문구만 표시됩니다. 아래 *실행 방법*
> 참고.

## 현재 발표(index.html) 슬라이드 구성

발표의 뼈대는 **저번 문제 → 지금 하는 것 → 다음에 할 것** 세 토막입니다.
각 슬라이드의 라벨에 `해결` / `지금` / `다음` 칩이 붙어 있어 어디쯤인지 바로 보입니다.

| # | 내용 | 단계 |
|---|---|---|
| 1 | 표지 | — |
| 2 | **저번에 제기한 문제, 지금 어떻게 되었나** (발표의 뼈대) | — |
| 3 | 하드웨어 없이 “맞다”를 세우는 법 — 검증 계층 5층 | 해결 |
| 4 | 여러 형상에서 재보니 이기는 조건이 있었다 | 해결 |
| 5 | STL 하나를 넣으면 G-code까지 — 통합 파이프라인 | 해결 |
| 6 | 출력할 기계를 정한다 — 3D 프린터 설계 | 지금 |
| 7 | Rep5x — 공개된 5축 개조 설계 (홈페이지 화면 재현) | 지금 |
| 8 | 기계가 어떻게 생겼나 — 사진과 **우리가 얻은 숫자** | 지금 |
| 9 | 부품을 3D 모델로 하나씩 (부품 10종 전환 뷰어) | 지금 |
| 10 | 기계가 정해지자 코드가 달라졌다 + B/C 자세 애니메이션 | 지금 |
| 11 | 지금 걸려 있는 것 | 지금 |
| 12 | 계산으로 갈 수 있는 끝까지 | 다음 |
| 13 | 출처 | — |

> **실물 제작은 현재 불가능합니다.** 6쪽에서 그것을 먼저 밝히고, 이번 범위를
> “설계까지”로 못박습니다. 12쪽의 실물 출력도 계획이 아니라 *여건이 생기면*
> 하는 일로 적혀 있습니다. 발표 중에 이 선을 넘지 않도록 문구를 그대로 두세요.

### 발표 전에 채워야 할 것

- **10쪽 영상 자리** — 실제 출력 영상이 생기면 `.video-placeholder` 를 `<video>` 로
  바꿉니다. (지난 발표 `2026-07-27-midterm.html` 9쪽에 사용 예가 있습니다.)
- **표지의 발표 일자** — 그룹별 일정이 확정되면 1쪽 `.eyebrow` 에 추가합니다.

### HTML로 만든 이유 — 화면에서 움직이는 것들

정적 슬라이드로는 안 되는 것을 쓰려고 HTML로 만들었습니다. reactbits.dev 의
컴포넌트들을 React 없이 Canvas2D + CSS 로 다시 구현해 넣었습니다.

| 무엇 | 어디 | 구현 |
|---|---|---|
| 부품 3D 뷰어 | 9쪽 | Three.js (`rep5x-parts.js`) |
| B/C 자세 애니메이션 | 10쪽 | 위 코드와 **같은 식을 실시간 계산** (`rep5x-motion.js`) |
| Galaxy 별밭 | 1쪽 배경 | `rep5x-fx.js` |
| Fuzzy Text | 1쪽 제목 | 캔버스에 그린 뒤 줄마다 흔든다 |
| ASCII Text | 6쪽 배경 워터마크 | 5×7 비트맵 글꼴 + 물결 |
| Magnet Lines | 12쪽 배경 | 커서를 가리키는 선 격자 |
| Ballpit | 13쪽 배경 | 충돌하는 공, 커서에 밀린다 |
| Tilted Card + 광택 | 모든 카드 | `[data-tilt]` — 커서 쪽으로 기운다 |
| Fluid Glass | 모든 카드 | `backdrop-filter` 유리 질감 (`rep5x.css`) |
| Splash Cursor | 전체 | 커서를 따라 번지는 자국 — 발표 중 포인팅용 |
| 진입 연출 | 전 슬라이드 | 카드가 읽는 순서대로 올라온다 |

배경 효과는 그 슬라이드가 화면에 있을 때만 돌고,
`prefers-reduced-motion` 을 켠 환경에서는 전부 꺼집니다.

### 새 발표 자료의 파일 구성

```text
index.html          # 13개 슬라이드
rep5x.css           # 레이아웃·글자 크기·유리 질감·CSS 애니메이션
rep5x-deck.js       # 발표자 메모
rep5x-parts.js      # 9쪽 부품 탐색기 (부품 데이터 + 3D 뷰어)
rep5x-motion.js     # 진입 연출 + 10쪽 B/C 자세 애니메이션
rep5x-fx.js         # Galaxy·Ballpit·Fuzzy·ASCII·Magnet·Tilt·Splash
assets/models/rep5x/*.stl    # Rep5x 부품 3D 모델 (3MF→STL, NOTICE.md 참고)
assets/images/rep5x/*.jpg    # Rep5x 조립 사진 (축소본)
```

부품 설명과 사진은 전부 `rep5x-parts.js` 상단의 `REP5X_PARTS` 객체 한 곳에
모여 있습니다. 부품을 추가하려면 그 객체에 항목을 넣고 `index.html` 의
`.parts-list` 에 버튼을 하나 추가하면 됩니다.

> `assets/models/rep5x/` 와 `assets/images/rep5x/` 의 자료는 오픈소스 프로젝트
> **Rep5x**(Dennis Klappe, GPL v3)의 것입니다. 출처와 변환 절차는
> [`assets/models/rep5x/NOTICE.md`](assets/models/rep5x/NOTICE.md) 에 있습니다.

## 프로젝트 구조

```text
adaptive-conical-slicing-presentation/
├─ index.html                 # 중간 성과공유회 13개 슬라이드
├─ 2026-07-27-midterm.html    # 지난 발표 17개 슬라이드
├─ rep5x.css / rep5x-deck.js / rep5x-parts.js
├─ styles.css                 # 16:9 레이아웃, 40px 안전 여백, 인쇄 스타일
├─ presentation.js            # 이동, 번호, 전체 화면, 탭, 발표자 메모
├─ stl-viewer.js              # STL 표시와 연결 성분별 면 색상 적용
├─ README.md
└─ assets/
   ├─ models/                 # 실제 STL과 연결 성분 JSON 위치
   │  └─ rep5x/               # Rep5x 부품 STL + NOTICE.md
   ├─ images/                 # 발표 참고 이미지와 결과 화면
   │  └─ rep5x/               # Rep5x 조립 사진
   ├─ data/
   │  ├─ model-manifest.json
   │  ├─ component-result-example.json
   │  ├─ results-summary.json
   │  └─ pipeline-schema.json
   └─ vendor/
      ├─ reveal/
      └─ three/
```

## 실행 방법

### 방법 1: 바로 열기

1. ZIP 파일의 압축을 풉니다.
2. `index.html`을 더블 클릭합니다.
3. 연결 프로그램이 표시되면 Chrome 또는 Edge를 선택합니다.

이 방식에서도 슬라이드 이동, 전체 화면, 탭 전환, 사용자가 직접 선택한 STL/JSON 파일 읽기가 동작합니다. 브라우저 보안 정책 때문에 미리 정한 경로에서 파일을 자동으로 읽는 기능은 제한됩니다.

### 방법 2: 로컬 HTTP 서버 사용 — 권장

PowerShell에서 프로젝트 폴더로 이동한 뒤 다음 명령을 실행합니다.

```powershell
cd "C:\경로\adaptive-conical-slicing-presentation"
python -m http.server 8000
```

Chrome 또는 Edge에서 다음 주소를 엽니다.

```text
http://localhost:8000
```

서버를 종료하려면 PowerShell에서 `Ctrl + C`를 누릅니다. 이 방식에서는 `assets/models/`와 `assets/data/`의 파일을 발표 화면에서 경로로 자동 로드할 수 있습니다.

## 발표 조작

| 조작 | 기능 |
| --- | --- |
| `←`, `↑`, `PageUp` | 이전 슬라이드 |
| `→`, `↓`, `PageDown`, `Space` | 다음 슬라이드 |
| `Home` / `End` | 첫 슬라이드 / 마지막 슬라이드 |
| 마우스 휠 | 이전 / 다음 슬라이드 |
| 오른쪽 아래 화살표 | 이전 / 다음 슬라이드 |
| `F` 또는 `⛶` | 전체 화면 전환 |
| STL 화면 드래그 | 모델 회전 |
| STL 화면 휠 | 확대·축소 |
| STL 화면 오른쪽 드래그 | 이동 |

STL 뷰어와 버튼 영역에서의 휠 입력은 슬라이드 전환에 전달되지 않습니다.

## 실제 STL 모델 연결 (지난 발표 `2026-07-27-midterm.html`)

> 아래 세 절의 쪽 번호는 **지난 발표 자료** 기준입니다. 현재 발표(`index.html`)의
> 부품 3D 모델은 `rep5x-parts.js` 가 `assets/models/rep5x/` 에서 바로 읽습니다.

다음 여섯 파일을 `assets/models/`에 넣습니다.

```text
arch-01.stl
arch-02.stl
arch-03.stl
l-shape-01.stl
l-shape-02.stl
l-shape-03.stl
```

그다음 `assets/data/model-manifest.json`에서 추가한 모델의 `available`을 `true`로 바꿉니다.

```json
{
  "id": "arch-01",
  "label": "아치형 1",
  "stl": "arch-01.stl",
  "components": "arch-01.components.json",
  "available": true
}
```

HTTP 서버로 연 뒤 8쪽에서 모델 탭을 선택하고 `폴더에서 불러오기`를 누르면 해당 STL을 표시합니다. `file://`로 연 경우에는 `STL 직접 선택`을 사용합니다.

## 연결 성분 JSON과 면 색상 (지난 발표)

10쪽 뷰어는 STL의 각 삼각형에 연결 성분 번호를 대응시켜 색을 입힙니다. JSON 파일은 STL과 같은 이름 규칙으로 `assets/data/`에 둡니다.

```text
assets/models/arch-01.stl
assets/data/arch-01.components.json
```

JSON 형식은 `assets/data/component-result-example.json`을 참고합니다.

```json
{
  "schemaVersion": 1,
  "stlFile": "arch-01.stl",
  "triangleCount": 6,
  "faceComponents": [-1, -1, 0, 0, 1, 1],
  "components": [
    {
      "label": "I_c1",
      "color": "#ff9d45",
      "selectedAngleDeg": null,
      "hMin": null,
      "hMax": null
    }
  ]
}
```

- `faceComponents[i]`는 STL의 i번째 삼각형이 속한 성분 번호입니다.
- `-1`은 일반 면이며 회색으로 표시됩니다.
- `0`, `1`, `2`는 `components` 배열의 순서입니다.
- `components[].color`에 CSS 색상값을 넣으면 해당 연결 성분의 표시색이 됩니다.
- `faceComponents` 길이는 실제 STL 삼각형 수와 같아야 합니다.
- 분석 과정과 발표 뷰어가 동일한 STL 삼각형 순서를 사용해야 합니다.

HTTP 서버에서는 STL과 JSON을 추가한 뒤 10쪽의 `폴더에서 불러오기`를 사용합니다. 파일명을 다르게 사용하려면 `STL 선택`, `JSON 선택`, `선택 파일 적용`을 차례로 누릅니다.

## Excel 시뮬레이션 결과 연결 (지난 발표)

원본 `.xlsx`는 `assets/data/`에 보관할 수 있습니다. 브라우저가 Excel 전체를 직접 분석하지 않도록 발표에 표시할 요약값은 `assets/data/results-summary.json`에 적습니다.

```json
{
  "status": "ready",
  "sourceFile": "simulation-results.xlsx",
  "sheet": "선택원뿔각",
  "input": "q0, kappa_max",
  "metric": "선택 각도·실행 시간",
  "finding": "실제 결과 요약"
}
```

`status`가 `pending`이면 11쪽은 자리표시자를 유지합니다. JSON 자동 로드는 HTTP 서버 실행 시 동작합니다.

## 슬라이드 문구와 발표자 메모 수정

수정할 발표 자료의 HTML에서 `<section id="slide-N">`을 검색해 해당 슬라이드 문구를 수정합니다. 제목 위치는 모든 본문 슬라이드에서 같은 `.slide-header`를 사용합니다.

발표자 메모는 현재 발표는 `rep5x-deck.js`, 지난 발표는 `presentation.js`의
`speakerNotes` 객체에 있습니다. `rep5x-deck.js`가 먼저 로드되면 `presentation.js`의
기본 메모를 덮지 않습니다.

```javascript
const speakerNotes = {
  1: "연구 주제와 전체 목표를 소개한다.",
  2: "발표 순서를 안내한다."
};
```

메모는 발표 화면에 기본적으로 보이지 않습니다.

## 슬라이싱 미니 애니메이션 수정 (지난 발표)

지난 발표 자료 4쪽의 네 개 애니메이션은 `index.html`의 SVG로 구성됩니다.

- 형상: `.slice-model`의 `d` 값
- 레이어: `.layer-lines` 안의 `<path>`
- 재생 간격: 각 path의 `style="--delay:N"`
- 색상과 이동 효과: `styles.css`의 `.slice-animation`, `.layer-lines`

실제 슬라이싱 계산 결과가 아니라 네 방식의 차이를 설명하는 개념도입니다.

## 주요 색상, 글꼴, 여백 수정

`styles.css`의 `:root` 변수에서 전체 디자인을 조정합니다.

```css
:root {
  --bg: #07111f;
  --text: #f4f8fb;
  --teal: #2de2c5;
  --orange: #ff9d45;
  --safe-x: 40px;
  --font-sans: "Pretendard", "Noto Sans KR", "Malgun Gothic", sans-serif;
}
```

`--safe-x`는 양옆 사용 금지 영역입니다. 화면 버튼과 진행 막대도 40px 경계 안쪽에 배치되어 있습니다.

## CDN으로 교체

현재는 오프라인 발표를 위해 로컬 라이브러리를 사용합니다. CDN 방식으로 바꾸려면 `index.html`의 경로를 다음처럼 교체합니다.

```html
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.css">

<script src="https://cdn.jsdelivr.net/npm/reveal.js@5.1.0/dist/reveal.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
```

다시 오프라인 방식으로 전환하려면 동일 버전의 파일을 아래 위치에 저장하고 현재 로컬 경로를 복원합니다.

```text
assets/vendor/reveal/reveal.css
assets/vendor/reveal/reveal.js
assets/vendor/three/three.min.js
assets/vendor/three/OrbitControls.js
assets/vendor/three/STLLoader.js
```

## 인쇄 또는 PDF 저장

Chrome/Edge에서 `Ctrl + P`를 누른 뒤 다음 설정을 권장합니다.

- 대상: PDF로 저장
- 레이아웃: 가로
- 용지: 16:9 또는 사용자 지정
- 여백: 없음
- 배경 그래픽: 켜기

브라우저 인쇄는 WebGL STL 화면을 캡처하는 시점에 따라 결과가 달라질 수 있습니다. 중요한 모델 화면은 먼저 해당 슬라이드에서 로드한 뒤 인쇄합니다.

## 알려진 제한 사항

### 현재 발표(index.html)

- **실물 제작이 현재 불가능합니다.** 물리 검증(브리징·수축·층간 접착)은 여전히 0건이고,
  모든 결론은 '증명'이 아니라 '경향'으로 씁니다.
- **10쪽 실제 출력 영상이 아직 없습니다.** 제작 여건이 생기면 채웁니다.
- **9쪽 3D 모델은 HTTP 서버에서만 자동 로드됩니다.** `file://` 로 열면 안내 문구가 표시됩니다.
- 10쪽의 `conical/rep5x.py` 코드는 **설계안이며 아직 구현·검증 전**입니다(11쪽 02번).
- Rep5x 사진·3D 모델은 GPL v3 자료이며 저작권은 원저작자에게 있습니다.

### 지난 발표(2026-07-27-midterm.html)

- 여섯 STL 모델과 연결 성분 JSON은 아직 자리표시자이며 사용자가 추가해야 합니다.
- 평가함수 코드와 성공 결과는 9쪽·11쪽 왼쪽에 `내용 추가 예정`으로 표시됩니다.
- Excel 원본 파일과 요약값은 아직 추가되지 않았습니다.
- 연결 성분의 색상 정확도는 STL 삼각형 순서와 JSON 배열 순서가 같을 때 보장됩니다.
- 교선 시각화는 기하학적 결과이며 실제 출력 가능한 G-code를 보장하지 않습니다.
- G-code 생성, 평면/원뿔 경계 처리, 축 제약, 충돌, 실제 출력 검증은 진행 중인 연구로 구분되어 있습니다.
- 사용자 제공 참고 이미지 중 원본 URL이 확인되지 않은 항목은 발표자 메모에 `출처 URL 추가 필요`로 남아 있습니다.
