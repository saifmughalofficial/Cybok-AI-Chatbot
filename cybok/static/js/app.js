/* Cybok web app: router, sidebar, chat with streaming, composer, sharing, search, shortcuts. */
import {
  $, $$, api, closeMenu, confirmDialog, copyText, esc, fileBadge, formatBytes, h, icon, isMobile, lightbox, modal,
  promptDialog, setAccent, setFontSize, setTheme, showMenu, timeAgo, toast,
} from "./core.js";
import { enhance, renderMarkdown } from "./markdown.js";
import { emit, modelBySlug, on, state } from "./state.js";
import { isDictating, speak, startDictation, startVoiceConversation, stopDictation, stopSpeaking, sttSupported } from "./voice.js";
import { showImages, showLogos } from "./studio.js";
import { showLibrary } from "./library.js";
import { openSettings } from "./settings.js";

const app = $("#app");
const els = {
  convList: $("#convList"), messages: $("#messages"), welcome: $("#welcome"), scroll: $("#chatScroll"),
  input: $("#input"), send: $("#sendBtn"), composer: $("#composer"), tray: $("#attachTray"), fileInput: $("#fileInput"),
  modelName: $("#modelName"), modelBadge: $("#modelBadge"), title: $("#topTitle"), share: $("#shareBtn"),
  chatMenu: $("#chatMenuBtn"), tempPill: $("#tempPill"), note: $("#composerNote"), scrollBottom: $("#scrollBottom"),
};

/* ================================================================ icons in static markup */
function paintIcons() {
  $$("[data-icon]").forEach((el) => { el.outerHTML = icon(el.dataset.icon); });
  const set = (id, name) => { const el = document.getElementById(id); if (el) el.innerHTML = icon(name); };
  set("sbCollapse", "panel"); set("sbOpen", "panel"); set("shareBtn", "share"); set("chatMenuBtn", "more");
  set("attachBtn", "clip"); set("imageModeBtn", "image"); set("imageModeOff", "x"); set("micBtn", "mic");
  set("voiceModeBtn", "headphones"); set("sendBtn", "send"); set("scrollBottom", "arrowdown");
  $(".btn-new .plus").innerHTML = icon("plus", "sm");
}

/* ================================================================ bootstrap */
async function boot() {
  paintIcons();
  let data;
  try {
    data = await api("/api/bootstrap");
  } catch (e) {
    toast(e.message, { type: "error" });
    return;
  }
  Object.assign(state, {
    user: data.user, settings: data.settings, models: data.models, defaultModel: data.default_model,
    currentModel: data.default_model, conversations: data.conversations, limits: data.limits,
    imageStyles: data.image_styles, imageSizes: data.image_sizes, app: data.app, mailConfigured: data.mail_configured,
  });
  applyAppearance();
  renderUser();
  renderConvList();
  renderModel();
  renderAnnouncements(data.announcements);
  renderSetupBanner();
  setupImageModeSelects();
  if (!sttSupported) { $("#micBtn").hidden = true; $("#voiceModeBtn").hidden = true; }
  try { if (localStorage.getItem("cybok-sidebar") === "closed" && !isMobile()) app.dataset.sidebar = "closed"; } catch {}
  route();
}

function applyAppearance() {
  const s = state.settings;
  setTheme(s.theme || "system");
  setAccent(s.accent || "cybok");
  setFontSize(s.font_size || "md");
}
on("settings-changed", () => { applyAppearance(); renderModel(); renderUser(); });

function renderUser() {
  const u = state.user;
  $("#userName").textContent = u.name;
  $("#userEmail").textContent = u.email;
  const av = $("#userAvatar");
  av.innerHTML = u.avatar ? `<img src="${esc(u.avatar)}" alt="">` : esc(u.initials);
  const hour = new Date().getHours();
  const part = hour < 5 ? "Working late" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  $("#greeting").textContent = `${part}, ${u.name.split(" ")[0]}`;
}
on("user-changed", renderUser);

function renderAnnouncements(list) {
  const root = $("#announcements");
  root.innerHTML = "";
  let dismissed = [];
  try { dismissed = JSON.parse(localStorage.getItem("cybok-dismissed") || "[]"); } catch {}
  (list || []).filter((a) => !dismissed.includes(a.id)).forEach((a) => {
    const el = h("div", { class: `announcement ${a.level}`, role: "status", html: icon(a.level === "warning" ? "alert" : "megaphone") });
    el.append(h("div", {}, h("strong", { text: a.title }), a.body ? h("span", { text: a.body }) : null));
    el.append(h("button", {
      class: "icon-btn sm", "aria-label": "Dismiss", html: icon("x"), onclick: () => {
        dismissed.push(a.id);
        try { localStorage.setItem("cybok-dismissed", JSON.stringify(dismissed)); } catch {}
        el.remove();
      },
    }));
    root.append(el);
  });
}

function renderSetupBanner() {
  const reliable = state.models.some((m) => m.available && !m.community);
  if (reliable) return;
  const admin = state.user.role === "admin";
  const el = h("div", { class: "announcement warning", role: "status", html: icon("zap") });
  el.append(h("div", {},
    h("strong", { text: "Connect a free AI model" }),
    h("span", {
      html: admin
        ? 'Cybok is free, but needs one AI engine: paste a free Groq key in <a href="/admin#system">Admin › System</a> (1 minute, no card) or install Ollama to run AI on this computer. See the user manual.'
        : "The administrator hasn't connected a free AI model yet. Until then only the community model is used, which may be busy.",
    })));
  $("#announcements").prepend(el);
}

/* ================================================================ router */
export function navigate(path, { replace = false } = {}) {
  if (location.pathname === path && !replace) { route(); return; }
  history[replace ? "replaceState" : "pushState"]({}, "", path);
  route();
}

window.addEventListener("popstate", route);
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-link]");
  if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  navigate(a.getAttribute("href"));
  if (isMobile()) closeMobileSidebar();
});

function showView(name) {
  $$(".view").forEach((v) => { v.hidden = v.id !== `view-${name}`; });
  $$("#sbNav .nav-item, .sb-foot .nav-item").forEach((n) => n.classList.toggle("active", n.dataset.nav === name));
  const chat = name === "chat";
  $("#modelBtn").style.visibility = chat ? "visible" : "hidden";
  if (!chat) { els.share.hidden = true; els.chatMenu.hidden = true; els.tempPill.hidden = true; els.title.textContent = ""; }
}

async function route() {
  closeMenu();
  const p = location.pathname.replace(/\/+$/, "");
  const m = p.match(/^\/app\/c\/([a-f0-9]{32})$/);
  if (m) { showView("chat"); if (state.current?.id !== m[1]) await loadConversation(m[1]); else renderChatHeader(); return; }
  if (p === "/app/images") { showView("images"); document.title = "Create Image · Cybok"; showImages($("#view-images")); return; }
  if (p === "/app/logos") { showView("logos"); document.title = "Logo Studio · Cybok"; showLogos($("#view-logos")); return; }
  if (p === "/app/library") { showView("library"); document.title = "Library · Cybok"; showLibrary($("#view-library")); return; }
  if (p === "/app/archived") { showView("archived"); document.title = "Archived · Cybok"; showArchived(); return; }
  if (p === "/app/settings") { showView("chat"); newChat({ silent: true }); openSettings(); return; }
  showView("chat");
  newChat({ silent: true });
}

