// R&E 연구보고서 초안 생성기 (v2: 수식·수치·그림 위주)
//   node build_report_draft.js report_draft.docx
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
let tabNo = 0;
const TAB = (caption) => { tabNo += 1; return CAPTION(`Table ${tabNo}. ${caption}`); };

// =====================================================================
const C = [];

// ---------------- 1. 연구결과 요약문 ----------------
C.push(BANNER("1. 연구결과 요약문"));
C.push(table([1900, W - 1900], [
  ["과 제 명", "형상 적응형 원뿔 슬라이싱: 원뿔각 자동 결정 알고리즘과 그 신뢰성 검증"],
  ["연구 필요성\n및 목적", "원뿔 슬라이싱은 층을 원뿔면으로 쌓아 서포트 없이 오버행을 출력하는 다축 3D 프린팅 기법이다. 위치마다 출력 방향을 최적화하는 곡면 슬라이싱보다 설계변수가 훨씬 적어 계산이 가볍고 방사 대칭 형상에 효과적이다. 그러나 원뿔각은 지금까지 사용자가 정해 왔고, 형상에서 원뿔각을 자동으로 정하는 알고리즘은 조사 범위 내에서 확인되지 않았다. 본 연구는 STL 에서 원뿔각과 높이 구간별 각도를 자동 결정하는 알고리즘을 만들고, 그 결정의 신뢰성과 구간 개수에 따른 거동을 검증한다."],
  ["연구내용\n및\n결과", "① 원본 면 법선으로 서포트를 판정하는 해석식(유효 오버행 = 원래 오버행 − θ)과 면별 임계각 θ* = α − 45° 유도 ② 가변각의 층간격 Δz = h − r·Δtanθ 로 층 교차 방지 조건·블렌드 최소 폭 유도 ③ 축대칭 17개 모델에서 두 균일 원뿔 기준선과 비교 【보류: 대표 결과】 ④ 구간 수 최선해는 단조 감소, 구간 분할의 고유 효과는 같은 서포트에서 평균 기울기 중앙 8.4° 감소 ⑤ 판정식 독립 구현 대조 최대 차 1.42×10⁻¹⁴°, 퇴적 복원 IoU 3회 재실행 해시 일치"],
  ["향후\n연구계획\n(요약)", "제작한 5축 프린터(REP5X)로 사전 등록한 시험 출력(L0~L5)을 수행해 판정 기준과 압출 모형을 실물로 확인하고, 곡면 슬라이싱과의 정량 비교와 비축대칭 형상으로 범위를 넓힌다."],
  ["Keyword\n(5개 이내)", "원뿔 슬라이싱, 원뿔각 자동 결정, 가변 원뿔각, 서포트 저감, 다축 3D 프린팅"],
], { header: false, firstColBold: true, firstColFill: true, size: 18 }));
C.push(BR());

// ---------------- 2. 과제 수행 과정 ----------------
C.push(BANNER("2. 과제 수행 과정"));
C.push(NOTE("※ 외부 전문가 피드백, 생성형 AI 활용 표, 팀원 역할·기여도 칸은 팀이 직접 작성한다(이 초안에서 제외)."));
C.push(table([1900, W - 1900], [
  ["문제해결\n과정", "① 판정 기준 선택 — 원뿔 변환은 XY 를 1/cosθ 배로 늘리는 비등각 사상이라 변환 공간의 각도는 실제 각도가 아니다(funnel: 실제 26° 에서 해결되는 벽이 변환 공간에서는 53° 필요). 원본 법선에서 층 방향을 직접 계산하는 해석식 하나를 판정 기준으로 정하고, 세 번 재유도와 팀원 독립 구현(약 22,000면)으로 대조하였다.\n② 가변각 안전 조건 — 이웃 두 원뿔 층의 높이 차로 층 교차 방지 조건과 블렌드 최소 폭을 닫힌 식으로 얻고, 실제 G-code 의 층간격으로 확인하였다.\n③ 해석의 공정성 — 평면이 아닌 균일 원뿔과 비교하고 기준선을 둘로 나누어 이득의 원천을 분리하였다. 판정 기준은 결과 전에 문서로 고정하였다.\n④ 기계 안전 — 출력용 G-code 는 자체 사전 검사기와 팀원의 가상 프린터(독립 역기구학)를 모두 통과해야 출력하도록 하였다."],
  ["과제 수행\n과정에서의 학습", "좌표 변환과 역변환, 벡터 내적과 삼각함수 합성, 다중적분의 변수변환(야코비안), 5축 기구학(공구 중심점 제어, 역기구학)을 연구에 직접 적용하며 배웠다. G-code 와 Marlin 펌웨어 구조, PrusaSlicer 명령행, 단위·회귀 테스트로 코드를 검증하는 방법을 익혔다. 예측을 먼저 적고 계산·실물로 확인하는 절차가 결론의 신뢰도를 어떻게 바꾸는지 경험하였다. 【팀 자체 평가 추가】"],
], { header: false, firstColBold: true, firstColFill: true, size: 18 }));
C.push(BR());

