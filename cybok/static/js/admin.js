/* Cybok admin dashboard. */
import { $, api, confirmDialog, esc, fmtDate, formatBytes, h, icon, isMobile, modal, timeAgo, toast } from "./core.js";

const root = $("#adminRoot");
const TABS = [
  ["overview", "Overview", "activity"], ["users", "Users", "users"], ["models", "AI Models", "cpu"],
  ["system", "System & APIs", "settings"], ["announcements", "Announcements", "megaphone"], ["errors", "System errors", "alert"],
];
const SERIES = [["chat", "AI chat requests", "#2f73ff"], ["image", "Images", "#ff3448"], ["logo", "Logos", "#b03dff"]];

$("#sbOpen").innerHTML = icon("panel");
$("#backToApp").innerHTML = icon("chevleft") + "Back to Cybok";
const app = $("#app");
$("#sbOpen").addEventListener("click", () => {
  if (isMobile()) app.dataset.mobileOpen = app.dataset.mobileOpen === "true" ? "false" : "true";
  else app.dataset.sidebar = app.dataset.sidebar === "closed" ? "open" : "closed";
});
$("#sbBackdrop").addEventListener("click", () => { app.dataset.mobileOpen = "false"; });

const nav = $("#adminTabs");
TABS.forEach(([k, label, ic]) => {
  const b = h("button", { class: "nav-item", dataset: { k }, html: icon(ic) + esc(label) });
  b.addEventListener("click", () => { location.hash = k; app.dataset.mobileOpen = "false"; });
  nav.append(b);
});
addEventListener("hashchange", show);

function show() {
  const k = TABS.some(([t]) => t === location.hash.slice(1)) ? location.hash.slice(1) : "overview";
  nav.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.k === k));
  $("#adminTitle").textContent = TABS.find(([t]) => t === k)[1];
  document.title = `${TABS.find(([t]) => t === k)[1]} · Cybok Admin`;
  root.innerHTML = "";
  ({ overview, users, models, system, announcements, errors })[k]();
}

const head = (title, sub, ...actions) => h("div", { class: "page-head" }, h("div", {}, h("h1", { text: title }), sub ? h("p", { text: sub }) : null), actions.length ? h("div", { class: "actions" }, ...actions) : null);
const loading = () => h("div", { class: "skeleton", style: { height: "180px", borderRadius: "18px" } });

/* ------------------------------------------------------------------ overview */
async function overview() {
  root.append(head("Overview", "How Cybok is being used.", h("button", { class: "btn sm", html: icon("refresh", "sm") + "Refresh", onclick: show })));
  const sk = loading(); root.append(sk);
  let s;
  try { s = await api("/api/admin/stats"); } catch (e) { toast(e.message, { type: "error" }); return; }
  sk.remove();
  const stat = (label, ic, value, sub) => h("div", { class: "stat" }, h("div", { class: "sl2", html: icon(ic, "sm") + esc(label) }), h("div", { class: "sv", text: value }), sub ? h("div", { class: "ss", text: sub }) : null);
  root.append(h("div", { class: "stat-grid" },
    stat("Total users", "users", s.users.toLocaleString(), `+${s.users_new_week} this week · ${s.disabled} disabled`),
    stat("Active users", "activity", s.active_day.toLocaleString(), `today · ${s.active_week} in last 7 days`),
    stat("Conversations", "chat", s.conversations.toLocaleString(), `${s.messages.toLocaleString()} messages`),
    stat("AI requests", "zap", s.ai_requests.toLocaleString(), `${s.ai_requests_day} today · ${s.ai_failures} failed`),
    stat("Image generations", "image", s.images.toLocaleString(), `${s.logos} logo batches`),
    stat("Uploads", "upload", s.uploads.toLocaleString(), `${s.files} files stored`),
    stat("Storage used", "database", formatBytes(s.storage_bytes), `${s.generated_items} generated items`),
    stat("Errors (24h)", "alert", s.errors_day.toLocaleString(), "see System errors")));

  const chartPanel = h("div", { class: "panel" }, h("h3", { html: icon("chart", "sm") + "Activity — last 14 days" }));
  chartPanel.append(barChart(s.series));
  const legend = h("div", { class: "legend" });
  SERIES.forEach(([, label, color]) => legend.append(h("span", { html: `<i style="background:${color}"></i>${esc(label)}` })));
  const tableBtn = h("button", { class: "btn sm ghost", text: "Show as table" });
  tableBtn.addEventListener("click", () => {
    const t = h("table", { class: "data-table" }, h("thead", {}, h("tr", {}, h("th", { text: "Date" }), ...SERIES.map(([, l]) => h("th", { class: "num", text: l })))),
      h("tbody", {}, ...s.series.map((d) => h("tr", {}, h("td", { text: d.date }), ...SERIES.map(([k]) => h("td", { class: "num", text: d[k] }))))));
    modal({ title: "Activity — last 14 days", body: h("div", { class: "table-scroll" }, t), wide: true });
  });
  chartPanel.append(h("div", { class: "row" }, legend, h("span", { class: "spacer" }), tableBtn));

  const modelPanel = h("div", { class: "panel" }, h("h3", { html: icon("cpu", "sm") + "Model usage" }));
  const max = Math.max(1, ...s.model_usage.map((m) => m.count));
  if (!s.model_usage.length) modelPanel.append(h("p", { class: "muted small", text: "No chat requests yet." }));
  s.model_usage.forEach((m) => modelPanel.append(h("div", { class: "hbar" }, h("span", { text: m.model }), h("b", { text: m.count.toLocaleString() }),
    h("div", { class: "track" }, h("i", { style: { width: `${(m.count / max) * 100}%` } })))));
  root.append(h("div", { class: "panel-grid" }, chartPanel, modelPanel));
}

