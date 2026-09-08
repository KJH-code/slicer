/* global ResearchSTLViewer */

/**
 * 9쪽 부품 탐색기.
 *
 * 여기 있는 셋은 '출력할 목록'이 아니다. 공개된 설계에서 우리 코드가 값을
 * 읽어야 하는 지점 셋을 고른 것이다 — 충돌 검사의 대상(B암), C 누적의
 * 근거(슬립링 홀더), 기종 의존이 격리된 곳(캐리지 마운트).
 *
 * assets/models/rep5x/ 에는 나머지 부품 STL 도 함께 있으므로,
 * 보여줄 부품을 바꾸려면 아래 객체와 index.html 의 버튼만 손보면 된다.
 */
const REP5X_PARTS = Object.freeze({
  "b-arm": {
    title: "B암",
    version: "b-arm v1.1.0 · 공용",
    dims: "48.0 × 91.8 × 51.4 mm · 10,268 면",
    role: "B축이 기울이는 것은 <b>노즐만이 아니라 이 팔 전체</b>다.",
    points: [
      "그래서 5축 충돌 검사의 대상은 노즐 팁이 아니라 이 형상이다",
      "지금 우리 검사기는 3축 노즐만 본다 — 다시 써야 한다 (11쪽 03)",
      "608 베어링 2개가 B축 회전을, 안쪽 스위치가 B 원점을 잡는다"
    ],
    photo: "assets/images/rep5x/b-arm-bearings-microswitch.jpg",
    photoCaption: "베어링과 원점 스위치를 넣은 B암"
  },
  "slip-ring-holder": {
    title: "슬립링 홀더",
    version: "slip-ring-holder v1.1.1 · 공용",
    dims: "3.8 × 15.8 × 14.0 mm · 2,840 면",
    role: "가장 작은 부품인데, <b>C를 계속 누적해도 되는 근거</b>가 여기 있다.",
    points: [
      "배선이 회전 중심을 지나 12채널 슬립링을 통과한다",
      "그래서 C가 무한 회전한다 → 코드의 <b>unwrap(phi)</b> 가 성립한다",
      "Open5x에는 이게 없어 구 데모에서 149회전이 문제였다"
    ],
    photo: "assets/images/rep5x/slip-ring-jst-connectors.jpg",
    photoCaption: "배선이 통과하는 슬립링"
  },
  "e3v3se-carriage-mount": {
    title: "캐리지 마운트",
    version: "carriage-mount v1.1.1 · V3 SE 전용",
    dims: "119.9 × 56.5 × 58.0 mm · 16,534 면",
    role: "<b>기종 의존이 이 부품 하나에만 있다.</b>",
    points: [
      "다른 기종으로 옮겨도 바뀌는 것은 이것과 엔드스톱 몇 개뿐",
      "즉 우리 파이프라인은 기종을 바꿔도 그대로 쓴다",
      "61804 베어링 2개가 C축 회전을 받고, 원점 센서가 여기에 붙는다"
    ],
    photo: "assets/images/rep5x/carriage-mount-installed.jpg",
    photoCaption: "X 캐리지에 장착된 캐리지 마운트"
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
        "원본: Rep5x 공개 설계 (GPL v3) · 3MF → STL 변환, 형상은 그대로";
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
