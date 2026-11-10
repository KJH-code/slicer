# -*- coding: utf-8 -*-
"""R&E 보고서 양식(HWPX)에 초안을 채운다. 수식은 LaTeX → 한글 네이티브 수식(<hp:equation>).

usage: python -I build.py <template.hwpx> <figures_dir> <out.hwpx>
"""
import copy
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import content as C  # noqa: E402

from hwpx.document import HwpxDocument  # noqa: E402
from hwpx.equation.authoring import latex_to_eqedit  # noqa: E402
from hwpx.oxml.paragraph import HwpxOxmlParagraph  # noqa: E402

TEMPLATE, FIGDIR, OUT = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
MM = 283.465  # HWPUNIT per mm
BODY_W = 45356  # 210mm - 2*25mm 여백 (template pagePr)

# ---- 템플릿에서 확인한 서식 id ----
PP_BODY, ST_BODY, CP_BODY = "6", "1", "3"      # 본문 (함초롬바탕 10pt, 양쪽, 160%)
PP_HEAD, ST_HEAD = "0", "0"
CP_H1, CP_H2 = "46", "51"                       # 12pt 굵게 / 11pt 굵게
PP_CENTER = "61"                                # 가운데 (그림 문단)
PP_FIGCAP, CP_FIGCAP = "24", "27"               # 그림 캡션 (가운데, 9pt)
PP_TBLCAP, CP_TBLCAP = "39", "69"               # 표 캡션 (왼쪽, 휴먼고딕 9pt)
PP_CELL, PP_CELL_C, CP_CELL = "7", "49", "71"   # 표 셀 (9pt)
TBL_BF, CELL_BF, CELL_BF_BODY = "6", "30", "32"                     # 템플릿 예시 표의 테두리
PP_REF, CP_REF = "6", "60"                      # 참고문헌
CP_SUMMARY = "93"                               # 요약문 셀 본문
EQ_BASE = 1000                                  # 수식 기준 크기 10pt
EQ_BASE_SMALL = 900

doc = HwpxDocument.open(TEMPLATE)
section = doc.sections[0]
root = section.element


def top_paragraphs():
    return [e for e in root if e.tag == f"{HP}p"]


# ---------------------------------------------------------------- LaTeX → EqEdit
EQ_LOG = []


def to_eqedit(latex):
    """검증된 토큰셋만 지원하는 변환기에 맞춰 간격·별표 등만 감싼 뒤 변환한다."""
    s = latex
    s = re.sub(r"\\mathrm\{([^}]*?)\\ ([^}]*)\}", r"\\mathrm{\1}\\ \\mathrm{\2}", s)
    s = s.replace("\\mathrm{atan2}", " QQATANQ ")
    s = s.replace("\\qquad", " QQQUADQ QQQUADQ ").replace("\\quad", " QQQUADQ ")
    s = s.replace("\\,", " QQTHINQ ").replace("\\ ", " QQSPACEQ ")
    s = s.replace("\\Leftrightarrow", " QQLRARROWQ ")
    s = s.replace("^*", "^{\\ast}").replace("*", "\\ast")
    s = s.replace("\\%", " QQPCTQ ")
    script = latex_to_eqedit(s)
    script = (script.replace("QQQUADQ", "~~").replace("QQTHINQ", "`").replace("QQSPACEQ", "~")
              .replace("QQLRARROWQ", "LRARROW").replace("QQPCTQ", "%").replace("QQATANQ", '"atan2"'))
    EQ_LOG.append((latex, script))
    return script


# ---------------------------------------------------------------- 문단 생성
def new_p(pp=PP_BODY, st=ST_BODY):
    attrs = {"id": "0", "paraPrIDRef": str(pp), "styleIDRef": str(st), "pageBreak": "0",
             "columnBreak": "0", "merged": "0"}
    el = root.makeelement(f"{HP}p", attrs)
    return el, HwpxOxmlParagraph(el, section)


