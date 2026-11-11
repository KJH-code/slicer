// R&E 연구보고서 초안 생성기 (v2: 수식·수치·그림 위주)
//   node build_report_v5.js report_v5.docx  (v5: v4 검토 지적 반영 — 표본 서술·S4 범위·k 기본값·교차참조·기호, 2026-11-11)
// 그림: docs/report/figures/<slug>.png 가 있으면 넣고, 없으면 자리 상자(slug 표기)를 넣는다.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType,
  AlignmentType, BorderStyle, ShadingType, PageBreak, VerticalAlign, HeadingLevel, ImageRun,
} = require("docx");

const FONT = "함초롬바탕";
const MONO = "Consolas";
const BODY = 20; // 10pt
const W = 9638;  // A4, 여백 20mm
const FIG_DIR = path.join(__dirname, "figures");

// ---------- 인라인: **굵게**, 【보류】(노랑) ----------
function runs(text, o = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|【[^】]*】)/g;
  let last = 0, m;
  const mk = (t, extra = {}) => new TextRun({ text: t, font: o.font || FONT, size: o.size || BODY, bold: o.bold, ...extra });
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(mk(text.slice(last, m.index)));
    const t = m[0];
    out.push(t.startsWith("**") ? mk(t.slice(2, -2), { bold: true }) : mk(t, { bold: true, highlight: "yellow" }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(mk(text.slice(last)));
  return out;
}
const P = (text, o = {}) => new Paragraph({
  children: runs(text, o), alignment: o.align || AlignmentType.JUSTIFIED,
  indent: o.noIndent ? undefined : { firstLine: 200 },
  spacing: { before: o.before ?? 0, after: o.after ?? 80, line: 300 }, keepNext: o.keepNext,
});
const EQ = (text, tag) => new Paragraph({
  children: [new TextRun({ text, font: "Cambria Math", size: BODY }), ...(tag ? [new TextRun({ text: `    (${tag})`, font: FONT, size: BODY })] : [])],
  alignment: AlignmentType.CENTER, spacing: { before: 40, after: 60 },
});
const BUL = (text) => new Paragraph({ children: runs(text), indent: { left: 360, hanging: 240 }, spacing: { after: 40, line: 280 } });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: t, font: FONT, size: 26, bold: true })], spacing: { before: 260, after: 100 }, keepNext: true });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: t, font: FONT, size: 22, bold: true })], spacing: { before: 160, after: 60 }, keepNext: true });
const BANNER = (t) => new Paragraph({ children: [new TextRun({ text: t, font: FONT, size: 28, bold: true })], spacing: { after: 160 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: "000000", space: 4 } } });
const CAPTION = (t) => new Paragraph({ children: runs(t, { bold: true, size: 18 }), alignment: AlignmentType.CENTER, spacing: { before: 100, after: 50 }, keepNext: true });
const FIGCAP = (t) => new Paragraph({ children: runs(t, { bold: true, size: 18 }), alignment: AlignmentType.CENTER, spacing: { before: 30, after: 140 } });
const NOTE = (t) => new Paragraph({ children: runs(t, { size: 16 }), spacing: { before: 20, after: 100 } });
const BR = () => new Paragraph({ children: [new PageBreak()] });

const line = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const borders = { top: line, bottom: line, left: line, right: line };
function cell(text, width, o = {}) {
  return new TableCell({
    children: String(text).split("\n").map((t) => new Paragraph({ children: runs(t, { size: o.size || 18, bold: o.bold, font: o.font }), alignment: o.align || AlignmentType.LEFT, spacing: { before: 10, after: 10, line: 250 } })),
    width: { size: width, type: WidthType.DXA }, borders,
    shading: o.fill ? { fill: o.fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
    verticalAlign: VerticalAlign.CENTER, margins: { top: 40, bottom: 40, left: 80, right: 80 },
  });
}
function table(widths, rows, o = {}) {
  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths, alignment: AlignmentType.CENTER,
    rows: rows.map((r, i) => new TableRow({
      tableHeader: i === 0 && o.header !== false,
      children: r.map((c, j) => cell(c, widths[j], {
        bold: (i === 0 && o.header !== false) || (o.firstColBold && j === 0),
        fill: (i === 0 && o.header !== false) || (o.firstColFill && j === 0) ? "E7E6E6" : undefined,
        align: o.center && !(o.firstColBold && j === 0) ? AlignmentType.CENTER : AlignmentType.LEFT, size: o.size,
      })),
    })),
  });
}
// ---------- 코드 상자: 실제 저장소 코드 발췌 ----------
function CODE(lines, src) {
  const paras = lines.map((l) => new Paragraph({ children: [new TextRun({ text: l || " ", font: MONO, size: 16 })], spacing: { before: 0, after: 0, line: 230 } }));
  paras.push(new Paragraph({ children: [new TextRun({ text: src, font: FONT, size: 14, italics: true, color: "555555" })], alignment: AlignmentType.RIGHT, spacing: { before: 30, after: 0 } }));
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: [W],
    rows: [new TableRow({ children: [new TableCell({ children: paras, width: { size: W, type: WidthType.DXA }, borders, shading: { fill: "F4F4F4", type: ShadingType.CLEAR, color: "auto" }, margins: { top: 60, bottom: 60, left: 120, right: 120 } })] })],
  });
}
// ---------- 그림: PNG 있으면 삽입, 없으면 자리 ----------
function pngSize(buf) { return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) }; }
let figNo = 0;
function FIG(slug, caption, widthCm = 15, note = "") {
  figNo += 1;
  const f = path.join(FIG_DIR, `${slug}.png`);
  const out = [];
  if (fs.existsSync(f)) {
    const buf = fs.readFileSync(f); const { w, h } = pngSize(buf);
    const px = Math.round(widthCm / 2.54 * 96);
    out.push(new Paragraph({ children: [new ImageRun({ type: "png", data: buf, transformation: { width: px, height: Math.round(px * h / w) } })], alignment: AlignmentType.CENTER, spacing: { before: 80, after: 20 }, keepNext: true }));
  } else {
    out.push(table([Math.round(widthCm * 567)], [[`【그림 대기: ${slug}.png】\n${note}`]], { header: false, center: true, size: 16 }));
  }
  out.push(FIGCAP(`[Fig. ${figNo}] ${caption}`));
  return out;
}

// 반폭 그림 두 개를 나란히 (각자 캡션)
function PAIR(a, b, widthCm = 8) {
  const colW = Math.round(W / 2);
  const one = (slug, cap) => {
    figNo += 1;
    const f = path.join(FIG_DIR, `${slug}.png`);
    const kids = [];
    if (fs.existsSync(f)) {
      const buf = fs.readFileSync(f); const { w, h } = pngSize(buf);
      const px = Math.round(widthCm / 2.54 * 96);
      kids.push(new Paragraph({ children: [new ImageRun({ type: "png", data: buf, transformation: { width: px, height: Math.round(px * h / w) } })], alignment: AlignmentType.CENTER }));
    } else {
      kids.push(new Paragraph({ children: runs(`【그림 대기: ${slug}.png】`, { size: 16 }), alignment: AlignmentType.CENTER, spacing: { before: 400, after: 400 } }));
    }
    kids.push(new Paragraph({ children: runs(`[Fig. ${figNo}] ${cap}`, { bold: true, size: 16 }), alignment: AlignmentType.CENTER, spacing: { before: 30, after: 60 } }));
    const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
    return new TableCell({ children: kids, width: { size: colW, type: WidthType.DXA }, borders: { top: none, bottom: none, left: none, right: none } });
  };
  return new Table({ width: { size: colW * 2, type: WidthType.DXA }, columnWidths: [colW, colW], alignment: AlignmentType.CENTER,
    rows: [new TableRow({ children: [one(a[0], a[1]), one(b[0], b[1])] })] });
}
let tabNo = 0;
const TAB = (caption) => { tabNo += 1; return CAPTION(`Table ${tabNo}. ${caption}`); };

// =====================================================================
const C = [];
// ===================== v4 본문 (2026-11-10, 추가 테스트 반영) =====================
// 출처: docs/report/body_restructure.md 의 근거 지도.
//   T1·T4·k 스윕·k 추정·밴드 경계·그림 A/C/E/F/G — claude/t1-t4-conventional-robustness
//   등왜곡 기준선(실험 1)·층고(실험 2)·보류 모델(실험 3)·각도 비용(실험 5) — claude/serene-cray-u07dzk