/* ================================================================ sidebar */
function bucket(iso) {
  const d = new Date(iso), now = new Date();
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = (day(now) - day(d)) / 86400000;
  if (diff < 1) return "Today";
  if (diff < 2) return "Yesterday";
  if (diff < 7) return "Previous 7 days";
  if (diff < 30) return "Previous 30 days";
  return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

export function renderConvList() {
  const list = els.convList;
  list.innerHTML = "";
  const convs = state.conversations.filter((c) => !c.archived && !c.deleted && !c.temporary);
  if (!convs.length) {
    list.append(h("div", { class: "sb-empty", html: `${icon("chat", "lg")}<p>Your conversations will appear here.</p>` }));
    return;
  }
  const pinned = convs.filter((c) => c.pinned);
  if (pinned.length) {
    const sec = h("div", { class: "sb-section" }, h("div", { class: "sb-section-title", html: icon("pin", "sm") + "Pinned" }));
    pinned.forEach((c) => sec.append(convItem(c)));
    list.append(sec);
  }
  const groups = new Map();
  convs.filter((c) => !c.pinned).sort((a, b) => b.updated_at.localeCompare(a.updated_at)).forEach((c) => {
    const k = bucket(c.updated_at);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(c);
  });
  for (const [k, items] of groups) {
    const sec = h("div", { class: "sb-section" }, h("div", { class: "sb-section-title", text: k }));
    items.forEach((c) => sec.append(convItem(c)));
    list.append(sec);
  }
}

function convItem(c) {
  const item = h("div", { class: `conv-item ${state.current?.id === c.id ? "active" : ""}`, tabindex: "0", role: "link", dataset: { id: c.id }, title: c.title });
  item.append(h("span", { class: "title", text: c.title }));
  if (c.shared) item.append(h("span", { class: "shared-dot", title: "Shared", html: icon("link", "sm") }));
  const more = h("button", { class: "icon-btn sm more", "aria-label": "Chat options", html: icon("more") });
  more.addEventListener("click", (e) => { e.stopPropagation(); convMenu(more, c); });
  item.append(more);
  item.addEventListener("click", () => { navigate(`/app/c/${c.id}`); if (isMobile()) closeMobileSidebar(); });
  item.addEventListener("keydown", (e) => { if (e.key === "Enter") item.click(); if (e.key === "F2") renameInline(item, c); });
  item.addEventListener("dblclick", (e) => { e.preventDefault(); renameInline(item, c); });
  return item;
}

function renameInline(item, c) {
  const titleEl = item.querySelector(".title");
  const input = h("input", { value: c.title, maxlength: 200, "aria-label": "Chat title" });
  titleEl.replaceWith(input);
  input.focus(); input.select();
  let done = false;
  const finish = async (save) => {
    if (done) return;
    done = true;
    const v = input.value.trim();
    if (save && v && v !== c.title) await updateConv(c.id, { title: v });
    else renderConvList();
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); e.stopPropagation(); });
  input.addEventListener("blur", () => finish(true));
  input.addEventListener("click", (e) => e.stopPropagation());
}

function convMenu(anchor, c) {
  showMenu(anchor, [
    { label: "Rename", icon: "edit", onClick: () => { const it = $(`.conv-item[data-id="${c.id}"]`); if (it) renameInline(it, c); else renameConv(c); } },
    { label: c.pinned ? "Unpin" : "Pin", icon: c.pinned ? "pinoff" : "pin", onClick: () => updateConv(c.id, { pinned: !c.pinned }) },
    { label: "Share", icon: "share", onClick: () => openShare(c) },
    { label: "Export as Markdown", icon: "download", onClick: () => { location.href = `/api/chats/${c.id}/export`; } },
    { label: c.archived ? "Unarchive" : "Archive", icon: "archive", onClick: () => updateConv(c.id, { archived: !c.archived }, c.archived ? "Chat restored" : "Chat archived") },
    "sep",
    { label: "Delete", icon: "trash", danger: true, onClick: () => deleteConv(c) },
  ], { align: "end" });
}

async function renameConv(c) {
  const v = await promptDialog({ title: "Rename chat", value: c.title, confirm: "Rename" });
  if (v) await updateConv(c.id, { title: v });
}

export async function updateConv(id, patch, message) {
  try {
    const r = await api(`/api/chats/${id}`, { method: "PATCH", body: patch });
    upsertConv(r.conversation);
    if (message) toast(message, { type: "success" });
    return r.conversation;
  } catch (e) { toast(e.message, { type: "error" }); }
}

function upsertConv(c) {
  const i = state.conversations.findIndex((x) => x.id === c.id);
  if (i >= 0) state.conversations[i] = { ...state.conversations[i], ...c };
  else state.conversations.unshift(c);
  if (state.current?.id === c.id) { state.current = { ...state.current, ...c }; renderChatHeader(); }
  renderConvList();
}

async function deleteConv(c) {
  try {
    await api(`/api/chats/${c.id}`, { method: "DELETE" });
    state.conversations = state.conversations.filter((x) => x.id !== c.id);
    renderConvList();
    if (state.current?.id === c.id) navigate("/app");
    toast("Moved to Trash", {
      action: "Undo", onAction: async () => {
        const r = await api(`/api/chats/${c.id}/restore`, { method: "POST" });
        upsertConv(r.conversation);
      },
    });
  } catch (e) { toast(e.message, { type: "error" }); }
}

/* sidebar open/close */
function toggleSidebar() {
  if (isMobile()) {
    app.dataset.mobileOpen = app.dataset.mobileOpen === "true" ? "false" : "true";
    return;
  }
  app.dataset.sidebar = app.dataset.sidebar === "closed" ? "open" : "closed";
  try { localStorage.setItem("cybok-sidebar", app.dataset.sidebar); } catch {}
}
function closeMobileSidebar() { app.dataset.mobileOpen = "false"; }
$("#sbCollapse").addEventListener("click", toggleSidebar);
$("#sbOpen").addEventListener("click", toggleSidebar);
$("#sbBackdrop").addEventListener("click", closeMobileSidebar);
$("#newChatBtn").addEventListener("click", () => { navigate("/app"); if (isMobile()) closeMobileSidebar(); setTimeout(() => els.input.focus(), 50); });
$("#openSearch").addEventListener("click", openSearch);
$("#userMenuBtn").addEventListener("click", (e) => userMenu(e.currentTarget));

function userMenu(anchor) {
  const u = state.user;
  showMenu(anchor, [
    { heading: u.email },
    { label: "Settings", icon: "settings", onClick: () => openSettings() },
    { label: "Library", icon: "library", onClick: () => navigate("/app/library") },
    u.role === "admin" ? { label: "Admin panel", icon: "shield", onClick: () => { location.href = "/admin"; } } : null,
    "sep",
    { label: "Light theme", icon: "sun", onClick: () => saveSetting({ theme: "light" }) },
    { label: "Dark theme", icon: "moon", onClick: () => saveSetting({ theme: "dark" }) },
    { label: "System theme", icon: "monitor", onClick: () => saveSetting({ theme: "system" }) },
    "sep",
    { label: "Keyboard shortcuts", icon: "keyboard", hint: "Ctrl /", onClick: showShortcuts },
    { label: "About Cybok", icon: "info", onClick: () => openSettings("about") },
    { label: "Log out", icon: "logout", danger: true, onClick: () => $("#logoutForm").submit() },
  ], { width: "250px" });
}

export async function saveSetting(patch) {
  Object.assign(state.settings, patch);
  emit("settings-changed");
  try {
    const r = await api("/api/settings", { method: "PATCH", body: patch });
    state.settings = r.settings;
  } catch (e) { toast(e.message, { type: "error" }); }
}

