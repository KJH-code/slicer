/* global ResearchSTLViewer */

/**
 * 9쪽 부품 탐색기.
 * 왼쪽 목록에서 부품을 고르면 오른쪽 3D 뷰어와 설명이 함께 바뀐다.
 * 3D 모델은 Rep5x 저장소의 3MF를 STL로 변환해 assets/models/rep5x/ 에 둔 것이다.
 */
const REP5X_PARTS = Object.freeze({
  "b-arm": {
    title: "B암",
    version: "v1.1.0 · 공용",
    dims: "48.0 × 91.8 × 51.4 mm · 10,268 면",
    role: "노즐을 기울이는 <b>B축의 몸체</b>. 배선과 보우덴 튜브가 이 팔 가운데를 지난다.",
    points: [
      "608 베어링 2개로 B축 회전을 받는다",
      "안쪽 마이크로스위치가 B축 원점",
      "케이블 절개선 — 배선을 뽑지 않고 떼어낼 수 있다"
    ],
    photo: "assets/images/rep5x/b-arm-bearings-microswitch.jpg",
    photoCaption: "베어링과 마이크로스위치를 넣은 B암"
  },
  "c-driven-pulley": {
    title: "C축 종동 풀리",
    version: "v1.1.0 · 공용",
    dims: "41.0 × 41.0 × 31.4 mm · 40,812 면",
    role: "헤드 전체를 Z축 둘레로 돌리는 <b>요(yaw) 풀리</b>.",
    points: [
      "가운데가 뚫려 배선이 회전 중심을 지난다",
      "이것이 연속 회전의 조건이다",
      "NEMA17 + GT2 벨트로 구동"
    ],
    photo: "assets/images/rep5x/carriage-mount-front-view.jpg",
    photoCaption: "캐리지 마운트에 장착된 C축 풀리"
  },
  "b-driven-pulley": {
    title: "B축 종동 풀리",
    version: "v1.1.0 · 공용",
    dims: "41.0 × 41.0 × 25.4 mm · 23,124 면",
    role: "B암을 기울이는 <b>틸트 풀리</b>. 원점 스위치를 때리는 볼트가 박힌다.",
    points: [
      "열간 인서트 2개 + 트리거 볼트",
      "볼트를 1~2 mm 내밀어 B축 원점을 잡는다"
    ],
    photo: "assets/images/rep5x/b-driven-pulley-heat-inserts.jpg",
    photoCaption: "인서트와 트리거 볼트를 넣은 상태"
  },
  "slip-ring-holder": {
    title: "슬립링 홀더",
    version: "v1.1.1 · 공용",
    dims: "3.8 × 15.8 × 14.0 mm · 2,840 면",
    role: "12채널 슬립링을 잡아 주는 작은 브래킷. <b>이 부품이 연속 회전을 가능하게 한다.</b>",
    points: [
      "히터·서미스터·팬·엔드스톱·스테퍼 배선이 통과",
      "배선이 꼬이지 않아 C축이 무한 회전한다"
    ],
    photo: "assets/images/rep5x/slip-ring-jst-connectors.jpg",
    photoCaption: "커넥터로 정리한 슬립링"
  },
  "hotend-spacer": {
    title: "핫엔드 스페이서",
    version: "v1.0.0 · 공용",
    dims: "20.0 × 4.0 × 6.0 mm · 692 면",
    role: "핫엔드를 B암에 물릴 때 두께를 맞추는 얇은 스페이서.",
    points: [
      "노즐 끝 ↔ B축 거리(LB)를 바꾼다",
      "넣고 빼면 <b>캘리브레이션을 다시</b> 해야 한다"
    ],
    photo: "assets/images/rep5x/hotend-b-arm-assembly.jpg",
    photoCaption: "B암에 장착된 핫엔드"
  },
  "spacer-3mm": {
    title: "3 mm 스페이서",
    version: "v1.0.0 · 공용",
    dims: "21.0 × 7.0 × 3.0 mm · 684 면",
    role: "체결부 간격을 3 mm 띄우는 범용 스페이서.",
    points: [
      "가장 단순하지만 없으면 체결부가 변형된다",
      "공용 부품은 전부 PETG 권장"
    ],
    photo: "assets/images/rep5x/carriage-mount-underside.jpg",
    photoCaption: "베어링이 보이는 마운트 아랫면"
  },
  "e3v3se-carriage-mount": {
    title: "캐리지 마운트",
    version: "v1.1.1 · V3 SE 전용",
    dims: "119.9 × 56.5 × 58.0 mm · 16,534 면",
    role: "X 캐리지에 붙어 5축 헤드를 지탱한다. <b>기종 의존이 이 부품 하나에 모여 있다.</b>",
    points: [
      "순정 핫엔드를 떼고 원래 나사 구멍에 체결",
      "61804 베어링 2개가 C축 회전을 받는다",
      "C축 스테퍼와 광학 원점 센서가 여기에"
    ],
    photo: "assets/images/rep5x/carriage-mount-installed.jpg",
    photoCaption: "X 캐리지에 장착된 캐리지 마운트"
  },
  "e3v3se-extruder-mount": {
    title: "외부 압출기 마운트",
    version: "v1.1.0 · V3 SE 전용",
    dims: "46.5 × 97.5 × 65.0 mm · 4,412 면",
    role: "직결 압출기를 프레임 쪽 <b>보우덴</b>으로 옮기는 마운트.",
    points: [
      "헤드가 회전하므로 압출기를 떼어내야 한다",
      "헤드 질량과 회전 반경이 줄어든다"
    ],
    photo: "assets/images/rep5x/extruder-mount-assembled.jpg",
    photoCaption: "조립된 보우덴 압출기 마운트"
  },
  "e3v3se-x-endstop": {
    title: "X 엔드스톱 마운트",
    version: "v1.1.0 · V3 SE 전용",
    dims: "27.0 × 25.5 × 7.6 mm · 6,538 면",
    role: "X축 원점 스위치를 새 위치에 다는 브래킷.",
    points: [
      "순정 X 엔드스톱은 <b>헤드에 붙어 있어</b> 못 쓴다",
      "원점이 바뀌므로 펌웨어도 함께 수정"
    ],
    photo: "assets/images/rep5x/x-endstop-assembled.jpg",
    photoCaption: "조립된 X 엔드스톱 마운트"
  },
  "e3v3se-z-endstop": {
    title: "Z 엔드스톱 마운트",
    version: "v1.1.0 · V3 SE 전용",
    dims: "21.0 × 22.0 × 19.0 mm · 1,442 면",
    role: "X 갠트리에 Z축 원점 스위치를 다는 브래킷.",
    points: [
      "순정 Z 프로브도 헤드에 붙어 있어 못 쓴다",
      "자동 베드 레벨링을 포기하는 대가"
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