// ---------------- 3. 연구보고서 ----------------
C.push(BANNER("3. 연구보고서"));
C.push(table([W], [["형상 적응형 원뿔 슬라이싱: 원뿔각 자동 결정 알고리즘과 그 신뢰성 검증\n저자명․저자명․저자명\n○○과학고등학교\nShape-Adaptive Conical Slicing: An Automatic Cone-Angle Selection Algorithm and Its Verification\nauthor․author․author\n○○ Science High School"]], { header: false, center: true, size: 20 }));
C.push(new Paragraph({ children: runs("국문 초록", { bold: true }), alignment: AlignmentType.CENTER, spacing: { before: 180, after: 60 } }));
C.push(P("원뿔 슬라이싱은 층을 원뿔면으로 쌓아 서포트 없이 오버행을 출력하는 방법으로, 곡면 슬라이싱보다 설계변수가 적어 계산이 가볍고 방사 대칭 형상에 효과적이다. 그러나 원뿔각은 지금까지 사용자가 정해 왔다. 본 연구는 STL 의 면 법선에서 서포트 필요 여부를 닫힌 식으로 판정하고, 이를 바탕으로 원뿔각과 높이 구간별 각도를 자동 결정하는 알고리즘을 제안한다. 각도를 높이에 따라 바꿀 때 층이 교차하거나 벌어지지 않는 조건을 유도해 알고리즘에 넣었다. 축대칭 17개 모델에서 【보류: 대표 결과】. 구간 수를 늘린 최선해는 단조 감소하였고, 구간 분할의 고유 효과는 같은 서포트에서 평균 기울기를 줄이는 것이었다. 판정식은 독립 구현과 10⁻¹⁴° 수준에서 일치했고, 퇴적 복원 IoU 는 반복 실행에서 재현되었다.", { noIndent: true }));
C.push(P("주제어: 원뿔 슬라이싱, 원뿔각 자동 결정, 가변 원뿔각, 서포트 저감, 다축 3D 프린팅", { noIndent: true, before: 40, after: 140 }));