/* ================================================================ model picker */
function renderModel() {
  const m = modelBySlug(state.currentModel) || state.models.find((x) => x.available);
  if (!m) { els.modelName.textContent = "No model available"; return; }
  state.currentModel = m.slug;
  els.modelName.textContent = m.name;
  els.modelBadge.innerHTML = m.vision ? '<span class="badge">Vision</span>' : "";
  els.note.textContent = `${m.name} · ${m.family} via ${m.provider}. Cybok can make mistakes — check important info.`;
}

$("#modelBtn").addEventListener("click", (e) => {
  const wrap = h("div");
  const ready = state.models.filter((m) => m.available), setup = state.models.filter((m) => !m.available);
  [...ready, ...setup].forEach((m, i) => {
    if (i === 0) wrap.append(h("div", { class: "menu-label", text: "Ready to use — all free" }));
    if (setup.length && m === setup[0]) wrap.append(h("div", { class: "menu-sep" }), h("div", { class: "menu-label", text: "Needs a free setup step" }));
    const b = h("button", { class: `model-opt ${m.available ? "" : "unavailable"}`, role: "menuitemradio", "aria-checked": String(m.slug === state.currentModel) });
    b.append(h("span", { class: "mi", html: icon(m.vision ? "eye" : m.slug.includes("fast") ? "zap" : m.slug.includes("ollama") ? "cpu" : "sparkles") }));
    const t = h("div", { style: { minWidth: 0 } });
    const title = h("div", { class: "mt" }, m.name);
    if (m.badge) title.append(h("span", { class: `badge ${m.available ? "" : "gray"}`, text: m.badge }));
    t.append(title, h("div", { class: "md2", html: `${esc(m.description)}<br>${esc(m.family)} · ${esc(m.provider)}${m.available ? "" : `<br><em>${esc(m.needs || "Unavailable")}</em>`}` }));
    b.append(t);
    if (m.slug === state.currentModel) b.append(h("span", { class: "check", html: icon("check") }));
    b.addEventListener("click", () => {
      closeMenu();
      if (!m.available) { toast(`${m.name}: ${m.needs}. See the user manual — it's free.`, { timeout: 6000 }); return; }
      selectModel(m.slug);
    });
    wrap.append(b);
  });
  showMenu(e.currentTarget, wrap, { className: "model-menu" });
});

function selectModel(slug) {
  state.currentModel = slug;
  renderModel();
  if (state.current) updateConv(state.current.id, { model: slug });
  toast(`Switched to ${modelBySlug(slug).name}`);
}

/* ================================================================ chat */
const SUGGESTIONS = [
  { icon: "code", title: "Write code", text: "A Python script that renames photos by date taken", prompt: "Write a Python script that renames all photos in a folder by the date they were taken (EXIF), with clear comments." },
  { icon: "filetext", title: "Analyze a document", text: "Upload a PDF, Word or Excel file and ask about it", action: "attach" },
  { icon: "image", title: "Create an image", text: "A futuristic city at night, neon red and blue", action: "image", prompt: "A futuristic city at night with neon red and blue lights, rain reflections, cinematic" },
  { icon: "bulb", title: "Brainstorm ideas", text: "Startup ideas for university students", prompt: "Give me 10 creative startup ideas that university students in Pakistan could start with a small budget. Include a one-line plan for each." },
  { icon: "mail", title: "Draft an email", text: "Politely ask for a deadline extension", prompt: "Write a short, professional email to my professor politely asking for a 3-day extension on my assignment because I was sick." },
  { icon: "calc", title: "Solve math step by step", text: "Solve x² − 5x + 6 = 0", prompt: "Solve x^2 - 5x + 6 = 0 step by step and explain each step." },
  { icon: "languages", title: "Translate", text: "Translate a message into Urdu", prompt: "Translate into Urdu: \"Thank you for your help. I will send the report by tomorrow morning.\"" },
  { icon: "book", title: "Explain a topic", text: "How does machine learning work?", prompt: "Explain how machine learning works in simple terms, with an everyday example." },
  { icon: "chart", title: "Write a report", text: "Outline a market research report", prompt: "Create a structured outline for a market research report on online food delivery in Pakistan." },
  { icon: "megaphone", title: "Marketing content", text: "Instagram captions for a coffee shop", prompt: "Write 5 catchy Instagram captions for a new coffee shop opening, with relevant hashtags." },
];

function renderSuggestions() {
  const root = $("#suggestions");
  root.innerHTML = "";
  const pool = [...SUGGESTIONS].sort(() => Math.random() - 0.5);
  const picks = [pool.find((s) => s.action === "image"), pool.find((s) => s.action === "attach"), ...pool.filter((s) => !s.action)].slice(0, 6);
  picks.sort(() => Math.random() - 0.5).forEach((s, i) => {
    const b = h("button", { class: "suggestion", style: { animationDelay: `${i * 50}ms` } },
      h("span", { class: "si", html: icon(s.icon) }), h("b", { text: s.title }), h("span", { text: s.text }));
    b.addEventListener("click", () => {
      if (s.action === "attach") { els.fileInput.click(); els.input.value = "Summarize this document and list the key points."; autosize(); return; }
      if (s.action === "image") setImageMode(true);
      els.input.value = s.prompt;
      autosize();
      updateSend();
      els.input.focus();
    });
    root.append(b);
  });
}

function newChat({ silent } = {}) {
  if (state.streaming) stopGeneration();
  state.current = null;
  state.messages = [];
  els.messages.innerHTML = "";
  els.messages.hidden = true;
  els.welcome.hidden = false;
  state.currentModel = modelBySlug(state.settings.default_model)?.available ? state.settings.default_model : state.defaultModel;
  state.tempNext = !state.settings.save_history;
  renderModel();
  renderSuggestions();
  renderChatHeader();
  renderConvList();
  document.title = "Cybok";
  if (!silent) els.input.focus();
}

function renderChatHeader() {
  const c = state.current;
  els.title.textContent = c ? c.title : "";
  els.share.hidden = !c || c.temporary;
  els.chatMenu.hidden = !c;
  els.tempPill.hidden = !(c ? c.temporary : state.tempNext);
  if (c) document.title = `${c.title} · Cybok`;
  $$(".conv-item").forEach((it) => it.classList.toggle("active", it.dataset.id === c?.id));
}

async function loadConversation(id) {
  if (state.streaming) stopGeneration();
  els.welcome.hidden = true;
  els.messages.hidden = false;
  els.messages.innerHTML = "";
  for (let i = 0; i < 3; i++) {
    els.messages.append(h("div", { class: "msg assistant" }, h("div", { class: "skeleton", style: { width: "32px", height: "32px", borderRadius: "10px" } }),
      h("div", { style: { flex: 1 } }, h("div", { class: "skeleton", style: { height: "14px", width: "40%", marginBottom: "10px" } }),
        h("div", { class: "skeleton", style: { height: "14px", width: "90%", marginBottom: "8px" } }), h("div", { class: "skeleton", style: { height: "14px", width: "75%" } }))));
  }
  try {
    const data = await api(`/api/chats/${id}`);
    state.current = data.conversation;
    state.messages = data.messages;
    const saved = modelBySlug(data.conversation.model);
    const better = modelBySlug(state.defaultModel);
    state.currentModel = saved?.available && !(saved.community && better && !better.community) ? saved.slug : state.defaultModel;
    renderModel();
    renderMessages();
    renderChatHeader();
    if (data.conversation.deleted) toast("This chat is in the Trash. Restore it from Archived & Trash.", { timeout: 5000 });
  } catch (e) {
    toast(e.status === 404 ? "That conversation no longer exists." : e.message, { type: "error" });
    navigate("/app", { replace: true });
  }
}

