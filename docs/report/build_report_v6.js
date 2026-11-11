// R&E 연구보고서 v6 생성기 — docs/paper_outline.md(집필 설계서)의 장·절·그림·표 배치를 따른다.
//   node build_report_v6.js report_v6.docx  (2026-11-11)
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
      tableHeader: i === 0 && o.header !== false, cantSplit: true,
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

// 여러 그림을 한 번호로 묶는다: items = [[slug, widthCm, 라벨], ...], dir = "row" | "col"
function FIGM(items, caption, dir = "row") {
  figNo += 1;
  const img = (slug, widthCm) => {
    const f = path.join(FIG_DIR, `${slug}.png`);
    if (!fs.existsSync(f)) return new Paragraph({ children: runs(`【그림 대기: ${slug}.png】`, { size: 16 }), alignment: AlignmentType.CENTER });
    const buf = fs.readFileSync(f); const { w, h } = pngSize(buf);
    const px = Math.round(widthCm / 2.54 * 96);
    return new Paragraph({ children: [new ImageRun({ type: "png", data: buf, transformation: { width: px, height: Math.round(px * h / w) } })], alignment: AlignmentType.CENTER, keepNext: true });
  };
  const lab = (t) => new Paragraph({ children: runs(t, { size: 16, bold: true }), alignment: AlignmentType.CENTER, spacing: { before: 0, after: 20 }, keepNext: true });
  const out = [];
  if (dir === "col") {
    items.forEach(([s, wcm, l]) => { if (l) out.push(lab(l)); out.push(img(s, wcm)); });
  } else {
    const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
    const nb = { top: none, bottom: none, left: none, right: none };
    const tot = items.reduce((a, [, wcm]) => a + wcm, 0);
    const widths = items.map(([, wcm]) => Math.round(W * wcm / tot));
    widths[widths.length - 1] = W - widths.slice(0, -1).reduce((a, b) => a + b, 0);
    out.push(new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: widths, alignment: AlignmentType.CENTER,
      rows: [new TableRow({ cantSplit: true, children: items.map(([s, wcm, l], i) => new TableCell({ width: { size: widths[i], type: WidthType.DXA }, borders: nb, verticalAlign: VerticalAlign.BOTTOM,
        children: [...(l ? [lab(l)] : []), img(s, wcm)] })) })] }));
  }
  out.push(FIGCAP(`[Fig. ${figNo}] ${caption}`));
  return out;
}
// 부록 그림 (Fig. A1…)
let figA = 0;
function FIGA(slug, caption, widthCm = 13) {
  const save = figNo; figNo = 0;
  const parts = FIG(slug, caption, widthCm);
  figNo = save; figA += 1;
  parts[parts.length - 1] = FIGCAP(`[Fig. A${figA}] ${caption}`);
  return parts;
}

// =====================================================================
const C = [];
// v6 (2026-11-11): docs/report_revision_plan.md(인터뷰 결정) + docs/paper_outline.md(집필 설계서)
//   + docs/hardware_comparison_plan.md(3축 대 5축) + docs/paper_consistency.md(정본 문장·조건 동반 규칙)
//   흐름: 필요성 → 자동 결정·k → (균일의 한계) → 구간 분할 → S4 → 신뢰성. 서론에서 밴드를 꺼내지 않는다.

// ---------------- 1. 연구결과 요약문 ----------------
C.push(BANNER("1. 연구결과 요약문"));
C.push(table([1900, W - 1900], [
  ["과 제 명", "형상 적응형 원뿔 슬라이싱: 원뿔각 자동 결정 알고리즘과 그 신뢰성 검증"],
  ["연구 필요성\n및 목적", "곡면 슬라이싱은 위치마다 출력 방향을 정해야 해서 변수가 너무 많고, 원뿔 슬라이싱은 층 전체를 원뿔각 θ 하나로 기술해 가볍고 방사 대칭 형상에 효율적이다. 그러나 원뿔각은 지금까지 사용자가 정해 왔고, 형상에서 원뿔각을 자동으로 정하는 알고리즘은 조사 범위 내에서 확인되지 않았다. 본 연구는 STL 에서 원뿔각을 자동으로 결정하는 알고리즘을 만들고(RQ1), 그 결정을 믿을 수 있는지 해석식부터 실물까지 단계별로 검증한다(RQ2)."],
  ["연구내용\n및\n결과", "**필요성.** 21개 모델의 최적 원뿔각은 16~42° 로 흩어져, 관례각 하나로는 모든 형상을 다룰 수 없었다.\n**자동 결정과 각도 비용.** 원본 면 법선으로 서포트를 판정하는 해석식과, 서포트 감소와 기울기를 맞바꾸는 목적함수 J = ΔS − k|θ| 로 각도·방향을 자동 결정하였다. 각도 비용이 없는 지표에서는 고정 45° 가 나아 사전 기준(T1)이 성립하지 않았고, 이를 계기로 k 를 분리하였다. 기울기 비용 k = 0.15~0.3 에서 자동 결정은 같은 평균 기울기의 고정각보다 미지지를 33~48% 줄였다(베드 상한 없이, 개발 표본; 상한 22.79° 에서는 【○○%】). k 는 데이터로 0.06(95% 0.055~0.08)으로 추정되었으나 층고에 따라 달랐다.\n**구간 분할.** 각이 하나라 아래쪽 일부 오버행 때문에 모델 전체가 기울어지는 한계를 높이별 두 구간으로 풀면, 허리가 있는 형상에서 같은 서포트를 평균 8.4° 적은 기울기로 얻었다. 보류 표본에서는 허리형 3/3 만 이겼고, 구간이 세 개 이상이면 블렌드 층간격 팽창 때문에 손해였다(N ≤ 2).\n**곡면 슬라이서 비교.** S4 Slicer 가 수렴한 2개 모델(sphere·torus)에서 서포트는 같거나 낮았고 계산은 약 450~1,200배 빨랐다.\n**신뢰성.** 해석식의 각도 순위는 G-code 툴패스 순위와 일치했고(ρ 중앙 0.956, 균일각), 메시 교란에도 J 손실은 대부분 0.4%p 이하였으며, 3축 대조군을 둔 5축 실물 출력으로 판정을 확인한다【실측 후 결과 문장】."],
  ["향후\n연구계획\n(요약)", "실물로 잰 처짐 시작 각도로 판정 문턱을 보정하고, 연속 오버행 지표와 층고 의존 문턱, 축에서 크게 벗어난 비축대칭 형상으로 범위를 넓힌다."],
  ["Keyword\n(5개 이내)", "원뿔 슬라이싱, 원뿔각 자동 결정, 각도 비용, 서포트 저감, 다축 3D 프린팅"],
], { header: false, firstColBold: true, firstColFill: true, size: 18 }));
C.push(BR());

