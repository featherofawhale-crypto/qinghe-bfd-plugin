(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const canvas = document.getElementById("hero-canvas");
  const ctx = canvas?.getContext("2d");
  let width = 0;
  let height = 0;
  let particles = [];
  let raf = 0;

  function resizeCanvas() {
    if (!canvas || !ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    particles = Array.from({ length: Math.max(46, Math.floor(width / 18)) }, (_, i) => ({
      x: Math.random() * width,
      y: Math.random() * height,
      r: 0.6 + Math.random() * 2.2,
      vx: -0.25 + Math.random() * 0.5,
      vy: -0.18 + Math.random() * 0.36,
      hue: i % 3,
    }));
  }

  function drawCanvas() {
    if (!ctx || !canvas) return;
    ctx.clearRect(0, 0, width, height);
    const gradient = ctx.createRadialGradient(width * 0.68, height * 0.44, 30, width * 0.68, height * 0.44, Math.max(width, height) * 0.72);
    gradient.addColorStop(0, "rgba(117,214,157,0.32)");
    gradient.addColorStop(0.34, "rgba(224,180,91,0.16)");
    gradient.addColorStop(1, "rgba(6,8,7,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    particles.forEach((p, index) => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < -20) p.x = width + 20;
      if (p.x > width + 20) p.x = -20;
      if (p.y < -20) p.y = height + 20;
      if (p.y > height + 20) p.y = -20;
      ctx.beginPath();
      ctx.fillStyle = p.hue === 0 ? "rgba(117,214,157,0.62)" : p.hue === 1 ? "rgba(224,180,91,0.5)" : "rgba(225,127,99,0.44)";
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
      const next = particles[(index + 7) % particles.length];
      const dx = next.x - p.x;
      const dy = next.y - p.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 150) {
        ctx.strokeStyle = `rgba(245,241,232,${0.08 * (1 - dist / 150)})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(next.x, next.y);
        ctx.stroke();
      }
    });
    raf = requestAnimationFrame(drawCanvas);
  }

  resizeCanvas();
  if (!reduceMotion) drawCanvas();
  window.addEventListener("resize", resizeCanvas, { passive: true });

  const hasGsap = window.gsap && window.ScrollTrigger;
  if (!hasGsap || reduceMotion) return;

  const { gsap } = window;
  gsap.registerPlugin(window.ScrollTrigger);
  gsap.defaults({ duration: 0.9, ease: "power3.out" });

  const intro = gsap.timeline();
  intro
    .from(".site-header", { y: -18, autoAlpha: 0 })
    .from(".eyebrow", { y: 22, autoAlpha: 0 }, "-=0.25")
    .from(".hero h1", { y: 52, autoAlpha: 0, duration: 1.1 }, "-=0.2")
    .from(".hero-copy", { y: 30, autoAlpha: 0 }, "-=0.55")
    .from(".hero-actions a", { y: 20, autoAlpha: 0, stagger: 0.08 }, "-=0.48")
    .from(".hero-product", { x: 80, rotationY: -12, rotationZ: 2, autoAlpha: 0, duration: 1.2 }, "-=0.8")
    .from(".hud", { y: 16, scale: 0.9, autoAlpha: 0, stagger: 0.08 }, "-=0.45");

  gsap.to(".scan-line", {
    yPercent: 310,
    duration: 2.2,
    repeat: -1,
    yoyo: true,
    ease: "sine.inOut",
  });

  gsap.to(".hero-product", {
    y: -80,
    scale: 0.92,
    scrollTrigger: {
      trigger: ".hero",
      start: "top top",
      end: "bottom top",
      scrub: true,
    },
  });

  gsap.from(".availability div", {
    y: 36,
    autoAlpha: 0,
    stagger: 0.08,
    scrollTrigger: { trigger: ".availability", start: "top 82%" },
  });

  const steps = [...document.querySelectorAll(".story-steps > div")];
  const title = document.querySelector(".story-title");
  const text = document.querySelector(".story-text");

  if (window.matchMedia("(min-width: 901px)").matches) {
    gsap.set(".screen-results", { xPercent: 8, yPercent: 8, scale: 0.88, opacity: 0.45, rotationY: -8 });
    gsap.set(".screen-fonts", { xPercent: 16, yPercent: 16, scale: 0.76, opacity: 0.28, rotationY: -14 });

    const storyTl = gsap.timeline({
      scrollTrigger: {
        trigger: ".story",
        start: "top top",
        end: "bottom bottom",
        scrub: 0.6,
        onUpdate: (self) => {
          const index = Math.min(2, Math.floor(self.progress * 3));
          const step = steps[index];
          if (step && title && title.textContent !== step.dataset.title) {
            gsap.to([title, text], {
              y: -12,
              autoAlpha: 0,
              duration: 0.18,
              onComplete: () => {
                title.textContent = step.dataset.title;
                text.textContent = step.dataset.text;
                gsap.fromTo([title, text], { y: 14, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.32, stagger: 0.04 });
              },
            });
          }
        },
      },
    });

    storyTl
      .to(".screen-main", { xPercent: -16, yPercent: -4, scale: 0.84, opacity: 0.42, rotationY: 10 }, 0.14)
      .to(".screen-results", { xPercent: 0, yPercent: 0, scale: 1, opacity: 1, rotationY: 0 }, 0.14)
      .to(".screen-fonts", { xPercent: 10, yPercent: 10, scale: 0.84, opacity: 0.36, rotationY: -8 }, 0.14)
      .to(".screen-results", { xPercent: -16, yPercent: -4, scale: 0.84, opacity: 0.42, rotationY: 10 }, 0.58)
      .to(".screen-fonts", { xPercent: 0, yPercent: 0, scale: 1, opacity: 1, rotationY: 0 }, 0.58);

    gsap.to(".story-orbit", {
      rotation: 360,
      ease: "none",
      scrollTrigger: { trigger: ".story", start: "top bottom", end: "bottom top", scrub: true },
    });
  }

  gsap.utils.toArray(".feature-row article, .install-copy, .steps, .download-panel, .legal-section > div").forEach((el) => {
    gsap.from(el, {
      y: 42,
      autoAlpha: 0,
      scrollTrigger: { trigger: el, start: "top 84%" },
    });
  });

  gsap.utils.toArray(".feature-row article").forEach((card) => {
    const yTo = gsap.quickTo(card, "y", { duration: 0.35, ease: "power3.out" });
    card.addEventListener("mouseenter", () => yTo(-8));
    card.addEventListener("mouseleave", () => yTo(0));
  });

  window.addEventListener("pagehide", () => cancelAnimationFrame(raf), { once: true });
})();