// Ⅰ. 서론 (산문 유지)
C.push(H1("Ⅰ. 서론"));
C.push(P("FDM 3D 프린팅은 모델을 수평면으로 잘라 아래층부터 쌓기 때문에, 아래로 45° 이상 기운 면에는 서포트가 필요하다. 서포트는 재료와 시간을 늘리고 표면을 손상시킨다. 다축 3D 프린팅은 출력 방향을 바꾸어 이를 푼다. 곡면 슬라이싱[3,4]은 위치마다 출력 방향을 최적화해 효율이 높지만 설계변수가 위치마다 있어 자유도가 매우 크고 대규모 최적화나 신경망 학습이 필요하다. 원뿔 슬라이싱[1,2]은 층 전체를 원뿔 반각 θ 하나로 기술해 계산이 가볍고, 기존 평면 슬라이서를 그대로 쓰며, 방사 대칭 형상의 오버행에 효과적이다(Table 1)."));
C.push(P("그러나 원뿔각은 지금까지 사람이 정했다. RotBot[1]은 45° 고정각을, 3축용 원뿔 슬라이서[5,6]는 사용자가 입력한 상수각을 쓴다. CNC Kitchen[7]은 구역마다 이상적인 각도를 자동으로 고르는 알고리즘을 다음 과제로 꼽았다. 조사 범위 내에서 원뿔 슬라이싱 계열에서 원뿔각을 형상으로부터 자동 결정하고 정량 비교한 연구는 확인되지 않았다. 본 연구는 이 알고리즘을 만들고 세 질문에 답한다. **RQ1** STL 만으로 원뿔각을 자동 결정할 수 있는가. **RQ2** 그 결정은 믿을 만한가. **RQ3** 높이 구간(밴드)의 개수를 늘리면 어떻게 되며 몇 개를 써야 하는가. 평면 대비 감소는 원뿔 슬라이싱 일반의 성과이므로 비교 기준은 균일 원뿔(모델 전체에 각도 하나)로 한다."));
C.push(TAB("Comparison of multi-axis slicing approaches"));
C.push(table([2300, 1700, 2200, 1800, 1638], [
  ["방법", "층의 형태", "설계변수", "방향·각도 결정", "계산 비용"],
  ["곡면(S³-Slicer[3], Neural Slicer[4])", "임의 곡면", "위치마다 방향(3차원 장)", "자동(최적화·학습)", "큼"],
  ["원뿔(RotBot[1], Slicer4RTN[5])", "원뿔면", "θ 1개", "사용자 지정", "작음"],
  ["본 연구", "높이별 원뿔면", "구간별 θ N개", "자동", "작음"],
], { center: true, size: 17 }));

// Ⅱ. 이론적 배경
C.push(H1("Ⅱ. 이론적 배경"));
C.push(H2("1. 원뿔 변환[1]"));
C.push(EQ("R = r / cosθ,   φ′ = φ,   Z′ = z + c·r·tanθ      (c = +1 outward, −1 inward)", "1"));
C.push(P("변환한 모델을 평면 슬라이서가 Z′ = 상수로 자르고 되돌리면 층은 z = Z′ − c·r·tanθ 인 원뿔면이 된다(Fig. 1).", { noIndent: true }));
C.push(...FIG("conical_layers_lamp", "Actual layers of generated G-code on the r–z section: (a) uniform 22°, (b) band 22°→0°", 15, "L3a/L3b G-code 의 층을 r–z 단면에"));

C.push(H2("2. 서포트 판정식"));
C.push(P("축을 지나는 단면에서 원뿔 층의 위쪽 단위 방향 b = (c·sinθ, cosθ) 와 면 법선 n 의 내적:", { noIndent: true }));
C.push(EQ("g(θ) = n_z·cosθ + c·n_r·sinθ,   서포트 필요 ⇔ g(θ) < κ = −sin45°", "2"));
C.push(P("오버행 각 α 인 면은 n = (cosα, −sinα) 이므로", { noIndent: true }));
C.push(EQ("g(θ) = −sin(α − c·θ)  ⇒  유효 오버행 = α − θ,   θ* = α − 45°", "3"));
C.push(P("funnel 벽(α = 70.3°)은 θ = 26° 에서 44.3° 로 통과한다. 변환 공간에서 재면 같은 벽이 θ = 53° 에서야 통과한다(Fig. 2b) — 판정을 식 (2) 하나로 통일한 이유이다. 구현은 식 (2) 를 그대로 옮긴 세 줄이다.", { noIndent: true }));
C.push(CODE([
  "def overhang_score(mesh, angle_deg, direction, radial=None):",
  "    nz = mesh.face_normals[:, 2]",
  "    nr = radial_normal(mesh) if radial is None else radial",
  "    d = _dir_sign(direction)",
  "    a = np.radians(angle_deg)",
  "    return nz * np.cos(a) + d * nr * np.sin(a)        # 식 (2)",
], "conical/analytic.py"));
C.push(...FIG("g_theta_funnel", "(a) g(θ) for overhang faces and the threshold −sin45°; (b) effective overhang vs. overhang measured in the warped space (funnel wall)", 15));
C.push(...FIG("theta_star_check", "Closed-form critical angle θ* vs. exhaustive search (independent numpy implementation)", 15));
C.push(P("검산: 닫힌 식 θ* 와 0~90° 전수 탐색이 무작위 면 423개에서 불일치 0, 팀원 독립 구현과 약 22,000면에서 최대 차 1.42×10⁻¹⁴° 였다. 【보류: 정확 선택 세션 — S(θ) 는 θ* 들에서만 바뀌는 계단함수이므로 최적 θ 는 유한 후보 {θ*} 안에 있다】", { noIndent: true }));

