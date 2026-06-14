(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const hasGsap = window.gsap;

  if (!hasGsap || reduceMotion) {
    document.documentElement.classList.add("motion-ready");
    return;
  }

  const { gsap } = window;
  gsap.registerPlugin(window.ScrollTrigger);
  gsap.defaults({ ease: "power3.out", duration: 0.8 });

  document.documentElement.classList.add("motion-ready");

  const intro = gsap.timeline();
  intro
    .from(".site-header", { y: -18, autoAlpha: 0, duration: 0.7 })
    .from(".eyebrow", { y: 16, autoAlpha: 0 }, "-=0.25")
    .from(".hero h1", { y: 34, autoAlpha: 0, duration: 0.95 }, "-=0.2")
    .from(".hero-copy", { y: 22, autoAlpha: 0 }, "-=0.45")
    .from(".hero-actions a", { y: 18, autoAlpha: 0, stagger: 0.08 }, "-=0.35")
    .from(".hero-stats div", { y: 18, autoAlpha: 0, stagger: 0.08 }, "-=0.35")
    .from(".signal-board", { x: 26, y: 18, rotation: 1.8, autoAlpha: 0, duration: 1 }, "-=0.8");

  gsap.to(".signal-board", {
    y: -18,
    rotation: -0.6,
    scrollTrigger: {
      trigger: ".hero",
      start: "top top",
      end: "bottom top",
      scrub: 0.8,
    },
  });

  gsap.to(".clip", {
    xPercent: 6,
    duration: 3.2,
    repeat: -1,
    yoyo: true,
    stagger: 0.24,
    ease: "sine.inOut",
  });

  gsap.to(".marker", {
    y: -5,
    duration: 1.25,
    repeat: -1,
    yoyo: true,
    stagger: 0.2,
    ease: "sine.inOut",
  });

  gsap.to(".waveform i", {
    scaleY: (i) => [1.5, 0.65, 1.1, 1.9, 0.8, 1.35][i % 6],
    transformOrigin: "bottom center",
    duration: 0.9,
    repeat: -1,
    yoyo: true,
    stagger: { each: 0.05, from: "center" },
    ease: "sine.inOut",
  });

  gsap.utils.toArray(".section-heading, .intro-grid > *, .feature-card, .preview-layout figure, .install-layout > *, .download-panel, .legal-grid > div").forEach((el) => {
    gsap.from(el, {
      y: 34,
      autoAlpha: 0,
      duration: 0.82,
      scrollTrigger: {
        trigger: el,
        start: "top 84%",
      },
    });
  });

  gsap.utils.toArray(".parallax-image").forEach((img) => {
    gsap.fromTo(
      img,
      { yPercent: -2, scale: 1.04 },
      {
        yPercent: 3,
        scale: 1.06,
        ease: "none",
        scrollTrigger: {
          trigger: img.closest("figure"),
          start: "top bottom",
          end: "bottom top",
          scrub: true,
        },
      },
    );
  });

  gsap.utils.toArray(".feature-card").forEach((card) => {
    const xTo = gsap.quickTo(card, "x", { duration: 0.35, ease: "power3.out" });
    const yTo = gsap.quickTo(card, "y", { duration: 0.35, ease: "power3.out" });

    card.addEventListener("mousemove", (event) => {
      const rect = card.getBoundingClientRect();
      xTo((event.clientX - rect.left - rect.width / 2) * 0.03);
      yTo((event.clientY - rect.top - rect.height / 2) * 0.03);
    });

    card.addEventListener("mouseleave", () => {
      xTo(0);
      yTo(0);
    });
  });
})();