// ---------------- 2. 과제 수행 과정 ----------------
C.push(BANNER("2. 과제 수행 과정"));
C.push(NOTE("※ 외부 전문가 피드백, 생성형 AI 활용 표, 팀원 역할·기여도 칸은 팀이 직접 작성한다(이 초안에서 제외)."));
C.push(table([1900, W - 1900], [
  ["문제해결\n과정", "① 판정 기준 선택 — 원뿔 변환은 XY 를 1/cosθ 배로 늘리는 비등각 사상이라 변환 공간의 각도는 실제 각도가 아니다(funnel: 실제 26° 에서 해결되는 벽이 변환 공간에서는 50.7° 필요). 원본 법선에서 층 방향을 직접 계산하는 해석식 하나를 판정 기준으로 정하고, 세 번 재유도와 팀원 독립 구현(약 22,000면)으로 대조하였다.\n② **관례각을 못 이긴 결과에서 k 를 분리하다** — 사전 기준 T1(자동 결정의 후회가 모든 관례각보다 작다)이 성립하지 않았다. 결과를 그대로 기록한 뒤 원인을 찾으니, 미지지 지표에는 각도의 비용이 없어 '각도를 많이 쓰는 쪽'이 이기는 구조였다. 그래서 각도 비용 k 를 바꾸며 교환 곡선으로 비교하고(k 스윕), k 를 데이터로 추정하는 별도 시험을 사전 등록하였다. 그 결과 '같은 평균 기울기에서 미지지 33~48% 감소'라는 자동 결정의 실제 가치와, k 가 층고에 따라 다르다는 한계를 함께 얻었다.\n③ 균일각의 한계와 구간 분할 — 최적각이 필요한 면은 모두 높이 하반부에 있었다. 높이마다 각을 달리하면서 층이 교차하지 않는 조건과 블렌드 최소 폭을 닫힌 식으로 얻어 계획기에 넣었고, 구간 수를 늘리면 오히려 손해가 되는 지점(N ≥ 3)을 툴패스 검사로 찾았다.\n④ 결함 추적 — funnel 이 상한 아래에서 0° 를 고르는 현상과 메시 세분화에 따라 밴드 각도가 바뀌는 현상을 각각 가설·절제 실험으로 원인(판정 문턱 위치, 면 중심 구적)까지 좁혔다.\n⑤ 실물로 판정하기 — 출력용 G-code 는 자체 사전 검사기와 팀원의 가상 프린터(독립 역기구학)를 모두 통과해야 출력하도록 하였고, 3축 대조군을 두어 기계·노즐 자세·각도 결정의 효과를 하나씩 분리하는 출력 실험을 설계하였다."],
  ["과제 수행\n과정에서의 학습", "좌표 변환과 역변환, 벡터 내적과 삼각함수 합성, 다중적분의 변수변환(야코비안), 5축 기구학(공구 중심점 제어, 역기구학)을 연구에 직접 적용하며 배웠다. 부트스트랩 신뢰구간과 교차검증으로 매개변수를 추정하고 표본 밖에서 확인하는 방법, G-code 와 Marlin 펌웨어 구조, PrusaSlicer 명령행, 단위·회귀 테스트로 코드를 검증하는 방법을 익혔다. 예측을 먼저 적고 계산·실물로 확인하는 절차가 결론의 신뢰도를 어떻게 바꾸는지, 기대와 다른 결과를 숨기지 않고 원인을 추적하는 것이 왜 필요한지 경험하였다. 【팀 자체 평가 추가】"],
], { header: false, firstColBold: true, firstColFill: true, size: 18 }));
C.push(BR());

// ---------------- 3. 연구보고서 ----------------
C.push(BANNER("3. 연구보고서"));
C.push(table([W], [["형상 적응형 원뿔 슬라이싱: 원뿔각 자동 결정 알고리즘과 그 신뢰성 검증\n저자명․저자명․저자명\n○○과학고등학교\nShape-Adaptive Conical Slicing: An Automatic Cone-Angle Selection Algorithm and Its Verification\nauthor․author․author\n○○ Science High School"]], { header: false, center: true, size: 20 }));
C.push(new Paragraph({ children: runs("국문 초록", { bold: true }), alignment: AlignmentType.CENTER, spacing: { before: 180, after: 60 } }));
C.push(P("원뿔 슬라이싱은 층을 원뿔면으로 쌓아 서포트 없이 오버행을 출력하는 방법으로, 곡면 슬라이싱보다 설계변수가 적어 계산이 가볍지만 원뿔각은 지금까지 사용자가 정해 왔다. 21개 모델의 최적 원뿔각은 16~42° 로 흩어져 관례각 하나로는 충분하지 않았다. 본 연구는 STL 의 원본 면 법선으로 서포트 필요 여부를 닫힌 식으로 판정하고, 서포트 감소와 기울기를 맞바꾸는 목적함수 J = ΔS − k|θ| 로 원뿔각과 방향을 자동 결정하는 알고리즘을 제안한다. 각도 비용이 없는 지표에서는 고정 45° 가 나았으나, 각도 비용 k = 0.15~0.3 에서 자동 결정은 같은 평균 기울기의 고정각보다 미지지를 33~48% 줄였다(베드 상한 없이). 각을 하나만 쓰는 한계는 높이별 두 구간으로 보완했으며, 허리가 있는 형상에서 같은 서포트를 평균 8.4° 적은 기울기로 얻었다(보류 표본에서는 허리형 3/3 만 우세). 공개 곡면 슬라이서가 수렴한 두 모델에서 서포트는 같거나 낮았고 계산은 약 450~1,200배 빨랐다. 해석식의 판단은 G-code 툴패스 순위와 일치했고(ρ 중앙 0.956) 메시 교란에도 J 손실이 작아, 자동 결정을 믿고 쓸 수 있는 근거를 얻었다【실물 결과 반영】.", { noIndent: true }));
C.push(P("주제어: 원뿔 슬라이싱, 원뿔각 자동 결정, 각도 비용, 서포트 저감, 다축 3D 프린팅", { noIndent: true, before: 40, after: 140 }));

// =================== Ⅰ. 서론 ===================
C.push(H1("Ⅰ. 서론"));
C.push(P("FDM 3D 프린팅은 모델을 수평면으로 잘라 아래층부터 쌓기 때문에, 아래로 45° 이상 기운 면에는 서포트가 필요하다. 서포트는 재료와 시간을 늘리고 표면을 손상시킨다. 다축 3D 프린팅은 출력 방향을 바꾸어 이를 푼다."));
C.push(P("곡면 슬라이싱(S³-Slicer[3], Neural Slicer[4], S4 Slicer[9])은 위치마다 출력 방향을 최적화해 효율이 높지만, 설계변수가 위치마다 있어 대규모 최적화나 신경망 학습이 필요하고 변수를 모두 통제하기 어렵다. 원뿔 슬라이싱[1,2]은 층 전체를 원뿔 반각 θ 하나로 기술한다. 계산이 가볍고, 방사 대칭 형상의 오버행에 효율적이며, 기존 평면 슬라이서를 그대로 쓸 수 있다(Table 1)."));
C.push(TAB("Comparison of multi-axis slicing approaches"));
C.push(table([2300, 1700, 2200, 1800, 1638], [
  ["방법", "층의 형태", "설계변수", "방향·각도 결정", "계산 비용"],
  ["곡면(S³-Slicer[3], Neural Slicer[4], S4[9])", "임의 곡면", "위치마다 방향(3차원 장)", "자동(최적화·학습)", "큼"],
  ["원뿔(RotBot[1], Slicer4RTN[5])", "원뿔면", "θ 1개", "사용자 지정", "작음"],
  ["본 연구", "원뿔면", "θ", "**자동**", "작음"],
], { center: true, size: 17 }));
C.push(P("그러나 원뿔각은 지금까지 사람이 정했다. RotBot[1]은 45° 고정각을 쓰고, 공개 원뿔 슬라이서인 Slicer4RTN[5]과 ConicalSlicer[6]는 사용자가 입력한 상수각을 쓴다. CNC Kitchen[7]은 구역마다 이상적인 각도를 자동으로 고르는 알고리즘을 다음 과제로 꼽았다. 조사 범위 내에서 원뿔각을 형상으로부터 자동 결정하고 정량 비교한 연구는 확인되지 않았다. 따라서 **원뿔각을 자동으로 정하는 알고리즘**이 필요하다."));
C.push(P("본 연구는 이 알고리즘을 만들고 두 질문에 답한다. **RQ1** 원뿔각을 형상(STL)에서 자동으로 정할 수 있는가. **RQ2** 그 결정을 믿을 수 있는가. 평면 대비 서포트 감소는 원뿔 슬라이싱 일반의 성과이므로, 비교 기준은 균일 원뿔(모델 전체에 각도 하나)과 사람이 써 온 관례 각도로 한다."));

// =================== Ⅱ. 이론적 배경 ===================
C.push(H1("Ⅱ. 이론적 배경"));
C.push(H2("1. 원뿔 변환[1]"));
C.push(EQ("R = r / cosθ,   φ′ = φ,   Z′ = z + c·r·tanθ      (c = +1 outward, −1 inward)", "1"));
C.push(P("변환한 모델을 평면 슬라이서가 Z′ = 상수로 자르고 되돌리면 층은 z = Z′ − c·r·tanθ 인 원뿔면이 된다(Fig. 1).", { noIndent: true }));
C.push(...FIG("conical_layers_lamp_uniform", "Actual layers of the generated G-code on the r–z section (lamp, uniform 22°)", 4.8));