function renderMessages() {
  els.messages.innerHTML = "";
  els.welcome.hidden = state.messages.length > 0;
  els.messages.hidden = state.messages.length === 0;
  state.messages.forEach((m) => els.messages.append(messageEl(m)));
  markLast();
  scrollToBottom(true);
}

function markLast() {
  $$(".msg", els.messages).forEach((x) => x.classList.remove("last"));
  const all = $$(".msg.assistant", els.messages);
  all[all.length - 1]?.classList.add("last");
  $$(".regen-btn", els.messages).forEach((b, i, arr) => { b.hidden = i !== arr.length - 1; });
}

function attachmentChips(list, align = "end") {
  if (!list?.length) return null;
  const row = h("div", { class: "att-row", style: { justifyContent: align === "end" ? "flex-end" : "flex-start" } });
  list.forEach((f) => {
    if (f.kind === "image") {
      const img = h("img", { class: "att-img", src: `${f.url}?thumb=1`, alt: f.name, loading: "lazy" });
      img.addEventListener("click", () => lightbox(f.url, f.name, f.download_url));
      row.append(img);
    } else {
      row.append(h("a", { class: "att-chip", href: f.url, target: "_blank", rel: "noopener", title: f.name },
        h("span", { class: "ft", text: fileBadge(f.ext) }), h("span", { class: "an" }, h("div", { text: f.name }), h("small", { text: formatBytes(f.size) }))));
    }
  });
  return row;
}

function messageEl(m) {
  if (m.role === "user") {
    const el = h("div", { class: "msg user", dataset: { id: m.id } });
    const body = h("div", { class: "msg-body" });
    const chips = attachmentChips(m.attachments);
    if (chips) body.append(chips);
    if (m.content) body.append(h("div", { class: "bubble", text: m.content }));
    const actions = h("div", { class: "msg-actions" });
    actions.append(actionBtn("copy", "Copy", (b) => { copyText(m.content); flash(b); }));
    if (m.content && !m.content.startsWith("\u{1F3A8} Create image:")) actions.append(actionBtn("edit", "Edit message", () => editMessage(el, m)));
    body.append(actions);
    el.append(body);
    return el;
  }
  const el = h("div", { class: `msg assistant ${m.status === "error" ? "error" : ""}`, dataset: { id: m.id } });
  el.append(h("img", { class: "ai-avatar", src: "/static/img/mark.png", alt: "" }));
  const body = h("div", { class: "msg-body" });
  const model = modelBySlug(m.model);
  body.append(h("div", { class: "msg-meta", html: `<b>Cybok</b>${model ? `<span>· ${esc(model.name)}</span>` : m.model === "image" ? "<span>· Image</span>" : ""}` }));
  const md = h("div", { class: "md" });
  md.innerHTML = renderMarkdown(m.content || "");
  enhance(md);
  body.append(md);
  if (m.status === "stopped") body.append(h("div", { class: "status-note", text: "Response stopped." }));
  if (m.status === "error") {
    body.append(h("div", { class: "error-actions" },
      h("button", { class: "btn sm", html: icon("refresh", "sm") + "Retry", onclick: () => regenerate() }),
      h("button", { class: "btn sm ghost", html: icon("sparkles", "sm") + "Switch model", onclick: () => $("#modelBtn").click() })));
  }
  body.append(assistantActions(el, m));
  el.append(body);
  return el;
}

function actionBtn(name, label, fn) {
  const b = h("button", { class: "icon-btn sm", title: label, "aria-label": label, html: icon(name, "sm") });
  b.addEventListener("click", () => fn(b));
  return b;
}

function flash(btn) {
  const old = btn.innerHTML;
  btn.innerHTML = icon("check", "sm");
  setTimeout(() => { btn.innerHTML = old; }, 1400);
}

function assistantActions(el, m) {
  const actions = h("div", { class: "msg-actions" });
  actions.append(actionBtn("copy", "Copy", (b) => { copyText(m.content.replace(/<think>[\s\S]*?<\/think>\s*/g, "")); flash(b); }));
  actions.append(actionBtn("volume", "Read aloud", (b) => speak(m.content, { button: b })));
  const regen = actionBtn("refresh", "Regenerate response", () => regenerate());
  regen.classList.add("regen-btn");
  actions.append(regen);
  const up = actionBtn("up", "Good response", () => feedback(m, m.feedback === 1 ? 0 : 1, up, down));
  const down = actionBtn("down", "Bad response", () => feedback(m, m.feedback === -1 ? 0 : -1, up, down));
  up.classList.toggle("on", m.feedback === 1);
  down.classList.toggle("on", m.feedback === -1);
  actions.append(up, down);
  actions.append(actionBtn("bookmark", "Save to Library", async (b) => {
    try { await api(`/api/messages/${m.id}/save`, { method: "POST", body: {} }); flash(b); toast("Saved to your Library", { type: "success", action: "Open", onAction: () => navigate("/app/library") }); }
    catch (e) { toast(e.message, { type: "error" }); }
  }));
  if (state.current && !state.current.temporary) actions.append(actionBtn("share", "Share conversation", () => openShare(state.current)));
  return actions;
}

async function feedback(m, value, up, down) {
  try {
    await api(`/api/messages/${m.id}/feedback`, { method: "POST", body: { value } });
    m.feedback = value;
    up.classList.toggle("on", value === 1);
    down.classList.toggle("on", value === -1);
    if (value) toast(value === 1 ? "Thanks for the feedback!" : "Thanks — we'll use this to improve.");
  } catch (e) { toast(e.message, { type: "error" }); }
}

function editMessage(el, m) {
  if (state.streaming) return;
  const body = el.querySelector(".msg-body");
  const ta = h("textarea", { "aria-label": "Edit message" });
  ta.value = m.content;
  const cancel = h("button", { class: "btn sm", text: "Cancel", onclick: () => el.replaceWith(messageEl(m)) });
  const save = h("button", { class: "btn sm primary", text: "Save & submit" });
  save.addEventListener("click", () => {
    const v = ta.value.trim();
    if (!v) return;
    m.content = v;
    // drop everything after this message (server does the same)
    let n = el.nextElementSibling;
    while (n) { const next = n.nextElementSibling; n.remove(); n = next; }
    const idx = state.messages.findIndex((x) => x.id === m.id);
    state.messages = state.messages.slice(0, idx + 1);
    el.replaceWith(messageEl(m));
    streamReply({ mode: "edit", message_id: m.id, content: v });
  });
  body.innerHTML = "";
  body.append(h("div", { class: "edit-box" }, ta, h("div", { class: "row" }, cancel, save)));
  ta.style.height = "auto";
  ta.style.height = Math.min(300, ta.scrollHeight + 4) + "px";
  ta.focus();
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) save.click(); if (e.key === "Escape") cancel.click(); });
}

function regenerate() {
  if (state.streaming || !state.current) return;
  const msgs = $$(".msg", els.messages);
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].classList.contains("user")) break;
    msgs[i].remove();
  }
  const lastUser = [...state.messages].reverse().findIndex((m) => m.role === "user");
  if (lastUser >= 0) state.messages = state.messages.slice(0, state.messages.length - lastUser);
  streamReply({ mode: "regenerate" });
}

