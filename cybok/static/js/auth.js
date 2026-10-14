import { startNetwork } from "./network.js";
import { setTheme } from "./core.js";

startNetwork(document.getElementById("netCanvas"));

document.querySelectorAll("[data-toggle-pw]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const input = btn.parentElement.querySelector("input");
    input.type = input.type === "password" ? "text" : "password";
    btn.setAttribute("aria-label", input.type === "password" ? "Show password" : "Hide password");
  });
});

document.querySelectorAll("[data-strength]").forEach((input) => {
  const bar = input.closest(".field").querySelector(".pw-meter i");
  input.addEventListener("input", () => {
    const v = input.value;
    let s = 0;
    if (v.length >= 8) s++;
    if (v.length >= 12) s++;
    if (/[a-z]/.test(v) && /[A-Z]/.test(v)) s++;
    if (/\d/.test(v)) s++;
    if (/[^A-Za-z0-9]/.test(v)) s++;
    const colors = ["#e5384a", "#e5384a", "#f59e0b", "#eab308", "#22c55e", "#12a160"];
    bar.style.width = `${(s / 5) * 100}%`;
    bar.style.background = colors[s];
  });
});

document.querySelectorAll("[data-busy-form]").forEach((form) => {
  form.addEventListener("submit", () => {
    const b = form.querySelector('button[type="submit"]');
    if (b) { b.disabled = true; b.innerHTML = '<span class="spinner"></span>'; }
  });
});

document.querySelectorAll("[data-theme-toggle]").forEach((b) => {
  b.addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
});
