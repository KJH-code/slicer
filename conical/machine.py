"""
machine.py — 기계 프로파일(시작/종료 G-code, 온도)을 G-code 에 주입한다.

왜 필요한가: 이 저장소의 파이프라인은 연구용이라 `G21/G90/M82` 만 내보낸다.
**그 파일로는 실물을 못 뽑는다** — 예열·호밍·프라임·냉각·모터 해제가 없다.
슬라이싱 결과(경로)와 기계 설정(예열·호밍)은 성질이 다르므로, 경로 생성 코드에
기계 상수를 섞지 않고 **파일 하나로 분리**한다.

형식은 INI 다 (`configparser`). 여러 줄 값은 들여쓰기로 잇는다.

    [machine]
    name = Open5x (Prusa 개조)
    nozzle_temp = 215
    bed_temp = 60
    start_gcode =
        M140 S{bed_temp}
        M104 S{nozzle_temp}
        G28
        M190 S{bed_temp}
        M109 S{nozzle_temp}
    end_gcode =
        M104 S0
        M140 S0
        M84

치환은 `{key}` 하나뿐이다 — 프로파일 자신의 키와, 슬라이싱이 정한 값
(`layer_height`, `angle`, `direction`, `mode`, `source_stl`)을 쓸 수 있다.
조건문·수식은 일부러 넣지 않았다: 학생이 읽고 손으로 고칠 수 있어야 한다.

⚠ **이 모듈은 G-code 를 검사하지 않는다.** 프로파일에 적은 대로 그대로 내보낸다.
  틀린 시작 코드는 기계를 상하게 할 수 있다. 첫 사용 전에 반드시 사람이 읽고,
  가능하면 노즐을 띄운 채로 한 번 돌려 볼 것.
"""

import configparser
import math
import re
from dataclasses import dataclass, field

REQUIRED_HINT = ("[machine] 절에 start_gcode / end_gcode 를 적는다. "
                 "예시는 profiles/machine.example.ini 참고.")


@dataclass
class MachineProfile:
    """기계 하나의 시작/종료 G-code 와 치환에 쓸 값들."""

    name: str = "unnamed"
    start_gcode: str = ""
    end_gcode: str = ""
    values: dict = field(default_factory=dict)

    @classmethod
    def from_file(cls, path):
        # ⚠ `;` 를 주석 접두사에서 **뺀다.** 기본값은 ('#', ';') 인데 G-code 의
        #   주석이 바로 `;` 라, 그대로 두면 start_gcode/end_gcode 안의 주석 줄이
        #   **조용히 사라진다.** 실제로 템플릿의 `; TODO(5축): U/V 축 호밍 …` 이
        #   출력 파일에서 없어지고 있었다(2026-09-24 발견). 기계로 나가는 파일에서
        #   사람이 적은 줄이 말없이 빠지는 것은 이 저장소가 막기로 한 종류의 일이다.
        #   → INI 자체의 주석은 `#` 로 쓴다 (machine.example.ini 가 그렇게 돼 있다).
        cp = configparser.ConfigParser(comment_prefixes=("#",))
        # 키 이름의 대소문자를 보존한다 (치환 키와 1:1 로 맞추려고).
        cp.optionxform = str
        with open(path, encoding="utf-8") as fh:
            cp.read_file(fh)
        if not cp.has_section("machine"):
            raise ValueError(f"{path}: [machine] 절이 없다. {REQUIRED_HINT}")
        sec = dict(cp["machine"])
        start = sec.pop("start_gcode", "")
        end = sec.pop("end_gcode", "")
        name = sec.pop("name", "unnamed")
        if not start.strip() and not end.strip():
            raise ValueError(f"{path}: start_gcode·end_gcode 가 둘 다 비었다. "
                             + REQUIRED_HINT)
        return cls(name=name, start_gcode=start, end_gcode=end, values=sec)

    def _render(self, text, context):
        """`{key}` 치환. 프로파일 값이 먼저, 슬라이싱 값이 그 뒤에 덮어쓴다."""
        table = dict(self.values)
        table.update(context)
        lines = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                lines.append(line.format(**table))
            except KeyError as e:
                raise ValueError(
                    f"기계 프로파일 '{self.name}' 의 줄 `{line}` 에 있는 "
                    f"{e} 를 채울 값이 없다. 프로파일에 그 키를 적거나 줄을 고쳐라."
                ) from None
        return lines

    def start_items(self, context=None):
        """시작 G-code 를 `gcode.write` 가 받는 ('raw', str) 목록으로."""
        ctx = context or {}
        out = [("raw", f"; --- machine start: {self.name} ---")]
        out += [("raw", ln) for ln in self._render(self.start_gcode, ctx)]
        out.append(("raw", "; --- machine start end ---"))
        return out

    def end_items(self, context=None):
        ctx = context or {}
        out = [("raw", f"; --- machine end: {self.name} ---")]
        out += [("raw", ln) for ln in self._render(self.end_gcode, ctx)]
        return out