C.push(H2("3. 가변 원뿔각과 층간격"));
C.push(P("층 k 를 z_k(r) = Z′_k − c·r·tanθ_k 로 두면 같은 반경에서 이웃 층 간격은", { noIndent: true }));
C.push(EQ("Δz(r) = h − c·r·(tanθ_{k+1} − tanθ_k),   m = Δz / h", "4"));
C.push(BUL("• 층 교차 없음: 모든 r ≤ r_max 에서 Δz > 0"));
C.push(BUL("• tanθ 를 Z′ 에 선형 보간(블렌드 폭 w, 총 변화 ΔT) ⇒ m = 1 − c·r·ΔT / w 가 블렌드 안에서 일정 → θ 가 아닌 tanθ 를 보간하는 이유"));
C.push(BUL("• 1/1.5 ≤ m ≤ 1.5 ⇒ w ≥ 2·r_b·|ΔT| (팽창), w ≥ 3·r_b·|ΔT| (압축)"));
C.push(BUL("• 상수각(ΔT = 0) ⇒ m ≡ 1 : 균일 원뿔에는 없고 가변각에서만 생기는 제약"));
C.push(CODE([
  "def spacing_factor(self, zw, r, direction=\"outward\"):",
  "    c = 1.0 if direction == \"outward\" else -1.0",
  "    return 1.0 - c * np.asarray(r, dtype=float) * self.slope_at(zw)   # 식 (4)",
], "conical/profile.py · AngleProfile"));
C.push(P("검산: 17개 모델의 블렌드 실제 최대 m = 1.47~1.50(한계 1.5 위반 0/17).", { noIndent: true }));
C.push(...FIG("spacing_heatmap", "Layer-spacing factor m(r, z) of a two-band profile with the limits 1/1.5 and 1.5", 15));
C.push(...FIG("t2_spacing", "(a) Measured vs. predicted layer spacing from generated G-code; (b) ratio distribution", 15, "T2 세션"));

C.push(H2("4. 압출량 보정"));
C.push(EQ("dV / dV′ = cos²θ · m", "5"));
C.push(P("역변환 시 압출량에 식 (5) 를 곱한다. 단독 벽에서는 1mm 당 압출비가 cosθ 가 되며, 22° 에서 생성 G-code 의 측정값 0.9271 대 cos22° = 0.9272 이다(Fig. 6). 실물 모형 판정은 L4 출력으로 한다.", { noIndent: true }));
C.push(...FIG("extrusion_ratio", "Extrusion per mm of a single wall vs. cone angle: measured from generated G-code and cosθ", 11));

// Ⅲ. 연구 방법
C.push(H1("Ⅲ. 연구 방법 및 절차"));
C.push(H2("1. 알고리즘"));
C.push(EQ("θ̂ = argmax_θ J(θ),   J(θ) = ΔS(θ) − k·|θ|   (k = 0.2 %p/°)", "6"));
C.push(BUL("① STL 축 정렬 → ② 면별 g(θ) → ③ 균일각: 식 (6), 방향은 outward/inward 중 큰 J"));
C.push(BUL("④ 밴드: 높이 N 구간마다 θ, 블렌드는 식 (4) 의 최소 폭, J 에서 블렌드 면적 비용 차감"));
C.push(BUL("⑤ 변환 → 평면 슬라이서 → 역변환(식 (5) 압출 보정, 경로 오차 ≤ 0.05mm)"));
C.push(BUL("⑥ 5축: B = θ(Z′), C = 방위각, 회전 속도 상한, 베드 안전각 22.8° → ⑦ 사전 검사 통과 시 출력"));
C.push(...FIG("support_vs_angle", "Support area S(θ) and objective J(θ) for demo models; markers are the selected angles", 15));
C.push(...FIG("toolpath_3d", "Generated 5-axis toolpath colored by head tilt B, and B per layer", 15));

