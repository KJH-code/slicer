/* global ResearchSTLViewer */

/**
 * 9쪽 부품 탐색기.
 * 왼쪽 목록에서 부품을 고르면 오른쪽 3D 뷰어와 설명이 함께 바뀐다.
 * 3D 모델은 Rep5x 저장소의 3MF를 STL로 변환해 assets/models/rep5x/ 에 둔 것이다.
 */
const REP5X_PARTS = Object.freeze({
  "b-arm": {
    title: "B암 (B_arm)",
    version: "v1.1.0 · 공용",
    dims: "48.0 × 91.8 × 51.4 mm · 10,268 면",
    role: "노즐을 기울이는 B축의 몸체. 슬립링을 지난 배선과 보우덴 튜브가 이 팔의 가운데를 통과한다.",
    points: [
      "608 베어링 2개를 압입해 B축 회전을 받는다",
      "마이크로스위치를 안쪽에 넣고 위치를 잡은 뒤 핫글루로 고정한다 — B축 원점",
      "v1.1.0에서 슬립링 케이블 구멍에 <b>절개선</b>이 생겼다. 핫엔드·스테퍼 배선을 뽑지 않고도 팔을 떼어낼 수 있다",
      "캐리지 마운트에 M3×10 볼트 2개로 붙는다"
    ],
    photo: "assets/images/rep5x/b-arm-bearings-microswitch.jpg",
    photoCaption: "베어링과 마이크로스위치를 넣은 B암"
  },
  "c-driven-pulley": {
    title: "C축 종동 풀리 (C-driven-pulley)",
    version: "v1.1.0 · 공용",
    dims: "41.0 × 41.0 × 31.4 mm · 40,812 면",
    role: "헤드 전체를 Z축 둘레로 돌리는 요(yaw) 축의 큰 풀리. 가운데가 뚫려 있어 슬립링 배선이 회전 중심을 지난다.",
    points: [
      "캐리지 마운트의 61804 베어링 위에 얹혀 돈다",
      "GT2 20T 풀리를 단 NEMA17이 벨트(188 mm)로 이 풀리를 돌린다",
      "배선을 <b>회전 중심</b>으로 통과시키는 것이 연속 회전의 조건이다",
      "프린터에 캐리지 마운트를 먼저 붙인 뒤에 끼운다 — 이 풀리가 마운트 나사를 가린다"
    ],
    photo: "assets/images/rep5x/carriage-mount-front-view.jpg",
    photoCaption: "캐리지 마운트에 장착된 C축 종동 풀리"
  },
  "b-driven-pulley": {
    title: "B축 종동 풀리 (b-driven-pulley)",
    version: "v1.1.0 · 공용",
    dims: "41.0 × 41.0 × 25.4 mm · 23,124 면",
    role: "B암을 기울이는 틸트 축의 풀리. 엔드스톱을 때리는 트리거 볼트가 여기에 박힌다.",
    points: [
      "M3 열간 인서트 2개를 넣고 그중 하나에 M3×10 볼트를 박는다",
      "볼트를 1~2 mm 튀어나오게 조절해 B암의 마이크로스위치를 누르게 한다 — 이것이 B축 원점",
      "v1.1.0에서 팬 마운트 구멍이 <b>삭제</b>됐다. 핫엔드 팬을 핫엔드에 직접 달게 바뀌었기 때문",
      "GT2 벨트(158 mm)로 B축 스테퍼와 연결된다"
    ],
    photo: "assets/images/rep5x/b-driven-pulley-heat-inserts.jpg",
    photoCaption: "열간 인서트와 엔드스톱 트리거 볼트를 넣은 상태"
  },
  "slip-ring-holder": {
    title: "슬립링 홀더 (slip-ring-holder)",
    version: "v1.1.1 · 공용",
    dims: "3.8 × 15.8 × 14.0 mm · 2,840 면",
    role: "12채널 슬립링(MST-005-12A)을 캐리지 마운트에 잡아 주는 작은 브래킷. 이 부품이 연속 회전을 가능하게 한다.",
    points: [
      "슬립링은 4핀 1개(B축 스테퍼) + 2핀 4개(히터·서미스터·팬·B 엔드스톱)를 통과시킨다",
      "채널당 2 A, 내경 5 mm — 배선이 꼬이지 않고 <b>C축이 무한 회전</b>할 수 있다",
      "v1.1.1에서 전체 길이를 줄여 캐리지 마운트와의 간섭을 없앴다",
      "v1.0.0 캐리지 마운트와는 호환되지 않는다 (v1.1.x 전용)"
    ],
    photo: "assets/images/rep5x/slip-ring-jst-connectors.jpg",
    photoCaption: "JST 커넥터로 배선을 정리한 슬립링"
  },
  "hotend-spacer": {
    title: "핫엔드 스페이서 (hotend-spacer)",
    version: "v1.0.0 · 공용",
    dims: "20.0 × 4.0 × 6.0 mm · 692 면",
    role: "핫엔드를 B암에 물릴 때 두께를 맞추는 얇은 스페이서.",
    points: [
      "핫엔드 종류에 따라 체결면 두께가 달라지는 것을 흡수한다",
      "노즐 끝과 B축 회전 중심 사이 거리(LB)를 바꾸므로, 넣고 빼면 <b>캘리브레이션을 다시</b> 해야 한다",
      "펌웨어 기본값 LB = 47.9 mm 는 이 구성 기준이다"
    ],
    photo: "assets/images/rep5x/hotend-b-arm-assembly.jpg",
    photoCaption: "B암에 장착된 핫엔드 조립체"
  },
  "spacer-3mm": {
    title: "3 mm 스페이서 (spacer-3mm)",
    version: "v1.0.0 · 공용",
    dims: "21.0 × 7.0 × 3.0 mm · 684 면",
    role: "체결부 간격을 3 mm 띄우는 범용 스페이서.",
    points: [
      "볼트 길이와 실제 체결 두께의 차이를 메운다",
      "가장 단순한 부품이지만 없으면 스테퍼 체결부가 변형된다",
      "PETG 권장 — 공용 부품 전부 같은 재료로 출력한다"
    ],
    photo: "assets/images/rep5x/carriage-mount-underside.jpg",
    photoCaption: "베어링과 체결부가 보이는 캐리지 마운트 아랫면"
  },
  "e3v3se-carriage-mount": {
    title: "캐리지 마운트 (carriage-mount)",
    version: "v1.1.1 · Ender 3 V3 SE 전용",
    dims: "119.9 × 56.5 × 58.0 mm · 16,534 면",
    role: "프린터의 X 캐리지에 붙어 5축 헤드 전체를 지탱한다. <b>기종 의존이 이 부품 하나에 모여 있다</b>.",
    points: [
      "순정 핫엔드를 떼고 원래 나사 구멍에 그대로 체결한다",
      "61804 얇은 베어링 2개가 들어가 C축 회전을 받는다",
      "C축 스테퍼(M3×6 4개)와 광학 원점 센서가 여기에 붙는다",
      "v1.1.1에서 요 스테퍼 볼트 구멍을 M3 와셔(외경 7 mm)에 맞춰 넓히고, 장력 조절 구멍 간격을 스테퍼 구멍과 맞췄다 — 이전 버전은 체결부가 변형됐다"
    ],
    photo: "assets/images/rep5x/carriage-mount-installed.jpg",
    photoCaption: "X 캐리지에 장착된 캐리지 마운트"
  },
  "e3v3se-extruder-mount": {
    title: "외부 압출기 마운트 (extruder-mount)",
    version: "v1.1.0 · Ender 3 V3 SE 전용",
    dims: "46.5 × 97.5 × 65.0 mm · 4,412 면",
    role: "V3 SE의 직결(direct drive) 압출기를 프레임 쪽 <b>보우덴</b> 방식으로 옮기기 위한 마운트.",
    points: [
      "헤드가 회전하므로 압출기를 헤드에서 떼어내야 한다 — 질량과 회전 반경이 줄어든다",
      "PTFE 튜브(외경 4 / 내경 2 mm, 약 500 mm)로 핫엔드와 연결한다",
      "순정 핫엔드는 보우덴 고정 구조가 없어 교체하거나 개조해야 한다",
      "압출량 캘리브레이션(E 스텝)을 반드시 다시 한다"
    ],
    photo: "assets/images/rep5x/extruder-mount-assembled.jpg",
    photoCaption: "조립된 외부 보우덴 압출기 마운트"
  },
  "e3v3se-x-endstop": {
    title: "X 엔드스톱 마운트 (x-endstop)",
    version: "v1.1.0 · Ender 3 V3 SE 전용",
    dims: "27.0 × 25.5 × 7.6 mm · 6,538 면",
    role: "X축 원점 스위치를 새 위치에 다는 브래킷.",
    points: [
      "순정 X 엔드스톱은 <b>프린트 헤드에 붙어 있어</b> 헤드를 통째로 바꾸면 쓸 수 없다",
      "마이크로스위치를 프레임 쪽으로 옮겨 원점을 다시 정의한다",
      "원점 위치가 바뀌므로 펌웨어의 홈 오프셋을 함께 수정한다"
    ],
    photo: "assets/images/rep5x/x-endstop-assembled.jpg",
    photoCaption: "조립된 X 엔드스톱 마운트"
  },
  "e3v3se-z-endstop": {
    title: "Z 엔드스톱 마운트 (z-endstop)",
    version: "v1.1.0 · Ender 3 V3 SE 전용",
    dims: "21.0 × 22.0 × 19.0 mm · 1,442 면",
    role: "X 갠트리에 Z축 원점 스위치를 다는 브래킷.",
    points: [
      "순정 CR Touch Z 프로브는 헤드에 붙어 있어 5축 헤드와 함께 쓸 수 없다",
      "기계식 스위치로 Z 원점을 대신한다 — 자동 베드 레벨링을 포기하는 대가",
      "노즐 끝이 회전으로 움직이므로 Z 원점은 <b>IK를 끈 상태(G49)</b>에서 잡는다"
    ],
    photo: "assets/images/rep5x/z-endstop-assembled.jpg",
    photoCaption: "조립된 Z 엔드스톱 마운트"
  }
});