TOKEN = re.compile(r"(\$[^$]+\$|\*\*[^*]+\*\*|【[^】]*】)")


def add_rich(para, text, cp=CP_BODY, eq_base=EQ_BASE, bold_all=False):
    """$수식$, **굵게**, 【보류】 마크업을 런·수식으로 만든다."""
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith("$"):
            script = to_eqedit(part[1:-1])
            para.add_equation(script, base_unit=eq_base, char_pr_id_ref=cp)
        elif part.startswith("**"):
            para.add_run(part[2:-2], char_pr_id_ref=cp, bold=True)
        elif part.startswith("【"):
            para.add_run(part, char_pr_id_ref=cp, bold=True, highlight="#FFFF00")
        else:
            para.add_run(part, char_pr_id_ref=cp, bold=bold_all) if bold_all else para.add_run(part, char_pr_id_ref=cp)


# ---------------------------------------------------------------- 표
def make_table(header, rows, weights, *, cell_cp=CP_CELL, width=BODY_W - 1200, border=(TBL_BF, CELL_BF),
               center_cols=None, header_bold=True):
    el, para = new_p(PP_CENTER, ST_BODY)
    nrows = len(rows) + (1 if header else 0)
    ncols = len(weights)
    tbl = para.add_table(nrows, ncols, width=width, border_fill_id_ref=border[0])
    t = tbl.element
    t.set("borderFillIDRef", border[0])
    tot = sum(weights)
    widths = [int(width * w / tot) for w in weights]
    widths[-1] = width - sum(widths[:-1])
    all_rows = ([header] if header else []) + rows
    for r_i, tr in enumerate(t.findall(f"{HP}tr")):
        for c_i, tc in enumerate(tr.findall(f"{HP}tc")):
            tc.set("borderFillIDRef", border[1] if (header and r_i == 0) else (CELL_BF_BODY if border[1] == CELL_BF else border[1]))
            tc.find(f"{HP}cellSz").set("width", str(widths[c_i]))
            sub = tc.find(f"{HP}subList")
            sub.set("vertAlign", "CENTER")
            for p in list(sub.findall(f"{HP}p")):
                sub.remove(p)
            centered = (header and r_i == 0) or (center_cols and c_i in center_cols)
            pel = sub.makeelement(f"{HP}p", {"id": "0", "paraPrIDRef": PP_CELL_C if centered else PP_CELL,
                                             "styleIDRef": "0", "pageBreak": "0", "columnBreak": "0", "merged": "0"})
            sub.append(pel)
            cp = HwpxOxmlParagraph(pel, section)
            add_rich(cp, all_rows[r_i][c_i] or " ", cp=cell_cp, eq_base=EQ_BASE_SMALL,
                     bold_all=bool(header and r_i == 0 and header_bold))
    sz = t.find(f"{HP}sz")
    if sz is not None:
        sz.set("width", str(width))
    return el


# ---------------------------------------------------------------- 그림
def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def add_png(para, path, width_mm):
    w_px, h_px = png_size(path)
    w = int(width_mm * MM)
    h = int(w * h_px / w_px)
    item = doc.add_image(Path(path).read_bytes(), "png")
    para.add_picture(str(item), width=w, height=h, treat_as_char=True)


FIG_NO = [0]


def fig_caption(cap):
    FIG_NO[0] += 1
    el, p = new_p(PP_FIGCAP, ST_BODY)
    p.add_run(f"[Fig. {FIG_NO[0]}] ", char_pr_id_ref=CP_FIGCAP, bold=True)
    add_rich(p, cap, cp=CP_FIGCAP, eq_base=EQ_BASE_SMALL)
    return el


def placeholder_box(text, width_mm=120, height_mm=35):
    el = make_table(None, [[text]], [1], width=int(width_mm * MM), center_cols={0}, border=(TBL_BF, "35"))
    for tc in el.iter(f"{HP}tc"):
        tc.find(f"{HP}cellSz").set("height", str(int(height_mm * MM)))
    return el