const REP = "모델마다 각도를 고르는 자동 결정은 같은 평균 기울기(23°)에서 한 각도를 모든 모델에 쓰는 것보다 미지지 합을 33~48% 줄였고, 높이별 두 구간(밴드2)은 같은 평균 기울기의 균일 원뿔보다 16개 중 15개 모델에서 오버행이 적었다(층고 0.3mm). 다만 기울기 비용을 두지 않는 지표에서는 고정 45° 가 자동 결정보다 나았다(사전 기준 불통과)";

// ---------------- 1. 연구결과 요약문 ----------------
C.push(BANNER("1. 연구결과 요약문"));
C.push(table([1900, W - 1900], [
  ["과 제 명", "형상 적응형 원뿔 슬라이싱: 원뿔각 자동 결정 알고리즘과 그 신뢰성 검증"],
  ["연구 필요성\n및 목적", "원뿔 슬라이싱은 층을 원뿔면으로 쌓아 서포트 없이 오버행을 출력하는 다축 3D 프린팅 기법이다. 위치마다 출력 방향을 최적화하는 곡면 슬라이싱보다 설계변수가 훨씬 적어 계산이 가볍고 방사 대칭 형상에 효과적이다. 그러나 원뿔각은 지금까지 사용자가 정해 왔고, 형상에서 원뿔각을 자동으로 정하는 알고리즘은 조사 범위 내에서 확인되지 않았다. 본 연구는 STL 에서 원뿔각과 높이 구간별 각도를 자동 결정하는 알고리즘을 만들고, 그 결정의 근거·신뢰성과 구간 개수에 따른 거동을 검증한다."],
  ["연구내용\n및\n결과", "① 원본 면 법선으로 서포트를 판정하는 해석식(유효 오버행 = 원래 오버행 − θ)과 면별 임계각 유도 ② 가변각의 층간격 Δz = h − r·Δtanθ 로 층 교차 방지 조건·블렌드 최소 폭 유도 ③ 서포트와 기울기를 맞바꾸는 목적함수 J 로 각도·방향·구간별 각도 자동 결정. 21개 모델에서 같은 평균 기울기(23°)의 고정 단일각보다 미지지 합 33~48% 감소, 밴드2 는 같은 평균 기울기의 균일 원뿔보다 15/16 모델에서 오버행 감소. 기울기 비용이 없는 지표에서는 고정 45° 가 나아 사전 기준은 불통과 ④ 각도 비용 가중치 k 를 데이터로 추정하면 0.06(95% 0.055~0.08), 층고에 따라 다름 ⑤ 구간 수는 세 개 이상에서 블렌드 층간격 팽창이 G-code 미지지를 키워 툴패스 검사로 상한(N ≤ 2) ⑥ 공개 곡면 슬라이서(S4 Slicer)와 같은 판정식으로 비교하면 S4 가 유효하게 수렴한 2개 모델(sphere·torus)에서 원뿔족의 서포트가 같거나 낮고 계산은 모델별 약 450~1,200배 빠름(funnel·mushroom 은 S4 실패로 비교 불가)"],
  ["향후\n연구계획\n(요약)", "Ender-3 V3 SE 를 REP5X 설계로 개조한 5축 프린터로 사전 등록한 시험 출력(L0~L5)을 수행해 판정 기준·압출 모형·각도 비용을 실물로 확인하고, 연속 오버행 지표와 면적 구적 개선, 축에서 크게 벗어난 비축대칭 형상(가지·돌출부가 있는 형상)으로 범위를 넓힌다."],
  ["Keyword\n(5개 이내)", "원뿔 슬라이싱, 원뿔각 자동 결정, 가변 원뿔각, 서포트 저감, 다축 3D 프린팅"],
], { header: false, firstColBold: true, firstColFill: true, size: 18 }));
C.push(BR());

// ---------------- 2. 과제 수행 과정 ----------------
C.push(BANNER("2. 과제 수행 과정"));
C.push(NOTE("※ 외부 전문가 피드백, 생성형 AI 활용 표, 팀원 역할·기여도 칸은 팀이 직접 작성한다(이 초안에서 제외)."));
C.push(table([1900, W - 1900], [
  ["문제해결\n과정", "① 판정 기준 선택 — 원뿔 변환은 XY 를 1/cosθ 배로 늘리는 비등각 사상이라 변환 공간의 각도는 실제 각도가 아니다(funnel: 실제 26° 에서 해결되는 벽이 변환 공간에서는 50.7° 필요). 원본 법선에서 층 방향을 직접 계산하는 해석식 하나를 판정 기준으로 정하고, 세 번 재유도와 팀원 독립 구현(약 22,000면)으로 대조하였다.\n② 가변각 안전 조건 — 이웃 두 원뿔 층의 높이 차로 층 교차 방지 조건과 블렌드 최소 폭을 닫힌 식으로 얻어 계획기에 넣었다.\n③ 해석의 공정성 — 평면이 아닌 균일 원뿔과 비교하고, 판정 기준은 결과 전에 문서로 고정하였다. 관례 각도 비교가 사전 기준을 통과하지 못하자 그 결과를 그대로 기록하고, 원인(각도 비용이 없는 지표)을 k 스윕·k 추정이라는 별도 시험으로 분리해 검증하였다.\n④ 결함 추적 — funnel 이 상한 아래에서 0° 를 고르는 현상과 메시 세분화에 따라 밴드 각도가 바뀌는 현상을 각각 가설·절제 실험으로 원인(판정 문턱 위치, 면 중심 구적)까지 좁혔다.\n⑤ 기계 안전 — 출력용 G-code 는 자체 사전 검사기와 팀원의 가상 프린터(독립 역기구학)를 모두 통과해야 출력하도록 하였다."],
  ["과제 수행\n과정에서의 학습", "좌표 변환과 역변환, 벡터 내적과 삼각함수 합성, 다중적분의 변수변환(야코비안), 5축 기구학(공구 중심점 제어, 역기구학)을 연구에 직접 적용하며 배웠다. 부트스트랩 신뢰구간과 교차검증으로 매개변수를 추정하고 표본 밖에서 확인하는 방법, G-code 와 Marlin 펌웨어 구조, PrusaSlicer 명령행, 단위·회귀 테스트로 코드를 검증하는 방법을 익혔다. 예측을 먼저 적고 계산·실물로 확인하는 절차가 결론의 신뢰도를 어떻게 바꾸는지, 기대와 다른 결과를 숨기지 않고 원인을 추적하는 것이 왜 필요한지 경험하였다. 【팀 자체 평가 추가】"],
], { header: false, firstColBold: true, firstColFill: true, size: 18 }));
C.push(BR());

// ---------------- 3. 연구보고서 ----------------
C.push(BANNER("3. 연구보고서"));
C.push(table([W], [["형상 적응형 원뿔 슬라이싱: 원뿔각 자동 결정 알고리즘과 그 신뢰성 검증\n저자명․저자명․저자명\n○○과학고등학교\nShape-Adaptive Conical Slicing: An Automatic Cone-Angle Selection Algorithm and Its Verification\nauthor․author․author\n○○ Science High School"]], { header: false, center: true, size: 20 }));
C.push(new Paragraph({ children: runs("국문 초록", { bold: true }), alignment: AlignmentType.CENTER, spacing: { before: 180, after: 60 } }));
C.push(P("원뿔 슬라이싱은 층을 원뿔면으로 쌓아 서포트 없이 오버행을 출력하는 방법으로, 곡면 슬라이싱보다 설계변수가 적어 계산이 가볍고 방사 대칭 형상에 효과적이다. 그러나 원뿔각은 지금까지 사용자가 정해 왔다. 본 연구는 STL 의 면 법선에서 서포트 필요 여부를 닫힌 식으로 판정하고, 서포트 감소와 기울기를 맞바꾸는 목적함수로 원뿔각·방향·높이 구간별 각도를 자동 결정하는 알고리즘을 제안한다. 각도를 높이에 따라 바꿀 때 층이 교차하거나 벌어지지 않는 조건을 유도해 알고리즘에 넣었다. " + REP + ". 각도 비용 가중치는 데이터로 추정하면 0.06 근처였고 층고에 따라 달랐으며, 본문의 결과는 결과를 보기 전에 정한 기본값 0.2(기울기 1° 를 미지지 2~5mm 와 맞바꾸는 가치판단)로 냈다. 구간 수를 늘린 해석식 최선해는 세 구간 이상에서 실제 G-code 의 미지지가 커졌다. 공개 곡면 슬라이서와 같은 판정식으로 비교하면, 곡면 슬라이서가 수렴한 두 모델에서 서포트는 같거나 낮았고 계산은 모델별 약 450~1,200배 빨랐다.", { noIndent: true }));
C.push(P("주제어: 원뿔 슬라이싱, 원뿔각 자동 결정, 가변 원뿔각, 서포트 저감, 다축 3D 프린팅", { noIndent: true, before: 40, after: 140 }));

