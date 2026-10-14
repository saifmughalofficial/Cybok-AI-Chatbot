import { startNetwork } from "./network.js";
import { setTheme } from "./core.js";

startNetwork(document.getElementById("heroNet"), { density: 0.00007, maxDist: 150 });

const nav = document.getElementById("lnav");
const onScroll = () => nav.classList.toggle("scrolled", scrollY > 40);
addEventListener("scroll", onScroll, { passive: true });
onScroll();

const io = new IntersectionObserver((entries) => {
  entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
}, { threshold: 0.12 });
document.querySelectorAll(".reveal").forEach((el) => io.observe(el));

document.querySelectorAll("[data-theme-toggle]").forEach((b) => {
  b.addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
});

// Typewriter demo answer
const target = document.getElementById("demoTyping");
const parts = [
  ["p", "Here's a quick summary of your sales sheet:"],
  ["li", "📈 Total revenue: PKR 4.8M across 12 months"],
  ["li", "🏆 Best month: November — PKR 612K (+18% vs October)"],
  ["li", "📉 Slowest month: February — PKR 271K"],
  ["p", "Want a chart-ready table or ideas to boost Q1 sales?"],
];
let started = false;
const demoIo = new IntersectionObserver(async ([e]) => {
  if (!e.isIntersecting || started) return;
  started = true;
  const caret = Object.assign(document.createElement("span"), { className: "caret" });
  let ul = null;
  for (const [tag, text] of parts) {
    let el;
    if (tag === "li") {
      if (!ul) { ul = document.createElement("ul"); target.append(ul); }
      el = document.createElement("li"); ul.append(el);
    } else { ul = null; el = document.createElement("p"); el.style.margin = "4px 0"; target.append(el); }
    for (const ch of text) {
      el.textContent += ch;
      el.append(caret);
      await new Promise((r) => setTimeout(r, 14));
    }
  }
}, { threshold: 0.4 });
if (target) demoIo.observe(target);