/* --------------------------------------------------------------- scrolling */
const nearBottom = () => els.scroll.scrollHeight - els.scroll.scrollTop - els.scroll.clientHeight < 140;
function scrollToBottom(force = false) {
  if (force || nearBottom()) els.scroll.scrollTop = els.scroll.scrollHeight;
}
els.scroll.addEventListener("scroll", () => { els.scrollBottom.hidden = nearBottom() || els.messages.hidden; }, { passive: true });
els.scrollBottom.addEventListener("click", () => { els.scroll.scrollTo({ top: els.scroll.scrollHeight, behavior: "smooth" }); });

/* --------------------------------------------------------------- sending */
async function ensureConversation() {
  if (state.current) return state.current;
  const r = await api("/api/chats", { method: "POST", body: { model: state.currentModel, temporary: state.tempNext } });
  state.current = r.conversation;
  if (!r.conversation.temporary) state.conversations.unshift(r.conversation);
  history.replaceState({}, "", `/app/c/${r.conversation.id}`);
  renderConvList();
  renderChatHeader();
  return r.conversation;
}

async function submit() {
  const text = els.input.value.trim();
  if (state.streaming) return;
  if (state.attachments.some((a) => a.uploading)) { toast("Please wait — files are still uploading."); return; }
  if (!text && !state.attachments.length) return;
  if (state.imageMode) { if (text) return createImageInChat(text); return; }
  const atts = state.attachments.map((a) => a.file);
  els.input.value = "";
  autosize();
  clearAttachments();
  try {
    await ensureConversation();
  } catch (e) {
    toast(e.message, { type: "error" });
    els.input.value = text;
    return;
  }
  els.welcome.hidden = true;
  els.messages.hidden = false;
  const temp = { id: "tmp", role: "user", content: text, attachments: atts };
  const userEl = messageEl(temp);
  els.messages.append(userEl);
  scrollToBottom(true);
  return streamReply({ mode: "send", content: text, attachments: atts.map((a) => a.id) }, { userEl, restoreText: text });
}

/** Streams the assistant reply. Resolves with the final text (used by voice mode). */
async function streamReply(payload, { userEl, restoreText } = {}) {
  const conv = state.current;
  const aMsg = { id: null, role: "assistant", content: "", model: state.currentModel, status: "streaming", feedback: 0 };
  const el = h("div", { class: "msg assistant streaming" });
  el.append(h("img", { class: "ai-avatar", src: "/static/img/mark.png", alt: "" }));
  const body = h("div", { class: "msg-body" });
  const model = modelBySlug(state.currentModel);
  body.append(h("div", { class: "msg-meta", html: `<b>Cybok</b><span>· ${esc(model?.name || "")}</span>` }));
  const md = h("div", { class: "md", html: '<div class="typing"><span></span><span></span><span></span></div>' });
  body.append(md);
  el.append(body);
  els.messages.append(el);
  scrollToBottom(true);

  const controller = new AbortController();
  state.streaming = { controller, assistantId: null };
  setStreamingUI(true);
  let text = "", frame = 0, finalStatus = "done", errorMsg = null;
  const paint = () => {
    frame = 0;
    md.innerHTML = renderMarkdown(text, { streaming: true });
    enhance(md, { final: false });
    scrollToBottom();
  };

  try {
    const res = await api(`/api/chats/${conv.id}/messages`, { method: "POST", body: { ...payload, model: state.currentModel }, signal: controller.signal, raw: true });
    if (!res.ok) {
      let msg = `Request failed (${res.status})`;
      try { msg = (await res.json()).error || msg; } catch {}
      if (res.status === 401) location.href = "/login";
      throw Object.assign(new Error(msg), { pre: true });
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 2);
        if (!line.startsWith("data:")) continue;
        let ev;
        try { ev = JSON.parse(line.slice(5)); } catch { continue; }
        if (ev.type === "meta") {
          aMsg.id = ev.assistant_id;
          state.streaming.assistantId = ev.assistant_id;
          if (userEl && ev.user_message) {
            const real = ev.user_message;
            const existing = state.messages.find((m) => m.id === real.id);
            if (existing) Object.assign(existing, real); else state.messages.push(real);
            userEl.replaceWith(messageEl(real));
          }
          if (ev.conversation) upsertConv(ev.conversation);
        } else if (ev.type === "notice") {
          toast(ev.text, { timeout: 5000 });
          if (ev.model) {
            aMsg.model = ev.model.slug;
            const meta = body.querySelector(".msg-meta span");
            if (meta) meta.textContent = `· ${ev.model.name}`;
          }
        } else if (ev.type === "delta") {
          text += ev.text;
          if (!frame) frame = requestAnimationFrame(paint);
        } else if (ev.type === "done") {
          finalStatus = ev.status;
          errorMsg = ev.error;
        } else if (ev.type === "title") {
          upsertConv({ ...state.current, title: ev.title });
        }
      }
    }
  } catch (e) {
    if (e.name === "AbortError") finalStatus = "stopped";
    else if (e.pre) {
      el.remove();
      state.streaming = null;
      setStreamingUI(false);
      toast(e.message, { type: "error", timeout: 6000 });
      if (userEl) { userEl.remove(); if (restoreText && !els.input.value) { els.input.value = restoreText; autosize(); updateSend(); } }
      if (!els.messages.children.length) { els.messages.hidden = true; els.welcome.hidden = false; }
      return null;
    } else { finalStatus = "error"; errorMsg = e.message || "Connection lost."; }
  }
  if (frame) cancelAnimationFrame(frame);
  state.streaming = null;
  setStreamingUI(false);
  aMsg.status = finalStatus;
  aMsg.content = text || (errorMsg ? errorMsg : "");
  if (errorMsg && text) aMsg.content = `${text}\n\n> ⚠️ ${errorMsg}`;
  if (errorMsg && !text) aMsg.status = "error";
  state.messages.push(aMsg);
  const finalEl = messageEl(aMsg);
  el.replaceWith(finalEl);
  markLast();
  scrollToBottom();
  const c = state.conversations.find((x) => x.id === conv.id);
  if (c) { c.updated_at = new Date().toISOString(); renderConvList(); }
  if (finalStatus === "done" && text) {
    if (state.settings.voice_autospeak && !voiceSession) speak(text, { button: finalEl.querySelector('[title="Read aloud"]') });
    notifyDone(text);
  }
  return aMsg.status === "error" ? null : text;
}