C.push(H2("2. 검증 계층과 실험 조건"));
C.push(TAB("Verification layers"));
C.push(table([2100, 4600, 2938], [
  ["계층", "측정량", "보장 범위"],
  ["해석식", "면 법선으로 서포트 면적 %", "기하 판정(45° 문턱)"],
  ["툴패스 검사기", "G-code 비드 아래 앞 층 유무, 진짜 오버행 미지지 길이 mm", "실제 경로, 중력·냉각 없음"],
  ["퇴적 복원", "복원 형상 대 원본 IoU", "형상 일치, 실물 아님"],
  ["기계 사전 검사", "축 범위·베드 간섭·회전 속도, 독립 역기구학 대조", "치수 일부 추정"],
  ["실물", "사전 등록 시험 출력 L0~L5", "【보류】"],
], { size: 17 }));
C.push(TAB("Experimental conditions"));
C.push(table([2300, 7338], [
  ["항목", "조건"],
  ["표본", "축대칭 17개: 구 1, 허리형 r = 1·2·3·4·5·7mm 6, 허리형 XY 배율 λ = 1.1~2 5, 로브 변형 5 / 데모: funnel, torus, mushroom"],
  ["층고·지지 모형", "0.3, 0.4mm / 낙관 지지(처진 비드도 지지로 셈)"],
  ["지표", "미지지 길이 mm(0.5mm 이내 무승부), 평균 |θ|"],
  ["기준선", "(a) J 가 고른 균일각  (b) 밴드 아래 구간 각도와 같은 균일각"],
  ["기계 제약", "베드 안전각 적용/미적용 두 판"],
  ["사전 등록", "판정 기준을 결과 전에 문서로 고정"],
], { header: true, size: 17 }));

// Ⅳ. 연구 결과
C.push(H1("Ⅳ. 연구 결과"));
C.push(H2("1. 원뿔각 자동 결정 (RQ1)"));
C.push(P("funnel 에서 고른 각도는 outward 26° = 식 (3) 의 θ* = 25.3° 를 2° 격자에서 처음 넘는 값이며, 서포트 51.5% → 0% 였다(구 14.7% → 0%).", { noIndent: true }));
C.push(TAB("Band2 vs. uniform baselines, 17 models (band2 wins · uniform wins · ties, unsupported length)"));
C.push(table([3238, 2000, 2000, 2400], [
  ["기준선", "층고 0.4mm", "층고 0.3mm", "베드 안전각 (0.4 / 0.3)"],
  ["(a) J 가 고른 균일", "5 · 3 · 9", "5 · 0 · 12", "3 · 1 · 13 / 3 · 0 · 14"],
  ["(b) 아래 구간 각도와 같은 균일", "0 · 2 · 15", "0 · 0 · 17", "0 · 1 · 16 / 0 · 0 · 17"],
], { center: true }));
C.push(BUL("• (a) 의 우세 5개 = 모두 밴드 아래 구간 각도 > 균일각인 모델 (26 대 16°, 28 대 20°, 30 대 24°, 24 대 22°, 26 대 20°)"));
C.push(BUL("• 같은 미지지에서 평균 |θ| 감소: 중앙 8.4° (1.0~11.1°)"));
C.push(BUL("• 램프(층고 0.3): 균일(J) 24° 17.8mm / 밴드 [30°, 0°] 0.0mm / 균일 30° 0.0mm"));
C.push(P("【보류: 결과 문장의 기준선】", { noIndent: true }));
C.push(...FIG("baseline_bars", "Unsupported length of 17 models: uniform (J), band2 and uniform at band2's bottom angle; (a) 0.4 mm, (b) 0.3 mm layers", 16));
C.push(...FIG("tilt_reduction", "Mean |θ| of uniform (J) and band2 per model", 11));
C.push(...FIG("t1_regret", "Regret of fixed conventional angles (15·20·25·45°) and automatic selection against the per-model optimum", 15, "T1 세션"));

