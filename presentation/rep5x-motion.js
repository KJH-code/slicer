/**
 * 발표 화면의 움직임.
 *
 *  1) 슬라이드 진입 연출 — 슬라이드가 활성화될 때마다 그 안의 카드/단계가
 *     순서대로 올라온다. 마크업은 건드리지 않고 여기서 선택자로 지정한다.
 *  2) 10쪽 5축 자세 애니메이션 — 원뿔 레이어 위를 도는 압출점에서
 *     노즐이 B(틸트)·C(요)로 어떻게 서는지를 실제로 계산해 그린다.
 *     같은 쪽의 코드 블록과 같은 식을 쓴다(하드코딩한 그림이 아니다).
 *
 * 접근성: prefers-reduced-motion 이면 진입 연출은 styles.css 의 전역 규칙이
 * 사실상 끄고, 캔버스 애니메이션은 정지 화면 한 장만 그린다.
 */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  /* ------------------------------------------------------------------ *
   * 1) 슬라이드 진입 연출
   * ------------------------------------------------------------------ */

  // 순서대로 등장시킬 대상. 슬라이드마다 '읽는 순서'와 같게 둔다.
  const STAGGER_SELECTORS = [
    ".spine-row:not(.spine-head)",
    ".verify-layer",
    ".verify-proof",
    ".angle-figure",
    ".angle-findings article",
    ".pipeline-flow li",
    ".pipeline-notes article",
    ".core-shift > *",
    ".core-why",
    ".site-layout > *",
    ".mock-cards article",
    ".design-hero",
    ".design-gallery figure",
    ".design-spec",
    ".parts-explorer > *",
    ".code-compare > *",
    ".code-map",
    ".demo-row > *",
    ".problem-grid article",
    ".next-card",
    ".source-column"
  ].join(",");

  function prepareSlide(slide) {
    if (!slide || slide.dataset.animPrepared === "true") return;
    slide.dataset.animPrepared = "true";
    const groups = new Map();
    slide.querySelectorAll(STAGGER_SELECTORS).forEach((el) => {
      // 중첩된 대상(예: .core-shift > * 안의 것)은 바깥 것만 센다.
      if (el.parentElement?.closest("[data-anim-item]")) return;
      el.setAttribute("data-anim-item", "");
      const key = el.parentElement;
      const index = groups.get(key) || 0;
      groups.set(key, index + 1);
      el.style.setProperty("--i", String(index));
    });
  }

  function replay(slide) {
    if (!slide) return;
    prepareSlide(slide);
    slide.classList.remove("anim-in");
    void slide.offsetWidth;          // 리플로 강제 — 애니메이션을 다시 재생시킨다
    slide.classList.add("anim-in");
  }

  /* ------------------------------------------------------------------ *
   * 2) 10쪽 — 원뿔 레이어 위의 노즐 자세
   * ------------------------------------------------------------------ */

  const DEG = 180 / Math.PI;

  class ConicalNozzleScene {
    constructor() {
      this.canvas = document.getElementById("kin-canvas");
      this.out = {
        b: document.getElementById("kin-b"),
        c: document.getElementById("kin-c"),
        theta: document.getElementById("kin-theta"),
        gcode: document.getElementById("kin-gcode")
      };
      this.toggle = document.getElementById("kin-toggle");
      this.ctx = this.canvas?.getContext("2d") || null;
      this.frame = null;
      this.active = false;
      this.paused = false;
      this.t = 0;
      this.last = 0;
      this.cPrev = 0;                 // C 는 감기지 않고 계속 누적된다(슬립링)
      this.trail = [];                // 이미 지나간 압출 경로
    }

    initialize() {
      if (!this.ctx) return;
      this.resizeObserver = new ResizeObserver(() => this.resize());
      this.resizeObserver.observe(this.canvas.parentElement);
      this.resize();
      this.toggle?.addEventListener("click", () => this.setPaused(!this.paused));
      this.step(0, true);
    }

    resize() {
      const host = this.canvas.parentElement;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const w = Math.max(1, host.clientWidth);
      const h = Math.max(1, host.clientHeight);
      this.canvas.width = Math.round(w * ratio);
      this.canvas.height = Math.round(h * ratio);
      this.canvas.style.width = `${w}px`;
      this.canvas.style.height = `${h}px`;
      this.w = w;
      this.h = h;
      this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      this.draw();
    }

    setActive(active) {
      this.active = Boolean(active) && Boolean(this.ctx);
      if (this.active && !this.paused) this.start();
      else this.stop();
      if (this.active) this.draw();
    }

    setPaused(paused) {
      this.paused = Boolean(paused);
      if (this.toggle) {
        this.toggle.textContent = this.paused ? "재생" : "일시정지";
        this.toggle.setAttribute("aria-pressed", String(!this.paused));
      }
      if (this.paused) this.stop();
      else if (this.active) this.start();
    }

    start() {
      if (this.frame !== null || reduceMotion.matches) return;
      this.last = performance.now();
      const tick = (now) => {
        if (!this.active || this.paused) { this.frame = null; return; }
        this.step((now - this.last) / 1000);
        this.last = now;
        this.frame = window.requestAnimationFrame(tick);
      };
      this.frame = window.requestAnimationFrame(tick);
    }

    stop() {
      if (this.frame !== null) {
        window.cancelAnimationFrame(this.frame);
        this.frame = null;
      }
    }

    /** 시간을 진행시키고 현재 압출점·자세를 다시 계산한다. */
    step(dt, initial = false) {
      this.t += Math.min(dt, 0.05);

      // 압출점: 원뿔 레이어를 따라 돌면서 천천히 바깥으로 나간다.
      const phi = this.t * 1.05;                       // 방위각 (rad)
      const r = 14 + 9 * (0.5 - 0.5 * Math.cos(this.t * 0.31));   // 반경 mm

      // 그 높이의 원뿔각 θ(z) — 가변각 프로필을 흉내낸다(B 가 따라 변하는 것을 보이려고).
      const theta = (28 + 12 * Math.sin(this.t * 0.42)) / DEG;

      // 코드와 같은 대응: B = θ(z),  C = 방위각(연속 누적)
      const phiDeg = phi * DEG;
      const k = Math.round((this.cPrev - phiDeg) / 360);
      const c = phiDeg + 360 * k;                       // unwrap
      this.cPrev = c;
      // 실공간 좌표. outward 원뿔이라 바깥으로 갈수록 레이어가 내려간다.
      const z = 26 - r * Math.tan(theta);
      const x = r * Math.cos(phi);
      const y = r * Math.sin(phi);

      this.state = { x, y, z, r, phi, theta, b: theta * DEG, c };
      this.trail.push([x, y, z]);
      if (this.trail.length > 220) this.trail.shift();
      this.draw();
      this.report(initial);
    }

    report() {
      const s = this.state;
      if (this.out.b) this.out.b.textContent = `${s.b.toFixed(1)}°`;
      if (this.out.c) this.out.c.textContent = `${s.c.toFixed(1)}°`;
      if (this.out.theta) this.out.theta.textContent = `${s.b.toFixed(1)}°`;
      if (this.out.gcode) {
        this.out.gcode.textContent =
          `G1 X${s.x.toFixed(2)} Y${s.y.toFixed(2)} Z${s.z.toFixed(2)} ` +
          `B${s.b.toFixed(2)} C${s.c.toFixed(2)}`;
      }
    }

    /** 아이소메트릭 투영: 부품좌표 mm → 캔버스 px */
    project(x, y, z) {
      const s = this.scale;
      return [
        this.cx + (x - y) * 0.866 * s,
        this.cy - (x + y) * 0.5 * s - z * s
      ];
    }

    draw() {
      const ctx = this.ctx;
      if (!ctx || !this.state) return;
      const { x, y, z, r, phi, theta } = this.state;

      this.scale = Math.min(this.w / 84, this.h / 72);
      this.cx = this.w * 0.47;
      this.cy = this.h * 0.68;

      ctx.clearRect(0, 0, this.w, this.h);

      // 베드 (z=0)
      ctx.strokeStyle = "rgba(99,179,255,.34)";
      ctx.lineWidth = 1;
      for (const rr of [26, 17, 9]) {
        ctx.beginPath();
        for (let i = 0; i <= 48; i += 1) {
          const t = (i / 48) * Math.PI * 2;
          const p = this.project(rr * Math.cos(t), rr * Math.sin(t), 0);
          if (i === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]);
        }
        ctx.stroke();
      }

      // 회전축 (C 축)
      ctx.strokeStyle = "rgba(255,157,69,.55)";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      let a = this.project(0, 0, 0);
      let b = this.project(0, 0, 34);
      ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
      ctx.stroke();
      ctx.setLineDash([]);

      // 원뿔 레이어면: 반경별 링을 겹쳐 그린다 (바깥일수록 낮다 = outward)
      for (let rr = 6; rr <= 26; rr += 4) {
        const near = Math.abs(rr - r) < 2.4;
        ctx.strokeStyle = near ? "rgba(45,226,197,.95)" : "rgba(45,226,197,.2)";
        ctx.lineWidth = near ? 2 : 1;
        ctx.beginPath();
        for (let i = 0; i <= 48; i += 1) {
          const t = (i / 48) * Math.PI * 2;
          const p = this.project(rr * Math.cos(t), rr * Math.sin(t),
                                 26 - rr * Math.tan(theta));
          if (i === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]);
        }
        ctx.stroke();
      }

      // 이미 압출한 경로
      if (this.trail.length > 1) {
        ctx.lineWidth = 2.4;
        ctx.lineCap = "round";
        for (let i = 1; i < this.trail.length; i += 1) {
          const fade = i / this.trail.length;
          ctx.strokeStyle = `rgba(255,157,69,${(0.08 + 0.62 * fade).toFixed(3)})`;
          const p0 = this.project(...this.trail[i - 1]);
          const p1 = this.project(...this.trail[i]);
          ctx.beginPath();
          ctx.moveTo(p0[0], p0[1]);
          ctx.lineTo(p1[0], p1[1]);
          ctx.stroke();
        }
      }

      const tip = this.project(x, y, z);

      // 압출점에서의 수직 기준선 — 이것과 노즐 사이의 벌어짐이 B 다
      ctx.strokeStyle = "rgba(214,237,248,.34)";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      const up = this.project(x, y, z + 17);
      ctx.moveTo(tip[0], tip[1]); ctx.lineTo(up[0], up[1]);
      ctx.stroke();
      ctx.setLineDash([]);

      // 노즐 축 n̂ = sinθ·r̂(φ) + cosθ·ẑ  — 코드와 같은 식
      const nx = Math.sin(theta) * Math.cos(phi);
      const ny = Math.sin(theta) * Math.sin(phi);
      const nz = Math.cos(theta);
      const L = 17;
      const back = this.project(x + nx * L, y + ny * L, z + nz * L);

      ctx.strokeStyle = "#ff9d45";
      ctx.lineWidth = 5;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(tip[0], tip[1]); ctx.lineTo(back[0], back[1]);
      ctx.stroke();

      // 노즐 팁
      ctx.fillStyle = "#ffd9b0";
      ctx.beginPath();
      ctx.arc(tip[0], tip[1], 3.6, 0, Math.PI * 2);
      ctx.fill();

      // 히트블록 (B 축이 무엇을 통째로 기울이는지 보이도록)
      ctx.fillStyle = "rgba(255,157,69,.34)";
      const hb = this.project(x + nx * L * 1.02, y + ny * L * 1.02, z + nz * L * 1.02);
      ctx.beginPath();
      ctx.arc(hb[0], hb[1], 6.4, 0, Math.PI * 2);
      ctx.fill();

      // 라벨 — 화면 좌표에 고정해 잘리지 않게 한다
      ctx.font = "600 10.5px Consolas, monospace";
      ctx.fillStyle = "rgba(255,157,69,.85)";
      ctx.fillText("C축", b[0] + 5, b[1] + 3);

      const ly = this.h - 46;
      ctx.strokeStyle = "rgba(45,226,197,.85)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(10, ly); ctx.lineTo(24, ly);
      ctx.stroke();
      ctx.fillStyle = "rgba(45,226,197,.85)";
      ctx.fillText("원뿔 레이어면", 28, ly + 3.5);

      ctx.strokeStyle = "rgba(255,157,69,.85)";
      ctx.beginPath();
      ctx.moveTo(10, ly - 14); ctx.lineTo(24, ly - 14);
      ctx.stroke();
      ctx.fillStyle = "rgba(255,157,69,.85)";
      ctx.fillText("압출 경로 · 노즐", 28, ly - 10.5);
    }

    dispose() {
      this.stop();
      this.resizeObserver?.disconnect();
    }
  }

  /* ------------------------------------------------------------------ */

  window.addEventListener("DOMContentLoaded", () => {
    const slides = Array.from(document.querySelectorAll(".slides > section"));
    const scene = new ConicalNozzleScene();
    scene.initialize();
    window.rep5xNozzleScene = scene;

    document.addEventListener("presentation:slidechange", (event) => {
      replay(event.detail.slide);
      scene.setActive(event.detail.slideId === "slide-10");
    });

    // 첫 슬라이드는 slidechange 가 오기 전에도 연출이 필요하다.
    const first = document.querySelector(".slides > section.present")
      || document.querySelector(".slides > section.is-active")
      || slides[0];
    replay(first);
    if (first?.id === "slide-10") scene.setActive(true);

    window.addEventListener("pagehide", () => scene.dispose(), { once: true });
  });
})();