function barChart(series) {
  const W = 640, H = 220, pl = 34, pb = 26, pt = 10, pr = 6;
  const totals = series.map((d) => SERIES.reduce((a, [k]) => a + d[k], 0));
  const max = Math.max(4, ...totals);
  const nice = Math.ceil(max / 4) * 4;
  const cw = (W - pl - pr) / series.length;
  const bw = Math.min(26, cw * 0.62);
  const y = (v) => pt + (H - pt - pb) * (1 - v / nice);
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Daily activity chart">`;
  for (let i = 0; i <= 4; i++) {
    const v = (nice / 4) * i;
    svg += `<line class="grid-line" x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}"/><text x="${pl - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
  }
  series.forEach((d, i) => {
    const x = pl + cw * i + (cw - bw) / 2;
    let acc = 0;
    const segs = SERIES.filter(([k]) => d[k] > 0);
    segs.forEach(([k, label, color], si) => {
      const y0 = y(acc), y1 = y(acc + d[k]);
      const hgt = Math.max(0, y0 - y1 - (si < segs.length - 1 ? 2 : 0));
      const r = si === segs.length - 1 ? 4 : 0;
      svg += `<path fill="${color}" d="M${x},${y0} V${y0 - hgt + r} ${r ? `Q${x},${y0 - hgt} ${x + r},${y0 - hgt} H${x + bw - r} Q${x + bw},${y0 - hgt} ${x + bw},${y0 - hgt + r}` : `H${x + bw}`} V${y0} Z"><title>${d.date} · ${label}: ${d[k]}</title></path>`;
      acc += d[k];
    });
    svg += `<rect x="${pl + cw * i}" y="${pt}" width="${cw}" height="${H - pt - pb}" fill="transparent"><title>${d.date}\n${SERIES.map(([k, l]) => `${l}: ${d[k]}`).join("\n")}</title></rect>`;
    if (i % 2 === 0 || series.length <= 7) svg += `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle">${d.date.slice(5)}</text>`;
  });
  return h("div", { html: svg + "</svg>" });
}

