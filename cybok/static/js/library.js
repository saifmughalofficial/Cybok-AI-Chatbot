/* Library: uploads, generated images, logos and saved responses in one searchable place. */
import { api, confirmDialog, debounce, esc, fileBadge, fmtDate, formatBytes, h, icon, lightbox, modal, promptDialog, showMenu, timeAgo, toast } from "./core.js";
import { enhance, renderMarkdown } from "./markdown.js";
import { emit } from "./state.js";

const lib = { type: "all", q: "", sort: "new", folder: "__all__", view: "grid", items: [], folders: [] };
try { lib.view = localStorage.getItem("cybok-lib-view") || "grid"; } catch {}
let built = false;
let els = {};

const TYPES = [["all", "All", "grid"], ["image", "Images", "image"], ["logo", "Logos", "pen"], ["document", "Documents", "filetext"],
  ["data", "Spreadsheets", "sheet"], ["code", "Code", "code"], ["text", "Saved responses", "bookmark"]];

export function showLibrary(root) {
  if (!built) build(root);
  load();
}

function build(root) {
  built = true;
  const search = h("input", { class: "input", placeholder: "Search your library…", "aria-label": "Search library" });
  search.addEventListener("input", debounce(() => { lib.q = search.value; load(); }, 250));
  const sort = h("select", { class: "select", "aria-label": "Sort" },
    ...[["new", "Newest first"], ["old", "Oldest first"], ["name", "Name A–Z"], ["size", "Largest first"]].map(([v, l]) => h("option", { value: v, text: l })));
  sort.addEventListener("change", () => { lib.sort = sort.value; load(); });
  const folder = h("select", { class: "select", "aria-label": "Folder" });
  folder.addEventListener("change", () => { lib.folder = folder.value; load(); });
  const viewSeg = h("div", { class: "segmented" });
  [["grid", "grid"], ["list", "list"]].forEach(([k, ic]) => {
    const b = h("button", { class: lib.view === k ? "on" : "", html: icon(ic, "sm"), title: k === "grid" ? "Grid view" : "List view", "aria-label": k === "grid" ? "Grid view" : "List view" });
    b.addEventListener("click", () => {
      lib.view = k;
      try { localStorage.setItem("cybok-lib-view", k); } catch {}
      viewSeg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      draw();
    });
    viewSeg.append(b);
  });
  const fileInput = h("input", { type: "file", multiple: true, hidden: true });
  fileInput.addEventListener("change", () => upload([...fileInput.files]).then(() => { fileInput.value = ""; }));
  const uploadBtn = h("button", { class: "btn brand", html: icon("upload") + "<span>Upload</span>", onclick: () => fileInput.click() });
  const chips = h("div", { class: "filter-chips" });
  TYPES.forEach(([k, l, ic]) => {
    const c = h("button", { class: `chip ${k === lib.type ? "on" : ""}`, html: icon(ic, "sm") + esc(l) });
    c.addEventListener("click", () => { lib.type = k; chips.querySelectorAll(".chip").forEach((x) => x.classList.toggle("on", x === c)); load(); });
    chips.append(c);
  });
  const grid = h("div", { class: "lib-grid" });
  const meter = h("div", { class: "storage-meter" });
  const page = h("div", { class: "page" }, h("div", { class: "page-inner" },
    h("div", { class: "page-head" }, h("div", {}, h("h1", { text: "Library" }), h("p", { text: "Your files, images, logos and saved answers — private to you." })),
      h("div", { class: "actions" }, meter, uploadBtn, fileInput)),
    h("div", { class: "lib-toolbar" }, h("div", { class: "search", html: icon("search") }, search), folder, sort, viewSeg),
    chips, grid));
  page.querySelector(".search").append(search);
  root.append(page);
  // drag & drop upload onto the library
  page.addEventListener("dragover", (e) => e.preventDefault());
  page.addEventListener("drop", (e) => { e.preventDefault(); upload([...(e.dataTransfer?.files || [])]); });
  els = { grid, folder, meter };
}