C.push(H2("2. 구간(밴드) 개수 (RQ3)"));
C.push(EQ("𝒫_N ⊂ 𝒫_{N+1}  ⇒  S*_{N+1} ≤ S*_N,   S*_N → S*_∞ (N → ∞)", "7"));
C.push(P("N 구간 프로필은 한 구간을 같은 각도로 둘로 나누어 N+1 구간으로도 표현되므로 최선해 S*_N 은 단조 감소·수렴한다. 측정:", { noIndent: true }));
C.push(BUL("• 각도 비용 k = 0 이면 밴드의 해석식 서포트 이득 = 0 (17/17) → 구간 분할의 값은 기울기 감소"));
C.push(BUL("• N 을 J 로 고르면 오버행이 달성 가능한 최소보다 나쁨 (7/7) → N 은 최선해 곡선으로 정한다"));
C.push(P("【보류: 최선해 곡선·포화 N* — T3】", { noIndent: true }));
C.push(...FIG("t3_band_curve", "Best-achievable unsupported length and mean |θ| vs. number of bands N", 15, "T3 세션"));
C.push(P("**가정.** 축대칭 곡면 층 z = Z′ − f(r) 의 1차 근사가 원뿔이며 오차는", { noIndent: true }));
C.push(EQ("|f(r) − f(r₀) − f′(r₀)(r − r₀)| ≈ ½·|f″|·(r − r₀)²", "8"));
C.push(P("이므로 층의 경선 곡률 f″ 가 작으면 원뿔족 극한(N → ∞)이 곡면 슬라이싱에 가깝다. 방사 대칭 모델은 밴드가 원뿔족 천장에 도달했고, 수평 아래면을 가진 mushroom 은 모든 칸이 28.3% 로 원뿔족이 풀 수 없다(Table 5).", { noIndent: true }));
C.push(TAB("Support area (%) along the degree-of-freedom ladder (analytic)"));
C.push(table([1800, 1400, 1400, 1400, 1800, 1838], [
  ["모델", "평면", "균일", "밴드", "원뿔족 천장", "곡면(S4)"],
  ["sphere", "14.7", "0.0", "0.0", "0.0", "【보류】"],
  ["funnel", "51.5", "0.0", "0.0", "0.0", "【보류】"],
  ["torus", "25.0", "18.6", "10.6", "10.6", "【보류】"],
  ["mushroom", "28.3", "28.3", "28.3", "28.3", "【보류】"],
], { center: true }));
C.push(...FIG("dof_ladder", "Support area from planar to the cone-family ceiling (and curved slicing, S4)", 15, "S4 세션 결과 오면 s4_dof_ladder 로 교체"));
C.push(...FIG("t6_cone_approx", "(a) Curved layer and its tangent cone; (b) height error vs. r on log–log axes (slope 2)", 15, "T6 세션"));

C.push(H2("3. 결정의 신뢰성 (RQ2)"));
C.push(P("퇴적 복원 IoU = 평균 교집합 / 평균 합집합(복셀당 측정점 4개, 복셀 0.3mm). mushroom_03, 46개 각도 후보:", { noIndent: true }));
C.push(TAB("Deposition-reconstruction IoU (mushroom_03)"));
C.push(table([2400, 2400, 2400, 2438], [
  ["각도", "IoU", "3회 재실행", "비고"],
  ["0°", "0.9262", "해시·IoU 일치", ""],
  ["10°", "0.9317", "해시·IoU 일치", "측정 최대"],
  ["12°", "0.9267", "해시·IoU 일치", ""],
  ["이웃 각도 차", "평균 0.57%p", "—", "0~12° 순위는 해상도로 못 가림"],
], { center: true, size: 17 }));
C.push(...FIG("iou_angle", "Deposition-reconstruction IoU over 46 cone-angle candidates (mushroom_03) with three re-runs", 15));
C.push(...FIG("t5_pred_vs_meas", "Analytic prediction vs. toolpath measurement with per-model Spearman ρ", 15, "T5 세션"));
C.push(...FIG("exact_step", "Step-shaped S(θ), objective J(θ), candidate angles {θ*}, exact vs. 2° grid optimum", 15, "정확 선택 세션"));

