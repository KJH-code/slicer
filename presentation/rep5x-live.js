/**
 * 슬라이드 내용 자체를 움직이게 하는 것들.
 *
 * 배경 장식(rep5x-fx.js)과 달리, 여기 있는 것들은 전부 '내용'에 붙는다.
 * 슬라이드에 들어올 때마다 다시 재생된다.
 *
 *  · 숫자 세어 올리기   — 우리가 얻은 값이 채워지는 것을 보인다 (3·8쪽)
 *  · 그림이 그려지듯 드러남 — 그래프를 왼쪽부터 훑어 보인다 (3·4쪽)
 *  · 파이프라인 진행     — 01→07 로 신호가 지나가며 각 단계가 켜진다 (5쪽)
 *  · 단계 표시기        — 헤더에 해결·지금·다음 중 어디인지 항상 보인다
 *  · 브라우저 로딩      — 화면 재현이 실제로 '열리는' 것처럼 (7쪽)
 *  · 부품 자동 회전     — 손대기 전까지 모델이 천천히 돈다 (9쪽)
 *
 * prefers-reduced-motion 이면 전부 최종 상태로 바로 둔다.
 */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const easeOut = (t) => 1 - Math.pow(1 - t, 3);

  /* ------------------------------------------------------------------ *
   * 숫자 세어 올리기
   * ------------------------------------------------------------------ */
  function formatNumber(value, decimals, comma) {
    let text = value.toFixed(decimals);
    if (comma) {
      const [int, frac] = text.split(".");
      text = int.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (frac ? `.${frac}` : "");
    }
    return text;
  }

  class CountUp {
    constructor(el) {
      this.el = el;
      this.target = parseFloat(el.dataset.countup);
      this.decimals = parseInt(el.dataset.decimals || "0", 10);
      this.comma = el.hasAttribute("data-comma");
      this.prefix = el.dataset.prefix || "";
      this.suffix = el.dataset.suffix || "";
      this.frame = null;
      this.write(reduceMotion.matches ? this.target : 0);
    }

    write(value) {
      this.el.textContent =
        this.prefix + formatNumber(value, this.decimals, this.comma) + this.suffix;
    }

    play(delay = 0) {
      if (reduceMotion.matches) { this.write(this.target); return; }
      this.stop();
      const duration = 900;
      const begin = performance.now() + delay;
      const tick = (now) => {
        const t = (now - begin) / duration;
        if (t < 0) { this.frame = requestAnimationFrame(tick); return; }
        if (t >= 1) { this.write(this.target); this.frame = null; return; }
        this.write(this.target * easeOut(t));
        this.frame = requestAnimationFrame(tick);
      };
      this.write(0);
      this.frame = requestAnimationFrame(tick);
    }

    stop() {
      if (this.frame) { cancelAnimationFrame(this.frame); this.frame = null; }
    }
  }

  /* ------------------------------------------------------------------ *
   * 파이프라인 진행 — 01→07 로 신호가 지나간다
   * ------------------------------------------------------------------ */
  class PipelineRun {
    constructor(list) {
      this.steps = Array.from(list.querySelectorAll("li"));
      this.timers = [];
      this.loop = null;
    }

    play() {
      this.stop();
      if (reduceMotion.matches) return;
      const step = 460;
      const run = () => {
        this.steps.forEach((li, i) => {
          this.timers.push(window.setTimeout(() => {
            li.classList.add("is-lit");
            this.timers.push(window.setTimeout(() => li.classList.remove("is-lit"), step * 1.6));
          }, i * step));
        });
      };
      run();
      this.loop = window.setInterval(run, step * this.steps.length + 1400);
    }

    stop() {
      this.timers.forEach(window.clearTimeout);
      this.timers = [];
      if (this.loop) { window.clearInterval(this.loop); this.loop = null; }
      this.steps.forEach((li) => li.classList.remove("is-lit"));
    }
  }

  /* ------------------------------------------------------------------ *
   * 단계 표시기 — 헤더에 해결 · 지금 · 다음
   * ------------------------------------------------------------------ */
  const PHASE_OF = {
    "slide-3": 0, "slide-4": 0, "slide-5": 0,
    "slide-6": 1, "slide-7": 1, "slide-8": 1, "slide-9": 1,
    "slide-10": 1, "slide-11": 1,
    "slide-12": 2
  };
  const PHASE_NAMES = ["해결한 것", "지금 하는 것", "다음에 할 것"];

  function buildPhaseTracks() {
    Object.entries(PHASE_OF).forEach(([id, active]) => {
      const header = document.querySelector(`#${id} .slide-header`);
      if (!header) return;
      const track = document.createElement("div");
      track.className = "phase-track";
      track.setAttribute("aria-hidden", "true");
      PHASE_NAMES.forEach((name, i) => {
        const item = document.createElement("span");
        item.className = "phase-step" + (i === active ? " is-active" : "")
          + (i < active ? " is-done" : "");
        item.innerHTML = `<i></i>${name}`;
        track.appendChild(item);
      });
      header.appendChild(track);
    });
  }

  /* ------------------------------------------------------------------ *
   * 브라우저 화면 재현이 '열리는' 연출
   * ------------------------------------------------------------------ */
  function playBrowserLoad() {
    const mock = document.querySelector(".browser-mock");
    if (!mock || reduceMotion.matches) return;
    mock.classList.remove("is-loaded");
    void mock.offsetWidth;
    mock.classList.add("is-loading");
    window.setTimeout(() => {
      mock.classList.remove("is-loading");
      mock.classList.add("is-loaded");
    }, 720);
  }

  /* ------------------------------------------------------------------ *
   * 9쪽 부품 모델 — 손대기 전까지 천천히 돈다
   * ------------------------------------------------------------------ */
  function setupAutoSpin() {
    const viewer = () => window.rep5xPartsExplorer?.viewer;
    let spinning = false;
    let raf = null;
    let last = 0;

    const tick = (now) => {
      const v = viewer();
      if (!spinning || !v?.modelGroup) { raf = null; return; }
      v.modelGroup.rotation.z += Math.min((now - last) / 1000, 0.05) * 0.34;
      last = now;
      raf = requestAnimationFrame(tick);
    };

    const start = () => {
      if (spinning || reduceMotion.matches) return;
      spinning = true;
      last = performance.now();
      raf = requestAnimationFrame(tick);
    };
    const stop = () => {
      spinning = false;
      if (raf) { cancelAnimationFrame(raf); raf = null; }
    };

    // 사용자가 뷰어를 만지면 자동 회전을 멈춘다
    document.getElementById("part-viewer")
      ?.addEventListener("pointerdown", stop, { once: false });

    return { start, stop };
  }

  /* ------------------------------------------------------------------ */

  window.addEventListener("DOMContentLoaded", () => {
    buildPhaseTracks();

    const counters = new Map();       // 슬라이드 id → CountUp[]
    document.querySelectorAll("[data-countup]").forEach((el) => {
      const id = el.closest(".slide")?.id || "";
      if (!counters.has(id)) counters.set(id, []);
      counters.get(id).push(new CountUp(el));
    });

    const pipelines = new Map();
    document.querySelectorAll(".pipeline-flow").forEach((list) => {
      pipelines.set(list.closest(".slide")?.id || "", new PipelineRun(list));
    });

    const spin = setupAutoSpin();

    const enter = (id) => {
      counters.forEach((list, slideId) => {
        list.forEach((c, i) => (slideId === id ? c.play(180 + i * 130) : c.stop()));
      });
      pipelines.forEach((p, slideId) => (slideId === id ? p.play() : p.stop()));
      if (id === "slide-7") playBrowserLoad();
      if (id === "slide-9") spin.start(); else spin.stop();
    };

    document.addEventListener("presentation:slidechange",
      (e) => enter(e.detail.slideId));

    const first = document.querySelector(".slides > section.present")
      || document.querySelector(".slides > section.is-active");
    enter(first?.id || "slide-1");
  });
})();