async function upload(files) {
  for (const f of files) {
    const form = new FormData();
    form.append("file", f);
    toast(`Uploading ${f.name}…`, { timeout: 1800 });
    try { await api("/api/files", { method: "POST", form }); toast(`${f.name} uploaded`, { type: "success" }); }
    catch (e) { toast(`${f.name}: ${e.message}`, { type: "error", timeout: 6000 }); }
  }
  load();
}

async function load() {
  if (!els.grid) return;
  if (!lib.items.length) {
    els.grid.innerHTML = "";
    for (let i = 0; i < 8; i++) els.grid.append(h("div", { class: "skeleton", style: { aspectRatio: "4/3.6", borderRadius: "18px" } }));
  }
  const params = new URLSearchParams({ type: lib.type, q: lib.q, sort: lib.sort, folder: lib.folder });
  try {
    const r = await api(`/api/library?${params}`);
    lib.items = r.items;
    lib.folders = r.folders;
    els.meter.innerHTML = `${icon("database", "sm")}<span>${formatBytes(r.storage_used)} used</span>`;
    els.folder.innerHTML = "";
    els.folder.append(h("option", { value: "__all__", text: "All folders" }), h("option", { value: "", text: "Unfiled" }), ...r.folders.map((f) => h("option", { value: f, text: f })));
    els.folder.value = lib.folder;
    draw();
  } catch (e) { toast(e.message, { type: "error" }); }
}

function draw() {
  const g = els.grid;
  g.innerHTML = "";
  g.className = `lib-grid ${lib.view === "list" ? "lib-list" : ""}`;
  if (!lib.items.length) {
    g.className = "";
    g.append(h("div", {
      class: "empty", html: lib.q || lib.type !== "all" ? `<div class="ei">${icon("search")}</div><h3>Nothing found</h3><p>Try a different search or filter.</p>`
        : `<div class="ei">${icon("library")}</div><h3>Your library is empty</h3><p>Upload documents, or save images, logos and answers from your chats — they'll all live here.</p>`,
    }));
    return;
  }
  lib.items.forEach((it, i) => g.append(card(it, i)));
}

function thumbFor(it) {
  const t = h("div", { class: `lib-thumb ${it.type === "logo" ? "logo" : ""}` });
  if (it.type === "image" || it.type === "logo") t.append(h("img", { src: it.thumb || it.url, alt: "", loading: "lazy" }));
  else if (it.type === "text") t.append(h("div", { class: "textprev", text: (it.output || "").slice(0, 300) }));
  else t.append(h("div", { class: "ftype", text: fileBadge(it.subtitle || it.type) }));
  return t;
}

function card(it, i) {
  const c = h("div", { class: "lib-card", tabindex: "0", style: { animationDelay: `${Math.min(i, 20) * 20}ms` } });
  c.append(thumbFor(it));
  const more = h("button", { class: "icon-btn sm", "aria-label": "Options", html: icon("more") });
  more.addEventListener("click", (e) => { e.stopPropagation(); itemMenu(more, it); });
  c.append(h("div", { class: "lib-info" },
    h("div", { class: "t" }, h("div", { text: it.title }), h("small", { text: `${it.subtitle || ""}${it.folder ? " · " + it.folder : ""} · ${timeAgo(it.created_at)}` })), more));
  c.addEventListener("click", () => preview(it));
  c.addEventListener("keydown", (e) => { if (e.key === "Enter") preview(it); });
  return c;
}

function itemMenu(anchor, it) {
  showMenu(anchor, [
    { label: "Preview", icon: "eye", onClick: () => preview(it) },
    it.file_id ? { label: "Ask Cybok about this", icon: "chat", onClick: () => askAbout(it) } : null,
    { label: "Rename", icon: "edit", onClick: () => rename(it) },
    { label: "Move to folder", icon: "folder", onClick: () => moveFolder(it) },
    it.download_url ? { label: "Download", icon: "download", onClick: () => { location.href = it.download_url; } } : null,
    it.type === "text" ? { label: "Copy text", icon: "copy", onClick: () => navigator.clipboard.writeText(it.output || "").then(() => toast("Copied")) } : null,
    "sep",
    { label: "Delete", icon: "trash", danger: true, onClick: () => remove(it) },
  ], { align: "end" });
}