C.push(H2("2. 서포트 판정식"));
C.push(P("**왜 원본 법선으로 판정하는가.** 원뿔 변환은 XY 를 1/cosθ 배로 늘리는 비등각 사상이라, 변환한 메시에서 잰 각도는 실제 물리 각도가 아니다. funnel 벽은 원본에서 θ = 26° 면 풀리지만 변환 공간에서 재면 50.7° 가 필요하다. 그래서 판정은 원본 면 법선에서 층 방향을 직접 계산하는 식 (2) 하나로 통일한다.", { noIndent: true }));
C.push(P("축을 지나는 단면에서 원뿔 층의 위쪽 단위 방향 b = (c·sinθ, cosθ) 와 면 법선 n 의 내적:", { noIndent: true }));
C.push(EQ("g(θ) = n_z·cosθ + c·n_r·sinθ,   서포트 필요 ⇔ g(θ) < κ = −sin45°", "2"));
C.push(P("오버행 각 α 인 면은 n = (cosα, −sinα) 이므로", { noIndent: true }));
C.push(EQ("g(θ) = −sin(α − c·θ)  ⇒  유효 오버행 = α − θ,   θ* = α − 45°", "3"));
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
C.push(P("이다(q = √(n_z² + n_r²)). 격자 없이 이 후보만 평가하면 최적이 정확히 나온다(Fig. 2). 2° 격자 대비 확장 표본 33개 중 32개에서 J 가 올랐고, 계산 시간은 1~4ms 대 3~78ms 였다.", { noIndent: true }));
C.push(...FIG("exact_step", "(a) Step-shaped support area S(θ) and the roots where faces become supported; (b) J(θ) with the exact and 2° grid optima (waist r = 2 mm)", 10.5));

C.push(H2("3. 가변 원뿔각과 층간격"));
C.push(P("높이에 따라 각을 바꾸는 경우(Ⅳ.2)를 위해 층간격 조건을 적어 둔다. 층 k 를 z_k(r) = Z′_k − c·r·tanθ_k 로 두면 같은 반경에서 이웃 층 간격은", { noIndent: true }));
C.push(EQ("Δz(r) = h − c·r·(tanθ_{k+1} − tanθ_k),   m = Δz / h", "5"));
C.push(BUL("• 층 교차 없음: 모든 r ≤ r_max 에서 Δz > 0"));
C.push(BUL("• tanθ 를 Z′ 에 선형 보간(블렌드 폭 w, 총 변화 ΔT) ⇒ m = 1 − c·r·ΔT / w 가 블렌드 안에서 일정 → θ 가 아닌 tanθ 를 보간하는 이유"));
C.push(BUL("• 1/1.5 ≤ m ≤ 1.5 ⇒ w ≥ 2·r_b·|ΔT| (팽창), w ≥ 3·r_b·|ΔT| (압축) — 블렌드 반경 r_b 가 작을수록 블렌드가 좁아도 된다"));
C.push(BUL("• 상수각(ΔT = 0) ⇒ m ≡ 1 : 균일 원뿔에는 없고 가변각에서만 생기는 제약"));

C.push(H2("4. 압출량 보정"));
C.push(EQ("dV / dV′ = cos²θ · m", "6"));
C.push(P("역변환 시 압출량에 식 (6) 을 곱한다(방향 무관). 이 모형이 실제 비드와 맞는지는 실물 출력으로 판정한다(Ⅳ.4.6).", { noIndent: true }));

// =================== Ⅲ. 연구 방법 ===================
C.push(H1("Ⅲ. 연구 방법 및 절차"));
C.push(H2("1. 알고리즘"));
C.push(EQ("θ̂ = argmax_θ J(θ),   J(θ) = ΔS(θ) − k·|θ|   (기본 k = 0.2 %p/°)", "7"));
C.push(BUL("① STL 축 정렬 → ② 면별 g(θ) → ③ 각도: 식 (4) 후보에서 식 (7), 방향은 outward/inward 중 큰 J"));
C.push(BUL("④ 변환 → 평면 슬라이서 → 역변환(식 (6) 압출 보정, 경로 오차 ≤ 0.05mm)"));
C.push(BUL("⑤ 5축: B = θ(Z′), C = 방위각, 회전 속도 상한, 베드 안전각 22.79° → ⑥ 사전 검사 통과 시 출력"));
C.push(P("**왜 1차인가.** 각도 비용을 |θ| 의 1차로 둔 것은 실험으로 정했다. 차수 비교 표본 18개(Table 4)에서 위·아래 두 구간 각을 4° 격자로 전부(144조합) G-code 로 만들어 툴패스 오버행을 재고, 각도 비용을 |θ|^p(p = 1~4)로 둘 때 고른 해가 실측 최적 전선에서 얼마나 멀어지는지(후회)를 비교하였다. 후회 중앙값은 1차 0.004%p, 2차 0.074, 3차 0.117, 4차 0.190 %p 였고, 1차는 18개 모델 모두에서 최저이거나 공동 최저였다(Fig. 3). 기본 선택기에 고차 항을 더한 216회 실행에서 오버행이 줄어든 경우는 한 번도 없었다.", { noIndent: true }));
C.push(...FIG("theta_power_more_regret", "Regret of the selected profile against the measured toolpath front for angle-cost orders p = 1–4 (18 models, 144 two-band combinations each): per-model regret (left) and number of models where each order is best (right, ties split)", 9));
C.push(P("**k 의 의미.** ΔS 만 최대화하면 언제나 최대각이 선택된다. 그런데 각도를 키우면 5축 회전이 늘어 출력 시간이 길어지고 표면 계단이 커진다. REP5X 축 한계로 잰 출력 시간을 균일 4~44° 에서 각도에 선형 맞춤하면 1° 당 lamp 0.525분, 허리 r=3 0.531분, 구 0.636분, 세 모델 평균 0.56분 늘었다(Table 2). 이 기울기로 번역하면 k = 0.2 는 \"서포트 1%p 를 없애는 데 출력 시간 약 2.8분까지 쓴다\"는 교환 비율이다. 본문의 모든 결과는 결과를 보기 전에 정한 기본값 k = 0.2 로 냈고, k 의 값은 Ⅳ.1.4 에서 데이터로 다시 추정한다.", { noIndent: true }));
C.push(TAB("Cost of tilt: REP5X print time and support (lamp, layer 0.3 mm, rewinds excluded)"));
C.push(table([2600, 1700, 2600, 2738], [
  ["조건", "출력 시간(분)", "오버행 낙관 / 비관 (%p)", "계단 정렬비 (평면 = 1)"],
  ["균일 4°", "21.0", "1.37 / 5.41", "0.98"],
  ["균일 24°", "28.3", "0.27 / 4.11", "0.88"],
  ["균일 36° (오버행 0 이 처음 되는 각)", "35.3", "0.00 / 0.00", "0.98"],
  ["균일 44°", "42.6", "0.02 / 1.17", "1.08"],
], { center: true, size: 17 }));
C.push(NOTE("평면(0°) 5.7분 → 4° 21.0분의 점프는 축 근처 C 축 회전(가속도 500 deg/s²)에서 오는 5축 전환 고정비이다. 절대 시간은 근사이고 비만 본다. 24° 이상의 균일각은 베드 안전각 22.79° 를 넘어 실제 기계에서는 출력할 수 없다. 이 행들은 기울기의 시간 비용을 재기 위한 계산값이다."));