function notifyDone(text) {
  if (!document.hidden || !state.settings.system_notifications || !("Notification" in window) || Notification.permission !== "granted") return;
  const n = new Notification("Cybok replied", { body: text.replace(/<think>[\s\S]*?<\/think>/g, "").replace(/[#*`>]/g, "").slice(0, 140), icon: "/static/img/icon-192.png" });
  n.onclick = () => { window.focus(); n.close(); };
}

function stopGeneration() {
  const s = state.streaming;
  if (!s) return;
  if (s.assistantId) api(`/api/messages/${s.assistantId}/stop`, { method: "POST", body: {} }).catch(() => {});
  s.controller.abort();
}

function setStreamingUI(on) {
  els.send.classList.toggle("stop", on);
  els.send.innerHTML = icon(on ? "stop" : "send");
  els.send.setAttribute("aria-label", on ? "Stop generating" : "Send message");
  els.send.title = on ? "Stop generating (Esc)" : "Send message";
  updateSend();
}

function updateSend() {
  els.send.disabled = !state.streaming && !els.input.value.trim() && !state.attachments.length;
}

/* --------------------------------------------------------------- image mode inside chat */
function setupImageModeSelects() {
  const st = $("#imgStyleSel"), sz = $("#imgSizeSel");
  st.innerHTML = state.imageStyles.map((s) => `<option value="${s.key}">${esc(s.label)}</option>`).join("");
  sz.innerHTML = state.imageSizes.map((s) => `<option value="${s}">${s[0].toUpperCase() + s.slice(1)}</option>`).join("");
}

function setImageMode(on) {
  state.imageMode = on;
  $("#imageModePill").hidden = !on;
  $("#imageModeBtn").hidden = on;
  $("#attachBtn").hidden = on;
  els.input.placeholder = on ? "Describe the image you want to create…" : "Message Cybok…";
  els.input.focus();
}
$("#imageModeBtn").addEventListener("click", () => setImageMode(true));
$("#imageModeOff").addEventListener("click", () => setImageMode(false));

async function createImageInChat(prompt) {
  els.input.value = "";
  autosize();
  try { await ensureConversation(); } catch (e) { toast(e.message, { type: "error" }); return; }
  els.welcome.hidden = true;
  els.messages.hidden = false;
  const userEl = messageEl({ id: "tmp", role: "user", content: `\u{1F3A8} Create image: ${prompt}` });
  els.messages.append(userEl);
  const ph = h("div", { class: "msg assistant streaming" }, h("img", { class: "ai-avatar", src: "/static/img/mark.png", alt: "" }),
    h("div", { class: "msg-body" }, h("div", { class: "msg-meta", html: "<b>Cybok</b><span>· Creating your image…</span>" }),
      h("div", { class: "tile skeleton", style: { width: "min(420px, 100%)" }, "data-label": "Painting pixels…" })));
  els.messages.append(ph);
  scrollToBottom(true);
  state.streaming = { controller: new AbortController(), assistantId: null };
  setStreamingUI(true);
  try {
    const r = await api(`/api/chats/${state.current.id}/image`, {
      method: "POST", body: { prompt, style: $("#imgStyleSel").value, size: $("#imgSizeSel").value }, signal: state.streaming.controller.signal,
    });
    state.messages.push(r.user_message, r.assistant_message);
    userEl.replaceWith(messageEl(r.user_message));
    ph.replaceWith(messageEl(r.assistant_message));
    upsertConv(r.conversation);
    if (r.error) toast(r.error, { type: "error" });
  } catch (e) {
    ph.remove();
    if (e.name !== "AbortError") toast(e.message, { type: "error" });
  } finally {
    state.streaming = null;
    setStreamingUI(false);
    markLast();
    scrollToBottom(true);
  }
}

/* --------------------------------------------------------------- composer */
function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(240, els.input.scrollHeight) + "px";
}
els.input.addEventListener("input", () => { autosize(); updateSend(); });
els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    const enterSends = state.settings.enter_to_send !== false;
    if (enterSends || e.ctrlKey || e.metaKey) {
      if (isMobile() && enterSends && !e.ctrlKey) return; // mobile keyboards: Enter = newline, use the send button
      e.preventDefault();
      submit();
    }
  }
});
els.composer.addEventListener("submit", (e) => {
  e.preventDefault();
  if (state.streaming) stopGeneration(); else submit();
});

/* attachments */
$("#attachBtn").addEventListener("click", () => els.fileInput.click());
els.fileInput.addEventListener("change", () => { addFiles([...els.fileInput.files]); els.fileInput.value = ""; });
els.input.addEventListener("paste", (e) => {
  const files = [...(e.clipboardData?.files || [])];
  if (files.length) { e.preventDefault(); addFiles(files); }
});
["dragenter", "dragover"].forEach((t) => els.composer.addEventListener(t, (e) => { if (e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); els.composer.classList.add("dragging"); } }));
["dragleave", "drop"].forEach((t) => els.composer.addEventListener(t, (e) => {
  if (t === "dragleave" && els.composer.contains(e.relatedTarget)) return;
  els.composer.classList.remove("dragging");
}));
els.composer.addEventListener("drop", (e) => { e.preventDefault(); addFiles([...(e.dataTransfer?.files || [])]); });
document.getElementById("view-chat").addEventListener("dragover", (e) => e.preventDefault());
document.getElementById("view-chat").addEventListener("drop", (e) => { e.preventDefault(); if (!els.composer.contains(e.target)) addFiles([...(e.dataTransfer?.files || [])]); });

export function addFiles(files, { preUploaded } = {}) {
  if (state.imageMode) setImageMode(false);
  const max = state.limits.max_attachments || 8;
  for (const file of files) {
    if (state.attachments.length >= max) { toast(`You can attach up to ${max} files per message.`); break; }
    if (preUploaded) { state.attachments.push({ key: file.id, file, uploading: false }); continue; }
    if (file.size > (state.limits.max_upload_mb || 20) * 1048576) { toast(`${file.name} is larger than ${state.limits.max_upload_mb} MB.`, { type: "error" }); continue; }
    const att = { key: Math.random().toString(36).slice(2), file: { name: file.name, ext: file.name.split(".").pop(), size: file.size }, uploading: true };
    state.attachments.push(att);
    const form = new FormData();
    form.append("file", file);
    api("/api/files", { method: "POST", form }).then((r) => {
      att.file = r.file;
      att.uploading = false;
      if (r.file.kind !== "image" && !r.file.has_text) toast(`${r.file.name}: no readable text found${r.file.meta?.note ? " — " + r.file.meta.note : ""}.`, { timeout: 6000 });
      renderTray();
    }).catch((e) => {
      state.attachments = state.attachments.filter((a) => a !== att);
      toast(`${file.name}: ${e.message}`, { type: "error", timeout: 6000 });
      renderTray();
    });
  }
  renderTray();
  els.input.focus();
}

function renderTray() {
  els.tray.innerHTML = "";
  els.tray.hidden = !state.attachments.length;
  state.attachments.forEach((a) => {
    const f = a.file;
    const chip = h("div", { class: `att-chip ${a.uploading ? "uploading" : ""}`, title: f.name });
    if (a.uploading) chip.append(h("span", { class: "ft", html: '<span class="spinner" style="width:14px;height:14px"></span>' }));
    else if (f.kind === "image") chip.append(h("img", { src: `${f.url}?thumb=1`, alt: "" }));
    else chip.append(h("span", { class: "ft", text: fileBadge(f.ext) }));
    chip.append(h("span", { class: "an" }, h("div", { text: f.name }), h("small", { text: a.uploading ? "Uploading…" : formatBytes(f.size) })));
    chip.append(h("button", {
      type: "button", class: "x", "aria-label": `Remove ${f.name}`, html: icon("x", "sm"),
      onclick: () => { state.attachments = state.attachments.filter((x) => x !== a); renderTray(); updateSend(); },
    }));
    els.tray.append(chip);
  });
  updateSend();
}

function clearAttachments() { state.attachments = []; renderTray(); }

/* voice: dictation + conversation */
let voiceSession = null;
$("#micBtn").addEventListener("click", () => {
  const btn = $("#micBtn");
  if (isDictating()) { stopDictation(); return; }
  const base = els.input.value ? els.input.value.replace(/\s*$/, " ") : "";
  btn.classList.add("mic-on");
  startDictation({
    onText: (final, interim) => { els.input.value = base + final + interim; autosize(); updateSend(); },
    onEnd: () => { btn.classList.remove("mic-on"); els.input.focus(); },
  });
});
$("#voiceModeBtn").addEventListener("click", () => {
  stopSpeaking();
  voiceSession = startVoiceConversation({
    send: async (text) => {
      if (state.imageMode) setImageMode(false);
      els.input.value = text;
      return await submit();
    },
    onClose: () => { voiceSession = null; },
  });
});