class Rep5xPartsExplorer {
  constructor() {
    this.viewer = null;
    this.currentId = "b-arm";
    this.loadedId = null;
    this.ui = {};
  }

  initialize() {
    const container = document.getElementById("part-viewer");
    if (!container) return;

    this.ui = {
      buttons: Array.from(document.querySelectorAll(".parts-list [data-part]")),
      expected: document.getElementById("part-expected-name"),
      title: document.getElementById("part-title"),
      version: document.getElementById("part-version"),
      role: document.getElementById("part-role"),
      points: document.getElementById("part-points"),
      dims: document.getElementById("part-dims"),
      photo: document.getElementById("part-photo-img"),
      photoCaption: document.getElementById("part-photo-cap"),
      source: document.getElementById("part-source"),
      reset: document.getElementById("part-camera-reset"),
      reload: document.getElementById("part-reload")
    };

    if (typeof ResearchSTLViewer === "function") {
      this.viewer = new ResearchSTLViewer(container);
      this.viewer.initialize();
    }

    this.ui.buttons.forEach((button) => {
      button.addEventListener("click", () => this.select(button.dataset.part));
    });
    this.ui.reset?.addEventListener("click", () => this.viewer?.resetCamera());
    this.ui.reload?.addEventListener("click", () => {
      this.loadedId = null;
      this.loadModel();
    });

    document.addEventListener("presentation:slidechange", (event) => {
      const active = event.detail.slideId === "slide-9";
      this.viewer?.setActive(active);
      if (active) this.loadModel();
    });
    window.addEventListener("pagehide", () => this.viewer?.dispose(), { once: true });

    this.select(this.currentId, { skipLoad: true });
    if (document.querySelector("#slide-9.is-active, #slide-9.present")) {
      this.viewer?.setActive(true);
      this.loadModel();
    }
  }