C.push(H2("2. 검증 계층"));
C.push(P("결정을 믿을 수 있는지(RQ2)는 다섯 계층으로 나누어 확인한다(Table 3). 표의 아래로 갈수록 실물에 가깝고, Ⅳ.4 는 이 순서로 올라간다.", { noIndent: true }));
C.push(TAB("Verification layers"));
C.push(table([1900, 3700, 2538, 1500], [
  ["계층", "측정량", "보장 범위", "결과 절"],
  ["① 해석식", "면 법선으로 서포트 면적 %", "기하 판정(45° 문턱)", "Ⅳ.4.1"],
  ["② 툴패스 검사기 A", "G-code 비드 아래 앞 층 유무, 진짜 오버행 미지지 길이 mm", "실제 경로, 중력·냉각 없음", "Ⅳ.4.2~4.3"],
  ["③ 퇴적 복원", "복원 형상 대 원본 IoU", "형상 일치, 실물 아님", "Ⅳ.4.4"],
  ["④ 기계 사전 검사", "축 범위·베드 간섭·회전 속도, 독립 역기구학 대조", "치수 일부 추정", "Ⅳ.4.5"],
  ["⑤ 실물", "3축 대조군을 둔 5축 출력(C1~C3)", "조건별 1~2회", "Ⅳ.4.6"],
], { size: 17 }));
C.push(P("**검사기 A 의 '지지됨'.** 압출 경로를 0.225mm 간격 점으로 나눠, 베드 위 첫 층(z ≤ h)이거나 G-code 순서상 먼저 쌓인 점이 수평 0.45mm·수직 (0, 1.5h] 안에 하나라도 있으면 지지된 것으로 본다(Fig. 4). 미지지로 쌓인 재료도 위층을 받친다고 보는 낙관 모형과, 지지된 재료만 받친다고 보는 비관 모형을 함께 쓴다. 미지지 페리미터 중 아랫층 단면 밖에 있는 것의 길이를 '진짜 오버행' 으로 센다. 평면 층이라면 이 기준은 atan(0.45/h) 의 자기지지각(0.3mm 에서 56°, 0.4mm 에서 48°)에 해당한다 — 해석식의 고정 45° 와 달리 **층고에 따라 문턱이 움직인다.**", { noIndent: true }));
C.push(...FIG("checker_criterion", "Support criterion of toolpath checker A: a sample point is supported if it lies on the first layer (z ≤ h) or if an earlier-deposited point lies within 0.45 mm horizontally and (0, 1.5h] below it; synthetic ring tests confirm both thresholds (h = 0.3 mm)", 8.5));

C.push(H2("3. 실험 조건"));
C.push(P("표본·층고·지표·기준선은 Table 4 와 같다.", { noIndent: true }));
C.push(TAB("Experimental conditions"));
C.push(table([2300, 7338], [
  ["항목", "조건"],
  ["표본", "기본 표본 21개 = 기본 17개[축대칭 7(구 1, 허리형 r = 1·2·3·4·5·7mm 6) + 비축대칭 10(허리 r=3 의 XY 배율 λ = 1.1~2 5, 로브 변형 5)] + 데모 4개(sphere, funnel, torus, mushroom)\n보류 표본 21개 = 무작위 20(시드 20261110: 원기둥·상자·나팔 14, 구 3, 허리형 3) + funnel\n**차수 비교 표본 18개**(Ⅲ.1): 허리형·램프·구·원뿔·와인잔·funnel·mushroom 등 — 기본 표본과 다른 집합\n확장 표본 33개(정확 탐색 검산), S³-Slicer[3] 공개 모델 ring·topopt·armadillo(실패 사례)"],
  ["층고·지지 모형", "0.3, 0.4mm (층고 실험은 0.2~0.5mm) / 낙관·비관"],
  ["지표", "미지지 길이 mm(0.5mm 이내 무승부) 또는 진짜 오버행 %p(0.1%p 이내 무승부), 평균 |θ|, 후회 = 사후 최적 대비 미지지 증가"],
  ["기준선", "(a) J 가 고른 균일각 (b) 밴드 아래 구간 각도와 같은 균일각 (c) 같은 평균 기울기(등왜곡)의 균일각 (d) 관례 고정각 15·20·25·45°"],
  ["기계 제약", "베드 안전각 22.79° 적용/미적용 두 판"],
  ["**실물 출력**", "Ender-3 V3 SE 를 REP5X[8] 설계로 개조한 5축 + 3축 대조군. 출력 12개(3축 5, 5축 7), 층고 0.3/0.4mm, 노즐 0.4mm, 같은 PLA, 서포트 끔. 비교 C1 기계 기준선 → C2 노즐 기울기 → C3 각도 결정 순서(Table 11)"],
  ["사전 등록", "시험마다 판정 기준을 결과 전에 문서로 커밋(git 기록). 결과를 본 뒤 추가한 분석은 '사후' 로 표시"],
], { header: true, size: 17 }));

// =================== Ⅳ. 연구 결과 ===================
C.push(H1("Ⅳ. 연구 결과"));
C.push(H2("1. 원뿔각 자동 결정 (RQ1)"));
C.push(P("**1.1 모델마다 최적각이 다르다.** 식 (4) 로 21개 모델의 0° 서포트 필요 면을 풀면, 그 면들의 θ* 는 0~44° 에 넓게 퍼져 있고 J 가 고르는 각도 모델마다 16~42° 로 다르다(Fig. 5). 관례각 하나로는 모든 형상을 다룰 수 없다 — 자동 결정의 필요성을 결과로 확인한 것이다. 모델마다 0° 필요 면적 중 θ* 가 베드 안전각 22.79° 를 넘는 몫의 중앙값은 26% 다(허리형 23~31%, torus 50%, funnel·mushroom 100%).", { noIndent: true }));
C.push(...FIGM([["critical_angle_select", 10, "(a)"], ["t1_angle_spread", 11.5, "(b)"]], "(a) Area-weighted distribution of per-face critical cone angles θ* for the 21 models, with the automatically selected angle (▼) and the bed-safe limit 22.79° (red); (b) spread of the per-model optimal angle", "col"));
C.push(P("**1.2 방향.** 표본 21개 중 안쪽 방향 오버행(inward θ*)을 가진 모델은 torus 하나뿐이고, 선택기는 상한 판 torus 한 건을 빼면 inward 를 고르지 않았다. 안쪽 오버행 그릇과 바깥 오버행 그릇을 따로 만들면 해석식이 각각 inward 15°·outward 15° 를 정확히 고르고, 툴패스에서도 층고 0.3mm 에서 고른 방향만 미지지가 0 이 된다(Fig. 6). 층고 0.4mm 에서는 15~16° 로 부족했다.", { noIndent: true }));
C.push(...FIG("direction_demo", "Automatic choice of cone direction on two hollow vessels with a 60° shoulder: S(θ), J(θ) and toolpath unsupported length for outward and inward cones at 0.3 and 0.4 mm layers", 11));

C.push(P("**1.3 관례 각도와 비교 (사전 등록 T1).** 사전 기준은 \"자동 결정의 후회 중앙값이 모든 실현 가능한 고정 관례각보다 작다\" 였다. 이 기준은 성립하지 않았다(Table 5).", { noIndent: true }));
C.push(TAB("Median regret (mm) of fixed conventional angles and automatic selection, 21 models (k = 0.2)"));
C.push(table([3100, 1200, 1200, 1200, 1200, 1738], [
  ["조건", "15°", "20°", "25°", "45°", "자동"],
  ["0.3mm · 상한 없음", "48.3", "35.2", "13.8", "**1.6**", "15.7"],
  ["0.3mm · 상한 22.79°", "18.9", "5.7", "불가", "불가", "**0.0**"],
  ["0.4mm · 상한 없음", "84.9", "66.4", "57.7", "**0.0**", "43.3"],
  ["0.4mm · 상한 22.79°", "22.1", "3.8", "불가", "불가", "**2.7**"],
], { center: true, size: 17 }));
C.push(BUL("• 상한이 없으면 고정 45° 가 이긴다. 미지지 길이는 각도를 키울수록 거의 계속 줄어 사후 최적이 30~44° 에 몰리고(21개 중 16개가 30~36°), J 는 k·|θ| 때문에 약 22° 에서 멈춘다"));
C.push(BUL("• 상한이 있으면 자동이 이기지만, 사후 최적이 거의 모두 상한 끝(22°)이라 '상한까지 올리기' 에 가깝다"));
C.push(P("**왜 성립하지 않았나.** 후회를 잰 미지지 지표에는 각도의 비용이 없다. 그래서 '각도를 많이 쓰는 쪽' 이 이기고, 각도 비용을 포함한 J 와는 비교의 목적부터 다르다. 비교를 성립시키려면 각도 비용 k 를 지표와 분리해 다루어야 했다. 다음 절은 k 를 바꾸어 가며 같은 기울기 예산에서 비교하고, k 자체를 데이터로 추정한다.", { noIndent: true }));