/* --------------------------------------------------------------- topbar: share & chat menu */
els.share.addEventListener("click", () => state.current && openShare(state.current));
els.chatMenu.addEventListener("click", (e) => state.current && convMenu(e.currentTarget, state.conversations.find((c) => c.id === state.current.id) || state.current));
els.tempPill.addEventListener("click", () => {
  if (state.current) return;
  state.tempNext = !state.tempNext;
  renderChatHeader();
});

export function openShare(c) {
  const body = h("div");
  const render = (conv) => {
    body.innerHTML = "";
    if (!conv.shared) {
      body.append(h("p", { text: "Create a public, read-only link to this conversation. People with the link can read the messages — your name, e-mail, files and other chats stay private." }));
      m.footer.innerHTML = "";
      m.footer.append(h("button", { class: "btn", text: "Cancel", onclick: () => m.close() }),
        h("button", { class: "btn brand", html: icon("link") + "<span>Create link</span>", onclick: () => setShare({ enabled: true }) }));
    } else {
      const url = location.origin + conv.share_url;
      const input = h("input", { class: "input", value: url, readonly: true });
      body.append(h("p", { text: "Anyone with this link can view this conversation (read-only). New messages you send later are included." }),
        h("div", { class: "share-link" }, input, h("button", { class: "btn primary", html: icon("copy") + "<span>Copy</span>", onclick: (e) => { copyText(url); flash(e.currentTarget); toast("Link copied", { type: "success" }); } })));
      m.footer.innerHTML = "";
      m.footer.append(
        h("button", { class: "btn danger", text: "Disable link", onclick: () => setShare({ enabled: false }) }),
        h("button", { class: "btn", text: "New link", title: "Old link stops working", onclick: () => setShare({ enabled: true, regenerate: true }) }),
        h("a", { class: "btn", href: conv.share_url, target: "_blank", rel: "noopener", html: icon("external") + "<span>Open</span>" }));
      input.addEventListener("focus", () => input.select());
    }
  };
  const setShare = async (payload) => {
    try {
      const r = await api(`/api/chats/${c.id}/share`, { method: "POST", body: payload });
      upsertConv(r.conversation);
      c = r.conversation;
      render(c);
      toast(payload.enabled ? "Share link is ready" : "Share link disabled", { type: "success" });
    } catch (e) { toast(e.message, { type: "error" }); }
  };
  const m = modal({ title: "Share conversation", body, footer: [h("span")] });
  render(state.conversations.find((x) => x.id === c.id) || c);
}

/* ================================================================ archived & trash */
async function showArchived(tab = "archived") {
  const root = $("#view-archived");
  root.innerHTML = "";
  const page = h("div", { class: "page" }, h("div", { class: "page-inner", style: { maxWidth: "820px" } }));
  const inner = page.firstChild;
  const seg = h("div", { class: "segmented" });
  const head = h("div", { class: "page-head" }, h("div", {}, h("h1", { text: "Archived & Trash" }), h("p", { text: "Archived chats are hidden from the sidebar. Deleted chats stay in the Trash for 30 days." })));
  const actions = h("div", { class: "actions" });
  head.append(actions);
  inner.append(head, h("div", { style: { marginBottom: "16px" } }, seg));
  const list = h("div");
  inner.append(list);
  root.append(page);
  [["archived", "Archived", "archive"], ["trash", "Trash", "trash"]].forEach(([k, label, ic]) => {
    seg.append(h("button", { class: tab === k ? "on" : "", html: icon(ic, "sm") + label, onclick: () => showArchived(k) }));
  });
  list.append(h("div", { class: "skeleton", style: { height: "60px", marginBottom: "8px" } }), h("div", { class: "skeleton", style: { height: "60px" } }));
  try {
    const r = await api(`/api/chats?${tab === "trash" ? "trash=1" : "archived=1"}`);
    list.innerHTML = "";
    if (r.conversations.length) {
      actions.append(h("button", {
        class: "btn sm danger", html: icon("trash", "sm") + (tab === "trash" ? "Empty trash" : "Delete all archived"),
        onclick: async () => {
          if (!await confirmDialog({ title: tab === "trash" ? "Empty trash?" : "Delete all archived chats?", message: "These conversations will be permanently deleted. This can't be undone.", confirm: "Delete permanently", danger: true })) return;
          await api(`/api/chats?scope=${tab}`, { method: "DELETE" });
          state.conversations = state.conversations.filter((c) => !(tab === "archived" && c.archived));
          renderConvList();
          toast("Deleted permanently", { type: "success" });
          showArchived(tab);
        },
      }));
    }
    if (!r.conversations.length) {
      list.append(h("div", { class: "empty", html: `<div class="ei">${icon(tab === "trash" ? "trash" : "archive")}</div><h3>${tab === "trash" ? "Trash is empty" : "No archived chats"}</h3><p>${tab === "trash" ? "Deleted conversations appear here for 30 days." : "Archive a chat from its ⋯ menu to tidy up your sidebar."}</p>` }));
      return;
    }
    r.conversations.forEach((c, i) => {
      const row = h("div", { class: "list-card", style: { animationDelay: `${i * 25}ms` } }, h("span", { class: "si", html: icon("chat") }),
        h("div", { class: "lt" }, h("b", { text: c.title }), h("small", { text: `Updated ${timeAgo(c.updated_at)}` })));
      if (tab === "archived") {
        row.append(h("button", { class: "btn sm", html: icon("eye", "sm") + "Open", onclick: () => navigate(`/app/c/${c.id}`) }),
          h("button", { class: "btn sm", html: icon("undo", "sm") + "Unarchive", onclick: async () => { await updateConv(c.id, { archived: false }, "Chat moved back to your history"); row.remove(); } }));
      } else {
        row.append(h("button", {
          class: "btn sm", html: icon("undo", "sm") + "Restore", onclick: async () => {
            const res = await api(`/api/chats/${c.id}/restore`, { method: "POST" });
            upsertConv(res.conversation); row.remove(); toast("Chat restored", { type: "success" });
          },
        }));
      }
      row.append(h("button", {
        class: "icon-btn sm", title: "Delete permanently", html: icon("trash", "sm"), onclick: async () => {
          if (!await confirmDialog({ title: "Delete permanently?", message: `"${c.title}" will be deleted forever.`, confirm: "Delete", danger: true })) return;
          await api(`/api/chats/${c.id}?permanent=1`, { method: "DELETE" });
          state.conversations = state.conversations.filter((x) => x.id !== c.id);
          renderConvList();
          row.remove();
        },
      }));
      list.append(row);
    });
  } catch (e) { toast(e.message, { type: "error" }); }
}

