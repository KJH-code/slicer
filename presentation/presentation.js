/* global Reveal */

/**
 * 발표자 메모. 화면에는 표시하지 않으며 콘솔에서
 * speakerNotes[슬라이드번호]로 확인할 수 있다.
 */
const speakerNotes = Object.freeze({
  1: `연구 제목과 핵심 목표를 소개한다. 사용자가 원뿔각을 직접 고르는 방식에서 STL 형상 기반 자동 선택으로 이동하는 연구임을 강조한다.
[Sources]
- 사용자 제공 발표자료.pptx, 1쪽`,
  2: `발표가 프린터 구조, 알고리즘, 시각화, 검증 계획의 순서로 진행됨을 안내한다.
[Sources]
- 사용자 제공 수정 지시`,
  3: `3축은 방향 고정, 4축은 단일 회전축, 5축은 두 회전축을 추가한다. 4축이 기구 복잡도와 비평면 자유도의 절충점임을 설명한다.
[Sources]
- 사용자 제공 이미지: Core-RΘ, RotBot, Open5x
- RotBot: https://www.mdpi.com/2076-3417/11/18/8760
- Open5x: https://dl.acm.org/doi/10.1145/3491101.3519782
- 이미지 원본 출처 URL 추가 필요`,
  4: `네 미니 애니메이션은 같은 형상에서 레이어 방향만 비교한다. 실제 슬라이싱 결과가 아니라 개념 애니메이션임을 설명한다.
[Sources]
- 사용자 제공 이미지 1, 2
- 사용자 제공 연구 설명
- 이미지 원본 출처 URL 추가 필요`,
  5: `원뿔 슬라이싱의 장점은 가능성으로 표현하고, 본 연구의 직접 목표는 STL 형상에 따른 원뿔각과 구간 자동 결정임을 명확히 한다.
[Sources]
- 사용자 제공 발표자료.pptx, 2·4쪽`,
  6: `기존 선행 연구 슬라이드의 RotBot, Slicer4RTN을 유지하고 Open5x와 일반 비평면 연구를 비교한다.
[Sources]
- RotBot: https://www.mdpi.com/2076-3417/11/18/8760
- Slicer4RTN: https://github.com/Spiritdude/Slicer4RTN
- Open5x: https://dl.acm.org/doi/10.1145/3491101.3519782
- 사용자 제공 발표자료.pptx, 3쪽`,
  7: `다섯 개의 독립 코드가 최적각 반환을 중심으로 하나의 파이프라인을 이루어야 한다. 공통 JSON과 로그가 통합의 핵심이다.
[Sources]
- 사용자 제공 발표자료.pptx, 4쪽
- 사용자 제공 수정 지시`,
  8: `왼쪽의 여섯 모델은 실제 STL 파일을 추가하면 전환할 수 있다. 교선 시각화는 STL과 구간별 각도를 입력받지만 G-code를 생성하지 않는다. G-code 도구는 이미 만들어진 실제 명령 경로를 검토한다.
[Sources]
- 사용자 제공 이미지 6, 7
- 사용자 제공 시각화 도구 설명`,
  9: `왼쪽은 서포트 감소와 평가식을 설명하고, 오른쪽은 실제 G-code 원본 영상을 재생한다. 하단 결과 영역은 평가함수의 선택 결과와 각도 비용의 의미를 정리한다.
[Sources]
- 사용자 제공 발표자료.pptx, 5쪽
- 사용자 제공 assets/videos/gcode.mp4`,
  10: `n_z<0 면을 공유 변으로 연결하고 BFS로 I_c를 구한다. q0와 kappa_max를 만족하는 후보 중 절댓값이 가장 작은 각도를 선택한다. STL과 같은 면 순서의 JSON을 입력하면 실제 성분이 색상으로 표시된다.
[Sources]
- 사용자 제공 연결 성분 코드 설명
- 사용자 확정 수식`,
  11: `왼쪽은 analyze-k.png의 실제 데이터 그래프를 원본 비율로 표시하고, 오른쪽은 실제 XLSX와 results-summary.json을 연결해 모델별·파라미터별 결과를 비교한다.
[Sources]
- 사용자 제공 assets/images/analyze-k.png
- 사용자 제공 이미지 8
- 사용자 제공 수정 지시`,
  12: `Z축 n등분은 단순한 기준 알고리즘이고 I_c 기반은 실제 오버행 구조를 보존하는 적응형 방식이다. I_c 기반이 모든 평가에서 우월하다는 뜻은 아니며 공간 분할 목적에서 더 적합하다고 설명한다.
[Sources]
- 사용자 제공 두 원뿔각 반환 알고리즘 설명`,
  13: `TOPPRA는 이미 생성된 경로의 속도·가속도 제한 기반 시간 매개화에 우선 사용한다. FCL은 기하 충돌만 판단하며 압출 안정성을 직접 판단하지 않는다.
[Sources]
- TOPPRA: https://hungpham2511.github.io/toppra/
- Ruckig: https://docs.ruckig.com/
- FCL: https://github.com/flexible-collision-library/fcl
- 사용자 제공 구현 현황`,
  14: `문제점을 실패 목록이 아니라 다음 검증 항목으로 설명한다. 특히 평면·원뿔 경계와 G-code 데이터 형식 통합이 중요하다.
[Sources]
- 사용자 제공 현재 연구 내용`,
  15: `실제 출력이 마지막 단계가 아니라 각도 알고리즘과 운동학 평가를 다시 보정하는 입력임을 설명한다.
[Sources]
- 사용자 제공 향후 연구 방향`,
  16: `구현한 기능과 부족한 검증을 같은 표에서 정리한다. 최종 목표는 기하학적으로 가능한 각도가 아니라 실제 출력 가능한 최적각이다.
[Sources]
- 사용자 제공 연구 목표와 구현 현황`
});