C.push(P("**1.4 k 를 분리하면: 교환 곡선과 k 추정.** k 를 0~1 로 바꾸어 다시 고르면, k → 0 에서 자동 균일각의 중앙값은 22° 에서 44° 로 커지고 사후 최적과 4° 안인 모델이 1개에서 12개로 늘었다(Fig. 7a). 같은 평균 기울기 예산에서 비교하면(Fig. 7b), 모델마다 다른 각도를 고르는 자동 결정이 한 각도를 모든 모델에 쓰는 것보다 미지지 합이 적었다: k = 0.2, 평균 23° 에서 층고 0.3mm **48% 감소**(1133 → 588mm), 0.4mm **33% 감소**(3118 → 2089mm). 이 수치는 **베드 상한 없이**, 개발 표본에서 얻은 것이고, 이득은 각도 예산이 빠듯한 중간 k(0.15~0.3)에서 네 조건 중 세 조건에서 나왔다. 예산이 사실상 무제한인 k ≤ 0.1 에서는 고정 40° 가 더 나았다. 상한 22.79° 판(Fig. 7b 의 (c)(d))에서의 이득은 【○○% — 원장 등록 후 기입】이다.", { noIndent: true }));
C.push(...FIGM([["k_sweep", 7.5, "(a)"], ["k_pareto", 9, "(b)"]], "(a) Median regret and selected angle vs. k; (b) trade-off curve of mean |θ| vs. total unsupported length — fixed uniform angles (line) vs. automatic selection (markers), without and with the bed-safe limit 22.79°"));
C.push(P("k 의 값은 사전 등록한 방법으로 추정하였다. 네 조건의 후회 중앙값 합을 손실로 두고 k = 0.005~0.5 에서 최소화한 뒤, 1-표준오차 규칙, 모델 부트스트랩(2,000회), 모델 가족 제외 교차검증(5겹)을 적용하였다(Table 6, 손실 곡선은 Fig. A1).", { noIndent: true }));
C.push(TAB("Data-driven estimate of the tilt cost k"));
C.push(table([2600, 1400, 2000, 3638], [
  ["추정 범위", "k̂", "95% 구간", "판정"],
  ["네 조건 전체", "**0.06**", "0.055~0.08", "정밀도 통과(폭 0.025), 안정성 통과(가족 제외 0.06~0.075)"],
  ["층고 0.3mm", "0.115", "0.085~0.16", "구간이 0.4mm 와 겹치지 않음 → 층고 의존"],
  ["층고 0.4mm", "0.06", "0.055~0.08", "표본 밖 0.4mm·상한 없음 1.9mm > 고정 45° 0.0mm → 불통과"],
], { size: 17 }));
C.push(BUL("• k 는 안정적으로 추정되지만 층고에 따라 다르다. 이 k̂ 는 각도 비용을 0 으로 둔 손실에서 나와 각도를 쓰는 쪽으로 치우친다. 손실에 '평균 기울기 1° = 미지지 λ mm' 를 더하면 λ = 2~5 에서 k̂ = 0.14~0.37 — 기본값 0.2 는 '1° 를 미지지 2~5mm 와 바꾼다' 는 가치판단에 해당한다"));
C.push(BUL("• 실제 기계 조건(베드 상한)에서는 k = 0.005~0.18 전 구간에서 후회가 0 이라 k 선택에 둔감하다"));

C.push(P("**1.5 실패 사례: funnel.** funnel 은 상한 판에서 0° 를 골라 미지지 736mm 를 남겼다(사후 최적 22° 는 2mm). 오버행 면 전부가 같은 θ* = 25.26° 라 [0°, 22.79°] 에서 해석식 S 가 51.514% 로 상수이고, J = −kθ 가 되어 k 와 무관하게 0° 가 선택된다(Fig. 8). 독립 계산과의 차 0.0%p 로 **구현 결함이 아니라 판정 문턱의 위치 차**이다 — funnel 툴패스에서 역산한 검사기의 실효 문턱은 층고 0.3mm 에서 약 53°(0.4mm 에서 약 41°)라 18° 에서 이미 풀린다. 차수 비교 실험(Ⅲ.1)의 격자 실측에서도 같은 현상이 보였다: 선택기가 고른 [26°, 26°] 는 오버행 16.9%p 를 남겼지만 격자 안의 [32°, 40°] 는 0%p 였다. S³-Slicer[3] 공개 모델 ring·topopt·armadillo 에서 0° 를 고른 것은 원인이 다르다: 1° 당 서포트 이득의 최대 k* = 0.10~0.16 이 k = 0.2 보다 작다.", { noIndent: true }));
C.push(...FIG("funnel_cap", "funnel: the analytic S(θ) is flat below the bed-safe limit while the toolpath unsupported length drops at 18° (layer 0.3 mm)", 7.5));

C.push(P("**1.6 각이 하나일 때의 한계.** Fig. 5 에서 0° 서포트가 필요한 면은 모두 높이 하반부에 있었다. 변수가 θ 하나이므로, 아래쪽 일부 오버행을 풀기 위해 **위쪽까지 모델 전체를 기울이게 된다.** 위쪽은 고칠 면이 없는데도 기울기의 시간·표면 비용(Table 2)을 그대로 낸다. 그렇다면 높이마다 각을 달리해, 필요한 곳만 기울이면 어떤가 — 다음 절의 질문이다.", { noIndent: true }));

// ----- Ⅳ.2 구간 분할 -----
C.push(H2("2. 구간 분할"));
C.push(P("높이를 N 구간으로 나누어 구간마다 θ 를 두고, 구간 사이는 식 (5) 의 최소 폭을 지키는 블렌드로 잇는다. 블렌드 경계는 모델 높이의 25% 안에서 반경이 작은 높이로 옮기며, J 에서 블렌드 면적 비용(k_blend = 0.1)을 뺀다. N = 2 를 밴드2 라 부른다.", { noIndent: true }));
C.push(P("**2.1 밴드 대 균일.** 두 기준선이 같은 이야기를 한다(Table 7). 밴드 아래 구간 각도와 같은 균일과는 미지지가 거의 무승부이고 평균 |θ| 는 중앙 8.4° 작다. 같은 평균 기울기의 균일과 비교하면 층고 0.3mm 에서 밴드2 가 낙관 15승 1무 0패, 비관 14승 1무 1패였다. 즉 밴드는 **같은 서포트를 더 적은 기울기로** 얻는다. 이 이득은 허리(반경이 작은 높이)가 있을 때 나온다: 블렌드를 허리로 옮기면 식 (5) 의 필요 폭이 lamp 에서 9.1 → 2.3mm 로 1/4 이 되고, 허리가 없는 구는 옮겨도 r_b = 7.6mm 로 커서 이득이 작다(Fig. 9). Table 2 와 같은 조건에서 밴드2 [30°→0°] 는 오버행 0.00 / 0.00%p 를 21.5분에 얻었다(균일 36° 는 35.3분). 보류 표본에서는 사전 기준을 글자 그대로 적용하면 밴드 승률 3/21 로 가설이 기각된다. 사전에 적어 둔 단서대로 허리 유무로 나누면 원기둥·상자·나팔 14개는 평면 오버행이 없어 밴드를 쓰지 않았고(올바른 동작), 허리형 3개는 낙관 3/3 승, 구 3개는 비관에서 2패였다.", { noIndent: true }));
C.push(TAB("Band2 vs. uniform baselines (band2 wins · uniform wins · ties)"));
C.push(table([3400, 2100, 2100, 2038], [
  ["기준선 (지표, 모델 수)", "층고 0.3mm", "층고 0.4mm", "비고"],
  ["(a) J 균일 (미지지 mm, 17)", "5 · 0 · 12", "5 · 3 · 9", "우세 5개 = 아래 구간 각 > 균일각"],
  ["(b) 아래 구간 각도와 같은 균일 (mm, 17)", "0 · 0 · 17", "0 · 2 · 15", "평균 |θ| 중앙 8.4° 감소"],
  ["(c) 등왜곡 균일, 낙관 (%p, 16)", "**15 · 0 · 1**", "15 · 1 · 0", "구는 밴드를 쓰지 않음"],
  ["(c) 등왜곡 균일, 비관 (%p, 16)", "**14 · 1 · 1**", "1 · 15 · 0", "0.4mm 는 지지 모형에 따라 반대"],
  ["보류 표본, 낙관 (%p, 21)", "3 승 / 21", "—", "사전 기준 기각. 허리형 3/3 승"],
], { size: 17 }));
C.push(NOTE("(c) 와 보류 표본은 현재 코드보다 이전 버전에서 잰 값이다. 【현재 코드로 재현 확인 후 '(c) 는 현재 코드로 다시 계산해 같은 결과를 확인하였다.' 로 교체】"));
C.push(...FIGM([["conical_layers_lamp_band", 4.6, "(a)"], ["band_vs_radius", 11.5, "(b)"]], "(a) Actual G-code layers of band 22°→0° on lamp (blue 22°, red blend, green 0°); (b) radius profile R(z), selected θ(Z′), blend position and width, and r* for lamp, waist r = 3, torus and sphere — the blend is moved to the waist"));