/* ------------------------------------------------------------------ users */
async function users() {
  const q = h("input", { class: "input", placeholder: "Search name or e-mail…", style: { maxWidth: "320px" } });
  root.append(head("Users", "Manage accounts and roles."), h("div", { class: "lib-toolbar" }, q));
  const box = h("div", {}, loading());
  root.append(box);
  const load = async () => {
    try {
      const r = await api(`/api/admin/users?q=${encodeURIComponent(q.value)}`);
      box.innerHTML = "";
      const tbody = h("tbody");
      r.users.forEach((u) => {
        const role = h("select", { class: "select", style: { height: "32px", width: "110px" }, disabled: u.is_self }, h("option", { value: "user", text: "User" }), h("option", { value: "admin", text: "Admin" }));
        role.value = u.role;
        role.addEventListener("change", () => patch(u, { role: role.value }));
        const status = h("button", { class: `btn sm ${u.disabled ? "accent" : ""}`, text: u.disabled ? "Enable" : "Disable", disabled: u.is_self });
        status.addEventListener("click", () => patch(u, { disabled: !u.disabled }));
        const del = h("button", { class: "icon-btn sm", title: "Delete user", html: icon("trash", "sm"), disabled: u.is_self });
        del.addEventListener("click", async () => {
          if (!await confirmDialog({ title: `Delete ${u.name}?`, message: "Their account, chats, files and creations will be permanently deleted.", confirm: "Delete user", danger: true })) return;
          try { await api(`/api/admin/users/${u.id}`, { method: "DELETE" }); toast("User deleted", { type: "success" }); load(); } catch (e) { toast(e.message, { type: "error" }); }
        });
        tbody.append(h("tr", {},
          h("td", {}, h("div", { class: "usercell" }, h("span", { class: "avatar", html: u.avatar ? `<img src="${esc(u.avatar)}" alt="">` : esc(u.initials) }), h("div", {}, h("b", { text: u.name + (u.is_self ? " (you)" : "") }), h("small", { text: u.email })))),
          h("td", {}, h("span", { class: `badge ${u.disabled ? "red" : "green"}`, text: u.disabled ? "Disabled" : "Active" }), u.google_linked ? h("span", { class: "badge gray", style: { marginLeft: "4px" }, text: "Google" }) : null),
          h("td", { class: "num", text: u.conversations }), h("td", { class: "num", text: formatBytes(u.storage) }),
          h("td", { text: timeAgo(u.last_seen_at) }), h("td", { text: fmtDate(u.created_at).split(",")[0] }),
          h("td", {}, role), h("td", {}, h("div", { class: "row" }, status, del))));
      });
      box.append(h("div", { class: "table-scroll" }, h("table", { class: "data-table" },
        h("thead", {}, h("tr", {}, ...["User", "Status", "Chats", "Storage", "Last seen", "Joined", "Role", ""].map((t, i) => h("th", { class: i === 2 || i === 3 ? "num" : "", text: t })))), tbody)));
      if (!r.users.length) box.append(h("div", { class: "empty", html: "<p>No users found.</p>" }));
    } catch (e) { toast(e.message, { type: "error" }); }
  };
  const patch = async (u, body) => {
    try { await api(`/api/admin/users/${u.id}`, { method: "PATCH", body }); toast("User updated", { type: "success" }); load(); }
    catch (e) { toast(e.message, { type: "error" }); load(); }
  };
  let t; q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(load, 250); });
  load();
}