  select(id, options = {}) {
    const part = REP5X_PARTS[id];
    if (!part) return;
    this.currentId = id;

    this.ui.buttons.forEach((button) => {
      button.classList.toggle("active", button.dataset.part === id);
      button.setAttribute("aria-selected", button.dataset.part === id ? "true" : "false");
    });

    if (this.ui.title) this.ui.title.textContent = part.title;
    if (this.ui.version) this.ui.version.textContent = part.version;
    if (this.ui.role) this.ui.role.innerHTML = part.role;
    if (this.ui.dims) this.ui.dims.textContent = part.dims;
    if (this.ui.expected) this.ui.expected.textContent = `${id}.stl`;

    if (this.ui.points) {
      this.ui.points.replaceChildren();
      part.points.forEach((text) => {
        const item = document.createElement("li");
        item.innerHTML = text;
        this.ui.points.appendChild(item);
      });
    }

    if (this.ui.photo) {
      this.ui.photo.src = part.photo;
      this.ui.photo.alt = part.photoCaption;
    }
    if (this.ui.photoCaption) this.ui.photoCaption.textContent = part.photoCaption;
    if (this.ui.source) {
      this.ui.source.textContent =
        `원본: Rep5x build-guide · ${id.startsWith("e3v3se-") ? "printer-specific/ender-3-v3-se" : "universal-parts"}/3d-printed-parts/current/3mf (GPL v3)`;
    }

    if (!options.skipLoad) this.loadModel();
  }

  loadModel() {
    if (!this.viewer || this.loadedId === this.currentId) return;

    if (window.location.protocol === "file:") {
      this.viewer.showPlaceholder(
        "3D 모델 자동 로드는 로컬 HTTP 서버에서 동작합니다 (python -m http.server).",
        `${this.currentId}.stl`
      );
      return;
    }

    this.loadedId = this.currentId;
    const requestedId = this.currentId;
    this.viewer.loadFromUrls(`assets/models/rep5x/${requestedId}.stl`).then((ok) => {
      if (!ok && this.loadedId === requestedId) this.loadedId = null;
    });
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const explorer = new Rep5xPartsExplorer();
  window.rep5xPartsExplorer = explorer;
  explorer.initialize();
});