C.push(P("**2.2 기계 제약의 비용.** 베드 안전각 22.79° 를 걸면 21개 중 9개의 균일각과 14개의 밴드2 아래 구간 각도가 내려가고, 균일 원뿔의 미지지가 바뀐 모델에서 중앙 33~36mm 늘었다. 늘어난 양의 55~57% 는 한 모델(층고 0.3mm: θ* 가 25~26° 에 몰린 funnel, 0.4mm: 허리 r=3·λ=2 모델)에서 나왔다(Fig. 10).", { noIndent: true }));
C.push(...FIG("bed_cap_cost", "Cost of the bed-safe limit 22.79°: selected angles and increase in unsupported length", 9));

C.push(P("**2.3 구간 수.** 경계 위치가 자유로우면 N 구간 프로필은 경계 하나를 더 넣고 양쪽 각을 같게 둔 N+1 구간 프로필로도 표현되므로, 해석식 최선해 S*_N 은 단조 감소·수렴한다.", { noIndent: true }));
C.push(EQ("𝒫_N ⊂ 𝒫_{N+1}  ⇒  S*_{N+1} ≤ S*_N", "8"));
C.push(P("그러나 전수 최선해(21 모델, N = 1~4)의 G-code 미지지 중앙(층고 0.4)은 N = 1, 2, 3 에서 0.0 → 1.3 → 68.9mm 로 커졌다(Fig. 11). N ≥ 3 의 블렌드가 바닥 오버행 위에 놓여 층간격 팽창이 미지지를 만든다 — 식 (2) 에는 m 이 없다. 해석식 최선해는 17/21 이 N* ≥ 4 로 포화하지 않지만(Table 8) 그 이득은 G-code 미지지로 되돌아오므로, **구간 수는 툴패스 검사로 상한을 둔다(이 표본에서 N ≤ 2).** 층고 0.4mm 에서 실패가 급증하는 이유(고정 수평 지지 폭 0.45mm)는 Fig. A2 에 있다.", { noIndent: true }));
C.push(TAB("Saturation band count N* of the analytic optimum (21 models, layer 0.3 mm)"));
C.push(table([3638, 1500, 1500, 1500, 1500], [
  ["목적", "N* = 1", "N* = 2", "N* = 3", "N* ≥ 4"],
  ["① 서포트 최소", "1", "1", "2", "17"],
  ["② 같은 서포트에서 |θ| 최소", "1", "9", "7", "4"],
], { center: true, size: 17 }));
C.push(NOTE("N* = N → N+1 에서 미지지 감소 < 0.5mm 이고 평균 |θ| 감소 < 1° 인 첫 N."));
C.push(...FIG("t3_band_curve", "(a) Toolpath unsupported length and (b) area-weighted mean |θ| of the analytic optimum vs. number of bands N; stars mark N*", 9.5));

// ----- Ⅳ.3 S4 -----
C.push(H2("3. 곡면 슬라이서와의 비교"));
C.push(P("서론에서 곡면 슬라이서는 변수가 많아 무겁다고 했다. 그렇다면 그 자유도가 서포트에서 이득을 주는가. 사면체 변형 기반의 공개 곡면 슬라이서 S4 Slicer[9](이하 S4)를 같은 판정식 (2) 로 쟀다. **S4 가 유효하게 수렴한 모델은 sphere·torus 두 개뿐**이고(funnel·mushroom 은 사면체가 뒤집혀 무효), 이 두 모델에서 원뿔족이 같거나 나았다(Table 9). 원뿔족 천장은 면 클러스터마다 가장 좋은 방향·각도를 따로 고를 수 있다고 가정했을 때 남는 서포트로, 원뿔족의 이론적 하한이다. 곡률이 큰 torus(층 경선 곡률 κ·r 중앙 0.59)에서도 곡면의 추가 자유도가 서포트 감소로 이어지지 않았다. 계산 시간은 원뿔 각도 결정 0.12~0.27s 대 S4 68~334s 로 모델별 약 450~1,200배 차이였다(Fig. 12). 각도 결정 시간은 면 수에 비례했다(로그-로그 기울기 0.95~1.06, Fig. A4).", { noIndent: true }));
C.push(TAB("Support area (%) along the degree-of-freedom ladder (same criterion, eq. 2) and run time"));
C.push(table([1300, 900, 900, 900, 1200, 1700, 1200, 1538], [
  ["모델", "평면", "균일", "밴드", "원뿔족 천장", "곡면(S4)", "S4 − 천장", "시간 원뿔 / S4"],
  ["sphere", "14.7", "0.0", "0.0", "0.0", "0.1 (0.0~0.4)", "+0.1", "【】 / 【】s"],
  ["torus", "25.0", "18.6", "10.6", "10.6", "16.3† (12.5~16.3)", "+1.9~+5.7", "0.27 / 334s"],
  ["funnel", "51.5", "0.0", "0.0", "0.0", "무효*", "—", "— / 무효"],
  ["mushroom", "27.5", "27.5", "27.5", "27.5", "무효*", "—", "— / 무효"],
], { center: true, size: 16 }));
C.push(NOTE("† 변형 4,000회로 수렴·뒤집힌 사면체 0 인 실행. * 변형 미수렴·사면체 뒤집힘. 원뿔 시간 = 균일+밴드+천장. 결과 표의 기준선은 여전히 균일 원뿔이다."));
C.push(...FIG("s4_runtime", "Run time: cone-angle selection vs. S4 stages (same tetrahedral surface mesh)", 8.5));