MISSING_FIGS = []


def figure_blocks(slug, cap, width_mm):
    path = FIGDIR / f"{slug}.png"
    if path.exists():
        el, p = new_p(PP_CENTER, ST_BODY)
        add_png(p, path, width_mm)
        out = [el]
    else:
        MISSING_FIGS.append(slug)
        out = [placeholder_box(f"【그림 대기: {slug}.png】", width_mm, 30)]
    out.append(fig_caption(cap))
    return out


def pair_blocks(a, b, width_mm=78):
    """반폭 그림 두 개를 테두리 없는 1×2 표에 나란히 (각자 캡션)."""
    el, para = new_p(PP_CENTER, ST_BODY)
    width = BODY_W - 400
    tbl = para.add_table(1, 2, width=width, border_fill_id_ref=NOBORDER)
    t = tbl.element
    t.set("borderFillIDRef", NOBORDER)
    for c_i, (tc, (slug, cap)) in enumerate(zip(t.iter(f"{HP}tc"), (a, b), strict=True)):
        tc.set("borderFillIDRef", NOBORDER)
        tc.find(f"{HP}cellSz").set("width", str(width // 2))
        sub = tc.find(f"{HP}subList")
        for p in list(sub.findall(f"{HP}p")):
            sub.remove(p)
        pic_el = sub.makeelement(f"{HP}p", {"id": "0", "paraPrIDRef": PP_CENTER, "styleIDRef": ST_BODY,
                                            "pageBreak": "0", "columnBreak": "0", "merged": "0"})
        sub.append(pic_el)
        pp = HwpxOxmlParagraph(pic_el, section)
        path = FIGDIR / f"{slug}.png"
        if path.exists():
            add_png(pp, path, width_mm)
        else:
            MISSING_FIGS.append(slug)
            pp.add_run(f"【그림 대기: {slug}.png】", char_pr_id_ref=CP_FIGCAP, bold=True, highlight="#FFFF00")
        sub.append(fig_caption(cap))
    return [el]


def find_noborder():
    hh = "{http://www.hancom.co.kr/hwpml/2011/head}"
    header = doc._root.headers[0].element
    for bf in header.iter(f"{hh}borderFill"):
        sides = [bf.find(f"{hh}{s}Border") for s in ("left", "right", "top", "bottom")]
        fill = bf.find(f"{hh}fillBrush")
        if all(s is not None and s.get("type") == "NONE" for s in sides) and fill is None:
            return bf.get("id")
    raise SystemExit("no borderless borderFill in template")


NOBORDER = find_noborder()


# ---------------------------------------------------------------- 본문 블록 → 문단 요소
def render_blocks(blocks):
    out = []
    for b in blocks:
        kind = b[0]
        if kind == "h1":
            el, p = new_p(PP_HEAD, ST_HEAD)
            p.add_run(b[1], char_pr_id_ref=CP_H1)
            out.append(el)
        elif kind == "h2":
            el, p = new_p(PP_HEAD, ST_HEAD)
            add_rich(p, "  " + b[1], cp=CP_H2)
            out.append(el)
        elif kind == "p":
            el, p = new_p()
            add_rich(p, b[1])
            out.append(el)
        elif kind == "bul":
            el, p = new_p()
            add_rich(p, " • " + b[1])
            out.append(el)
        elif kind == "eq":
            el, p = new_p(PP_CENTER, ST_BODY)
            p.add_equation(to_eqedit(b[1]), base_unit=EQ_BASE, char_pr_id_ref=CP_BODY)
            p.add_run(f"      ({b[2]})", char_pr_id_ref=CP_BODY)
            out.append(el)
        elif kind == "code":
            lines, src = b[1], b[2]
            el = make_table(None, [["\n".join(lines)]], [1], width=BODY_W - 1200, border=(TBL_BF, "38"))
            # 셀 안을 줄마다 문단으로, 고정폭 글꼴
            sub = next(el.iter(f"{HP}subList"))
            for p in list(sub.findall(f"{HP}p")):
                sub.remove(p)
            for ln in lines + [src]:
                pel = sub.makeelement(f"{HP}p", {"id": "0", "paraPrIDRef": PP_CELL, "styleIDRef": "0",
                                                 "pageBreak": "0", "columnBreak": "0", "merged": "0"})
                sub.append(pel)
                cp = HwpxOxmlParagraph(pel, section)
                if ln is src:
                    cp.add_run(src, char_pr_id_ref=CP_CELL, italic=True, size=8)
                else:
                    cp.add_run(ln, char_pr_id_ref=CP_CELL, font="D2Coding", size=8)
            out.append(el)
        elif kind == "table":
            _, cap, header, rows, weights, note = b
            el, p = new_p(PP_TBLCAP, ST_BODY)
            add_rich(p, cap, cp=CP_TBLCAP)
            out.append(el)
            out.append(make_table(header, rows, weights, center_cols=set(range(1, len(weights)))
                                  if len(weights) >= 4 else None))
            if note:
                el, p = new_p(PP_BODY, ST_BODY)
                add_rich(p, note, cp=CP_FIGCAP, eq_base=EQ_BASE_SMALL)
                out.append(el)
        elif kind == "fig":
            out += figure_blocks(b[1], b[2], b[3])
        elif kind == "pair":
            out += pair_blocks(b[1], b[2])
        elif kind == "box":
            out.append(placeholder_box(b[1], 120, 30))
        elif kind == "figcap":
            out.append(fig_caption(b[1]))
        else:
            raise ValueError(kind)
    return out


# ---------------------------------------------------------------- 셀 채우기
def cell_of(tbl_el, row, col):
    for tc in tbl_el.iter(f"{HP}tc"):
        a = tc.find(f"{HP}cellAddr")
        if a.get("rowAddr") == str(row) and a.get("colAddr") == str(col):
            return tc
    raise KeyError((row, col))


def fill_cell(tc, paragraphs, *, cp, keep_from=None, pp=None, valign="TOP", prefix_paras=None):
    """셀 문단을 새 문단들로 교체. keep_from: 남길 기존 문단 시작 인덱스(그 뒤는 보존)."""
    sub = tc.find(f"{HP}subList")
    old = sub.findall(f"{HP}p")
    proto = old[0]
    keep = old[keep_from:] if keep_from is not None else []
    for p in old:
        sub.remove(p)
    sub.set("vertAlign", valign)
    for text in paragraphs:
        pel = sub.makeelement(f"{HP}p", {"id": "0", "paraPrIDRef": pp or proto.get("paraPrIDRef"),
                                         "styleIDRef": proto.get("styleIDRef"), "pageBreak": "0",
                                         "columnBreak": "0", "merged": "0"})
        sub.append(pel)
        add_rich(HwpxOxmlParagraph(pel, section), text, cp=cp)
    for p in keep:
        sub.append(p)


def set_label_text(tc, text, cp=None):
    """'(국문)' 같은 라벨 셀 뒤에 제목을 붙인다."""
    p = tc.find(f"{HP}subList").find(f"{HP}p")
    para = HwpxOxmlParagraph(p, section)
    run = p.find(f"{HP}run")
    para.add_run(" " + text, char_pr_id_ref=cp or run.get("charPrIDRef"))


paras = top_paragraphs()
anchor_p = {i: paras[i] for i in range(len(paras))}

# ---- 표지(P1): 연구과제명 국문/영문
cover = anchor_p[1].find(f".//{HP}tbl")
set_label_text(cell_of(cover, 3, 1), C.TITLE_KO, cp=CP_SUMMARY)
set_label_text(cell_of(cover, 4, 1), C.TITLE_EN, cp=CP_SUMMARY)

# ---- 1. 연구결과 요약문(P3)
summ = anchor_p[3].find(f".//{HP}tbl")
PP_SUMCELL = "7"
fill_cell(cell_of(summ, 0, 1), [C.TITLE_KO], cp=CP_SUMMARY, pp=PP_SUMCELL, valign="CENTER")
fill_cell(cell_of(summ, 1, 1), C.SUMMARY["need"], cp=CP_SUMMARY, pp=PP_SUMCELL)
fill_cell(cell_of(summ, 2, 1), C.SUMMARY["result"], cp=CP_SUMMARY, pp=PP_SUMCELL)
fill_cell(cell_of(summ, 3, 1), C.SUMMARY["future"], cp=CP_SUMMARY, pp=PP_SUMCELL)
fill_cell(cell_of(summ, 4, 1), C.SUMMARY["keyword"], cp=CP_SUMMARY, pp=PP_SUMCELL, valign="CENTER")

# ---- 2. 과제 수행 과정(P6 첫 표): 문제해결 과정(1,1) 앞 두 안내 문단 교체(생성형 AI 안내·표는 보존), 학습(6,1)
proc = anchor_p[6].find(f".//{HP}tbl")
fill_cell(cell_of(proc, 1, 1), C.PROCESS_SOLVE, cp=CP_SUMMARY, pp=PP_SUMCELL, keep_from=2)
fill_cell(cell_of(proc, 6, 1), C.PROCESS_LEARN, cp=CP_SUMMARY, pp=PP_SUMCELL)

# ---- 3. 연구보고서 제목 표(P12)
head = anchor_p[12].find(f".//{HP}tbl")
# (0,0): 첫 run 의 'R&E 과제명(국문)' 만 제목으로 교체, 저자·학교 줄은 템플릿 그대로
for t in cell_of(head, 0, 0).iter(f"{HP}t"):
    if t.text and "R&E 과제명(국문)" in t.text:
        t.text = t.text.replace("R&E 과제명(국문)", C.TITLE_KO)
for t in cell_of(head, 1, 0).iter(f"{HP}t"):
    if t.text and "Title(English)" in t.text:
        t.text = t.text.replace("Title(English)", C.TITLE_EN)
abs_tc = cell_of(head, 3, 0)
abs_cp = abs_tc.find(f".//{HP}run").get("charPrIDRef")
fill_cell(abs_tc, [C.ABSTRACT, "주제어: " + C.KEYWORDS], cp=abs_cp)

# ---- 본문: P14(Ⅰ. 서론) ~ P55(참고문헌 예시 [2]) 교체
start, stop = 14, 55
body_els = render_blocks(C.B)
# 참고문헌
ref_head, rp = new_p(PP_HEAD, ST_HEAD)
rp.add_run("■ 참고문헌", char_pr_id_ref=CP_H1)
ref_els = [ref_head]
for r in C.REFS:
    el, p = new_p(PP_REF, "0")
    add_rich(p, r, cp=CP_REF)
    ref_els.append(el)
new_els = []
for el in body_els:
    new_els.append(el)
# 큰 장 사이 빈 줄
spaced = []
for el in new_els:
    is_h1 = any(r.get("charPrIDRef") == CP_H1 for r in el.findall(f"{HP}run"))
    if is_h1 and spaced:
        sp, _ = new_p()
        spaced.append(sp)
    spaced.append(el)
sp, _ = new_p()
spaced.append(sp)
spaced += ref_els

insert_at = list(root).index(anchor_p[start])
for i in range(start, stop + 1):
    root.remove(anchor_p[i])
for off, el in enumerate(spaced):
    root.insert(insert_at + off, el)
section.mark_dirty()

doc.save_to_path(OUT)
print("saved", OUT)
print("figures:", FIG_NO[0], "missing:", MISSING_FIGS)
print("equations:", len(EQ_LOG))
Path(OUT).with_suffix(".equations.tsv").write_text(
    "\n".join(f"{a}\t{b}" for a, b in EQ_LOG), encoding="utf-8")