# ─────────────────────────────────────────────────────────────
# 시작 G-code 의 압출(프라임 선)이 부품 자리와 겹치는지
# ─────────────────────────────────────────────────────────────
_WORD = re.compile(r"([GXYEgxye])\s*(-?\d+(?:\.\d*)?|-?\.\d+)")


def _seg_dist_to_origin(x0, y0, x1, y1):
    """선분 (x0,y0)-(x1,y1) 과 원점 사이 최소 거리."""
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, -(x0 * dx + y0 * dy) / L2))
    return math.hypot(x0 + t * dx, y0 + t * dy)


def check_start_extrusion(start_items, part_radius, margin=3.0,
                          printable_radius=None):
    """시작 G-code 안의 **압출 이동**(프라임 선 등)이 부품 자리와 겹치는지 본다.

    왜: 이 파이프라인은 부품을 **XY 원점(= 원뿔 축)** 에 놓는다(`center_on_axis`).
    템플릿의 프라임 선이 오래 (5,5)→(100,5) 였는데, 이는 부품 한가운데를 지나간다 —
    첫 층이 프라임 선 위에 올라간다. REP5X 에서는 끝점이 PRINTABLE_RADIUS 100 도
    넘었다(반경 100.1). 2026-10-16 `rep5x_check` 로 새 모델을 돌리다 발견.

    part_radius: 부품 경로의 원점 기준 최대 반경 (mm)
    margin: 부품 둘레에 띄울 여유 (mm)
    printable_radius: 주면 압출 이동이 그 반경 안인지도 본다 (REP5X 100)

    반환: [(심각도, 메시지)]. 위치를 못 따라가는 경우(G91 상대 좌표)는 "정보" 로
    알리고 그 뒤를 보지 않는다 — 모르면서 통과로 치지 않는다.
    """
    findings = []
    x = y = None
    e = 0.0
    rel = False
    ox = oy = 0.0           # G92 X/Y 로 옮긴 원점 (기계좌표 = G-code 좌표 + 오프셋)
    segs = []               # (기계좌표 시작, 끝, 원문)
    for kind, line in start_items:
        if kind != "raw" or not isinstance(line, str):
            continue
        code = line.split(";", 1)[0].strip().upper()
        if not code:
            continue
        words = dict(_WORD.findall(code))
        g = words.get("G")
        if g == "90":
            rel = False
            continue
        if g == "91":
            rel = True
            continue
        if g == "92":
            if "E" in words:
                e = float(words["E"])
            # 부품 원점 이동 (`part_origin` → `G92 X0 Y0`): 지금 자리를 새 값으로 부른다
            if "X" in words:
                if x is None:
                    findings.append(("정보", f"`{line.strip()}` 앞에서 X 위치를 모른다 — "
                                            f"원점 이동을 따라갈 수 없다"))
                    return findings
                ox, x = ox + x - float(words["X"]), float(words["X"])
            if "Y" in words:
                if y is None:
                    findings.append(("정보", f"`{line.strip()}` 앞에서 Y 위치를 모른다 — "
                                            f"원점 이동을 따라갈 수 없다"))
                    return findings
                oy, y = oy + y - float(words["Y"]), float(words["Y"])
            continue
        if g not in ("0", "1") or rel:
            if g in ("0", "1") and rel and ("X" in words or "Y" in words):
                findings.append(("정보", f"시작 G-code 가 상대 좌표(G91)로 XY 를 움직여 "
                                        f"위치를 못 따라간다: `{line.strip()}` — "
                                        f"사람이 확인할 것"))
                return findings
            continue
        nx = float(words["X"]) if "X" in words else x
        ny = float(words["Y"]) if "Y" in words else y
        ne = float(words["E"]) if "E" in words else e
        if ne > e + 1e-9 and None not in (x, y, nx, ny):
            segs.append(((x + ox, y + oy), (nx + ox, ny + oy), line.strip()))
        x, y, e = nx, ny, ne

    # 부품은 **마지막 원점**(경로가 나오는 좌표계의 0,0) 둘레에 놓인다.
    for (ax, ay), (bx, by), src in segs:
        d = _seg_dist_to_origin(ax - ox, ay - oy, bx - ox, by - oy)
        if d < part_radius + margin:
            findings.append(("치명", f"시작 G-code 의 압출 `{src}` 이 "
                                    f"부품 자리(원점에서 반경 {part_radius:.1f}mm"
                                    f" + 여유 {margin:g}mm)를 지난다 "
                                    f"(원점 거리 {d:.1f}mm). 첫 층이 그 위에 올라간다"))
        if printable_radius is not None:
            far = max(math.hypot(ax, ay), math.hypot(bx, by))
            if far > printable_radius + 1e-9:
                findings.append(("치명", f"시작 G-code 의 압출 `{src}` 이 "
                                        f"출력 가능 반경 {printable_radius:g}mm 를 "
                                        f"넘는다 (기계좌표 반경 {far:.1f}mm)"))
    return findings
