/* Create Image + Logo Studio views. */
import { $, api, confirmDialog, esc, h, icon, lightbox, toast } from "./core.js";
import { state } from "./state.js";

const SURPRISE = [
  "A futuristic city at night with neon red and blue lights reflecting on wet streets",
  "A cozy reading nook inside a giant seashell, warm lamp light, ocean outside the window",
  "An astronaut riding a camel across the dunes of Cholistan under a sky full of stars",
  "A tiny dragon sleeping on a stack of old books, soft morning light",
  "The Badshahi Mosque in Lahore reimagined in the year 2200, holographic gardens",
  "A robot barista making latte art in a minimalist cafe, isometric view",
  "A floating island with waterfalls, lush forest and a small glass house at sunset",
  "A majestic snow leopard on a Karakoram peak, golden hour, ultra detailed",
  "A retro-futuristic train crossing a bridge over a canyon, synthwave colors",
  "A watercolor of a busy Faisalabad bazaar with colorful fabrics and rickshaws",
];

function tile(item, { onChange, logo = false } = {}) {
  const t = h("div", { class: `tile ${logo ? "logo-tile" : ""}` });
  const img = h("img", { src: item.url + (item.url.includes("/media/file/") ? "?thumb=1" : ""), alt: item.prompt || item.title || "", loading: "lazy" });
  img.addEventListener("click", () => lightbox(item.url, item.title || item.prompt, item.download_url));
  t.append(img);
  if (logo) t.append(h("span", { class: `badge tag ${item.meta?.kind === "ai" ? "grad" : "gray"}`, text: item.meta?.kind === "ai" ? "AI concept" : item.meta?.concept || "Vector" }));
  const ov = h("div", { class: "overlay" });
  const save = h("button", { class: `icon-btn ${item.saved ? "on" : ""}`, title: item.saved ? "Saved to Library" : "Save to Library", html: icon("bookmark", "sm") });
  save.addEventListener("click", async () => {
    try {
      const r = await api(`/api/generated/${item.id}`, { method: "PATCH", body: { saved: !item.saved } });
      Object.assign(item, r.item);
      save.classList.toggle("on", item.saved);
      save.title = item.saved ? "Saved to Library" : "Save to Library";
      toast(item.saved ? "Saved to Library" : "Removed from Library", { type: "success" });
    } catch (e) { toast(e.message, { type: "error" }); }
  });
  ov.append(h("span", { class: "cap", text: item.title || item.prompt || "" }), save,
    h("a", { class: "icon-btn", href: item.download_url, title: "Download", html: icon("download", "sm") }));
  if (onChange?.regenerate) ov.append(h("button", { class: "icon-btn", title: "Regenerate", html: icon("refresh", "sm"), onclick: () => onChange.regenerate(item) }));
  if (onChange?.reuse) ov.append(h("button", { class: "icon-btn", title: "Use this prompt", html: icon("edit", "sm"), onclick: () => onChange.reuse(item) }));
  ov.append(h("button", {
    class: "icon-btn", title: "Delete", html: icon("trash", "sm"), onclick: async () => {
      if (!await confirmDialog({ title: "Delete this item?", message: "It will be removed from your history and Library.", confirm: "Delete", danger: true })) return;
      try { await api(`/api/generated/${item.id}`, { method: "DELETE" }); t.style.animation = "fadeIn .2s reverse forwards"; setTimeout(() => t.remove(), 180); }
      catch (e) { toast(e.message, { type: "error" }); }
    },
  }));
  t.append(ov);
  return t;
}

function emptyState(ic, title, text) {
  return h("div", { class: "empty", html: `<div class="ei">${icon(ic)}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>` });
}

/* ================================================================ images */
let imagesBuilt = false;
const img = { style: "none", size: "square", count: 2 };