// ----- Ⅳ.4 신뢰성 -----
C.push(H2("4. 결정의 신뢰성 (RQ2)"));
C.push(P("Table 3 의 계층을 아래에서 위로 올라가며, 각 계층에서 무엇을 믿게 되었는지 적는다.", { noIndent: true }));
C.push(P("**4.1 해석식 구현.** 판정식 (2)~(4) 를 서로 다른 방법(기울기·야코비안·접선)으로 세 번 재유도해 코드와 대조하였고(최대 차 7.6×10⁻¹⁴°), 팀원의 독립 구현과 약 22,000면에서 일치하였다(1.42×10⁻¹⁴°). 구현은 식대로 동작한다. 다만 세 구현 모두 45° 문턱 가정을 공유한다.", { noIndent: true }));
C.push(P("**4.2 해석식 대 툴패스.** 균일 0~44°(12각)의 해석식 서포트 순위와 툴패스 미지지 순위의 모델별 스피어만 ρ 중앙값은 0.956(층고 0.3), 0.998(0.4), 20모델이다(Fig. 13). 0.8 미만은 두 방향 오버행을 가진 torus 하나이고, mushroom 은 해석식이 모든 각에서 상수라 ρ 가 정의되지 않는다. 이 일치는 **균일각**에서 확인한 것이다. 가변각에서는 해석식이 층간격 팽창을 모르기 때문에 순위가 어긋날 수 있다(Ⅳ.2.3).", { noIndent: true }));
C.push(...FIG("t5_pred_vs_meas", "Analytic prediction vs. toolpath measurement with per-model Spearman ρ (uniform angles 0–44°)", 9));
C.push(P("**4.3 견고성 (사전 등록 T4).** 고른 각도 변화가 2° 이하인 모델 비율로 재면 균일각은 메시 해상도·축 중심 이동에 견고하고 축 기울임에 흔들리며, 밴드2 는 어느 축에서도 사전 기준(90%)에 못 미쳤다(Table 10). 원인을 절제 실험으로 좁히면 J 의 블렌드 면적을 면 중심 한 점으로 세는 구적이었다. 그러나 **고른 해를 원본 메시에서 평가한 J 손실**은 기울임 3° 를 빼면 95~100% 가 0.4%p 이하였다 — 각도는 흔들려도 J 가 평평한 곳이라 고른 해가 원본에서도 거의 최선이다.", { noIndent: true }));
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
C.push(P("**4.4 퇴적 복원.** G-code 에서 비드를 0.1mm 복셀로 쌓아 복원한 형상을 원본과 비교하였다. mushroom_03 의 46개 각도 후보에서 IoU 는 0.926~0.932, 이웃 각도 차 평균 0.57%p 로 0~12° 의 순위는 복원 해상도로 가려지지 않았다.", { noIndent: true }));
C.push(P("**4.5 기계 사전 검사.** 출력용 G-code 는 축 범위·베드 간섭·회전 속도를 보는 자체 사전 검사기와 팀원의 가상 프린터(독립 역기구학)를 모두 통과해야 출력한다. 이 단계에서 부품과 무관하게 각도만으로 정해지는 베드면 침하 −d(1−cosθ)(20° 에서 −3.02mm)와 축 근처의 방위각 급회전을 찾아 출력 전에 조치하였다【조치 내용 기입】. 핫엔드 치수와 축 부호는 실측 전이다.", { noIndent: true }));

C.push(P("**4.6 실물: 3축 대 5축.** 마지막 계층은 실물이다. 비교 하나가 변수 하나만 바꾸도록 셋으로 나누었다. **C1 기계 기준선**은 같은 평면 G-code 를 3축과 개조한 5축(B = 0, Fig. 14)에서 뽑아 개조한 5축이 평면 품질을 해치지 않는지 본다. C1 이 통과해야 C2·C3 의 차이를 기계가 아닌 슬라이싱의 효과로 읽을 수 있다. **C2 노즐 기울기**는 같은 원뿔 층을 노즐 수직(3축)과 노즐 기울임(5축)으로 뽑아 비교한다. **C3 각도 결정**은 5축에서 균일과 밴드2 를 비교해 알고리즘의 판정이 실물과 맞는지 본다. 판정 기준은 출력 전에 커밋하였고(Table 11), 출력물은 Fig. 15 에 싣는다.", { noIndent: true }));
C.push(TAB("Physical prints, 3-axis vs. 5-axis: pre-registered predictions and measurements"));
C.push(table([700, 2700, 2300, 1300, 1300, 1338], [
  ["비교", "출력물", "사전 예측", "3축", "5축", "판정"],
  ["C1", "L1 원기둥 r10×8", "지름 20.00 ± 0.10mm, 두 기계 차 ≤ 0.05mm", "【】", "【】", "【】"],
  ["C1", "L4 얇은 벽 r10×20", "두께비 0.927 (식 6)", "【】", "【】", "【】"],
  ["C1", "L5 오버행 계단 40~65°", "50° 단부터 처짐 (식 2)", "【】", "—", "【】"],
  ["C2", "L2 원뿔대 벽 60°, 균일 15°", "서포트 불필요", "【】", "【】", "【】"],
  ["C2", "L3 램프, 균일 24°", "간섭 3.51%(3축) / 0%(5축)", "【】", "【】", "【】"],
  ["C3", "L3 램프 균일 24° 대 밴드2 (0.3mm)", "밴드2 가 더 깨끗", "—", "【】", "【】"],
  ["C3", "L3 램프 균일 24° 대 밴드2 (0.4mm)", "낙관 모형이면 밴드2, 비관이면 균일", "—", "【】", "【】"],
], { size: 16 }));
C.push(NOTE("오버행 등급 0 = 깨끗, 1 = 약한 처짐, 2 = 늘어진 비드, 3 = 구멍·분리(출력 전 사진 예시와 함께 고정). 층고 0.3mm, 노즐 0.4mm, 같은 PLA, 서포트 끔, 팬 100%, 체적 유량을 맞추고 시간은 비교에서 뺀다. C3 의 0.4mm 에서 균일이 깨끗하면 밴드 우세 주장을 철회한다. 【측정 사진·캘리퍼스 원자료·날짜를 연구노트 쪽수와 함께 기입】"));
C.push(...FIG("printer_photo", "The modified 5-axis printer (REP5X on Ender-3 V3 SE) and the 3-axis control", 15, "【사진 대기: 5축 전경 · B/C 헤드 근접 · 3축 대조 기계】"));
C.push(...FIG("print_results_grid", "Printed parts: rows C1/C2/C3, columns 3-axis / 5-axis (uniform / band2 for C3), same lighting, background and scale", 15, "【사진 대기: 행 C1·C2·C3 × 열 3축·5축, 자 포함, 오버행 등급 예시】"));

C.push(P("**4.7 신뢰성 근거 요약.** 지금까지의 근거를 Table 12 에 모은다.", { noIndent: true }));
C.push(TAB("Summary of reliability evidence"));
C.push(table([2300, 4700, 2638], [
  ["무엇을 믿게 하나", "근거", "범위·단서"],
  ["① 판정식 구현", "재유도 3회(최대 차 7.6×10⁻¹⁴°), 팀원 독립 구현 약 22,000면(1.42×10⁻¹⁴°), funnel 독립 θ* 계산 차 0.0%p", "45° 문턱 가정은 공유"],
  ["② 예측이 G-code 를 대표", "순위상관 ρ 중앙 0.956(층고 0.3)·0.998(0.4), 20모델", "균일각만. mushroom 제외, torus ρ < 0.8"],
  ["② 결정의 견고성", "J 손실 ≤ 0.4%p 비율 95~100%(기울임 3° 제외)", "밴드 각도 자체는 흔들림"],
  ["k 값", "부트스트랩 95% 0.055~0.08, 가족 제외 교차검증 0.06~0.075", "층고 의존, 표본 밖 1조건 불통과"],
  ["J 의 형태(1차)", "차수 비교 18모델 × 144조합 툴패스 실측, 후회 중앙 1차 0.004%p", "차수 비교 표본에 한정"],
  ["③ 퇴적 복원", "IoU 0.926~0.932, 순위 보존", "1모델"],
  ["④ 기계 안전", "자체 사전 검사 + 팀원 가상 프린터(독립 역기구학)", "핫엔드 치수·축 부호 실측 전"],
  ["⑤ 실물", "C1 기계 기준선 · C2 노즐 기울기 · C3 각도 결정 【결과】", "조건별 1~2회"],
  ["유도한 식", "증명 9개 식(부록), 독립 수치 검산(야코비안 상대오차 1.1×10⁻⁷ 등)", "식의 일치, 물리 검증 아님"],
  ["해석의 공정성", "시험마다 판정 기준 사전 등록, 불통과도 그대로 기록", "사후 분석은 표시"],
  ["독립성의 한계", "검증 계층 일부가 같은 AI 도구로 작성됨 【2장 생성형 AI 활용 표와 맞출 것】", "완전 독립 아님"],
], { size: 16 }));