/* ------------------------------------------------------------------ models */
async function models() {
  const add = h("button", { class: "btn brand sm", html: icon("plus", "sm") + "Add model", onclick: () => modelForm() });
  root.append(head("AI Models", "Any OpenAI-compatible API works: Groq, OpenRouter, Together, Mistral, Ollama, LM Studio, vLLM…", add));
  const box = h("div", {}, loading());
  root.append(box);
  try {
    const r = await api("/api/admin/models");
    box.innerHTML = "";
    const tbody = h("tbody");
    r.models.forEach((m) => {
      const test = h("button", { class: "btn sm", html: icon("zap", "sm") + "Test" });
      test.addEventListener("click", async () => {
        test.disabled = true; test.innerHTML = '<span class="spinner" style="width:14px;height:14px"></span>';
        try {
          const res = await api(`/api/admin/models/${m.id}/test`, { method: "POST", body: {} });
          res.ok ? toast(`${m.name}: ${res.reply}`, { type: "success", timeout: 6000 }) : toast(`${m.name}: ${res.error}`, { type: "error", timeout: 8000 });
        } catch (e) { toast(e.message, { type: "error" }); }
        test.disabled = false; test.innerHTML = icon("zap", "sm") + "Test";
      });
      tbody.append(h("tr", {},
        h("td", {}, h("b", { text: m.name }), h("div", { class: "small muted", text: m.slug })),
        h("td", {}, h("div", { text: m.provider }), h("div", { class: "small muted", text: m.api_model })),
        h("td", {}, h("span", { class: `badge ${m.available ? "green" : "amber"}`, text: m.available ? "Ready" : m.enabled ? "Needs key" : "Disabled" }), h("div", { class: "small muted", text: m.key_required ? `key: ${m.key_status}` : "no key needed" })),
        h("td", { text: [m.supports_vision ? "Vision" : "", m.supports_streaming ? "Streaming" : ""].filter(Boolean).join(" · ") }),
        h("td", { class: "num", text: m.sort_order }),
        h("td", {}, h("div", { class: "row" }, test, h("button", { class: "btn sm", html: icon("edit", "sm") + "Edit", onclick: () => modelForm(m) })))));
    });
    box.append(h("div", { class: "table-scroll" }, h("table", { class: "data-table" },
      h("thead", {}, h("tr", {}, ...["Model", "Provider", "Status", "Features", "Order", ""].map((t) => h("th", { text: t })))), tbody)));
  } catch (e) { toast(e.message, { type: "error" }); }
}

function modelForm(m = null) {
  const v = m || { name: "", slug: "", description: "", provider: "", model_family: "", api_base: "https://", api_model: "", api_key_env: "", badge: "", key_required: true, supports_vision: false, supports_streaming: true, temperature: 0.7, max_tokens: 2048, context_chars: 24000, enabled: true, sort_order: 100 };
  const f = {};
  const inp = (k, label, attrs = {}) => { f[k] = h("input", { class: "input", value: v[k] ?? "", ...attrs }); return h("div", { class: "field" }, h("label", { text: label }), f[k]); };
  const chk = (k, label) => { f[k] = h("input", { type: "checkbox" }); f[k].checked = !!v[k]; return h("label", {}, f[k], label); };
  f.api_key = h("input", { class: "input", type: "password", placeholder: m?.key_hint ? `Stored: ${m.key_hint} — leave blank to keep` : "Optional — prefer an environment variable", autocomplete: "off" });
  const body = h("div", {},
    h("div", { class: "form-grid" }, inp("name", "Display name"), inp("slug", "Slug (unique id)", { placeholder: "e.g. mistral-small" }),
      h("div", { class: "field full" }, h("label", { text: "Description" }), (f.description = h("input", { class: "input", value: v.description }))),
      inp("provider", "Provider label", { placeholder: "e.g. Groq" }), inp("model_family", "Model family (shown to users)", { placeholder: "e.g. Meta Llama 3.3 70B" }),
      inp("api_base", "API base URL", { placeholder: "https://api.groq.com/openai/v1" }), inp("api_model", "API model id", { placeholder: "llama-3.3-70b-versatile" }),
      inp("api_key_env", "API key env variable", { placeholder: "GROQ_API_KEY" }), h("div", { class: "field" }, h("label", { text: "API key (stored in database)" }), f.api_key),
      inp("badge", "Badge", { placeholder: "e.g. Free" }), inp("sort_order", "Sort order", { type: "number" }),
      inp("temperature", "Temperature", { type: "number", step: "0.1", min: "0", max: "2" }), inp("max_tokens", "Max output tokens", { type: "number" }),
      inp("context_chars", "Context budget (characters)", { type: "number" })),
    h("div", { class: "checks" }, chk("enabled", "Enabled"), chk("key_required", "Requires API key"), chk("supports_vision", "Vision (images)"), chk("supports_streaming", "Streaming")));
  const saveBtn = h("button", { class: "btn primary", text: m ? "Save changes" : "Add model" });
  const footer = [];
  if (m) footer.push(h("button", {
    class: "btn danger", text: "Delete", onclick: async () => {
      if (!await confirmDialog({ title: `Delete ${m.name}?`, message: "Users won't be able to pick this model anymore.", confirm: "Delete", danger: true })) return;
      await api(`/api/admin/models/${m.id}`, { method: "DELETE" }); md.close(); toast("Model deleted", { type: "success" }); show();
    },
  }));
  footer.push(h("span", { class: "spacer" }), h("button", { class: "btn", text: "Cancel", onclick: () => md.close() }), saveBtn);
  const md = modal({ title: m ? `Edit ${m.name}` : "Add AI model", body, footer, wide: true });
  saveBtn.addEventListener("click", async () => {
    const data = {};
    for (const [k, el] of Object.entries(f)) data[k] = el.type === "checkbox" ? el.checked : el.value;
    if (!data.api_key) data.api_key = "__keep__";
    try {
      await api(m ? `/api/admin/models/${m.id}` : "/api/admin/models", { method: m ? "PATCH" : "POST", body: data });
      md.close(); toast("Model saved", { type: "success" }); show();
    } catch (e) { toast(e.message, { type: "error" }); }
  });
}