export function showImages(root) {
  if (imagesBuilt) { loadImageHistory(); return; }
  imagesBuilt = true;
  const ta = h("textarea", { id: "imgPrompt", rows: 2, maxlength: 1500, placeholder: "Describe the image you want… e.g. “A futuristic city at night”", "aria-label": "Image prompt" });
  const gen = h("button", { class: "btn brand lg", html: icon("sparkles") + "<span>Generate</span>" });
  const chips = h("div", { class: "style-chips", role: "radiogroup", "aria-label": "Style" });
  state.imageStyles.forEach((s) => {
    const c = h("button", { class: `chip ${s.key === img.style ? "on" : ""}`, text: s.label, role: "radio" });
    c.addEventListener("click", () => { img.style = s.key; chips.querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === c)); });
    chips.append(c);
  });
  const sizeSeg = h("div", { class: "segmented", "aria-label": "Size" });
  [["square", "Square"], ["portrait", "Portrait"], ["landscape", "Landscape"], ["wide", "Wide"]].forEach(([k, l]) => {
    const b = h("button", { class: k === img.size ? "on" : "", text: l });
    b.addEventListener("click", () => { img.size = k; sizeSeg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); });
    sizeSeg.append(b);
  });
  const countSeg = h("div", { class: "segmented", "aria-label": "Number of images" });
  [1, 2, 3, 4].forEach((n) => {
    const b = h("button", { class: n === img.count ? "on" : "", text: String(n) });
    b.addEventListener("click", () => { img.count = n; countSeg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); });
    countSeg.append(b);
  });
  const surprise = h("button", { class: "btn sm ghost", html: icon("dice", "sm") + "Surprise me" });
  surprise.addEventListener("click", () => { ta.value = SURPRISE[Math.floor(Math.random() * SURPRISE.length)]; ta.focus(); });
  const results = h("div", { class: "gallery big", id: "imgResults" });
  const progress = h("div", { class: "gen-progress", hidden: true });
  const history = h("div", { class: "gallery", id: "imgHistory" });

  const page = h("div", { class: "page" }, h("div", { class: "page-inner" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", { html: 'Create <span class="grad-text">Image</span>' }), h("p", { text: "Turn your words into pictures. Free — powered by open image models." }))),
    h("div", { class: "studio-card" },
      h("div", { class: "prompt-box" }, ta, gen), chips,
      h("div", { class: "studio-opts" }, h("span", { class: "label", text: "Size" }), sizeSeg, h("span", { class: "label", text: "Images" }), countSeg, h("span", { class: "spacer" }), surprise)),
    progress, results,
    h("div", { class: "section-title" }, h("h2", { text: "Your images" }), h("span", { class: "muted", text: "Save the ones you like to your Library" })),
    history));
  root.append(page);

  const run = async (prompt, { style = img.style, size = img.size, count = img.count } = {}) => {
    if (prompt.trim().length < 3) { toast("Describe your image in a few words first."); ta.focus(); return; }
    gen.disabled = true;
    gen.innerHTML = '<span class="spinner"></span><span>Creating…</span>';
    progress.hidden = false;
    progress.innerHTML = `<span class="spinner"></span><span>Creating ${count} image${count > 1 ? "s" : ""} — this usually takes 5–30 seconds…</span>`;
    const skeletons = Array.from({ length: count }, () => h("div", { class: "tile skeleton", "data-label": "Painting pixels…" }));
    results.prepend(...skeletons);
    try {
      const r = await api("/api/images", { method: "POST", body: { prompt, style, size, count } });
      skeletons.forEach((s) => s.remove());
      const hooks = { regenerate: (it) => run(it.prompt, { style: it.style || "none", size: it.meta?.size || "square", count: 1 }), reuse: (it) => { ta.value = it.prompt; ta.focus(); window.scrollTo(0, 0); } };
      r.items.reverse().forEach((it) => results.prepend(tile(it, { onChange: hooks })));
      progress.innerHTML = `${icon("check")}<span>Done! Hover an image to save, download or regenerate it.</span>`;
      loadImageHistory();
    } catch (e) {
      skeletons.forEach((s) => s.remove());
      progress.hidden = true;
      toast(e.message, { type: "error", timeout: 6000 });
    } finally {
      gen.disabled = false;
      gen.innerHTML = icon("sparkles") + "<span>Generate</span>";
    }
  };
  gen.addEventListener("click", () => run(ta.value));
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); run(ta.value); } });
  loadImageHistory();
  setTimeout(() => ta.focus(), 50);
}

async function loadImageHistory() {
  const box = $("#imgHistory");
  if (!box) return;
  try {
    const r = await api("/api/generated?type=image&limit=60");
    box.innerHTML = "";
    if (!r.items.length) { box.append(emptyState("image", "No images yet", "Write a prompt above and press Generate.")); box.style.display = "block"; return; }
    box.style.display = "";
    const hooks = { reuse: (it) => { const ta = $("#imgPrompt"); ta.value = it.prompt; ta.focus(); window.scrollTo(0, 0); } };
    r.items.forEach((it) => box.append(tile(it, { onChange: hooks })));
  } catch (e) { toast(e.message, { type: "error" }); }
}

/* ================================================================ logos */
let logosBuilt = false;
const COLOR_HEX = { blue: "#2563eb", navy: "#1e3a8a", sky: "#0ea5e9", cyan: "#06b6d4", teal: "#0d9488", green: "#16a34a", emerald: "#059669", lime: "#65a30d", yellow: "#eab308", gold: "#d4a017", amber: "#f59e0b", orange: "#f97316", coral: "#fb7185", red: "#dc2626", crimson: "#be123c", maroon: "#7f1d1d", pink: "#ec4899", rose: "#f43f5e", magenta: "#d946ef", purple: "#7c3aed", violet: "#8b5cf6", indigo: "#4f46e5", brown: "#92400e", black: "#0b0b0f", white: "#ffffff", gray: "#6b7280", grey: "#6b7280", silver: "#9ca3af", turquoise: "#14b8a6", mint: "#34d399" };

