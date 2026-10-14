/* Animated "neural network" background inspired by the Cybok logo's molecule nodes. */
export function startNetwork(canvas, { density = 0.00009, maxDist = 140 } = {}) {
  if (!canvas || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const ctx = canvas.getContext("2d");
  let w, h, nodes = [], raf, mouse = { x: -9999, y: -9999 };
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const colors = ["255,52,72", "176,61,255", "47,115,255"];

  function resize() {
    const r = canvas.getBoundingClientRect();
    w = r.width; h = r.height;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.max(24, Math.min(110, Math.floor(w * h * density)));
    nodes = Array.from({ length: n }, () => ({
      x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - 0.5) * 0.35, vy: (Math.random() - 0.5) * 0.35,
      r: Math.random() * 2 + 1, c: colors[Math.floor(Math.random() * colors.length)],
    }));
  }

  function frame() {
    ctx.clearRect(0, 0, w, h);
    for (const n of nodes) {
      n.x += n.vx; n.y += n.vy;
      if (n.x < 0 || n.x > w) n.vx *= -1;
      if (n.y < 0 || n.y > h) n.vy *= -1;
      const dx = n.x - mouse.x, dy = n.y - mouse.y, d = Math.hypot(dx, dy);
      if (d < 120) { n.x += dx / d; n.y += dy / d; }
    }
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < maxDist) {
          ctx.strokeStyle = `rgba(${a.c},${(1 - d / maxDist) * 0.35})`;
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
    }
    for (const n of nodes) {
      ctx.fillStyle = `rgba(${n.c},0.9)`;
      ctx.shadowColor = `rgba(${n.c},0.9)`;
      ctx.shadowBlur = 10;
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill();
    }
    ctx.shadowBlur = 0;
    raf = requestAnimationFrame(frame);
  }

  resize();
  frame();
  addEventListener("resize", () => { cancelAnimationFrame(raf); resize(); frame(); });
  canvas.parentElement.addEventListener("mousemove", (e) => {
    const r = canvas.getBoundingClientRect();
    mouse = { x: e.clientX - r.left, y: e.clientY - r.top };
  });
  canvas.parentElement.addEventListener("mouseleave", () => { mouse = { x: -9999, y: -9999 }; });
  document.addEventListener("visibilitychange", () => { if (document.hidden) cancelAnimationFrame(raf); else frame(); });
}
