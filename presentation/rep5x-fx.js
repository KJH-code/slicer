/**
 * 발표 화면의 지속 효과.
 *
 * 표지의 별밭(Galaxy), 6쪽 배경 글자(ASCII Text), 표지 제목(Fuzzy Text),
 * 13쪽 배경(Ballpit). 전부 마우스와 무관하게 스스로 움직이는 배경 질감이다.
 * 유리 질감은 CSS 쪽(rep5x.css)에 있다.
 *
 * 배경 효과는 그 슬라이드가 화면에 있을 때만 돈다.
 * prefers-reduced-motion 이면 전부 켜지 않는다.
 */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const rand = (a, b) => a + Math.random() * (b - a);

  /* ================================================================== *
   * 공통: 슬라이드에 붙어 켜지고 꺼지는 캔버스 효과
   * ================================================================== */
  class CanvasEffect {
    constructor(host) {
      this.host = host;
      this.canvas = document.createElement("canvas");
      this.ctx = this.canvas.getContext("2d");
      host.appendChild(this.canvas);
      this.frame = null;
      this.ready = false;
      this.w = 0;
      this.h = 0;
      this.ratio = Math.min(window.devicePixelRatio || 1, 2);
      this.observer = new ResizeObserver(() => this.resize());
    }

    /** 서브클래스가 자기 상태를 다 만든 뒤에 부른다. */
    mount() {
      this.ready = true;
      this.observer.observe(this.host);
      this.resize();
    }

    resize() {
      const w = Math.max(1, this.host.clientWidth);
      const h = Math.max(1, this.host.clientHeight);
      if (w === this.w && h === this.h) return;
      this.w = w;
      this.h = h;
      this.canvas.width = Math.round(w * this.ratio);
      this.canvas.height = Math.round(h * this.ratio);
      this.ctx.setTransform(this.ratio, 0, 0, this.ratio, 0, 0);
      this.onResize?.();
      if (this.ready) this.render(0);
    }

    setActive(active) {
      if (active && !this.frame && !reduceMotion.matches) {
        let last = performance.now();
        const tick = (now) => {
          if (!this.frame) return;
          this.render(Math.min((now - last) / 1000, 0.05));
          last = now;
          this.frame = window.requestAnimationFrame(tick);
        };
        this.frame = window.requestAnimationFrame(tick);
      } else if (!active && this.frame) {
        window.cancelAnimationFrame(this.frame);
        this.frame = null;
      }
      if (active && this.ready) this.render(0);
    }

    dispose() {
      this.setActive(false);
      this.observer.disconnect();
      this.canvas.remove();
    }
  }

  /* ================================================================== *
   * Galaxy — 천천히 도는 별밭 (표지)
   * ================================================================== */
  class Galaxy extends CanvasEffect {
    constructor(host) {
      super(host);
      this.angle = 0;
      this.stars = Array.from({ length: 320 }, () => {
        const r = Math.pow(Math.random(), 0.6);
        return {
          r,
          a: rand(0, Math.PI * 2),
          z: rand(0.25, 1),                 // 크기·밝기용 깊이
          tw: rand(0, Math.PI * 2),         // 반짝임 위상
          hue: Math.random() < 0.22 ? "255,157,69" : "150,235,255"
        };
      });
      this.mount();
    }

    render(dt) {
      const ctx = this.ctx;
      this.angle += dt * 0.028;
      ctx.clearRect(0, 0, this.w, this.h);

      const cx = this.w * 0.5;
      const cy = this.h * 0.5;
      const span = Math.hypot(this.w, this.h) * 0.62;

      // 은하 중심의 옅은 빛
      const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, span * 0.8);
      glow.addColorStop(0, "rgba(45,226,197,.09)");
      glow.addColorStop(0.55, "rgba(60,120,190,.05)");
      glow.addColorStop(1, "transparent");
      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, this.w, this.h);

      for (const s of this.stars) {
        // 안쪽일수록 빠르게 도는 미분회전
        const a = s.a + this.angle * (1.6 - s.r);
        const d = s.r * span;
        const x = cx + Math.cos(a) * d * 1.22;
        const y = cy + Math.sin(a) * d * 0.62;
        if (x < -20 || x > this.w + 20 || y < -20 || y > this.h + 20) continue;
        s.tw += dt * 2.4;
        const alpha = (0.24 + 0.5 * s.z) * (0.62 + 0.38 * Math.sin(s.tw));
        ctx.fillStyle = `rgba(${s.hue},${alpha.toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(x, y, 0.5 + s.z * 1.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  /* ================================================================== *
   * Ballpit — 떠다니며 부딪히는 공 (출처 쪽 배경)
   * ================================================================== */
  class Ballpit extends CanvasEffect {
    constructor(host) {
      super(host);
      this.balls = [];
      this.mount();
    }

    onResize() {
      const colors = ["45,226,197", "255,157,69", "99,179,255", "185,156,255"];
      this.balls = Array.from({ length: 26 }, () => ({
        x: rand(60, this.w - 60),
        y: rand(60, this.h - 60),
        vx: rand(-26, 26),
        vy: rand(-26, 26),
        r: rand(14, 38),
        c: colors[Math.floor(Math.random() * colors.length)]
      }));
    }

    render(dt) {
      const ctx = this.ctx;
      const balls = this.balls;
      ctx.clearRect(0, 0, this.w, this.h);

      for (const b of balls) {
        b.x += b.vx * dt;
        b.y += b.vy * dt;
        if (b.x < b.r) { b.x = b.r; b.vx = Math.abs(b.vx); }
        if (b.x > this.w - b.r) { b.x = this.w - b.r; b.vx = -Math.abs(b.vx); }
        if (b.y < b.r) { b.y = b.r; b.vy = Math.abs(b.vy); }
        if (b.y > this.h - b.r) { b.y = this.h - b.r; b.vy = -Math.abs(b.vy); }
        // 너무 느려지지도, 빨라지지도 않게
        const sp = Math.hypot(b.vx, b.vy);
        const want = Math.min(Math.max(sp, 16), 90);
        if (sp > 0.01) { b.vx = b.vx / sp * want; b.vy = b.vy / sp * want; }
      }

      // 공끼리 튕김
      for (let i = 0; i < balls.length; i += 1) {
        for (let j = i + 1; j < balls.length; j += 1) {
          const a = balls[i];
          const b = balls[j];
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const d = Math.hypot(dx, dy);
          const min = a.r + b.r;
          if (d > 0.01 && d < min) {
            const nx = dx / d;
            const ny = dy / d;
            const overlap = (min - d) / 2;
            a.x -= nx * overlap; a.y -= ny * overlap;
            b.x += nx * overlap; b.y += ny * overlap;
            const av = a.vx * nx + a.vy * ny;
            const bv = b.vx * nx + b.vy * ny;
            a.vx += (bv - av) * nx; a.vy += (bv - av) * ny;
            b.vx += (av - bv) * nx; b.vy += (av - bv) * ny;
          }
        }
      }

      for (const b of balls) {
        const g = ctx.createRadialGradient(b.x - b.r * 0.3, b.y - b.r * 0.35, b.r * 0.1,
                                           b.x, b.y, b.r);
        g.addColorStop(0, `rgba(${b.c},.34)`);
        g.addColorStop(1, `rgba(${b.c},.05)`);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = `rgba(${b.c},.3)`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    }

  }

  /* ================================================================== *
   * ASCII Text — 글자를 아스키 블록으로 그려 물결치게 한다
   * ================================================================== */
  const ASCII_FONT = {
    "5": ["#####", "#....", "#....", "####.", "....#", "....#", "####."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."]
  };
  const RAMP = "@%#*+=-:.";

  class AsciiText {
    constructor(host) {
      this.host = host;
      this.t = 0;
      this.frame = null;
      const text = (host.dataset.text || "").toUpperCase();
      // 글자를 2배로 키운 픽셀 격자로 펼친다
      const rows = [];
      for (let r = 0; r < 7; r += 1) {
        let line = "";
        for (const ch of text) {
          const glyph = ASCII_FONT[ch] || ASCII_FONT[" "];
          for (const px of glyph[r]) line += px === "#" ? "##" : "..";
          line += "..";
        }
        rows.push(line, line);          // 세로도 2배
      }
      this.rows = rows;
    }

    setActive(active) {
      if (active && !this.frame && !reduceMotion.matches) {
        let last = performance.now();
        const tick = (now) => {
          if (!this.frame) return;
          this.t += (now - last) / 1000;
          last = now;
          this.draw();
          this.frame = window.requestAnimationFrame(tick);
        };
        this.frame = window.requestAnimationFrame(tick);
      } else if (!active && this.frame) {
        window.cancelAnimationFrame(this.frame);
        this.frame = null;
      }
      if (active) this.draw();
    }

    draw() {
      let out = "";
      for (let y = 0; y < this.rows.length; y += 1) {
        const row = this.rows[y];
        for (let x = 0; x < row.length; x += 1) {
          if (row[x] !== "#") { out += " "; continue; }
          const wave = Math.sin((x * 0.16) - (y * 0.24) + this.t * 2.1);
          out += RAMP[Math.floor((wave * 0.5 + 0.5) * (RAMP.length - 1))];
        }
        out += "\n";
      }
      this.host.textContent = out;
    }

    dispose() { this.setActive(false); }
  }

  /* ================================================================== *
   * Fuzzy Text — 제목을 캔버스에 그리고 줄마다 흔든다
   * ================================================================== */
  class FuzzyText {
    constructor(host) {
      this.host = host;
      this.text = host.dataset.fuzzy || host.textContent.trim();
      this.frame = null;
      this.intensity = 5;
      this.build();
      host.addEventListener("pointerenter", () => { this.intensity = 13; });
      host.addEventListener("pointerleave", () => { this.intensity = 5; });
    }

    build() {
      const style = window.getComputedStyle(this.host);
      const size = parseFloat(style.fontSize) || 72;
      const font = `${style.fontWeight} ${size}px ${style.fontFamily}`;
      const color = style.color;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const pad = 22;

      const measure = document.createElement("canvas").getContext("2d");
      measure.font = font;
      const m = measure.measureText(this.text);
      const w = Math.ceil(m.width) + pad * 2;
      const h = Math.ceil(size * 1.42) + pad * 2;

      this.src = document.createElement("canvas");
      this.src.width = Math.round(w * ratio);
      this.src.height = Math.round(h * ratio);
      const sctx = this.src.getContext("2d");
      sctx.scale(ratio, ratio);
      sctx.font = font;
      sctx.fillStyle = color;
      sctx.textBaseline = "middle";
      sctx.fillText(this.text, pad, h / 2);

      this.canvas = document.createElement("canvas");
      this.canvas.width = this.src.width;
      this.canvas.height = this.src.height;
      this.canvas.style.width = `${w}px`;
      this.canvas.style.height = `${h}px`;
      this.canvas.style.marginLeft = `${-pad}px`;
      this.canvas.style.marginBlock = `${-pad * 0.55}px`;
      this.ctx = this.canvas.getContext("2d");
      this.ratio = ratio;
      this.w = w;
      this.h = h;

      // 원본 글자는 스크린 리더용으로 남기고 화면에서만 감춘다
      const label = document.createElement("span");
      label.className = "fuzzy-text";
      label.textContent = this.text;
      this.host.textContent = "";
      this.host.append(label, this.canvas);
      this.host.classList.add("is-canvas");
      this.draw();
    }

    setActive(active) {
      if (active && !this.frame && !reduceMotion.matches) {
        const tick = () => {
          if (!this.frame) return;
          this.draw();
          this.frame = window.requestAnimationFrame(tick);
        };
        this.frame = window.requestAnimationFrame(tick);
      } else if (!active && this.frame) {
        window.cancelAnimationFrame(this.frame);
        this.frame = null;
      }
      if (active) this.draw();
    }

    draw() {
      const ctx = this.ctx;
      const H = this.src.height;
      ctx.clearRect(0, 0, this.src.width, H);
      for (let y = 0; y < H; y += 1) {
        const dx = (Math.random() - 0.5) * this.intensity * this.ratio;
        ctx.drawImage(this.src, 0, y, this.src.width, 1, dx, y, this.src.width, 1);
      }
    }

    dispose() { this.setActive(false); }
  }

  /* ================================================================== */

  const FACTORIES = { galaxy: Galaxy, ballpit: Ballpit };

  window.addEventListener("DOMContentLoaded", () => {
    const bound = [];   // [슬라이드 id, 효과]

    document.querySelectorAll("[data-fx]").forEach((host) => {
      const kind = host.dataset.fx;
      const slide = host.closest(".slide");
      let fx = null;
      if (FACTORIES[kind]) fx = new FACTORIES[kind](host);
      else if (kind === "ascii") fx = new AsciiText(host);
      if (fx) bound.push([slide?.id || "", fx]);
    });

    document.querySelectorAll("[data-fuzzy]").forEach((host) => {
      const slide = host.closest(".slide");
      bound.push([slide?.id || "", new FuzzyText(host)]);
    });

    const apply = (activeId) => bound.forEach(([id, fx]) => fx.setActive(id === activeId));

    document.addEventListener("presentation:slidechange",
      (e) => apply(e.detail.slideId));

    const first = document.querySelector(".slides > section.present")
      || document.querySelector(".slides > section.is-active");
    apply(first?.id || "slide-1");

    window.addEventListener("pagehide",
      () => bound.forEach(([, fx]) => fx.dispose()), { once: true });
  });
})();