/* 발표별 메모를 먼저 정의해 둔 경우(예: rep5x-deck.js)에는 그것을 유지한다. */
window.speakerNotes = window.speakerNotes || speakerNotes;

/**
 * Reveal.js를 우선 사용하고, 로드에 실패하면 동일한 키보드·휠 조작을
 * 제공하는 기본 슬라이드 모드로 전환한다.
 */
class PresentationController {
  constructor() {
    this.slides = Array.from(document.querySelectorAll(".slides > section"));
    this.index = 0;
    this.revealReady = false;
    this.wheelLockedUntil = 0;
    this.fallbackResizeObserver = null;

    this.ui = {
      previous: document.getElementById("prev-slide"),
      next: document.getElementById("next-slide"),
      fullscreen: document.getElementById("fullscreen-toggle"),
      current: document.getElementById("current-slide"),
      total: document.getElementById("total-slides"),
      progress: document.getElementById("global-progress-bar"),
      status: document.getElementById("presentation-status")
    };

    this.onKeyDown = this.onKeyDown.bind(this);
    this.onWheel = this.onWheel.bind(this);
    this.onFullscreenChange = this.onFullscreenChange.bind(this);
    this.resizeFallback = this.resizeFallback.bind(this);
  }

  async initialize() {
    this.slides.forEach((slide, index) => {
      slide.dataset.index = String(index);
    });

    this.ui.total.textContent = String(this.slides.length);
    this.bindCommonControls();
    this.initializeToolTabs();
    this.loadResultSummary();

    if (typeof window.Reveal !== "undefined") {
      try {
        await window.Reveal.initialize({
          width: 1600,
          height: 900,
          margin: 0,
          minScale: 0.15,
          maxScale: 2,
          center: false,
          controls: false,
          progress: false,
          slideNumber: false,
          hash: true,
          history: true,
          keyboard: false,
          touch: true,
          transition: "fade",
          transitionSpeed: "fast",
          backgroundTransition: "fade"
        });

        this.revealReady = true;
        window.Reveal.on("ready", (event) => this.handleRevealChange(event));
        window.Reveal.on("slidechanged", (event) => this.handleRevealChange(event));
        this.update(window.Reveal.getIndices().h || 0, null);
        return;
      } catch (error) {
        this.showStatus("Reveal.js 초기화에 실패하여 기본 슬라이드 모드로 전환했습니다.");
      }
    } else {
      this.showStatus("Reveal.js를 불러오지 못해 기본 슬라이드 모드로 실행합니다.");
    }

    this.initializeFallback();
  }

  bindCommonControls() {
    this.ui.previous.addEventListener("click", () => this.previous());
    this.ui.next.addEventListener("click", () => this.next());
    this.ui.fullscreen.addEventListener("click", () => this.toggleFullscreen());

    document.addEventListener("keydown", this.onKeyDown);
    document.addEventListener("wheel", this.onWheel, { passive: false });
    document.addEventListener("fullscreenchange", this.onFullscreenChange);
    window.addEventListener("pagehide", () => this.releaseSlideVideos(), { once: true });
    this.bindSlideVideos();

    document.querySelectorAll("button, input, .presentation-nav, .interactive-zone")
      .forEach((element) => {
        element.addEventListener("wheel", (event) => event.stopPropagation(), { passive: true });
      });
  }