// =================== Ⅴ. 고찰 ===================
C.push(H1("Ⅴ. 고찰"));
C.push(BUL("1. **각도 비용과 k.** 각도 비용이 없는 지표에서는 각도를 키울수록 좋아지므로 큰 고정각이 이긴다(T1, Table 5). 각도에는 출력 시간(세 모델 평균 1° 당 0.56분)과 표면 계단이라는 비용이 있고, 그 비용을 두는 한 모델마다 다른 각도를 고르는 것이 같은 기울기 예산에서 미지지를 줄였다(Fig. 7). k 는 데이터만으로 정해지지 않는다: 미지지만 보면 k ≈ 0.06(층고 0.4)~0.115(층고 0.3)이고, 기본값 0.2 는 '기울기 1° = 미지지 2~5mm' 라는 가치판단이다. 층고에 따라 k 가 다른 것은 검사기의 실효 문턱 atan(0.45/h) 이 층고에 따라 움직이기 때문으로 보인다"));
C.push(BUL("2. **고정 45° 문턱의 한계.** 해석식은 면이 45° 를 넘는 순간만 센다. funnel 처럼 상한 안에서 문턱을 못 넘는 면은 '조금 줄이기' 를 평가하지 못하고(Fig. 8), 검사기의 문턱은 층고 0.3~0.4mm 에서 41~56° 로 움직인다. 실물 L5 에서 잰 처짐 시작 각도【】와 비교하면 【】. 연속 지표나 층고 의존 문턱이 향후 과제이다"));
C.push(BUL("3. **구간 분할의 고유 효과는 기울기 감소이다.** 같은 서포트를 평균 |θ| 8.4° 적게 얻고, 이는 허리에 블렌드를 둘 수 있을 때 나온다(Table 7). 기울기를 최대로 줄인 최선해는 해석식이 층간격을 모르기 때문에 G-code 에서 졌다(Fig. 11)"));
C.push(BUL("4. **실물 예측의 불일치.** 【실측 후 작성 — L4 압출 모형(식 6)과 L5 처짐 각도가 예측과 어떻게 달랐고 왜 그런지】"));
C.push(BUL("5. **견고성은 각도가 아니라 J 손실로 본다.** 밴드 각도는 메시 교란에 흔들리지만 J 가 평평한 곳의 동점 깨기여서 손해가 작다(Table 10). 남은 결함(면 중심 구적)은 블렌드 경계에서 면을 자르는 적분으로 고칠 수 있다"));
C.push(BUL("• **한계**: 기본 표본 21개(축대칭 11, 약한 비축대칭 10), 45° 문턱 기하 판정(중력·냉각 없음), 핫엔드 치수·베드 안전각 22.79° 는 공개 자료 기반 추정, 일부 결과(Table 7 (c)·보류 표본)는 이전 버전에서 잰 값, S4 비교는 수렴 모델 2개, 실물은 조건별 1~2회 출력"));

// =================== Ⅵ. 결론 ===================
C.push(H1("Ⅵ. 결론"));
C.push(P("본 연구는 원뿔 슬라이싱의 원뿔각을 STL 에서 자동으로 결정하는 알고리즘을 만들었다. 모델마다 최적각이 16~42° 로 흩어져 관례각 하나로는 충분하지 않았다. RQ1: 원본 면 법선만으로 서포트를 판정하는 해석식과 서포트 감소·기울기를 맞바꾸는 목적함수로 원뿔각과 방향을 자동 결정하였다. 각도 비용이 없는 지표에서는 고정 45° 가 나았지만, 각도 비용 k = 0.15~0.3 에서 자동 결정은 같은 평균 기울기의 고정각보다 미지지를 33~48% 줄였다(베드 상한 없이). k 는 데이터로 0.06 근처로 추정되었으나 층고에 따라 달랐다. 각이 하나인 한계는 높이별 두 구간으로 보완되어, 허리가 있는 형상에서 같은 서포트를 평균 8.4° 적은 기울기로 얻었다. 구간이 세 개 이상이면 블렌드의 층간격 팽창이 손해였다. 공개 곡면 슬라이서가 수렴한 두 모델에서 원뿔족은 서포트에서 뒤지지 않으면서 약 450~1,200배 가벼웠다. RQ2: **해석식의 판단은 G-code 툴패스 순위와 일치했고(ρ 중앙 0.956), 교란에도 J 손실이 작았으며, 실물 출력에서 【C1~C3 결과】 — 자동 결정을 믿고 쓸 수 있는 근거를 얻었다.**"));
C.push(NOTE("【C3 이 사전 기준을 통과하지 못하면 마지막 문장을 \"…실물에서는 ○○ 조건에서 어긋났고, 그 원인은 ○○ 이다\" 로 바꾼다. 두 판 모두 출력 전에 써 둔다.】"));

// 참고문헌
C.push(H1("■ 참고문헌"));
[
  "[1] Wüthrich, M., Gubser, M., Elspass, W. J., & Jaeger, C. (2021). A novel slicing strategy to print overhangs without support material. Applied Sciences, 11(18), 8760.",
  "[2] Coupek, D., Friedrich, J., Battran, D., & Riedel, O. (2018). Reduction of support structures and building time by optimized path planning algorithms in multi-axis additive manufacturing. Procedia CIRP, 67, 221–226. 【권·쪽 DOI 확인 필요 — 제목·연도는 확인됨】",
  "[3] Zhang, T., Fang, G., Huang, Y., Dutta, N., Lefebvre, S., Kilic, Z. M., & Wang, C. C. L. (2022). S³-Slicer: A general slicing framework for multi-axis 3D printing. ACM Transactions on Graphics, 41(6), 277.",
  "[4] Liu, T., Zhang, T., Chen, Y., Huang, Y., & Wang, C. C. L. (2024). Neural slicer for multi-axis 3D printing. ACM Transactions on Graphics, 43(4), 85.",
  "[5] Spiritdude. Slicer4RTN. https://xyzdims.com/3d-printing/slicer4rtn/ (접속일: 2026.11.11)",
  "[6] CNC Kitchen. ConicalSlicer. https://github.com/CNCKitchen/ConicalSlicer (접속일: 2026.11.11)",
  "[7] CNC Kitchen. Conical Slicing: A different angle of 3D printing. https://www.cnckitchen.com/blog/conical-slicing-a-different-angle-of-3d-printing (접속일: 2026.11.11)",
  "[8] Klappe, D. Rep5x. https://github.com/dennisklappe/Rep5x 【링크 확인 후 접속일 기입】",
  "[9] Bird, J. S4_Slicer. https://github.com/jyjblrd/S4_Slicer (접속일: 2026.11.11)",
].forEach((r) => C.push(new Paragraph({ children: runs(r, { size: 18 }), indent: { left: 400, hanging: 400 }, spacing: { after: 50 } })));

// 부록
const MAIN_FIGS = figNo, MAIN_TABS = tabNo;
C.push(BR());
C.push(H1("■ 부록"));
C.push(P("**A. 증명.** 【식 (2)~(6), (8) 등 9개 식의 증명 — 검산 스크립트 tools/verify_proofs.py】", { noIndent: true }));
C.push(P("**B. 보조 그림.**", { noIndent: true }));
C.push(...FIGA("k_estimate", "Loss L(k) with bootstrap band, 1-SE estimate and per-layer-height estimates of k (Ⅳ.1.4)", 10));
C.push(...FIGA("layer_height_blend", "Why failures rise at 0.4 mm: (a) layer height h_c above which checker A becomes stricter than the selector's rule; (b) unsupported length of uniform and two-band profiles and the part in blend layers; (c) faces that pass the selector but fail the checker (Ⅳ.2.3)", 13));
C.push(...FIGA("t3_nstar_hist", "Distribution of the saturation band count N* (Ⅳ.2.3)", 10));
C.push(...FIGA("t7_scaling", "Run time of angle selection vs. number of faces, log–log (Ⅳ.3)", 10));
C.push(...FIGA("theta_power_more_selector", "Shipped selector with added higher-order angle terms: change in overhang over 216 runs (Ⅲ.1)", 11));
C.push(P("**C. 사전 등록 목록.** 【시험별 판정 기준 커밋 해시·날짜: T1, T4, k 추정, 밴드 보류 표본, 실물 C1~C3】", { noIndent: true }));

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
if (MAIN_FIGS !== 15 || MAIN_TABS !== 12) { console.error(`번호 불일치: 그림 ${MAIN_FIGS}(15), 표 ${MAIN_TABS}(12) — 본문 교차참조를 확인할 것`); process.exit(1); }
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(process.argv[2] || "report_v6.docx", b); console.log("written; figures:", MAIN_FIGS, "+ appendix", figA, "tables:", MAIN_TABS); });
