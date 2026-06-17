(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.documentElement;

  const setPointer = (event) => {
    const x = (event.clientX / window.innerWidth) * 100;
    const y = (event.clientY / window.innerHeight) * 100;
    root.style.setProperty("--mouse-x", `${x.toFixed(2)}%`);
    root.style.setProperty("--mouse-y", `${y.toFixed(2)}%`);
  };

  window.addEventListener("pointermove", setPointer, { passive: true });

  const cards = document.querySelectorAll(
    ".screenshot-frame, .tour-stage, .download-card, .feature-stack article, .workflow-grid article, .panel-gallery figure, .proof-strip article, .install-steps article, .star-panel, .donate-panel, .notice-section > div"
  );

  cards.forEach((card) => {
    card.addEventListener("pointermove", (event) => {
      const rect = card.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width) * 100;
      const y = ((event.clientY - rect.top) / rect.height) * 100;
      card.style.setProperty("--card-x", `${x.toFixed(2)}%`);
      card.style.setProperty("--card-y", `${y.toFixed(2)}%`);
      card.classList.add("is-card-hovered");
    });
    card.addEventListener("pointerleave", () => {
      card.classList.remove("is-card-hovered");
    });
  });

  const tour = document.querySelector(".screen-tour");
  if (tour) {
    const buttons = Array.from(tour.querySelectorAll("[data-shot]"));
    const shots = Array.from(tour.querySelectorAll(".tour-shot"));
    const title = tour.querySelector(".tour-copy h3");
    const label = tour.querySelector(".tour-index");
    const copy = tour.querySelector(".tour-copy p");
    let active = 0;
    let timer = null;

    const setShot = (index, userInitiated = false) => {
      active = (index + shots.length) % shots.length;
      tour.style.setProperty("--shot-index", active);
      shots.forEach((shot, shotIndex) => {
        shot.classList.toggle("is-active", shotIndex === active);
      });
      buttons.forEach((button, buttonIndex) => {
        const selected = buttonIndex === active;
        button.classList.toggle("is-active", selected);
        button.setAttribute("aria-selected", String(selected));
      });
      const shot = shots[active];
      if (title) title.textContent = shot.dataset.title || "";
      if (label) label.textContent = shot.dataset.label || "";
      if (copy) copy.textContent = shot.dataset.copy || "";
      if (userInitiated) restartTimer();
    };

    const restartTimer = () => {
      if (timer) window.clearInterval(timer);
      if (!reduceMotion) {
        timer = window.setInterval(() => setShot(active + 1), 5200);
      }
    };

    buttons.forEach((button) => {
      button.addEventListener("click", () => setShot(Number(button.dataset.shot), true));
    });

    setShot(0);
    restartTimer();
  }

  if (window.gsap && !reduceMotion) {
    if (window.ScrollTrigger) {
      gsap.registerPlugin(ScrollTrigger);
    }

    gsap.from(".hero-copy > *", {
      y: 24,
      opacity: 0,
      duration: 0.8,
      ease: "power3.out",
      stagger: 0.08,
    });

    gsap.from(".hero-visual", {
      y: 32,
      opacity: 0,
      rotateX: 3,
      duration: 0.95,
      ease: "power3.out",
      delay: 0.12,
    });

    if (window.ScrollTrigger) {
      gsap.utils
        .toArray(".proof-strip article, .section-copy, .screen-tour, .scan-layout, .workflow-grid article, .panel-gallery figure, .install-steps article, .download-card, .notice-section > div, .community-section > div")
        .forEach((element) => {
          gsap.from(element, {
            y: 34,
            opacity: 0,
            duration: 0.75,
            ease: "power3.out",
            scrollTrigger: {
              trigger: element,
              start: "top 84%",
              once: true,
            },
          });
        });

      gsap.to(".hero-frame", {
        y: -18,
        ease: "none",
        scrollTrigger: {
          trigger: ".hero",
          start: "top top",
          end: "bottom top",
          scrub: true,
        },
      });
    }
  }

  const canvas = document.getElementById("field-canvas");
  if (!canvas || reduceMotion) return;

  const ctx = canvas.getContext("2d", { alpha: true });
  let width = 0;
  let height = 0;
  let dpr = 1;
  let pointerX = window.innerWidth * 0.58;
  let pointerY = window.innerHeight * 0.34;
  let targetX = pointerX;
  let targetY = pointerY;
  const particles = [];
  const bands = [];

  const resize = () => {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    particles.length = 0;
    bands.length = 0;
    const count = Math.min(90, Math.max(42, Math.floor((width * height) / 21000)));
    for (let i = 0; i < count; i += 1) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.18,
        vy: (Math.random() - 0.5) * 0.18,
        r: Math.random() * 1.8 + 0.5,
        a: Math.random() * 0.26 + 0.08,
      });
    }
    for (let i = 0; i < 6; i += 1) {
      bands.push({
        y: height * (0.08 + i * 0.18),
        speed: 0.15 + i * 0.025,
        amp: 20 + i * 9,
        phase: Math.random() * Math.PI * 2,
      });
    }
  };

  window.addEventListener("resize", resize, { passive: true });
  window.addEventListener(
    "pointermove",
    (event) => {
      targetX = event.clientX;
      targetY = event.clientY;
    },
    { passive: true }
  );

  const drawBand = (band, time) => {
    const gradient = ctx.createLinearGradient(0, band.y - 80, width, band.y + 100);
    gradient.addColorStop(0, "rgba(60, 122, 255, 0)");
    gradient.addColorStop(0.45, "rgba(96, 152, 255, 0.12)");
    gradient.addColorStop(1, "rgba(125, 214, 255, 0)");
    ctx.beginPath();
    ctx.moveTo(0, band.y);
    for (let x = 0; x <= width + 24; x += 24) {
      const wave =
        Math.sin(x * 0.004 + time * band.speed + band.phase) * band.amp +
        Math.sin(x * 0.011 + time * 0.08) * 8;
      ctx.lineTo(x, band.y + wave);
    }
    ctx.lineTo(width, band.y + 120);
    ctx.lineTo(0, band.y + 120);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();
  };

  const render = (timeMs) => {
    const time = timeMs * 0.001;
    pointerX += (targetX - pointerX) * 0.08;
    pointerY += (targetY - pointerY) * 0.08;

    ctx.clearRect(0, 0, width, height);
    ctx.globalCompositeOperation = "source-over";

    bands.forEach((band) => drawBand(band, time));

    const halo = ctx.createRadialGradient(pointerX, pointerY, 0, pointerX, pointerY, Math.min(width, height) * 0.42);
    halo.addColorStop(0, "rgba(98, 159, 255, 0.18)");
    halo.addColorStop(0.38, "rgba(74, 132, 255, 0.07)");
    halo.addColorStop(1, "rgba(74, 132, 255, 0)");
    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, width, height);

    ctx.globalCompositeOperation = "lighter";
    particles.forEach((particle) => {
      const dx = pointerX - particle.x;
      const dy = pointerY - particle.y;
      const distSq = dx * dx + dy * dy;
      if (distSq < 36000) {
        const force = (1 - distSq / 36000) * 0.015;
        particle.vx -= dx * force * 0.01;
        particle.vy -= dy * force * 0.01;
      }

      particle.x += particle.vx + Math.sin(time * 0.35 + particle.y * 0.006) * 0.12;
      particle.y += particle.vy + Math.cos(time * 0.28 + particle.x * 0.005) * 0.08;
      particle.vx *= 0.995;
      particle.vy *= 0.995;

      if (particle.x < -20) particle.x = width + 20;
      if (particle.x > width + 20) particle.x = -20;
      if (particle.y < -20) particle.y = height + 20;
      if (particle.y > height + 20) particle.y = -20;

      ctx.beginPath();
      ctx.arc(particle.x, particle.y, particle.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(126, 211, 255, ${particle.a})`;
      ctx.fill();
    });

    requestAnimationFrame(render);
  };

  resize();
  requestAnimationFrame(render);
})();