// Ⅰ. 서론
C.push(H1("Ⅰ. 서론"));
C.push(P("FDM 3D 프린팅은 모델을 수평면으로 잘라 아래층부터 쌓기 때문에, 아래로 45° 이상 기운 면에는 서포트가 필요하다. 서포트는 재료와 시간을 늘리고 표면을 손상시킨다. 다축 3D 프린팅은 출력 방향을 바꾸어 이를 푼다. 곡면 슬라이싱[3,4,9]은 위치마다 출력 방향을 최적화해 효율이 높지만 설계변수가 위치마다 있어 자유도가 매우 크고 대규모 최적화나 신경망 학습이 필요하다. 원뿔 슬라이싱[1,2]은 층 전체를 원뿔 반각 θ 하나로 기술해 계산이 가볍고, 기존 평면 슬라이서를 그대로 쓰며, 방사 대칭 형상의 오버행에 효과적이다(Table 1)."));
C.push(P("그러나 원뿔각은 지금까지 사람이 정했다. RotBot[1]은 45° 고정각을 쓰고, 공개 원뿔 슬라이서인 Slicer4RTN[5](회전 경사 노즐용, 3·4·5축 지원)과 ConicalSlicer[6](3축용)는 사용자가 입력한 상수각을 쓴다. CNC Kitchen[7]은 구역마다 이상적인 각도를 자동으로 고르는 알고리즘을 다음 과제로 꼽았다. 조사 범위 내에서 원뿔 슬라이싱 계열에서 원뿔각을 형상으로부터 자동 결정하고 정량 비교한 연구는 확인되지 않았다. 본 연구는 이 알고리즘을 만들고 세 질문에 답한다. **RQ1** STL 만으로 원뿔각을 자동 결정할 수 있으며, 그 결정은 무엇을 근거로 하는가. **RQ2** 그 결정은 믿을 만한가. **RQ3** 높이 구간(밴드)의 개수를 늘리면 어떻게 되며 몇 개를 써야 하는가. 평면 대비 감소는 원뿔 슬라이싱 일반의 성과이므로 비교 기준은 균일 원뿔(모델 전체에 각도 하나)과 사람이 써 온 관례 각도로 한다."));
C.push(TAB("Comparison of multi-axis slicing approaches"));
C.push(table([2300, 1700, 2200, 1800, 1638], [
  ["방법", "층의 형태", "설계변수", "방향·각도 결정", "계산 비용"],
  ["곡면(S³-Slicer[3], Neural Slicer[4])", "임의 곡면", "위치마다 방향(3차원 장)", "자동(최적화·학습)", "큼"],
  ["원뿔(RotBot[1], Slicer4RTN[5])", "원뿔면", "θ 1개", "사용자 지정", "작음"],
  ["본 연구", "높이별 원뿔면", "구간별 θ N개", "자동", "작음"],
], { center: true, size: 17 }));

// Ⅱ. 이론적 배경 (기존 유지)
C.push(H1("Ⅱ. 이론적 배경"));
C.push(H2("1. 원뿔 변환[1]"));
C.push(EQ("R = r / cosθ,   φ′ = φ,   Z′ = z + c·r·tanθ      (c = +1 outward, −1 inward)", "1"));
C.push(P("변환한 모델을 평면 슬라이서가 Z′ = 상수로 자르고 되돌리면 층은 z = Z′ − c·r·tanθ 인 원뿔면이 된다(Fig. 1).", { noIndent: true }));
C.push(...FIG("conical_layers_lamp", "Actual layers of generated G-code on the r–z section: (a) uniform 22°, (b) band 22°→0°", 12));

C.push(H2("2. 서포트 판정식"));
C.push(P("축을 지나는 단면에서 원뿔 층의 위쪽 단위 방향 b = (c·sinθ, cosθ) 와 면 법선 n 의 내적:", { noIndent: true }));
C.push(EQ("g(θ) = n_z·cosθ + c·n_r·sinθ,   서포트 필요 ⇔ g(θ) < κ = −sin45°", "2"));
C.push(P("오버행 각 α 인 면은 n = (cosα, −sinα) 이므로", { noIndent: true }));
C.push(EQ("g(θ) = −sin(α − c·θ)  ⇒  유효 오버행 = α − θ,   θ* = α − 45°", "3"));
C.push(P("funnel 벽(α = 70.3°)은 θ = 26° 에서 44.3° 로 통과한다. 변환 공간에서 재면 같은 벽이 θ = 50.7° 에서야 통과한다 — 판정을 식 (2) 하나로 통일한 이유이다.", { noIndent: true }));
C.push(CODE([
  "def overhang_score(mesh, angle_deg, direction, radial=None):",
  "    nz = mesh.face_normals[:, 2]",
  "    nr = radial_normal(mesh) if radial is None else radial",
  "    d = _dir_sign(direction)",
  "    a = np.radians(angle_deg)",
  "    return nz * np.cos(a) + d * nr * np.sin(a)        # 식 (2)",
], "conical/analytic.py  (코드의 d = 식의 c)"));
C.push(P("**정확한 최적 각도.** 면마다 g 는 θ 의 연속함수이므로 서포트 면적 S(θ) 는 g = κ 가 되는 근에서만 바뀌는 계단함수이다. 근 사이에서 J = S(0) − S(θ) − k·θ 는 −k·θ 로 감소하므로", { noIndent: true }));
C.push(EQ("θ̂ ∈ {0°} ∪ {면이 고쳐지는 근 θ* = asin(κ/q) − atan2(n_z, c·n_r)}", "4"));
C.push(P("이다(q = √(n_z² + n_r²) 는 법선의 r–z 단면 성분 크기로, 식 (1) 의 R 과 다르다). 격자 없이 이 후보만 평가하면 최적이 정확히 나온다(Fig. 2). 2° 격자 대비 확장 표본 33개(데모 6 + 기본 표본 17 + 허리 r=3 의 λ 축 10, Table 4) 중 32개에서 J 가 올랐고, 계산 시간은 1~4ms 대 3~78ms 였다.", { noIndent: true }));
C.push(...FIG("exact_step", "(a) Step-shaped support area S(θ) and the roots where faces become supported; (b) J(θ) with the exact and 2° grid optima (waist r = 2 mm)", 12));

C.push(H2("3. 가변 원뿔각과 층간격"));
C.push(P("층 k 를 z_k(r) = Z′_k − c·r·tanθ_k 로 두면 같은 반경에서 이웃 층 간격은", { noIndent: true }));
C.push(EQ("Δz(r) = h − c·r·(tanθ_{k+1} − tanθ_k),   m = Δz / h", "5"));
C.push(BUL("• 층 교차 없음: 모든 r ≤ r_max 에서 Δz > 0"));
C.push(BUL("• tanθ 를 Z′ 에 선형 보간(블렌드 폭 w, 총 변화 ΔT) ⇒ m = 1 − c·r·ΔT / w 가 블렌드 안에서 일정 → θ 가 아닌 tanθ 를 보간하는 이유"));
C.push(BUL("• 1/1.5 ≤ m ≤ 1.5 ⇒ w ≥ 2·r_b·|ΔT| (팽창), w ≥ 3·r_b·|ΔT| (압축) — 블렌드 반경 r_b 가 작을수록 블렌드가 좁아도 된다"));
C.push(BUL("• 상수각(ΔT = 0) ⇒ m ≡ 1 : 균일 원뿔에는 없고 가변각에서만 생기는 제약"));
C.push(P("m 이 한계에 닿는 반경은 r* = (m_max − 1) / |s| 이다. 여기서 s = c·ΔT / w 는 블렌드 안에서 Z′ 1mm 당 tanθ 의 변화(단위 /mm)이고 m = 1 − r·s 이다(예: 밴드 22°→0°, s = −0.378/mm 에서 r* = 1.32mm).", { noIndent: true }));

C.push(H2("4. 압출량 보정"));
C.push(EQ("dV / dV′ = cos²θ · m", "6"));
C.push(P("역변환 시 압출량에 식 (6) 을 곱한다(방향 무관). 이 모형이 실제 비드와 맞는지는 실물 L4 출력으로 판정한다.", { noIndent: true }));

