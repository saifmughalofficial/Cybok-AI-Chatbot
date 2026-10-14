/* Markdown rendering: GFM + syntax highlighting + KaTeX math + collapsible reasoning. Output is sanitized. */
import { copyText, esc, icon, toast } from "./core.js";

const hasLibs = () => typeof window.marked !== "undefined" && typeof window.DOMPurify !== "undefined";
let configured = false;

function configure() {
  if (configured || !hasLibs()) return;
  configured = true;
  const renderer = new window.marked.Renderer();
  renderer.code = function (token, langArg) {
    const text = typeof token === "object" ? token.text : token;
    const lang = ((typeof token === "object" ? token.lang : langArg) || "").trim().split(/\s+/)[0];
    const label = lang || "code";
    return `<div class="code-block"><div class="code-head"><span>${esc(label)}</span>` +
      `<button type="button" class="code-copy" aria-label="Copy code">${icon("copy", "sm")}<span>Copy</span></button></div>` +
      `<pre><code class="${lang ? "language-" + esc(lang) : ""}">${esc(text)}</code></pre></div>`;
  };
  window.marked.setOptions({ gfm: true, breaks: false, renderer });
}

const MATH_BLOCK = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]/g;
const MATH_INLINE = /\\\(([\s\S]+?)\\\)|(?<![\\$\w])\$(?!\s)([^$\n]+?)(?<!\s)\$(?![\d$])/g;

function protect(text) {
  const code = [];
  const math = [];
  // 1. hide code so math/think detection never touches it
  let t = text.replace(/```[\s\S]*?(?:```|$)|`[^`\n]+`/g, (m) => `KXCODE${code.push(m) - 1}XK`);
  // 2. math
  if (window.katex) {
    t = t.replace(MATH_BLOCK, (m, a, b) => `\n\nKXMATH${math.push({ tex: a ?? b, display: true }) - 1}XK\n\n`);
    t = t.replace(MATH_INLINE, (m, a, b) => `KXMATH${math.push({ tex: a ?? b, display: false }) - 1}XK`);
  }
  // 3. restore code for marked
  t = t.replace(/KXCODE(\d+)XK/g, (m, i) => code[+i]);
  return { text: t, math };
}

function splitThink(text) {
  // Reasoning models stream <think>...</think>; show it as a collapsible block.
  const blocks = [];
  let t = text.replace(/<think>([\s\S]*?)(<\/think>|$)/g, (m, inner, closed) => {
    blocks.push({ inner: inner.trim(), done: !!closed });
    return `\n\nKXTHINK${blocks.length - 1}XK\n\n`;
  });
  return { text: t, blocks };
}

export function renderMarkdown(src, { streaming = false } = {}) {
  configure();
  const { text: noThink, blocks } = splitThink(src || "");
  if (!hasLibs()) {
    return `<p style="white-space:pre-wrap">${esc(noThink.replace(/KXTHINK\d+XK/g, ""))}</p>`;
  }
  const { text, math } = protect(noThink);
  let html = window.marked.parse(text);
  html = window.DOMPurify.sanitize(html, { ADD_ATTR: ["target"], FORBID_TAGS: ["style", "form", "input"] });
  html = html.replace(/KXMATH(\d+)XK/g, (m, i) => {
    const { tex, display } = math[+i];
    try {
      return window.katex.renderToString(tex, { displayMode: display, throwOnError: false, output: "html" });
    } catch {
      return esc(tex);
    }
  });
  html = html.replace(/(?:<p>)?KXTHINK(\d+)XK(?:<\/p>)?/g, (m, i) => {
    const b = blocks[+i];
    const label = b.done ? "Reasoning" : "Thinking…";
    return `<details class="think"${!b.done && streaming ? " open" : ""}><summary>${label}</summary><div class="think-body">${esc(b.inner)}</div></details>`;
  });
  return html;
}

export function enhance(container, { final = true } = {}) {
  container.querySelectorAll("table").forEach((t) => {
    if (!t.parentElement.classList.contains("table-wrap")) {
      const w = document.createElement("div");
      w.className = "table-wrap";
      t.replaceWith(w);
      w.append(t);
    }
  });
  container.querySelectorAll("a[href]").forEach((a) => {
    if (!a.getAttribute("href").startsWith("/")) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
  });
  if (final && window.hljs) {
    container.querySelectorAll("pre code").forEach((c) => {
      if (c.dataset.hl) return;
      c.dataset.hl = "1";
      try { window.hljs.highlightElement(c); } catch {}
    });
  }
}

// One delegated listener for every code "Copy" button in the page.
document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".code-copy");
  if (!btn) return;
  const code = btn.closest(".code-block")?.querySelector("code")?.innerText || "";
  await copyText(code);
  const label = btn.querySelector("span");
  btn.innerHTML = icon("check", "sm") + "<span>Copied</span>";
  setTimeout(() => { btn.innerHTML = icon("copy", "sm") + "<span>Copy</span>"; }, 1600);
  if (!label) toast("Copied");
});

export function plainText(markdown) {
  return (markdown || "")
    .replace(/<think>[\s\S]*?(<\/think>|$)/g, "")
    .replace(/```[\s\S]*?```/g, " code block ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/<[^>]+>/g, "")
    .replace(/[#>*_`~|]/g, "")
    .replace(/\$\$?([^$]+)\$\$?/g, "$1")
    .replace(/\n{2,}/g, "\n")
    .trim();
}