  initializeToolTabs() {
    const buttons = Array.from(document.querySelectorAll(".tool-tabs [data-tool]"));
    const views = Array.from(document.querySelectorAll("[data-tool-view]"));

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const tool = button.dataset.tool;
        buttons.forEach((item) => item.classList.toggle("active", item === button));
        views.forEach((view) => view.classList.toggle("active", view.dataset.toolView === tool));
      });
    });
  }

  async loadResultSummary() {
    if (window.location.protocol === "file:") return;

    try {
      const response = await fetch("assets/data/results-summary.json", { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json();
      if (data.status !== "ready") return;

      const filename = document.getElementById("result-file-name");
      const sheet = document.getElementById("result-sheet-name");
      if (filename) filename.textContent = data.sourceFile || "결과 파일";
      if (sheet) sheet.textContent = `시트: ${data.sheet || "미지정"}`;

      document.querySelectorAll("[data-result-field]").forEach((element) => {
        const key = element.dataset.resultField;
        element.textContent = data[key] || "추가 예정";
      });
    } catch (error) {
      // file:// 또는 데이터 미준비 상태에서는 자리표시자를 유지한다.
    }
  }

  initializeFallback() {
    document.body.classList.add("fallback-mode");
    const requestedIndex = this.indexFromHash();
    this.index = Math.max(0, Math.min(this.slides.length - 1, requestedIndex));
    this.slides.forEach((slide, slideIndex) => {
      slide.classList.toggle("is-active", slideIndex === this.index);
      slide.setAttribute("aria-hidden", slideIndex === this.index ? "false" : "true");
    });

    this.fallbackResizeObserver = new ResizeObserver(this.resizeFallback);
    this.fallbackResizeObserver.observe(document.body);
    this.resizeFallback();
    this.update(this.index, null);
  }

  resizeFallback() {
    if (!document.body.classList.contains("fallback-mode")) return;
    const scale = Math.min(window.innerWidth / 1600, window.innerHeight / 900);
    const active = this.slides[this.index];
    if (!active) return;
    active.style.transform = `scale(${scale})`;
    active.style.left = `${(window.innerWidth - 1600 * scale) / 2}px`;
    active.style.top = `${(window.innerHeight - 900 * scale) / 2}px`;
  }

  handleRevealChange(event) {
    const parsedPreviousIndex = event.previousSlide
      ? Number(event.previousSlide.dataset.index)
      : Number.NaN;
    const previousIndex = Number.isInteger(parsedPreviousIndex) ? parsedPreviousIndex : null;
    const nextIndex = window.Reveal.getIndices(event.currentSlide).h;
    this.update(nextIndex, previousIndex);
  }

  update(nextIndex, previousIndex) {
    const oldIndex = Number.isInteger(previousIndex) ? previousIndex : this.index;
    this.index = Math.max(0, Math.min(this.slides.length - 1, nextIndex));

    if (!this.revealReady) {
      this.slides.forEach((slide, slideIndex) => {
        slide.classList.toggle("is-active", slideIndex === this.index);
        slide.setAttribute("aria-hidden", slideIndex === this.index ? "false" : "true");
      });
    }

    const displayIndex = this.index + 1;
    this.ui.current.textContent = String(displayIndex);
    this.ui.progress.style.width = `${(displayIndex / this.slides.length) * 100}%`;
    this.ui.previous.disabled = this.index === 0;
    this.ui.next.disabled = this.index === this.slides.length - 1;

    const activeSlide = this.slides[this.index];
    document.title = `${displayIndex}/${this.slides.length} · ${this.slideTitle(activeSlide)}`;
    this.updateSlideVideos(activeSlide);

    if (!this.revealReady) {
      window.location.hash = `slide-${displayIndex}`;
      this.resizeFallback();
    }

    document.dispatchEvent(new CustomEvent("presentation:slidechange", {
      detail: {
        index: this.index,
        previousIndex: oldIndex,
        slide: activeSlide,
        slideId: activeSlide?.id || ""
      }
    }));
  }

  updateSlideVideos(activeSlide) {
    this.slides.forEach((slide) => {
      slide.querySelectorAll("video[data-slide-autoplay]").forEach((video) => {
        const shouldPlay = slide === activeSlide;

        if (shouldPlay) {
          const isEntering = video.dataset.slideActive !== "true";
          video.dataset.slideActive = "true";
          video.autoplay = true;
          if (isEntering) this.resetSlideVideo(video);
          this.playSlideVideo(video);
        } else {
          delete video.dataset.slideActive;
          video.autoplay = false;
          video.pause();
          this.resetSlideVideo(video);
        }
      });
    });
  }

  bindSlideVideos() {
    this.slides.forEach((slide) => {
      slide.querySelectorAll("video[data-slide-autoplay]").forEach((video) => {
        video.defaultMuted = true;
        video.muted = true;
        video.loop = true;
        video.playsInline = true;
        video.preload = "auto";

        const retryPlayback = () => {
          if (video.dataset.slideActive === "true") this.playSlideVideo(video);
        };

        video.addEventListener("loadedmetadata", retryPlayback);
        video.addEventListener("canplay", retryPlayback);
        if (window.location.protocol === "file:") {
          video.load();
        } else {
          this.prepareSlideVideo(video);
        }
      });
    });
  }

  async prepareSlideVideo(video) {
    const source = video.getAttribute("src");
    if (!source || video.dataset.preparing === "true") return;
    video.dataset.preparing = "true";

    try {
      const response = await fetch(source, { cache: "force-cache" });
      if (!response.ok) throw new Error("video-fetch-failed");
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      video.dataset.objectUrl = objectUrl;
      video.src = objectUrl;
      video.load();
    } catch (error) {
      video.load();
    } finally {
      delete video.dataset.preparing;
    }
  }

  playSlideVideo(video) {
    if (video.dataset.slideActive !== "true" || !video.paused) return;
    const playback = video.play();
    playback?.catch(() => {
      // 미디어가 준비되면 loadedmetadata/canplay 이벤트에서 다시 시도한다.
    });
  }

  resetSlideVideo(video) {
    try {
      video.currentTime = 0;
    } catch (error) {
      // 메타데이터가 아직 없으면 초기 재생 위치는 기본값 0초를 유지한다.
    }
  }

  releaseSlideVideos() {
    this.updateSlideVideos(null);
    this.slides.forEach((slide) => {
      slide.querySelectorAll("video[data-slide-autoplay]").forEach((video) => {
        const objectUrl = video.dataset.objectUrl;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        delete video.dataset.objectUrl;
      });
    });
  }

  slideTitle(slide) {
    const heading = slide?.querySelector("h1, h2");
    return heading?.textContent?.replace(/\s+/g, " ").trim() || "연구 발표";
  }

  next() {
    if (this.index >= this.slides.length - 1) return;
    if (this.revealReady) window.Reveal.next();
    else this.update(this.index + 1, this.index);
  }

  previous() {
    if (this.index <= 0) return;
    if (this.revealReady) window.Reveal.prev();
    else this.update(this.index - 1, this.index);
  }

  goTo(targetIndex) {
    const bounded = Math.max(0, Math.min(this.slides.length - 1, targetIndex));
    if (this.revealReady) window.Reveal.slide(bounded);
    else this.update(bounded, this.index);
  }

  onKeyDown(event) {
    if (event.defaultPrevented || this.isTypingTarget(event.target)) return;
    const key = event.key;

    if (["ArrowRight", "ArrowDown", "PageDown", " "].includes(key)) {
      event.preventDefault();
      this.next();
    } else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(key)) {
      event.preventDefault();
      this.previous();
    } else if (key === "Home") {
      event.preventDefault();
      this.goTo(0);
    } else if (key === "End") {
      event.preventDefault();
      this.goTo(this.slides.length - 1);
    } else if (key.toLowerCase() === "f") {
      event.preventDefault();
      this.toggleFullscreen();
    }
  }

  onWheel(event) {
    if (event.defaultPrevented || this.shouldIgnoreWheel(event.target)) return;
    const now = performance.now();
    if (now < this.wheelLockedUntil || Math.abs(event.deltaY) < 22) return;
    this.wheelLockedUntil = now + 620;
    event.preventDefault();
    if (event.deltaY > 0) this.next();
    else this.previous();
  }

  shouldIgnoreWheel(target) {
    return Boolean(target?.closest?.(
      ".interactive-zone, .presentation-nav, button, input, textarea, select"
    ));
  }

  isTypingTarget(target) {
    const tag = target?.tagName?.toLowerCase();
    return target?.isContentEditable || ["input", "textarea", "select"].includes(tag);
  }

  async toggleFullscreen() {
    try {
      if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
      else await document.exitFullscreen();
    } catch (error) {
      this.showStatus("브라우저가 전체 화면 전환을 허용하지 않았습니다.");
    }
  }

  onFullscreenChange() {
    const active = Boolean(document.fullscreenElement);
    this.ui.fullscreen.setAttribute("aria-pressed", String(active));
    this.ui.fullscreen.setAttribute("aria-label", active ? "전체 화면 종료" : "전체 화면 전환");
  }

  indexFromHash() {
    const match = window.location.hash.match(/slide-(\d+)/);
    return match ? Number(match[1]) - 1 : 0;
  }

  showStatus(message) {
    this.ui.status.textContent = message;
    this.ui.status.hidden = false;
    window.setTimeout(() => {
      this.ui.status.hidden = true;
    }, 6000);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const presentation = new PresentationController();
  window.presentationController = presentation;
  presentation.initialize();
});