C.push(H2("4. 실물 출력"));
C.push(TAB("Pre-registered predictions for the test ladder"));
C.push(table([1100, 3400, 2600, 2538], [
  ["단계", "출력물", "예측", "실측"],
  ["L1", "원기둥 r10 × 8, B = 0", "지름 20.0mm", "【보류】"],
  ["L4a/b", "단벽 원기둥 B = 0 / 22°", "벽 두께비 0.927 (식 5)", "【보류】"],
  ["L5", "오버행 계단 40~65°, 평면", "50° 단부터 처짐(식 2)", "【보류】"],
  ["L2p/L2", "벽 60° 원뿔대: 평면 / 균일 15°", "49.87%p / 0.00%p", "【보류】"],
  ["L3a/b", "램프: 균일 22° / 밴드 22°→0°", "0.53 / 0.58%p (구별 안 됨)", "【보류】"],
], { size: 17 }));
C.push(table([W], [["【사진 대기: 개조한 REP5X 프린터 전경 · 헤드(B/C축) 근접】"]], { header: false, center: true, size: 16 }));
C.push(FIGCAP(`[Fig. ${++figNo}] The modified 5-axis printer (REP5X on Ender-3 V3 SE)`));
C.push(table([W], [["【사진 대기: L1~L5 출력물 — 같은 조명·배경·스케일, 4방향 + 위】"]], { header: false, center: true, size: 16 }));
C.push(FIGCAP(`[Fig. ${++figNo}] Printed test ladder L1–L5`));

C.push(H2("5. 계산 비용"));
C.push(P("데모 모델당 균일각 결정 2~32ms, 밴드 계획 3~45ms (해석식). 【보류: 메시 크기별 — T7, S4 비교】", { noIndent: true }));
C.push(...FIG("t7_scaling", "Run time vs. number of faces (log–log) for uniform and band selection", 11, "T7 세션"));
C.push(...FIG("s4_runtime", "Run time: cone-angle selection vs. curved slicing (S4) stages", 11, "S4 세션"));

// Ⅴ. 고찰
C.push(H1("Ⅴ. 고찰"));
C.push(BUL("• **이득의 원천**: (a) 대비 우세 5/17 은 전부 아래 구간 각도 차이, (b) 대비 0/17 → 자동 결정의 이득 = 형상에 맞는 아래 구간 각도 선택. 구간 분할의 고유 효과 = 평균 |θ| 중앙 8.4° 감소(실물 가치는 L3 로 판정). 【보류: 베드 램프 결과 포함 여부】"));
C.push(BUL("• **적용 범위**: 방사 대칭(구·funnel·torus)은 밴드 = 원뿔족 천장, 수평 아래면(mushroom)은 28.3% 불변 → 식 (8) 의 f″ 가 큰 형상은 곡면 슬라이싱의 영역"));
C.push(BUL("• **한계**: 축대칭 표본 17개, 45° 문턱 기하 판정(중력·냉각 없음), 핫엔드 치수·베드 안전각 22.8° 는 공개 자료 기반 추정, 실물 결과 【보류】"));