// Ⅲ. 연구 방법
C.push(H1("Ⅲ. 연구 방법 및 절차"));
C.push(H2("1. 알고리즘"));
C.push(EQ("θ̂ = argmax_θ J(θ),   J(θ) = ΔS(θ) − k·|θ|   (기본 k = 0.2 %p/°)", "7"));
C.push(BUL("① STL 축 정렬 → ② 면별 g(θ) → ③ 균일각: 식 (4) 후보에서 식 (7), 방향은 outward/inward 중 큰 J"));
C.push(BUL("④ 밴드: 높이 N 구간마다 θ. 블렌드는 식 (5) 의 최소 폭을 지키며, 경계를 모델 높이의 25% 안에서 반경이 작은 높이로 옮긴다. J 에서 블렌드 면적 비용(k_blend = 0.1) 차감"));
C.push(BUL("⑤ 변환 → 평면 슬라이서 → 역변환(식 (6) 압출 보정, 경로 오차 ≤ 0.05mm)"));
C.push(BUL("⑥ 5축: B = θ(Z′), C = 방위각, 회전 속도 상한, 베드 안전각 22.79° → ⑦ 사전 검사 통과 시 출력"));
C.push(P("**k 의 의미.** ΔS 만 최대화하면 언제나 최대각이 선택된다. 그런데 각도를 키우면 5축 회전이 늘어 출력 시간이 길어지고 표면 계단이 커진다. REP5X 축 한계로 잰 출력 시간을 균일 4~44° 에서 각도에 선형 맞춤하면 1° 당 lamp 0.525분, 허리 r=3 0.531분, 구 0.636분, 세 모델 평균 0.56분 늘었다(Table 2 는 lamp). 이 기울기로 번역하면 k = 0.2 는 \"서포트 1%p 를 없애는 데 출력 시간 약 2.8분까지 쓴다\"는 교환 비율이다. k 는 서포트와 기울기(시간·표면)를 맞바꾸는 비율이며, 그 값은 Ⅳ.1.5 에서 데이터로 다시 추정한다. 본문의 모든 결과는 결과를 보기 전에 정한 기본값 k = 0.2 로 냈다. Ⅳ.1.5 의 추정치(0.06)는 각도 비용을 0 으로 둔 손실에서 나온 값이라 기울기의 시간·표면 비용을 반영하지 않고, 결과를 본 뒤 k 를 바꾸면 사전 등록의 의미가 사라지므로 0.2 를 유지하였다.", { noIndent: true }));
C.push(TAB("Cost of tilt: REP5X print time and support (lamp, layer 0.3 mm, rewinds excluded)"));
C.push(table([2600, 1700, 2600, 2738], [
  ["조건", "출력 시간(분)", "오버행 낙관 / 비관 (%p)", "계단 정렬비 (평면 = 1)"],
  ["균일 4°", "21.0", "1.37 / 5.41", "0.98"],
  ["균일 24°", "28.3", "0.27 / 4.11", "0.88"],
  ["균일 36° (오버행 0 이 처음 되는 각)", "35.3", "0.00 / 0.00", "0.98"],
  ["균일 44°", "42.6", "0.02 / 1.17", "1.08"],
  ["**밴드2 [30°→0°]**", "**21.5**", "**0.00 / 0.00**", "1.09"],
], { center: true, size: 17 }));
C.push(NOTE("평면(0°) 5.7분 → 4° 21.0분의 점프는 축 근처 C 축 회전(가속도 500 deg/s²)에서 오는 5축 전환 고정비이다. 절대 시간은 근사이고 비만 본다. 허리 r=3 도 같은 모양(밴드2 22.1분, 균일 24° 30.0분). 24° 이상의 균일각과 밴드2 아래 구간 30° 는 베드 안전각 22.79° 를 넘어 실제 기계에서는 출력할 수 없다. 이 행들은 기울기의 시간 비용을 재기 위한 계산값이다."));

C.push(H2("2. 검증 계층"));
C.push(P("결과는 다섯 계층으로 나누어 확인한다(Table 3). 표의 아래로 갈수록 실물에 가깝다.", { noIndent: true }));
C.push(TAB("Verification layers"));
C.push(table([2100, 4600, 2938], [
  ["계층", "측정량", "보장 범위"],
  ["해석식", "면 법선으로 서포트 면적 %", "기하 판정(45° 문턱)"],
  ["툴패스 검사기 A", "G-code 비드 아래 앞 층 유무, 진짜 오버행 미지지 길이 mm", "실제 경로, 중력·냉각 없음"],
  ["퇴적 복원", "복원 형상 대 원본 IoU", "형상 일치, 실물 아님"],
  ["기계 사전 검사", "축 범위·베드 간섭·회전 속도, 독립 역기구학 대조", "치수 일부 추정"],
  ["실물", "사전 등록 시험 출력 L0~L5", "【보류】"],
], { size: 17 }));
C.push(P("**검사기 A 의 '지지됨'.** 압출 경로를 0.225mm 간격 점으로 나눠, 베드 위 첫 층(z ≤ h)이거나 G-code 순서상 먼저 쌓인 점이 수평 0.45mm·수직 (0, 1.5h] 안에 하나라도 있으면 지지된 것으로 본다(Fig. 3). 미지지로 쌓인 재료도 위층을 받친다고 보는 낙관 모형이며, 지지된 재료만 받친다고 보는 비관 모형을 함께 쓴다. 미지지 페리미터 중 아랫층 단면 밖에 있는 것의 길이를 '진짜 오버행' 으로 센다. 평면 층이라면 이 기준은 atan(0.45/h) 의 자기지지각(0.3mm 에서 56°, 0.4mm 에서 48°)에 해당한다 — 해석식의 고정 45° 와 달리 **층고에 따라 문턱이 움직인다.**", { noIndent: true }));
C.push(...FIG("checker_criterion", "Support criterion of toolpath checker A. (a) A sample point is supported if it lies on the first layer (z ≤ h) or if an earlier-deposited point lies within 0.45 mm horizontally and (0, 1.5h] below it. (b, c) Synthetic test with stacked rings: the supported fraction drops from 1 to 0 exactly at a radial step of 0.45 mm and at a vertical gap of 1.5h (h = 0.3 mm)", 11));

C.push(H2("3. 실험 조건"));
C.push(P("표본·층고·지표·기준선은 Table 4 와 같다.", { noIndent: true }));
C.push(TAB("Experimental conditions"));
C.push(table([2300, 7338], [
  ["항목", "조건"],
  ["표본", "기본 표본 21개 = 기본 17개[축대칭 7(구 1, 허리형 r = 1·2·3·4·5·7mm 6) + 비축대칭 10(허리 r=3 의 XY 배율 λ = 1.1~2 5, 로브 변형 5)] + 데모 4개(sphere, funnel, torus, mushroom)\n보류 표본 21개 = 무작위 20(시드 20261110: 원기둥·상자·나팔 14, 구 3, 허리형 3) + funnel(기본 표본과 중복 — 엄밀한 보류는 무작위 20개)\n확장 표본: 정확 탐색 검산(Ⅱ.2)은 데모 6 + 기본 17 + 허리 r=3 의 λ 축 10 = 33개, 실패 사례(Ⅳ.1.8)는 S³-Slicer[3] 공개 모델 ring·topopt·armadillo 추가"],
  ["층고·지지 모형", "0.3, 0.4mm (층고 실험은 0.2~0.5mm) / 낙관·비관"],
  ["지표", "미지지 길이 mm(0.5mm 이내 무승부) 또는 진짜 오버행 %p(0.1%p 이내 무승부), 평균 |θ|, 후회 = 사후 최적 대비 미지지 증가"],
  ["기준선", "(a) J 가 고른 균일각 (b) 밴드 아래 구간 각도와 같은 균일각 (c) 같은 평균 기울기(등왜곡)의 균일각 (d) 관례 고정각 15·20·25·45°"],
  ["기계 제약", "베드 안전각 22.79° 적용/미적용 두 판"],
  ["사전 등록", "시험마다 판정 기준을 결과 전에 문서로 커밋(git 기록). 결과를 본 뒤 추가한 분석은 '사후' 로 표시"],
], { header: true, size: 17 }));