/* ------------------------------------------------------------------ system */
async function freeKeysPanel() {
  const panel = h("div", { class: "panel" }, h("h3", { html: icon("zap", "sm") + "Free AI keys" }),
    h("p", { class: "small muted", html: "All of these are <b>free</b> (no credit card). Create an account, copy the key and paste it here — it's stored on the server only and never shown to users. <b>Groq</b> unlocks Cybok Fast, Cybok Smart, GPT-OSS and Vision. Cybok Local (Ollama) needs no key at all." }));
  const list = h("div");
  panel.append(list);
  const draw = (keys) => {
    list.innerHTML = "";
    keys.forEach((k) => {
      const input = h("input", { class: "input", type: "password", autocomplete: "off", placeholder: k.set ? `${k.hint} (${k.source === "env" ? "from .env" : "saved"}) — paste to replace` : `Paste your free ${k.label} key` , disabled: k.source === "env" });
      const save = h("button", { class: "btn sm primary", text: "Save" });
      save.addEventListener("click", async () => {
        if (!input.value.trim()) { toast("Paste a key first."); return; }
        try { const r = await api("/api/admin/keys", { method: "PATCH", body: { [k.name]: input.value.trim() } }); draw(r.keys); toast(`${k.label} key saved — models unlocked`, { type: "success" }); }
        catch (e) { toast(e.message, { type: "error" }); }
      });
      const actions = h("div", { class: "row" }, save);
      if (k.source === "admin") actions.append(h("button", { class: "btn sm ghost", text: "Remove", onclick: async () => { const r = await api("/api/admin/keys", { method: "PATCH", body: { [k.name]: "" } }); draw(r.keys); toast("Key removed"); } }));
      list.append(h("div", { class: "set-row" },
        h("div", { class: "sl" }, h("b", { html: `${esc(k.label)} <span class="badge ${k.set ? "green" : "gray"}">${k.set ? "Connected" : "Not set"}</span>` }),
          h("span", { html: `<code>${k.name}</code> · <a href="${k.url}" target="_blank" rel="noopener">Get a free key ↗</a>` })),
        h("div", { style: { flex: "1 1 260px", minWidth: "0" } }, input), actions));
    });
  };
  try { draw((await api("/api/admin/keys")).keys); } catch (e) { toast(e.message, { type: "error" }); }
  return panel;
}