// Ⅵ. 결론 (산문)
C.push(H1("Ⅵ. 결론"));
C.push(P("본 연구는 원뿔 슬라이싱의 원뿔각을 STL 에서 자동으로 결정하는 알고리즘을 만들었다. RQ1: 원본 면 법선만으로 서포트를 판정하는 해석식을 유도하고, 원뿔각과 방향, 구간별 각도를 자동으로 결정하였다. 【보류: 대표 결과 한 문장】 RQ2: 판정식은 독립 구현과 일치했고, 선택한 각도의 G-code 는 퇴적 복원에서 재현되었다. RQ3: 구간 수를 늘린 최선해는 단조 감소하며 구간 분할의 고유 효과는 기울기 감소이므로, 구간 수는 J 가 아니라 최선해 곡선으로 정해야 한다. 향후 제작한 5축 프린터로 사전 등록한 시험 출력을 수행하고, 곡면 슬라이싱과의 정량 비교와 비축대칭 형상으로 연구를 넓힐 것이다."));
C.push(H2("연구 신뢰성 정리"));
C.push(TAB("Summary of reliability evidence"));
C.push(table([2500, 4500, 2638], [
  ["무엇을 믿게 하나", "근거", "범위·단서"],
  ["판정식 구현", "재유도 3회(최대 차 7.6×10⁻¹⁴°), 팀원 독립 구현 약 22,000면(1.42×10⁻¹⁴°), 전수 탐색 423면 불일치 0", "45° 문턱 가정은 공유"],
  ["정답을 아는 입력", "수직 원기둥·직육면체 0%p, 60° 원뿔 판정 일치", ""],
  ["유도한 식", "증명 9개 식, 저장소 코드 없이 독립 수치 검산(야코비안 상대오차 1.1×10⁻⁷ 등)", "식의 일치, 물리 검증 아님"],
  ["기존 방식과의 일치", "상수 프로필 = RotBot 고정각(회귀 테스트, 왕복 오차 10⁻¹⁴ 수준)", ""],
  ["코드 전체", "단위·회귀 테스트 230개 통과, 정적 검사 0건", ""],
  ["기계 안전", "자체 사전 검사 + 팀원 가상 프린터(독립 역기구학), 시험 출력 파일 치명 결함 0", "핫엔드 치수·축 부호 실측 전"],
  ["재현성", "같은 입력 → 바이트 단위로 같은 G-code, 퇴적 복원 3회 해시 일치", ""],
  ["해석의 공정성", "판정 기준 사전 등록", ""],
  ["독립성의 한계", "검증 계층 일부가 같은 AI 도구로 작성됨", "완전 독립 아님"],
], { size: 16 }));

// 참고문헌
C.push(H1("■ 참고문헌"));
[
  "[1] Wüthrich, M., Gubser, M., Elspass, W. J., & Jaeger, C. (2021). A novel slicing strategy to print overhangs without support material. Applied Sciences, 11(18), 8760.",
  "[2] Coupek, D., Friedrich, J., Battran, D., & Riedel, O. (2018). Reduction of support structures and building time by optimized path planning algorithms in multi-axis additive manufacturing. Procedia CIRP, 67, 221–226. 【서지 원문 확인 필요】",
  "[3] Zhang, T., Fang, G., Huang, Y., Dutta, N., Lefebvre, S., Kilic, Z. M., & Wang, C. C. L. (2022). S³-Slicer: A general slicing framework for multi-axis 3D printing. ACM Transactions on Graphics, 41(6), 277.",
  "[4] Liu, T., Zhang, T., Chen, Y., Huang, Y., & Wang, C. C. L. (2024). Neural slicer for multi-axis 3D printing. ACM Transactions on Graphics, 43(4), 85.",
  "[5] Slicer4RTN. https://xyzdims.com/3d-printing/slicer4rtn/ (접속일 기입)",
  "[6] CNC Kitchen. ConicalSlicer. https://github.com/CNCKitchen/ConicalSlicer (접속일 기입)",
  "[7] CNC Kitchen. Conical Slicing: A different angle of 3D printing. https://www.cnckitchen.com/blog/conical-slicing-a-different-angle-of-3d-printing (접속일 기입)",
  "[8] Klappe, D. Rep5x. https://github.com/dennisklappe/Rep5x (접속일 기입)",
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
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(process.argv[2] || "report_draft.docx", b); console.log("written; figures:", figNo, "tables:", tabNo); });
