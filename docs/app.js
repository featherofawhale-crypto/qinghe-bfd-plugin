(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const bg = document.getElementById("vanta-bg");
  if (bg && !reduceMotion && window.VANTA?.FOG && window.THREE) {
    const effect = window.VANTA.FOG({
      el: bg,
      THREE: window.THREE,
      mouseControls: true,
      touchControls: true,
      gyroControls: false,
      minHeight: 200,
      minWidth: 200,
      highlightColor: 0x75d69d,
      midtoneColor: 0x173126,
      lowlightColor: 0x060807,
      baseColor: 0x050706,
      blurFactor: 0.62,
      speed: 0.75,
      zoom: 0.72,
    });
    window.addEventListener("pagehide", () => effect.destroy());
  } else if (bg) {
    bg.classList.add("is-static");
  }

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
    .from(".hero-points span", { y: 18, autoAlpha: 0, stagger: 0.06 }, "-=0.48")
    .from(".hero-actions a", { y: 20, autoAlpha: 0, stagger: 0.08 }, "-=0.42")
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

  gsap.from(".quick-features div", {
    y: 36,
    autoAlpha: 0,
    stagger: 0.08,
    scrollTrigger: { trigger: ".quick-features", start: "top 82%" },
  });

  const switcher = document.querySelector(".interface-switcher");
  if (switcher) {
    const shots = [...switcher.querySelectorAll(".interface-stage img")];
    const buttons = [...switcher.querySelectorAll(".interface-tabs button")];
    const kicker = switcher.querySelector(".interface-kicker");
    const title = switcher.querySelector(".interface-copy h3");
    const copy = switcher.querySelector(".interface-copy p");
    let activeShot = 0;
    let timer = 0;

    const showShot = (index) => {
      activeShot = (index + shots.length) % shots.length;
      switcher.style.setProperty("--shot-index", String(activeShot));
      shots.forEach((shot, shotIndex) => {
        shot.classList.toggle("is-active", shotIndex === activeShot);
      });
      buttons.forEach((button, buttonIndex) => {
        const selected = buttonIndex === activeShot;
        button.classList.toggle("is-active", selected);
        button.setAttribute("aria-selected", String(selected));
      });
      const shot = shots[activeShot];
      if (shot && kicker && title && copy) {
        gsap.to([kicker, title, copy], {
          y: -8,
          autoAlpha: 0,
          duration: 0.16,
          onComplete: () => {
            kicker.textContent = shot.dataset.kicker || "";
            title.textContent = shot.dataset.title || "";
            copy.textContent = shot.dataset.copy || "";
            gsap.fromTo([kicker, title, copy], { y: 10, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.28, stagger: 0.035 });
          },
        });
      }
    };

    const restartTimer = () => {
      window.clearInterval(timer);
      timer = window.setInterval(() => showShot(activeShot + 1), 4200);
    };

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        showShot(Number(button.dataset.shot || 0));
        restartTimer();
      });
    });

    restartTimer();

    gsap.from(switcher, {
      y: 54,
      clipPath: "inset(10% 0 10% 0)",
      autoAlpha: 0,
      scrollTrigger: { trigger: switcher, start: "top 82%" },
    });

    gsap.fromTo(
      ".interface-stage",
      { y: 28 },
      {
        y: -18,
        scrollTrigger: {
          trigger: switcher,
          start: "top bottom",
          end: "bottom top",
          scrub: true,
        },
      },
    );
  }

  gsap.utils.toArray(".function-grid article, .innovation-list article, .install-copy, .steps, .download-panel, .legal-section > div").forEach((el) => {
    gsap.from(el, {
      y: 42,
      autoAlpha: 0,
      scrollTrigger: { trigger: el, start: "top 84%" },
    });
  });

  gsap.utils.toArray(".function-grid article, .innovation-list article").forEach((card) => {
    const yTo = gsap.quickTo(card, "y", { duration: 0.35, ease: "power3.out" });
    card.addEventListener("mouseenter", () => yTo(-8));
    card.addEventListener("mouseleave", () => yTo(0));
  });

  window.addEventListener("pagehide", () => cancelAnimationFrame(raf), { once: true });
})();