/* ================================================================ search palette */
function openSearch() {
  closeMenu();
  const input = h("input", { placeholder: "Search chats, files, images, logos and commands…", "aria-label": "Search", autofocus: true });
  const results = h("div", { class: "palette-results" });
  const box = h("div", {}, h("div", { class: "palette-input", html: icon("search") }), results,
    h("div", { class: "pal-foot", html: "<span><kbd>↑</kbd> <kbd>↓</kbd> navigate</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span>" }));
  box.firstChild.append(input);
  const m = modal({ body: box, className: "palette", sheet: false });
  m.body.style.padding = "0";
  let items = [], focus = 0;
  const commands = [
    { label: "New chat", icon: "newchat", run: () => navigate("/app") },
    { label: "Create image", icon: "image", run: () => navigate("/app/images") },
    { label: "Logo Studio", icon: "pen", run: () => navigate("/app/logos") },
    { label: "Open Library", icon: "library", run: () => navigate("/app/library") },
    { label: "Upload a file", icon: "upload", run: () => { navigate("/app"); setTimeout(() => els.fileInput.click(), 100); } },
    { label: "Settings", icon: "settings", run: () => openSettings() },
    { label: "Archived & Trash", icon: "archive", run: () => navigate("/app/archived") },
    { label: "Toggle dark / light theme", icon: "moon", run: () => saveSetting({ theme: document.documentElement.dataset.theme === "dark" ? "light" : "dark" }) },
    { label: "Keyboard shortcuts", icon: "keyboard", run: showShortcuts },
  ];
  const hl = (text, q) => {
    const s = esc(text || "");
    if (!q) return s;
    const i = s.toLowerCase().indexOf(esc(q).toLowerCase());
    return i < 0 ? s : s.slice(0, i) + "<mark>" + s.slice(i, i + esc(q).length) + "</mark>" + s.slice(i + esc(q).length);
  };
  const draw = (groups, q) => {
    results.innerHTML = "";
    items = [];
    groups.forEach(([name, list]) => {
      if (!list.length) return;
      results.append(h("div", { class: "pal-group", text: name }));
      list.forEach((it) => {
        const b = h("button", { class: "pal-item" });
        b.append(h("span", { class: "pi", html: it.thumb ? `<img src="${esc(it.thumb)}" alt="">` : icon(it.icon) }),
          h("span", { class: "pt", html: `<div>${hl(it.label, q)}</div>${it.sub ? `<small>${hl(it.sub, q)}</small>` : ""}` }));
        b.addEventListener("click", () => { m.close(); it.run(); });
        b.addEventListener("mousemove", () => setFocus(items.indexOf(b)));
        results.append(b);
        items.push(b);
      });
    });
    if (!items.length) results.append(h("div", { class: "empty", html: `<p>No results for “${esc(q)}”.</p>` }));
    setFocus(0);
  };
  const setFocus = (i) => {
    focus = Math.max(0, Math.min(i, items.length - 1));
    items.forEach((x, j) => x.classList.toggle("focus", j === focus));
    items[focus]?.scrollIntoView({ block: "nearest" });
  };
  const recent = () => draw([
    ["Actions", commands.slice(0, 5).map((c) => ({ ...c }))],
    ["Recent chats", state.conversations.filter((c) => !c.archived).slice(0, 6).map((c) => ({ label: c.title, sub: timeAgo(c.updated_at), icon: "chat", run: () => navigate(`/app/c/${c.id}`) }))],
  ], "");
  let seq = 0;
  const search = async () => {
    const q = input.value.trim();
    if (q.length < 2) { recent(); return; }
    const my = ++seq;
    const cmds = commands.filter((c) => c.label.toLowerCase().includes(q.toLowerCase()));
    try {
      const r = await api(`/api/search?q=${encodeURIComponent(q)}`);
      if (my !== seq) return;
      draw([
        ["Actions", cmds],
        ["Chats", r.chats.map((c) => ({ label: c.title, sub: c.snippet || timeAgo(c.updated_at), icon: c.pinned ? "pin" : "chat", run: () => navigate(`/app/c/${c.id}`) }))],
        ["Files", r.files.map((f) => ({ label: f.name, sub: f.snippet || formatBytes(f.size), icon: "file", thumb: f.kind === "image" ? `${f.url}?thumb=1` : null, run: () => navigate("/app/library") }))],
        ["Generated", r.generated.map((g) => ({ label: g.title, sub: g.subtitle, icon: g.type === "text" ? "bookmark" : "image", thumb: g.type !== "text" ? g.thumb : null, run: () => navigate(g.type === "logo" ? "/app/logos" : g.type === "image" ? "/app/images" : "/app/library") }))],
      ], q);
    } catch (e) { toast(e.message, { type: "error" }); }
  };
  const debounced = ((fn) => { let t; return () => { clearTimeout(t); t = setTimeout(fn, 180); }; })(search);
  input.addEventListener("input", debounced);
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setFocus(focus + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setFocus(focus - 1); }
    else if (e.key === "Enter") { e.preventDefault(); items[focus]?.click(); }
  });
  recent();
  setTimeout(() => input.focus(), 30);
}

/* ================================================================ shortcuts */
const SHORTCUTS = [
  ["Search everything", ["Ctrl", "K"]], ["New chat", ["Ctrl", "Shift", "O"]], ["Toggle sidebar", ["Ctrl", "B"]],
  ["Create image mode", ["Ctrl", "Shift", "I"]], ["Focus message box", ["Shift", "Esc"]], ["Stop generating", ["Esc"]],
  ["Copy last response", ["Ctrl", "Shift", "C"]], ["Send message", ["Enter"]], ["New line", ["Shift", "Enter"]],
  ["Rename chat (in sidebar)", ["F2"]], ["Settings", ["Ctrl", ","]], ["Show shortcuts", ["Ctrl", "/"]],
];
export function showShortcuts() {
  const list = h("div", { class: "kbd-list" });
  SHORTCUTS.forEach(([label, keys]) => list.append(h("div", {}, h("span", { text: label }), h("span", { html: keys.map((k) => `<kbd>${k}</kbd>`).join("") }))));
  modal({ title: "Keyboard shortcuts", body: list });
}

document.addEventListener("keydown", (e) => {
  const mod = e.ctrlKey || e.metaKey;
  const k = e.key.toLowerCase();
  if (mod && k === "k") { e.preventDefault(); openSearch(); }
  else if (mod && e.shiftKey && k === "o") { e.preventDefault(); navigate("/app"); setTimeout(() => els.input.focus(), 50); }
  else if (mod && !e.shiftKey && k === "b") { e.preventDefault(); toggleSidebar(); }
  else if (mod && e.shiftKey && k === "i") { e.preventDefault(); if (location.pathname !== "/app" && !location.pathname.startsWith("/app/c/")) navigate("/app"); setImageMode(true); }
  else if (mod && e.shiftKey && k === "c") {
    const last = [...state.messages].reverse().find((m) => m.role === "assistant");
    if (last) { e.preventDefault(); copyText(last.content.replace(/<think>[\s\S]*?<\/think>\s*/g, "")); toast("Last response copied", { type: "success" }); }
  }
  else if (mod && k === "/") { e.preventDefault(); showShortcuts(); }
  else if (mod && k === ",") { e.preventDefault(); openSettings(); }
  else if (e.key === "Escape" && e.shiftKey) { e.preventDefault(); els.input.focus(); }
  else if (e.key === "Escape" && state.streaming && !document.querySelector(".modal-backdrop")) { stopGeneration(); }
});

/* lightbox for images inside messages */
els.messages.addEventListener("click", (e) => {
  const img = e.target.closest(".md img");
  if (img) lightbox(img.src, img.alt, img.getAttribute("src").startsWith("/media/file/") ? img.getAttribute("src") + "?download=1" : null);
});

/* other modules can start a chat about a file (Library → "Ask Cybok") */
on("ask-about-file", (file) => {
  navigate("/app");
  setTimeout(() => {
    addFiles([file], { preUploaded: true });
    els.input.value = file.kind === "image" ? "Describe this image." : `Summarize "${file.name}" and list the most important points.`;
    autosize();
    updateSend();
  }, 60);
});
on("conversations-changed", async () => {
  const r = await api("/api/chats");
  state.conversations = r.conversations;
  renderConvList();
});
on("navigate", (path) => navigate(path));

boot();
