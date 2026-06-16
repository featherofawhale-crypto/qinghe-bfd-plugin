(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const bg = document.getElementById("vanta-bg");
  let bgRaf = 0;

  if (bg && !reduceMotion) {
    let targetX = 0.52;
    let targetY = 0.38;
    let currentX = targetX;
    let currentY = targetY;

    const renderPointerLight = () => {
      currentX += (targetX - currentX) * 0.12;
      currentY += (targetY - currentY) * 0.12;
      bg.style.setProperty("--mouse-x", `${(currentX * 100).toFixed(2)}%`);
      bg.style.setProperty("--mouse-y", `${(currentY * 100).toFixed(2)}%`);

      if (Math.abs(targetX - currentX) > 0.001 || Math.abs(targetY - currentY) > 0.001) {
        bgRaf = window.requestAnimationFrame(renderPointerLight);
      } else {
        bgRaf = 0;
      }
    };

    window.addEventListener(
      "pointermove",
      (event) => {
        targetX = event.clientX / window.innerWidth;
        targetY = event.clientY / window.innerHeight;
        if (!bgRaf) bgRaf = window.requestAnimationFrame(renderPointerLight);
      },
      { passive: true },
    );
  }

  if (bg && !reduceMotion && window.THREE) {
    const scene = new window.THREE.Scene();
    const camera = new window.THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 1, 1600);
    camera.position.z = 520;

    const renderer = new window.THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7));
    renderer.setSize(window.innerWidth, window.innerHeight);
    bg.appendChild(renderer.domElement);

    const count = window.innerWidth < 720 ? 520 : 980;
    const positions = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const palette = [
      [0.30, 0.49, 1.0],
      [0.47, 0.78, 1.0],
      [0.47, 0.91, 0.84],
      [0.87, 0.74, 0.45],
    ];

    for (let i = 0; i < count; i += 1) {
      const ix = i * 3;
      positions[ix] = (Math.random() - 0.5) * 1250;
      positions[ix + 1] = (Math.random() - 0.5) * 720;
      positions[ix + 2] = (Math.random() - 0.5) * 760;
      const color = palette[Math.floor(Math.random() * palette.length)];
      colors[ix] = color[0];
      colors[ix + 1] = color[1];
      colors[ix + 2] = color[2];
    }

    const geometry = new window.THREE.BufferGeometry();
    geometry.setAttribute("position", new window.THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new window.THREE.BufferAttribute(colors, 3));
    const material = new window.THREE.PointsMaterial({
      size: 2.2,
      vertexColors: true,
      transparent: true,
      opacity: 0.72,
      depthWrite: false,
      blending: window.THREE.AdditiveBlending,
    });
    const particles = new window.THREE.Points(geometry, material);
    scene.add(particles);

    const pointer = { x: 0, y: 0 };
    window.addEventListener(
      "pointermove",
      (event) => {
        pointer.x = (event.clientX / window.innerWidth - 0.5) * 2;
        pointer.y = (event.clientY / window.innerHeight - 0.5) * 2;
      },
      { passive: true },
    );

    let running = true;
    const tick = () => {
      if (!running) return;
      const time = performance.now() * 0.00018;
      particles.rotation.y += (pointer.x * 0.12 - particles.rotation.y) * 0.018;
      particles.rotation.x += (-pointer.y * 0.08 - particles.rotation.x) * 0.018;
      particles.position.x = Math.sin(time * 2.2) * 18 + pointer.x * 12;
      particles.position.y = Math.cos(time * 1.7) * 10 - pointer.y * 8;
      renderer.render(scene, camera);
      window.requestAnimationFrame(tick);
    };
    tick();

    window.addEventListener("resize", () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    });
    window.addEventListener("pagehide", () => {
      running = false;
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    });
  } else if (bg) {
    bg.classList.add("is-static");
  }

  const glowCards = document.querySelectorAll(
    ".hero-product, .quick-features div, .interface-switcher, .function-grid article, .innovation-list article, .steps, .mac-help-grid article, .download-panel, .platform-card, .netdisk-panel, .legal-section > div, .community-section > div:first-child, .donate-mini, .donate-grid article",
  );

  glowCards.forEach((card) => {
    card.addEventListener(
      "pointermove",
      (event) => {
        const rect = card.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * 100;
        const y = ((event.clientY - rect.top) / rect.height) * 100;
        card.style.setProperty("--card-x", `${x.toFixed(2)}%`);
        card.style.setProperty("--card-y", `${y.toFixed(2)}%`);
        card.classList.add("is-card-hovered");
      },
      { passive: true },
    );
    card.addEventListener("pointerleave", () => card.classList.remove("is-card-hovered"));
  });

  window.addEventListener(
    "pagehide",
    () => {
      if (bgRaf) window.cancelAnimationFrame(bgRaf);
    },
    { once: true },
  );

  const hasGsap = window.gsap && window.ScrollTrigger;
  if (!hasGsap || reduceMotion) return;

  const { gsap } = window;
  gsap.registerPlugin(window.ScrollTrigger);
  gsap.defaults({ duration: 0.9, ease: "power3.out" });

  const intro = gsap.timeline();
  intro
    .from(".site-header", { y: -14, autoAlpha: 0, duration: 0.42 })
    .from(".eyebrow", { y: 18, autoAlpha: 0, duration: 0.42 }, "-=0.2")
    .from(".hero h1", { y: 38, autoAlpha: 0, duration: 0.72 }, "-=0.14")
    .from(".hero-copy, .beta-note", { y: 22, autoAlpha: 0, stagger: 0.06, duration: 0.52 }, "-=0.36")
    .from(".hero-points span", { y: 14, autoAlpha: 0, stagger: 0.045, duration: 0.42 }, "-=0.32")
    .from(".hero-actions a", { y: 16, autoAlpha: 0, stagger: 0.06, duration: 0.42 }, "-=0.28")
    .from(".hero-product", { x: 54, rotationY: -8, rotationZ: 1.4, autoAlpha: 0, duration: 0.82 }, "-=0.68")
    .from(".hud", { y: 12, scale: 0.94, autoAlpha: 0, stagger: 0.06, duration: 0.36 }, "-=0.32");

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

  gsap.from(".quick-features", {
    y: 18,
    autoAlpha: 0,
    scrollTrigger: { trigger: ".quick-features", start: "top 86%" },
  });

  const switcher = document.querySelector(".interface-switcher");
  if (switcher) {
    const shots = [...switcher.querySelectorAll(".interface-stage .mock-shot")];
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

  gsap.utils.toArray(".function-grid article, .innovation-list article, .install-copy, .steps, .download-panel").forEach((el) => {
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

})();