async function system() {
  root.append(head("System & APIs", "Free AI keys, Cybok's identity, registration, uploads and image provider."));
  root.append(await freeKeysPanel());
  const box = h("div", {}, loading());
  root.append(box);
  let r;
  try { r = await api("/api/admin/settings"); } catch (e) { toast(e.message, { type: "error" }); return; }
  box.innerHTML = "";
  const s = r.settings;
  const date = h("input", { class: "input", type: "date", value: s.creation_date || "", style: { maxWidth: "220px" } });
  const reg = h("input", { type: "checkbox" }); reg.checked = s.registration_open === "1";
  const upl = h("input", { class: "input", type: "number", min: "1", max: "200", value: s.max_upload_mb, style: { maxWidth: "120px" } });
  const defModel = h("select", { class: "select" }, h("option", { value: "", text: "Automatic (first available)" }), ...r.models.map((m) => h("option", { value: m.slug, text: m.name })));
  defModel.value = s.default_model || "";
  const extra = h("textarea", { class: "textarea", maxlength: 2000, placeholder: "Extra instructions added to every conversation (optional)" });
  extra.value = s.system_prompt_extra || "";
  const prov = h("select", { class: "select" }, ...r.image_providers.map((p) => h("option", { value: p.key, text: p.label })));
  prov.value = s.image_provider;
  const imodel = h("input", { class: "input", value: s.image_model, placeholder: "flux" });
  const hfmodel = h("input", { class: "input", value: s.hf_image_model });
  const save = h("button", { class: "btn brand", html: icon("check") + "<span>Save settings</span>" });
  save.addEventListener("click", async () => {
    try {
      await api("/api/admin/settings", { method: "PATCH", body: { creation_date: date.value, registration_open: reg.checked, max_upload_mb: upl.value, default_model: defModel.value, system_prompt_extra: extra.value, image_provider: prov.value, image_model: imodel.value, hf_image_model: hfmodel.value } });
      toast("Settings saved", { type: "success" });
    } catch (e) { toast(e.message, { type: "error" }); }
  });
  const field = (label, el, hint) => h("div", { class: "field" }, h("label", { text: label }), el, hint ? h("span", { class: "hint", html: hint }) : null);
  box.append(
    h("div", { class: "panel" }, h("h3", { html: icon("info", "sm") + "Cybok identity" }),
      field("Official creation date", date, 'Cybok answers “When were you manufactured?” with this date. Leave empty and it says the date <b>has not been configured yet</b> — it never invents one.'),
      h("div", { class: "row" }, h("button", { class: "btn sm ghost", text: "Clear date", onclick: () => { date.value = ""; } }))),
    h("div", { class: "panel" }, h("h3", { html: icon("settings", "sm") + "General" }),
      h("div", { class: "checks" }, h("label", {}, reg, "Allow new sign-ups")),
      field("Max upload size (MB)", upl), field("Default model for new users", defModel), field("System prompt addition", extra)),
    h("div", { class: "panel" }, h("h3", { html: icon("image", "sm") + "Image generation" }),
      field("Provider", prov, "Pollinations is free with no key. Hugging Face needs a free <code>HF_TOKEN</code> in .env."),
      h("div", { class: "form-grid" }, field("Pollinations model", imodel, "flux, turbo, …"), field("Hugging Face model", hfmodel))),
    h("div", { class: "row", style: { marginBottom: "16px" } }, h("span", { class: "spacer" }), save));
  const env = h("div", { class: "env-list" });
  Object.entries(r.env).forEach(([k, ok]) => env.append(h("div", {}, h("span", { text: k }), h("span", { class: `badge ${ok ? "green" : "gray"}`, text: ok ? "set" : "not set" }))));
  box.append(h("div", { class: "panel" }, h("h3", { html: icon("lock", "sm") + "API keys & environment (.env)" }),
    h("p", { class: "small muted", text: "Secret keys live in the .env file on the server and are never sent to browsers. Edit .env and restart Cybok to change them. All listed keys are optional and free." }), env,
    h("p", { class: "small muted", style: { marginTop: "12px" }, text: `Version ${r.app.version} · database: ${r.app.database}` })));
}