// Ⅳ. 연구 결과
C.push(H1("Ⅳ. 연구 결과"));
C.push(H2("1. 원뿔각 자동 결정 (RQ1)"));
C.push(P("**1.1 알고리즘은 무엇을 보고 각도를 고르나.** 식 (4) 로 21개 모델의 0° 서포트 필요 면을 풀면, 그 면들은 모두 높이 하반부에 있고 θ* 가 0~44° 에 넓게 퍼져 있다(Fig. 4). 균일 J 는 '이 각을 1° 올려 새로 풀리는 면적' 이 k 보다 작아지는 자리에서 멈추므로 모델마다 16~42° 로 다른 각을 고르고, 밴드2 의 위 구간 각도는 고칠 면이 없어 0~20° 로 내려간다. 모델마다 0° 필요 면적 중 θ* 가 베드 안전각 22.79° 를 넘는 몫을 구하면 그 중앙값이 26% 다(허리형 23~31%, 허리 r=3·λ=2 47%, torus 50%, funnel·mushroom 100%).", { noIndent: true }));
C.push(...FIG("critical_angle_select", "Area-weighted distribution of per-face critical cone angles θ* (positive = outward, negative = inward) for the 21 sample models, with the automatically selected uniform angle (▼), the two band angles (dashed) and the bed-safe limit 22.79° (red)", 13));
C.push(P("**1.2 방향.** 표본 21개 중 안쪽 방향 오버행(inward θ*)을 가진 모델은 torus 하나뿐이고(0° 필요 면의 10.6%, 구멍 쪽 아랫면), 나머지 20개는 오버행이 모두 바깥을 향한다. 선택기는 상한 판 torus 한 건을 빼면 inward 를 고르지 않았다. 안쪽 오버행 그릇과 바깥 오버행 그릇을 따로 만들면 해석식이 각각 inward 15°·outward 15° 를 정확히 고르고, 툴패스에서도 층고 0.3mm 에서 고른 방향만 미지지가 0 이 된다(Fig. 5). 층고 0.4mm 에서는 15~16° 로 부족했다(층고 의존성은 Ⅳ.3 절).", { noIndent: true }));
C.push(...FIG("direction_demo", "Automatic choice of cone direction on two hollow vessels with a 60° shoulder: S(θ), J(θ) and toolpath unsupported length for outward and inward cones at 0.3 and 0.4 mm layers", 13));

C.push(P("**1.3 관례 각도와 비교 (사전 등록 T1).** 사전 기준은 \"자동 결정의 후회 중앙값이 모든 실현 가능한 고정 관례각보다 작다\" 였다. **결과는 불통과이다**(Table 5).", { noIndent: true }));
C.push(TAB("Median regret (mm) of fixed conventional angles and automatic selection, 21 models (k = 0.2)"));
C.push(table([2600, 1000, 1000, 1000, 1000, 1500, 1538], [
  ["조건", "15°", "20°", "25°", "45°", "자동 균일", "자동 밴드2"],
  ["0.3mm · 상한 없음", "48.3", "35.2", "13.8", "**1.6**", "15.7", "6.9"],
  ["0.3mm · 상한 22.79°", "18.9", "5.7", "불가", "불가", "**0.0**", "**0.0**"],
  ["0.4mm · 상한 없음", "84.9", "66.4", "57.7", "**0.0**", "43.3", "56.1"],
  ["0.4mm · 상한 22.79°", "22.1", "3.8", "불가", "불가", "2.7", "**0.0**"],
], { center: true, size: 17 }));
C.push(BUL("• 상한이 없으면 고정 45° 가 이긴다. 미지지 길이는 각도를 키울수록 거의 계속 줄어 사후 최적이 30~44° 에 몰리고(21개 중 16개가 30~36°), J 는 k·|θ| 때문에 약 22° 에서 멈춘다"));
C.push(BUL("• 상한이 있으면 자동이 이기지만, 사후 최적이 거의 모두 상한 끝(22°)이라 '상한까지 올리기' 에 가깝다"));
C.push(P("즉 이 지표에는 각도의 비용이 없어서, 각도 비용을 포함한 J 와 목적이 다르다. 그래서 다음 두 시험으로 k 를 분리하였다.", { noIndent: true }));

C.push(P("**1.4 k 스윕과 교환 곡선.** k 를 0~1 로 바꾸어 다시 고르면, k → 0 에서 자동 균일각의 중앙값은 22° 에서 44° 로 커지고 사후 최적과 4° 안인 모델이 1개에서 12개로 늘었다(사전 기준 충족, Fig. 6). 그러나 네 조건 모두에서 관례각보다 후회가 엄격히 작은 k 는 없었다 — 상한 없는 0.4mm 에서 고정 45° 의 후회가 0 이라 구조적으로 동률이 최선이다. 동률을 허용하면 k = 0.05 하나만 네 조건을 통과했다. 같은 평균 기울기 예산에서 비교하면(Fig. 7), 모델마다 다른 각도를 고르는 자동 결정이 한 각도를 모든 모델에 쓰는 것보다 미지지 합이 적었다: k = 0.2, 평균 23° 에서 층고 0.3mm **48% 감소**(1133 → 588mm), 0.4mm **33% 감소**(3118 → 2089mm). 이 이득은 각도 예산이 빠듯한 중간 k(0.15~0.3)에서 네 조건 중 세 조건에서 나왔고, 예산이 사실상 무제한인 k ≤ 0.1 에서는 고정 40° 가 더 나았다.", { noIndent: true }));
C.push(PAIR(["k_sweep", "Median regret and selected angle vs. k"], ["k_pareto", "Trade-off curve: mean |θ| vs. total unsupported length; fixed angles vs. automatic selection"]));

C.push(P("**1.5 k 의 데이터 추정 (사전 등록).** 네 조건의 후회 중앙값 합을 손실로 두고 k = 0.005~0.5 에서 최소화한 뒤, 1-표준오차 규칙으로 각도를 덜 쓰는 쪽을 고르고 모델 부트스트랩(2,000회)과 모델 가족 제외 교차검증(5겹)을 하였다(Table 6, Fig. 8).", { noIndent: true }));
C.push(TAB("Data-driven estimate of the tilt cost k"));
C.push(table([2600, 1400, 2000, 3638], [
  ["추정 범위", "k̂", "95% 구간", "판정"],
  ["네 조건 전체", "**0.06**", "0.055~0.08", "정밀도 통과(폭 0.025), 안정성 통과(가족 제외 0.06~0.075)"],
  ["층고 0.3mm", "0.115", "0.085~0.16", "구간이 0.4mm 와 겹치지 않음 → 층고 의존"],
  ["층고 0.4mm", "0.06", "0.055~0.08", "표본 밖 0.4mm·상한 없음 1.9mm > 고정 45° 0.0mm → 불통과"],
], { size: 17 }));
C.push(BUL("• 결론(사전 문구): k 는 안정적으로 추정되지만 표본 밖에서 관례각을 모두 이기지는 못하고, 층고에 따라 다르다. 기본값 0.2 는 95% 구간 밖이다"));
C.push(BUL("• 이 k̂ 는 각도 비용을 0 으로 둔 값이라 각도를 쓰는 쪽으로 치우친다. 손실에 '평균 기울기 1° = 미지지 λ mm' 를 더하면 λ = 2~5 에서 k̂ = 0.14~0.37 — 기본값 0.2 는 '1° 를 미지지 2~5mm 와 바꾼다' 는 가치판단에 해당한다"));
C.push(BUL("• 실제 기계 조건(베드 상한)에서는 k = 0.005~0.18 전 구간에서 후회가 0 이라 k 선택에 둔감하다"));
C.push(...FIG("k_estimate", "Loss L(k) with bootstrap band, 1-SE estimate and per-layer-height estimates of k", 11));