async function askAbout(it) {
  try {
    const r = await api(`/api/files/${it.file_id}`);
    emit("ask-about-file", r.file);
  } catch (e) { toast(e.message, { type: "error" }); }
}

async function rename(it) {
  const v = await promptDialog({ title: "Rename", value: it.title, confirm: "Rename" });
  if (!v) return;
  try { await api(`/api/library/${it.key}`, { method: "PATCH", body: { title: v } }); toast("Renamed", { type: "success" }); load(); }
  catch (e) { toast(e.message, { type: "error" }); }
}

async function moveFolder(it) {
  const v = await promptDialog({ title: "Move to folder", label: `Folder name${lib.folders.length ? " (existing: " + lib.folders.join(", ") + ")" : ""}. Leave empty for no folder.`, value: it.folder || "", confirm: "Move", maxlength: 80 });
  if (v === null) return;
  try { await api(`/api/library/${it.key}`, { method: "PATCH", body: { folder: v } }); toast(v ? `Moved to “${v}”` : "Removed from folder", { type: "success" }); load(); }
  catch (e) { toast(e.message, { type: "error" }); }
}

async function remove(it) {
  if (!await confirmDialog({ title: "Delete permanently?", message: `“${it.title}” will be deleted from your library. This can't be undone.`, confirm: "Delete", danger: true })) return;
  try { await api(`/api/library/${it.key}`, { method: "DELETE" }); toast("Deleted", { type: "success" }); load(); }
  catch (e) { toast(e.message, { type: "error" }); }
}

async function preview(it) {
  if (it.type === "image" || it.type === "logo") { lightbox(it.url, it.title, it.download_url); return; }
  const body = h("div");
  const footer = [];
  if (it.file_id) footer.push(h("button", { class: "btn", html: icon("chat") + "<span>Ask Cybok</span>", onclick: () => { m.close(); askAbout(it); } }));
  if (it.download_url) footer.push(h("a", { class: "btn primary", href: it.download_url, html: icon("download") + "<span>Download</span>" }));
  const m = modal({ title: it.title, body, footer, wide: true });
  if (it.type === "text") {
    const md = h("div", { class: "md" });
    md.innerHTML = renderMarkdown(it.output || "");
    enhance(md);
    body.append(h("p", { class: "small muted", text: `Saved ${fmtDate(it.created_at)}${it.prompt ? " · from “" + it.prompt + "”" : ""}` }), md);
    return;
  }
  body.append(h("div", { class: "skeleton", style: { height: "200px" } }));
  try {
    const r = await api(`/api/files/${it.file_id}`);
    const f = r.file;
    body.innerHTML = "";
    const meta = Object.entries(f.meta || {}).filter(([k]) => !["width", "height"].includes(k) || f.kind === "image")
      .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ");
    body.append(h("p", { class: "small muted", text: `${f.ext.toUpperCase()} · ${formatBytes(f.size)} · uploaded ${fmtDate(f.created_at)}${meta ? " · " + meta : ""}` }));
    if (f.mime === "application/pdf") body.append(h("p", {}, h("a", { href: f.url, target: "_blank", rel: "noopener", html: "Open the original PDF in a new tab ↗" })));
    if (f.text_preview) {
      body.append(h("div", { class: "label", style: { margin: "6px 0" }, text: `Extracted text (${f.text_length.toLocaleString()} characters) — this is what Cybok reads:` }),
        h("div", { class: "preview-text", text: f.text_preview + (f.text_length > f.text_preview.length ? "\n\n… (truncated preview)" : "") }));
    } else {
      body.append(h("p", { text: "No text could be extracted from this file." }));
    }
  } catch (e) { body.innerHTML = ""; body.append(h("p", { text: e.message })); }
}