/* ------------------------------------------------------------------ announcements */
async function announcements() {
  root.append(head("Announcements", "Show a banner to every user inside the app.", h("button", { class: "btn brand sm", html: icon("plus", "sm") + "New announcement", onclick: () => annForm() })));
  const box = h("div", {}, loading());
  root.append(box);
  try {
    const r = await api("/api/admin/announcements");
    box.innerHTML = "";
    if (!r.announcements.length) box.append(h("div", { class: "empty", html: `<div class="ei">${icon("megaphone")}</div><h3>No announcements</h3><p>Create one to inform users about updates or maintenance.</p>` }));
    r.announcements.forEach((a) => {
      const sw = h("input", { type: "checkbox" }); sw.checked = a.active;
      sw.addEventListener("change", async () => { await api(`/api/admin/announcements/${a.id}`, { method: "PATCH", body: { active: sw.checked } }); toast(sw.checked ? "Announcement live" : "Announcement hidden", { type: "success" }); });
      box.append(h("div", { class: "list-card" }, h("span", { class: `badge ${a.level === "warning" ? "amber" : a.level === "success" ? "green" : ""}`, text: a.level }),
        h("div", { class: "lt" }, h("b", { text: a.title }), h("small", { text: `${a.body || ""} · ${timeAgo(a.created_at)}` })),
        h("label", { class: "switch", title: "Visible" }, sw, h("span")),
        h("button", { class: "icon-btn sm", title: "Edit", html: icon("edit", "sm"), onclick: () => annForm(a) }),
        h("button", { class: "icon-btn sm", title: "Delete", html: icon("trash", "sm"), onclick: async () => { if (await confirmDialog({ title: "Delete announcement?", confirm: "Delete", danger: true })) { await api(`/api/admin/announcements/${a.id}`, { method: "DELETE" }); show(); } } })));
    });
  } catch (e) { toast(e.message, { type: "error" }); }
}

function annForm(a = null) {
  const title = h("input", { class: "input", value: a?.title || "", maxlength: 200 });
  const body = h("textarea", { class: "textarea", maxlength: 2000 }); body.value = a?.body || "";
  const level = h("select", { class: "select" }, ...["info", "success", "warning"].map((l) => h("option", { value: l, text: l })));
  level.value = a?.level || "info";
  const save = h("button", { class: "btn primary", text: "Save" });
  const m = modal({ title: a ? "Edit announcement" : "New announcement", body: h("div", {}, h("div", { class: "field" }, h("label", { text: "Title" }), title), h("div", { class: "field" }, h("label", { text: "Message" }), body), h("div", { class: "field" }, h("label", { text: "Style" }), level)), footer: [h("button", { class: "btn", text: "Cancel", onclick: () => m.close() }), save] });
  save.addEventListener("click", async () => {
    try {
      await api(a ? `/api/admin/announcements/${a.id}` : "/api/admin/announcements", { method: a ? "PATCH" : "POST", body: { title: title.value, body: body.value, level: level.value, active: a ? a.active : true } });
      m.close(); toast("Saved", { type: "success" }); show();
    } catch (e) { toast(e.message, { type: "error" }); }
  });
}

/* ------------------------------------------------------------------ errors */
async function errors() {
  const clear = h("button", { class: "btn sm", html: icon("trash", "sm") + "Clear log", onclick: async () => { if (await confirmDialog({ title: "Clear error log?", confirm: "Clear", danger: true })) { await api("/api/admin/errors", { method: "DELETE" }); show(); } } });
  root.append(head("System errors", "Provider failures and unexpected server errors.", clear));
  const box = h("div", {}, loading());
  root.append(box);
  try {
    const r = await api("/api/admin/errors");
    box.innerHTML = "";
    if (!r.errors.length) { box.append(h("div", { class: "empty", html: `<div class="ei">${icon("check")}</div><h3>All clear</h3><p>No errors have been logged.</p>` })); return; }
    box.append(h("div", { class: "table-scroll" }, h("table", { class: "data-table" },
      h("thead", {}, h("tr", {}, h("th", { text: "When" }), h("th", { text: "Source" }), h("th", { text: "User" }), h("th", { text: "Message" }))),
      h("tbody", {}, ...r.errors.map((e) => h("tr", {}, h("td", { text: fmtDate(e.created_at), style: { whiteSpace: "nowrap" } }), h("td", {}, h("span", { class: "badge red", text: e.source })), h("td", { text: e.user_id ?? "—" }), h("td", {}, h("div", { class: "err-msg", text: e.message }))))))));
  } catch (e) { toast(e.message, { type: "error" }); }
}

show();