C.push(P("**1.6 밴드 대 균일.** 두 기준선이 같은 이야기를 한다(Table 7). 밴드 아래 구간 각도와 같은 균일과는 미지지가 거의 무승부이고 평균 |θ| 는 중앙 8.4° 작다. 같은 평균 기울기의 균일과 비교하면 층고 0.3mm 에서 밴드2 가 낙관 15승 1무 0패, 비관 14승 1무 1패였다. 즉 밴드는 **같은 서포트를 더 적은 기울기로** 얻는다. 이 이득은 허리(반경이 작은 높이)가 있을 때 나온다: 블렌드를 허리로 옮기면 식 (5) 의 필요 폭이 lamp에서 9.1 → 2.3mm 로 1/4 이 되고, 허리가 없는 구는 옮겨도 r_b = 7.6mm 로 커서 이득이 작다(Fig. 9). lamp에서 밴드2 [30°→0°] 는 오버행 0 을 균일 4° 수준의 시간(21.5분)에 얻었다(Table 2).", { noIndent: true }));
C.push(TAB("Band2 vs. uniform baselines (band2 wins · uniform wins · ties)"));
C.push(table([3400, 2100, 2100, 2038], [
  ["기준선 (지표)", "층고 0.3mm", "층고 0.4mm", "비고"],
  ["(a) J 균일 (미지지 mm, 17)", "5 · 0 · 12", "5 · 3 · 9", "우세 5개 = 아래 구간 각 > 균일각"],
  ["(b) 아래 구간 각도와 같은 균일 (mm, 17)", "0 · 0 · 17", "0 · 2 · 15", "평균 |θ| 중앙 8.4° 감소"],
  ["(c) 등왜곡 균일, 낙관 (%p, 16)", "**15 · 0 · 1**", "15 · 1 · 0", "구는 밴드를 쓰지 않음"],
  ["(c) 등왜곡 균일, 비관 (%p, 16)", "**14 · 1 · 1**", "1 · 15 · 0", "0.4mm 는 지지 모형에 따라 반대"],
], { size: 17 }));
C.push(NOTE("(c) 는 현재 코드보다 이전 코드 시점에서 잰 값이다. 【현재 코드로 재현 확인 필요 — 보류 구 두 모델의 밴드 각도가 시점 간 다르게 나옴】"));
C.push(...FIG("band_vs_radius", "Radius profile R(z), selected θ(Z′), blend position and width, and r* for lamp, waist r = 3, torus and sphere; the blend is moved to the waist", 13));

C.push(P("**1.7 기계 제약의 비용.** 베드 안전각 22.79° 를 걸면 21개 중 9개의 균일각과 14개의 밴드2 아래 구간 각도가 내려가고, 균일 원뿔의 미지지가 바뀐 모델에서 중앙 33~36mm 늘었다. 늘어난 양의 55~57% 는 한 모델(층고 0.3mm: θ* 가 25~26° 에 몰린 funnel, 0.4mm: 허리 r=3·λ=2 모델)에서 나왔다(Fig. 10, 11).", { noIndent: true }));
C.push(PAIR(["bed_cap_cost", "Cost of the bed-safe limit: selected angles and increase in unsupported length"], ["funnel_cap", "funnel: analytic S(θ) is flat below the cap while the toolpath drops at 18° (0.3 mm)"]));
C.push(P("**1.8 실패 사례와 원인.** (i) funnel 은 상한 판에서 0° 를 골라 미지지 736mm 를 남겼다(사후 최적 22° 는 2mm). 오버행 면 전부가 같은 θ* = 25.26° 라 [0°, 22.79°] 에서 해석식 S 가 51.514% 로 상수이고, J = −kθ 가 되어 k 와 무관하게 0° 가 선택된다. 독립 계산과의 차 0.0%p 로 **구현 결함이 아니라 판정 문턱의 위치 차**이다 — funnel 툴패스에서 역산한 검사기의 실효 문턱은 층고 0.3mm 에서 약 53°(0.4mm 에서 약 41°)라 18° 에서 이미 풀린다. 이는 평면 층 기준 환산값(Ⅲ.2 의 56°·48°)이 아니라 실제 원뿔 툴패스에서 잰 값이다. (ii) 확장 표본인 S³-Slicer[3] 공개 모델 ring·topopt·armadillo 에서 0° 를 고르는 것은 원인이 다르다: 1° 당 서포트 이득의 최대 k* = 0.10~0.16 이 k = 0.2 보다 작다. 사후 민감도로 면적 가중 초과 오버행각 max(0, α − θ − 45°)(α − θ 는 식 (3) 의 유효 오버행) 같은 연속 지표를 쓰면 funnel 이 22° 를 골랐다(판정 밖).", { noIndent: true }));

C.push(H2("2. 결정의 신뢰성 (RQ2)"));
C.push(P("**2.1 메시 예측 대 G-code.** 균일 0~44°(12각)의 해석식 서포트 순위와 툴패스 미지지 순위의 모델별 스피어만 ρ 중앙값은 0.956(층고 0.3), 0.998(0.4), 20모델이다. 0.8 미만은 두 방향 오버행을 가진 torus 하나이고, mushroom 은 해석식이 모든 각에서 상수라 ρ 가 정의되지 않는다(Fig. 12).", { noIndent: true }));
C.push(...FIG("t5_pred_vs_meas", "Analytic prediction vs. toolpath measurement with per-model Spearman ρ", 11.5));
C.push(P("**2.2 견고성 (사전 등록 T4).** 고른 각도 변화가 2° 이하인 모델 비율로 재면 균일각은 메시 해상도·축 중심 이동에 견고하고 축 기울임에 흔들리며, 밴드2 는 어느 축에서도 사전 기준(90%)에 못 미쳤다(Table 8). 메시 세분화만으로 밴드 각도가 바뀌는 원인을 절제 실험으로 좁히면, 경계 위치가 아니라 J 의 블렌드 면적을 면 중심 한 점으로 세는 구적이었다(세분화로 밴드 각도가 조금이라도 바뀐 8개 모델 — 2° 초과는 Table 8 의 4개 — 중 7개는 J 차 0.004~0.06%p 의 동점 깨기, funnel 은 거친 메시가 블렌드를 '못 본' 결함). 메시 독립 경계 옵션은 이 문제를 고치지 못했다. 그러나 **고른 해를 원본 메시에서 평가한 J 손실** 은 기울임 3° 를 빼면 95~100% 가 0.4%p 이하였다 — 각도는 흔들려도 J 가 평평한 곳이라 고른 해가 원본에서도 거의 최선이다.", { noIndent: true }));
C.push(TAB("Robustness: share of models whose selection changes by ≤ 2° (and J loss ≤ 0.4 %p for band2)"));
C.push(table([2700, 1900, 2300, 2738], [
  ["교란", "균일", "밴드2 (≤ 2°)", "밴드2 J 손실 ≤ 0.4%p"],
  ["메시 세분화 ×4", "21/21", "17/21", "21/21"],
  ["메시 단순화 ×0.5", "19/21", "14/21", "20/20"],
  ["축 중심 0.1mm 이동", "21/21", "13/21", "21/21"],
  ["축 중심 0.5mm 이동", "20/21", "15/21", "21/21"],
  ["축 1° 기울임", "17/21", "10/21", "19/20"],
  ["축 3° 기울임", "14/21", "11/21", "17/19"],
], { center: true, size: 17 }));
C.push(NOTE("분모가 21 보다 작은 칸은 교란 해가 원본 메시에서 층간격 제약을 어겨 실현 불가인 경우. 각도가 튄 60건 중 53건은 J 차 0.4%p 이하 구간."));
C.push(P("**2.3 보류 표본.** 결과를 보기 전에 시드를 고정한 무작위 20개 모델에 funnel 을 더한 21개에서 시험하였다(층고 0.3mm). funnel 은 기본 표본(데모)에도 있으므로 엄밀한 보류 표본은 무작위 20개이다. 구성은 원기둥·상자·나팔 14, 구 3, 허리형 3, funnel 1 이다. 사전 기준을 글자 그대로 적용하면 밴드 승률 3/21 로 가설이 기각된다. 사전에 적어 둔 단서(허리 유무로 나눠 볼 것)대로 나누면 원기둥·상자·나팔 14개는 평면 오버행이 없어 선택기가 밴드를 쓰지 않았고(올바른 동작), 허리형 3개는 낙관 3/3 승이었다. 구 3개는 낙관에서 2무·1개 밴드 미사용이었지만 비관에서 2패(+3.0, +5.8%p)였다. 각도 차가 작은 밴드(26°→24°)가 이득 없이 블렌드의 미지지만 만든 경우다. funnel 은 낙관 무·비관 승이었다. 두 판정을 모두 적는다. 【현재 코드로 재현 확인 필요】", { noIndent: true }));
C.push(P("**2.4 퇴적 복원.** mushroom_03 의 46개 각도 후보에서 IoU 는 0.926~0.932, 이웃 각도 차 평균 0.57%p 로 0~12° 의 순위는 복원 해상도로 가려지지 않았다.", { noIndent: true }));