export function showLogos(root) {
  if (logosBuilt) { loadLogoHistory(); return; }
  logosBuilt = true;
  const field = (label, el, hint) => h("div", { class: "field" }, h("label", { text: label }), el, hint ? h("span", { class: "hint", text: hint }) : null);
  const sel = (opts) => h("select", { class: "select" }, ...opts.map((o) => h("option", { value: o, text: o })));
  const brand = h("input", { class: "input", placeholder: "e.g. NovaTech", maxlength: 40, required: true });
  const industry = h("input", { class: "input", placeholder: "e.g. Technology", maxlength: 60 });
  const style = sel(["Minimal", "Modern", "Bold", "Elegant / Luxury", "Playful", "Vintage", "Futuristic", "Corporate"]);
  const colors = h("input", { class: "input", placeholder: "e.g. Blue + White, or #ff3448", maxlength: 60 });
  const swatches = h("div", { class: "swatches" });
  const symbol = h("input", { class: "input", placeholder: "e.g. lightning, leaf, network, shield", maxlength: 80 });
  const typo = sel(["Modern sans", "Geometric", "Bold", "Serif", "Elegant", "Rounded", "Mono", "Script"]);
  const ai = sel(["2 AI concepts", "4 AI concepts", "Vector only (instant)"]);
  colors.addEventListener("input", () => {
    swatches.innerHTML = "";
    const v = colors.value.toLowerCase();
    const found = [...(v.match(/#[0-9a-f]{6}\b|#[0-9a-f]{3}\b/g) || []), ...(v.match(/[a-z]+/g) || []).map((w) => COLOR_HEX[w]).filter(Boolean)];
    found.slice(0, 5).forEach((c) => swatches.append(h("span", { style: { background: c }, title: c })));
  });
  const gen = h("button", { class: "btn brand lg", html: icon("sparkles") + "<span>Generate logos</span>" });
  const results = h("div", { class: "gallery big", id: "logoResults" });
  const progress = h("div", { class: "gen-progress", hidden: true });
  const history = h("div", { class: "gallery", id: "logoHistory" });

  const page = h("div", { class: "page" }, h("div", { class: "page-inner" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", { html: 'Logo <span class="grad-text">Studio</span>' }), h("p", { text: "Describe your brand and get instant vector logos plus AI-designed concepts — free." }))),
    h("div", { class: "studio-card" },
      h("div", { class: "logo-form" },
        field("Brand name *", brand), field("Industry", industry), field("Style", style),
        h("div", { class: "field" }, h("label", { text: "Colors" }), colors, swatches), field("Symbol preference", symbol), field("Typography", typo)),
      h("div", { class: "studio-opts" }, field("AI concepts", ai), h("span", { class: "spacer" }), gen)),
    progress, results,
    h("div", { class: "section-title" }, h("h2", { text: "Logo history" }), h("span", { class: "muted", text: "Save favourites to your Library" })),
    history));
  root.append(page);

  gen.addEventListener("click", async () => {
    if (!brand.value.trim()) { toast("Enter your brand name first."); brand.focus(); return; }
    const aiCount = ai.value.startsWith("4") ? 4 : ai.value.startsWith("2") ? 2 : 0;
    gen.disabled = true;
    gen.innerHTML = '<span class="spinner"></span><span>Designing…</span>';
    progress.hidden = false;
    progress.innerHTML = `<span class="spinner"></span><span>${aiCount ? "Drawing vector concepts and asking the AI designer — about 10–40 seconds…" : "Drawing vector concepts…"}</span>`;
    const skeletons = Array.from({ length: aiCount }, () => h("div", { class: "tile logo-tile skeleton", "data-label": "AI is designing…" }));
    results.prepend(...skeletons);
    try {
      const r = await api("/api/logos", {
        method: "POST",
        body: { brand: brand.value, industry: industry.value, style: style.value, colors: colors.value, symbol: symbol.value, typography: typo.value, ai_count: aiCount },
      });
      skeletons.forEach((s) => s.remove());
      results.innerHTML = "";
      r.items.forEach((it, i) => { const t = tile(it, { logo: true }); t.style.animationDelay = `${i * 40}ms`; results.append(t); });
      progress.innerHTML = r.ai_error ? `${icon("alert")}<span>Vector concepts ready. AI concepts failed: ${esc(r.ai_error)}</span>` : `${icon("check")}<span>${r.items.length} logo concepts ready. Save your favourites to the Library.</span>`;
      loadLogoHistory();
    } catch (e) {
      skeletons.forEach((s) => s.remove());
      progress.hidden = true;
      toast(e.message, { type: "error" });
    } finally {
      gen.disabled = false;
      gen.innerHTML = icon("sparkles") + "<span>Generate logos</span>";
    }
  });
  loadLogoHistory();
  setTimeout(() => brand.focus(), 50);
}

async function loadLogoHistory() {
  const box = $("#logoHistory");
  if (!box) return;
  try {
    const r = await api("/api/generated?type=logo&limit=60");
    box.innerHTML = "";
    if (!r.items.length) { box.append(emptyState("pen", "No logos yet", "Fill in your brand details above and press Generate.")); box.style.display = "block"; return; }
    box.style.display = "";
    r.items.forEach((it) => box.append(tile(it, { logo: true })));
  } catch (e) { toast(e.message, { type: "error" }); }
}