C.push(H2("3. 구간(밴드) 개수 (RQ3)"));
C.push(EQ("𝒫_N ⊂ 𝒫_{N+1}  ⇒  S*_{N+1} ≤ S*_N,   S*_N → S*_∞ (N → ∞)", "8"));
C.push(P("경계 위치가 자유로우면 N 구간 프로필은 경계 하나를 더 넣고 양쪽 각을 같게 둔 N+1 구간 프로필로도 표현되므로(같은 각 사이에는 블렌드가 필요 없다) 해석식 최선해 S*_N 은 단조 감소·수렴한다. 계획기는 경계 이동을 모델 높이의 25% 안으로 제한하므로 식 (8) 은 그 제약 아래에서는 근사적으로만 성립한다. 그러나 전수 최선해(21 모델, N = 1~4)의 G-code 미지지 중앙(층고 0.4)은 N = 1, 2, 3 에서 0.0 → 1.3 → 68.9mm 로 커졌다. N ≥ 3 의 블렌드가 바닥 오버행 위에 놓여 층간격 팽창이 미지지를 만든다 — 식 (2) 에는 m 이 없다. N 을 J 로 고르면 오버행이 달성 가능한 최소보다 나빴다(구와 허리형 6개, 7개 모델 모두 — 층고 0.3·0.4mm 공통). 해석식 최선해가 몇 구간에서 포화하는지는 층고 0.3mm 에서 Table 9 와 Fig. 13 에 보인다.", { noIndent: true }));
C.push(TAB("Saturation band count N* of the analytic optimum (21 models, layer 0.3 mm)"));
C.push(table([3638, 1500, 1500, 1500, 1500], [
  ["목적", "N* = 1", "N* = 2", "N* = 3", "N* ≥ 4"],
  ["① 서포트 최소", "1", "1", "2", "17"],
  ["② 같은 서포트에서 |θ| 최소", "1", "9", "7", "4"],
], { center: true, size: 17 }));
C.push(NOTE("N* = N → N+1 에서 미지지 감소 < 0.5mm 이고 평균 |θ| 감소 < 1° 인 첫 N. 해석식 최선해는 포화하지 않지만(17/21 이 N* ≥ 4) 그 이득은 G-code 미지지로 되돌아오므로, 밴드 수는 툴패스 검사로 상한을 둔다(이 표본에서 N ≤ 2)."));
C.push(...FIG("t3_band_curve", "(a) Toolpath unsupported length and (b) area-weighted mean |θ| of the analytic optimum vs. number of bands N; stars mark N*", 11.5));
C.push(P("**층고에 따라 결과가 달라지는 이유.** 블렌드의 층간격 배율 m 과 검사기의 수직 창 1.5h 는 둘 다 층고에 비례하므로 m > 1.5 경계는 층고와 무관하고, 계획기가 m ≤ 1.5 로 묶어 실제로 넘지 않는다(측정 최대 1.47). 층고 의존성은 고정된 수평 지지 폭 0.45mm 에서 나온다: 층고가 h_c = w(cot(θ+45°) + tanθ)/m 을 넘으면 검사기가 선택기의 45° 기준보다 엄격해지며, m = 1 에서 h_c 의 최소가 0.37mm 라 0.4mm 에서 실패가 급증한다(Fig. 14). 블렌드 팽창(m ≈ 1.4)은 이 경계를 0.25~0.30mm 로 당긴다. 그래서 비관 지지 모형에서 밴드는 층고 0.25~0.30mm 창에서만 균일을 이겼다.", { noIndent: true }));
C.push(...FIG("layer_height_blend", "Why failures rise at 0.4 mm: (a) layer height h_c above which checker A becomes stricter than the selector's rule, for m = 1, 1.25, 1.5; (b) measured unsupported length of uniform and two-band profiles and the part in blend layers; (c) area of faces that pass the selector but fail the checker", 13));
C.push(P("**자유도를 더 늘리면.** 사면체 변형 기반의 공개 곡면 슬라이서 S4 Slicer[9](이하 S4)를 같은 판정식으로 재면, S4 가 유효하게 수렴한 sphere·torus 두 모델에서 원뿔족이 같거나 나았다(Table 10). 원뿔족 천장은 면 클러스터마다 자기에게 가장 좋은 방향·각도를 따로 고를 수 있다고 가정했을 때 남는 서포트로, 실현 가능한 슬라이싱이 아닌 원뿔족의 이론적 하한이다. 층 경선 곡률 κ·r 중앙은 구 0.086, torus 0.59 였고, 곡률이 큰 torus 에서도 곡면의 추가 자유도가 서포트 감소로 이어지지 않았다. funnel·mushroom 은 S4 변형에서 사면체가 뒤집혀 무효였다.", { noIndent: true }));
C.push(TAB("Support area (%) along the degree-of-freedom ladder (same criterion, eq. 2) and run time"));
C.push(table([1500, 1100, 1100, 1100, 1500, 1900, 1438], [
  ["모델", "평면", "균일", "밴드", "원뿔족 천장", "곡면(S4)", "S4 − 천장"],
  ["sphere", "14.7", "0.0", "0.0", "0.0", "0.1 (0.0~0.4)", "+0.1"],
  ["torus", "25.0", "18.6", "10.6", "10.6", "16.3† (12.5~16.3)", "+1.9~+5.7"],
  ["funnel", "51.5", "0.0", "0.0", "0.0", "무효*", "—"],
  ["mushroom", "27.5", "27.5", "27.5", "27.5", "무효*", "—"],
], { center: true, size: 17 }));
C.push(NOTE("† 변형 4,000회로 수렴·뒤집힌 사면체 0 인 실행. * 변형 미수렴·사면체 뒤집힘. 계산 시간: 원뿔 각도 결정(균일+밴드+천장) 0.12~0.27s 대 S4 68~334s. 같은 모델끼리의 시간 비는 약 450~1,200배이다(예: torus 0.27s 대 334s)."));

C.push(H2("4. 실물 출력 계획 (사전 등록 예측)"));
C.push(P("프린터는 Ender-3 V3 SE 를 REP5X[8] 설계로 개조한 5축 프린터이다(Fig. 15). 아래 순서로 출력해 결과를 보기 전에 적어 둔 예측과 비교하고(Table 11), 출력물은 Fig. 16 에 싣는다.", { noIndent: true }));
C.push(TAB("Pre-registered predictions for the test ladder"));
C.push(table([1100, 3400, 2600, 2538], [
  ["단계", "출력물", "예측", "실측"],
  ["L1", "원기둥 r10 × 8, B = 0", "지름 20.0mm", "【보류】"],
  ["L4a/b", "단벽 원기둥 B = 0 / 22°", "벽 두께비 0.927 (식 6)", "【보류】"],
  ["L5", "오버행 계단 40~65°, 평면", "50° 단부터 처짐(식 2)", "【보류】"],
  ["L2p/L2", "벽 60° 원뿔대: 평면 / 균일 15°", "49.87%p / 0.00%p", "【보류】"],
  ["L3a/b", "lamp: 균일 22° / 밴드 22°→0°", "0.53 / 0.58%p (구별 안 됨)", "【보류】"],
], { size: 17 }));
C.push(table([W], [["【사진 대기: 개조한 REP5X 프린터 전경 · 헤드(B/C축) 근접】"]], { header: false, center: true, size: 16 }));
C.push(FIGCAP(`[Fig. ${++figNo}] The modified 5-axis printer (REP5X on Ender-3 V3 SE)`));
C.push(table([W], [["【사진 대기: L1~L5 출력물 — 같은 조명·배경·스케일, 4방향 + 위】"]], { header: false, center: true, size: 16 }));
C.push(FIGCAP(`[Fig. ${++figNo}] Printed test ladder L1–L5`));

C.push(H2("5. 계산 비용"));
C.push(P("균일각 결정은 정확 탐색 1~4ms(확장 표본 33개 합 0.09s)이다. 시간은 면 수에 비례하며(로그-로그 기울기 0.95~1.06), 구 130만 면에서 균일 10.5s · 밴드2 556s, 최대 메모리 564/804MB 였다. S4 와 같은 사면체 표면 메시에서 모델별로 비교하면 약 450~1,200배 빠르다(Fig. 17, 18).", { noIndent: true }));
C.push(PAIR(["t7_scaling", "Run time vs. number of faces (log–log)"], ["s4_runtime", "Run time: cone-angle selection vs. S4 stages"]));

// Ⅴ. 고찰
C.push(H1("Ⅴ. 고찰"));
C.push(BUL("• **자동 결정의 가치는 교환 곡선에서 판단해야 한다.** 각도 비용이 없는 지표(미지지 mm)에서는 각도를 키울수록 좋아지므로 큰 고정각이 이긴다(T1 불통과). 각도에는 출력 시간(세 모델 평균 1° 당 0.56분)과 표면 계단이라는 비용이 있고, 그 비용을 두는 한 모델마다 다른 각도를 고르는 것이 같은 기울기 예산에서 미지지를 33~48% 줄였다"));
C.push(BUL("• **k 는 데이터가 아니라 데이터 + 가치판단으로 정해진다.** 미지지만 보면 k ≈ 0.06(층고 0.4)~0.115(층고 0.3)이고, 기본값 0.2 는 '기울기 1° = 미지지 2~5mm' 에 해당한다. 층고에 따라 k 가 다른 것은 검사기의 실효 문턱 atan(0.45/h) 이 층고에 따라 움직이기 때문으로 보인다(Ⅳ.1.8, Ⅳ.3 절)"));
C.push(BUL("• **고정 45° 문턱의 한계.** 해석식은 면이 45° 를 넘는 순간만 센다. funnel 처럼 상한 안에서 문턱을 못 넘는 면은 '조금 줄이기' 를 평가하지 못하고, 검사기의 문턱은 층고 0.3~0.4mm 에서 41~56° 로 움직인다(평면 환산 56°·48°, funnel 실측 53°·41°). 연속 지표나 층고 의존 문턱이 향후 과제이다"));
C.push(BUL("• **구간 분할의 고유 효과는 기울기 감소이다.** 같은 서포트를 평균 |θ| 8.4° 적게 얻고, 이는 허리에 블렌드를 둘 수 있을 때 나온다. 기울기를 최대로 줄인 최선해는 해석식이 층간격을 모르기 때문에 G-code 에서 졌다"));
C.push(BUL("• **견고성은 각도가 아니라 J 손실로 본다.** 밴드 각도는 메시 교란에 흔들리지만 J 가 평평한 곳의 동점 깨기여서 손해가 작다. 남은 결함(면 중심 구적)은 블렌드 경계에서 면을 자르는 적분으로 고칠 수 있다"));
C.push(BUL("• **한계**: 기본 표본 21개(축대칭 11, XY 배율·로브의 약한 비축대칭 10), 45° 문턱 기하 판정(중력·냉각 없음), 핫엔드 치수·베드 안전각 22.79° 는 공개 자료 기반 추정, 일부 결과(Table 7 (c)·2.3 절)는 다른 코드 시점에서 잰 값, 실물 결과 【보류】"));

// Ⅵ. 결론
C.push(H1("Ⅵ. 결론"));
C.push(P("본 연구는 원뿔 슬라이싱의 원뿔각을 STL 에서 자동으로 결정하는 알고리즘을 만들었다. RQ1: 원본 면 법선만으로 서포트를 판정하는 해석식을 유도하고, 서포트 감소와 기울기를 맞바꾸는 목적함수로 원뿔각·방향·구간별 각도를 자동으로 결정하였다. " + REP + ". 각도 비용 가중치 k 는 데이터로 0.06(95% 0.055~0.08) 근처로 안정적으로 추정되었지만 층고에 따라 달랐다. 본문 결과에 쓴 기본값 0.2 는 이 구간 밖이며 '기울기 1° = 미지지 2~5mm' 라는 가치판단을 반영한 값이므로, 서포트와 기울기의 교환 비율은 기계와 층고에 맞춰 정해야 한다. RQ2: 해석식의 각도별 순위는 G-code 측정 순위와 모델별 ρ 중앙 0.956(층고 0.3) 으로 일치했고, 결정은 메시 교란에 각도로는 흔들려도 J 손실은 대부분 0.4%p 이하였다. 예외는 두 방향 오버행, 수평 아래면, 모든 면이 한 각도에서 풀리는 형상처럼 예측기의 전제 밖인 경우였다. RQ3: 구간 수를 늘린 최선해의 해석식 서포트는 단조 감소하지만 세 구간 이상에서는 블렌드의 층간격 팽창이 실제 G-code 의 미지지를 키웠으므로, 구간 수는 툴패스 검사로 상한을 두어야 하며 이 표본에서는 두 구간이 한계였다. 또한 공개 곡면 슬라이서와 같은 판정식으로 비교했을 때, 곡면 슬라이서가 수렴한 두 모델(sphere·torus)에서 원뿔족은 서포트에서 뒤지지 않으면서 계산이 모델별 약 450~1,200배 가벼웠다. 향후 REP5X 설계로 개조한 5축 프린터로 사전 등록한 시험 출력을 수행해 판정 문턱과 각도 비용을 실물로 확인할 것이다."));

C.push(H2("연구 신뢰성 정리"));
C.push(P("지금까지의 근거를 Table 12 에 모은다.", { noIndent: true }));
C.push(TAB("Summary of reliability evidence"));
C.push(table([2500, 4500, 2638], [
  ["무엇을 믿게 하나", "근거", "범위·단서"],
  ["판정식 구현", "재유도 3회(최대 차 7.6×10⁻¹⁴°), 팀원 독립 구현 약 22,000면(1.42×10⁻¹⁴°), funnel 독립 θ* 계산 차 0.0%p", "45° 문턱 가정은 공유"],
  ["예측 단계가 G-code 를 대표", "순위상관 ρ 중앙 0.956(층고 0.3)·0.998(0.4), 20모델", "mushroom 제외(ρ 정의 불가), torus 는 ρ < 0.8"],
  ["결정의 견고성", "J 손실 ≤ 0.4%p 비율 95~100%(기울임 3° 제외)", "밴드 각도 자체는 흔들림"],
  ["k 값", "부트스트랩 95% 0.055~0.08, 가족 제외 교차검증 0.06~0.075", "층고 의존, 표본 밖 1조건 불통과"],
  ["유도한 식", "증명 9개 식(【증명 부록 추가】, 검산 스크립트 tools/verify_proofs.py), 독립 수치 검산(야코비안 상대오차 1.1×10⁻⁷ 등)", "식의 일치, 물리 검증 아님"],
  ["코드 전체", "단위·회귀 테스트 통과, 정적 검사 0건", ""],
  ["기계 안전", "자체 사전 검사 + 팀원 가상 프린터(독립 역기구학)", "핫엔드 치수·축 부호 실측 전"],
  ["해석의 공정성", "시험마다 판정 기준 사전 등록, 불통과도 그대로 기록", "사후 분석은 표시"],
  ["독립성의 한계", "검증 계층 일부가 같은 AI 도구로 작성됨 【2장 생성형 AI 활용 표와 맞출 것】", "완전 독립 아님"],
], { size: 16 }));

// 참고문헌
C.push(H1("■ 참고문헌"));
[
  "[1] Wüthrich, M., Gubser, M., Elspass, W. J., & Jaeger, C. (2021). A novel slicing strategy to print overhangs without support material. Applied Sciences, 11(18), 8760.",
  "[2] Coupek, D., Friedrich, J., Battran, D., & Riedel, O. (2018). Reduction of support structures and building time by optimized path planning algorithms in multi-axis additive manufacturing. Procedia CIRP, 67, 221–226. 【서지 원문 확인 필요】",
  "[3] Zhang, T., Fang, G., Huang, Y., Dutta, N., Lefebvre, S., Kilic, Z. M., & Wang, C. C. L. (2022). S³-Slicer: A general slicing framework for multi-axis 3D printing. ACM Transactions on Graphics, 41(6), 277.",
  "[4] Liu, T., Zhang, T., Chen, Y., Huang, Y., & Wang, C. C. L. (2024). Neural slicer for multi-axis 3D printing. ACM Transactions on Graphics, 43(4), 85.",
  "[5] Spiritdude. Slicer4RTN. https://xyzdims.com/3d-printing/slicer4rtn/ (접속일 기입)",
  "[6] CNC Kitchen. ConicalSlicer. https://github.com/CNCKitchen/ConicalSlicer (접속일 기입)",
  "[7] CNC Kitchen. Conical Slicing: A different angle of 3D printing. https://www.cnckitchen.com/blog/conical-slicing-a-different-angle-of-3d-printing (접속일 기입)",
  "[8] Klappe, D. Rep5x. https://github.com/dennisklappe/Rep5x (접속일 기입)",
  "[9] jyjblrd. S4_Slicer. https://github.com/jyjblrd/S4_Slicer (접속일 기입)",
].forEach((r) => C.push(new Paragraph({ children: runs(r, { size: 18 }), indent: { left: 400, hanging: 400 }, spacing: { after: 50 } })));

const doc = new Document({
  styles: {
    default: { document: { run: { font: FONT, size: BODY } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 26, bold: true }, paragraph: { spacing: { before: 260, after: 100 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 22, bold: true }, paragraph: { spacing: { before: 160, after: 60 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } }, children: C }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(process.argv[2] || "report_v5.docx", b); console.log("written; figures:", figNo, "tables:", tabNo); });
