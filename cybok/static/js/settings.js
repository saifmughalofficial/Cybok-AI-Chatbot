/* Settings modal: Account, Appearance, Chat, Voice, Privacy & Data, Notifications, Shortcuts, About. */
import { api, confirmDialog, esc, fmtDate, h, icon, isMobile, modal, toast } from "./core.js";
import { emit, state } from "./state.js";
import { speak, sttSupported, ttsSupported, voices } from "./voice.js";

const SECTIONS = [
  ["account", "Account", "user"], ["appearance", "Appearance", "palette"], ["chat", "Chat", "chat"], ["voice", "Voice", "mic"],
  ["privacy", "Privacy & Data", "shield"], ["notifications", "Notifications", "bell"], ["shortcuts", "Shortcuts", "keyboard"], ["about", "About", "info"],
];

async function save(patch, silent = false) {
  Object.assign(state.settings, patch);
  emit("settings-changed");
  try {
    const r = await api("/api/settings", { method: "PATCH", body: patch });
    state.settings = r.settings;
    if (!silent) toast("Saved", { type: "success", timeout: 1400 });
  } catch (e) { toast(e.message, { type: "error" }); }
}

const row = (title, desc, control) => h("div", { class: "set-row" }, h("div", { class: "sl" }, h("b", { text: title }), desc ? h("span", { text: desc }) : null), control);

function toggle(key, onChange) {
  const input = h("input", { type: "checkbox" });
  input.checked = !!state.settings[key];
  input.addEventListener("change", async () => {
    if (onChange && (await onChange(input.checked)) === false) { input.checked = !input.checked; return; }
    save({ [key]: input.checked });
  });
  return h("label", { class: "switch" }, input, h("span"));
}

function select(key, options) {
  const s = h("select", { class: "select" }, ...options.map(([v, l]) => h("option", { value: v, text: l })));
  s.value = state.settings[key] ?? options[0][0];
  s.addEventListener("change", () => save({ [key]: s.value }));
  return s;
}

export function openSettings(section = "account") {
  const nav = h("nav", { class: "settings-nav", "aria-label": "Settings sections" }, h("h3", { text: "Settings" }));
  const pane = h("div", { class: "settings-pane" });
  const wrap = h("div", { class: "settings" }, nav, pane);
  const m = modal({ body: wrap, xl: true });
  m.body.style.padding = "0";
  const close = h("button", { class: "icon-btn", "aria-label": "Close settings", html: icon("x"), style: { position: "absolute", top: "12px", right: "12px", zIndex: 2 }, onclick: () => m.close() });
  m.el.style.position = "relative";
  m.el.append(close);
  const show = (key) => {
    nav.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.k === key));
    pane.innerHTML = "";
    pane.scrollTop = 0;
    RENDER[key](pane, m);
  };
  SECTIONS.forEach(([k, label, ic]) => {
    const b = h("button", { class: "nav-item", dataset: { k }, html: icon(ic) + esc(label) });
    b.addEventListener("click", () => show(k));
    nav.append(b);
  });
  show(section);
}

const RENDER = {
  account(p, m) {
    const u = state.user;
    p.append(h("h2", { text: "Account" }), h("p", { class: "lead", text: "Your profile and sign-in details." }));
    // avatar
    const av = h("div", { class: "avatar lg", html: u.avatar ? `<img src="${esc(u.avatar)}" alt="">` : esc(u.initials) });
    const file = h("input", { type: "file", accept: "image/*", hidden: true });
    file.addEventListener("change", async () => {
      if (!file.files[0]) return;
      const form = new FormData();
      form.append("file", file.files[0]);
      try {
        const r = await api("/api/profile/avatar", { method: "POST", form });
        state.user = r.user; emit("user-changed"); RENDER.account(clear(p), m); toast("Profile picture updated", { type: "success" });
      } catch (e) { toast(e.message, { type: "error" }); }
    });
    const avRow = h("div", { class: "row", style: { gap: "16px", marginBottom: "18px" } }, av,
      h("div", { class: "row wrap" }, h("button", { class: "btn sm", html: icon("upload", "sm") + "Change photo", onclick: () => file.click() }),
        u.avatar ? h("button", { class: "btn sm ghost", text: "Remove", onclick: async () => { const r = await api("/api/profile/avatar", { method: "DELETE" }); state.user = r.user; emit("user-changed"); RENDER.account(clear(p), m); } }) : null), file);
    p.append(avRow);

    const name = h("input", { class: "input", value: u.name, maxlength: 120 });
    const email = h("input", { class: "input", value: u.email, type: "email" });
    const pw = h("input", { class: "input", type: "password", placeholder: "Current password (needed to change e-mail)" });
    const saveBtn = h("button", { class: "btn primary", text: "Save profile" });
    saveBtn.addEventListener("click", async () => {
      try {
        const r = await api("/api/profile", { method: "PATCH", body: { name: name.value, email: email.value, password: pw.value } });
        state.user = r.user; emit("user-changed"); pw.value = ""; toast("Profile saved", { type: "success" });
      } catch (e) { toast(e.message, { type: "error" }); }
    });
    p.append(h("div", { class: "set-group", style: { padding: "16px" } },
      h("div", { class: "field" }, h("label", { text: "Name" }), name),
      h("div", { class: "field" }, h("label", { text: "E-mail" }), email),
      u.has_password ? h("div", { class: "field" }, pw) : null,
      h("div", { class: "row" }, h("span", { class: "small muted", text: `Member since ${fmtDate(u.created_at).split(",")[0]}${u.google_linked ? " · Google account linked" : ""}` }), h("span", { class: "spacer" }), saveBtn)));

    // password
    const cur = h("input", { class: "input", type: "password", autocomplete: "current-password", placeholder: "Current password" });
    const nw = h("input", { class: "input", type: "password", autocomplete: "new-password", placeholder: "New password (8+ chars, letter + number)" });
    const nw2 = h("input", { class: "input", type: "password", autocomplete: "new-password", placeholder: "Repeat new password" });
    const pwBtn = h("button", { class: "btn", text: u.has_password ? "Change password" : "Set password" });
    pwBtn.addEventListener("click", async () => {
      if (nw.value !== nw2.value) { toast("New passwords don't match.", { type: "error" }); return; }
      try {
        await api("/api/profile/password", { method: "POST", body: { current: cur.value, new: nw.value } });
        cur.value = nw.value = nw2.value = "";
        state.user.has_password = true;
        toast("Password updated. Other devices were signed out.", { type: "success" });
      } catch (e) { toast(e.message, { type: "error" }); }
    });
    p.append(h("h3", { text: "Password", style: { margin: "6px 0 10px", fontSize: "15px" } }),
      h("div", { class: "set-group", style: { padding: "16px" } },
        u.has_password ? h("div", { class: "field" }, cur) : h("p", { class: "small muted", text: "You signed in with Google. Set a password to also sign in with e-mail." }),
        h("div", { class: "field" }, nw), h("div", { class: "field" }, nw2), h("div", { class: "row" }, h("span", { class: "spacer" }), pwBtn)));

    // sessions + delete
    const logoutAll = h("form", { method: "post", action: "/account/logout-everywhere" },
      h("input", { type: "hidden", name: "csrf_token", value: document.querySelector('meta[name="csrf-token"]').content }),
      h("button", { class: "btn sm", type: "submit", text: "Sign out everywhere" }));
    p.append(h("div", { class: "set-group" }, row("Active sessions", "Sign out of Cybok on every device, including this one.", logoutAll)));
    p.append(h("h3", { text: "Danger zone", style: { margin: "6px 0 10px", fontSize: "15px", color: "var(--danger)" } }),
      h("div", { class: "set-group danger" }, row("Delete account", "Permanently delete your account, chats, files, images and settings.",
        h("button", { class: "btn sm danger", text: "Delete account", onclick: () => deleteAccount() }))));
  },

  appearance(p) {
    p.append(h("h2", { text: "Appearance" }), h("p", { class: "lead", text: "Make Cybok look the way you like." }));
    const cards = h("div", { class: "theme-cards" });
    [["light", "Light"], ["dark", "Dark"], ["system", "System"]].forEach(([k, l]) => {
      const c = h("button", { class: `theme-card ${state.settings.theme === k ? "on" : ""}` }, h("div", { class: `tp ${k}` }, h("i"), h("em")), l);
      c.addEventListener("click", () => { save({ theme: k }, true); cards.querySelectorAll(".theme-card").forEach((x) => x.classList.toggle("on", x === c)); });
      cards.append(c);
    });
    p.append(h("div", { class: "label", text: "Theme", style: { marginBottom: "8px" } }), cards);
    const dots = h("div", { class: "accent-dots" });
    [["cybok", "linear-gradient(135deg,#ff3448,#2f73ff)"], ["blue", "#2f6bff"], ["red", "#ef3a4b"], ["violet", "#7b5cff"], ["emerald", "#10a56b"]].forEach(([k, bg]) => {
      const b = h("button", { class: state.settings.accent === k ? "on" : "", style: { background: bg }, title: k, "aria-label": `Accent ${k}` });
      b.addEventListener("click", () => { save({ accent: k }, true); dots.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); });
      dots.append(b);
    });
    p.append(h("div", { class: "set-group", style: { marginTop: "18px" } },
      row("Accent color", "Used for buttons, links and highlights.", dots),
      row("Chat text size", "Size of messages in conversations.", select("font_size", [["sm", "Small"], ["md", "Default"], ["lg", "Large"]]))));
  },

  chat(p) {
    p.append(h("h2", { text: "Chat" }), h("p", { class: "lead", text: "How Cybok answers you." }));
    const models = state.models.filter((m) => m.available).map((m) => [m.slug, `${m.name} — ${m.family}`]);
    const ci = h("textarea", { class: "textarea", maxlength: 3000, placeholder: "e.g. I'm a computer science student. Explain things simply and give code examples in Python." });
    ci.value = state.settings.custom_instructions || "";
    const ciSave = h("button", { class: "btn sm primary", text: "Save instructions", onclick: () => save({ custom_instructions: ci.value }) });
    p.append(h("div", { class: "set-group" },
      row("Default model", "Used for new chats. All models are free.", select("default_model", models.length ? models : [["", "No model available"]])),
      row("Response style", "Concise answers or detailed explanations.", select("response_style", [["concise", "Concise"], ["balanced", "Balanced"], ["detailed", "Detailed"]])),
      row("Enter to send", "Off: Enter adds a new line and Ctrl+Enter sends.", toggle("enter_to_send"))),
      h("div", { class: "field" }, h("label", { text: "Custom instructions" }), ci, h("span", { class: "hint", text: "Cybok follows these in every new message." })),
      h("div", { class: "row" }, h("span", { class: "spacer" }), ciSave));
  },

  voice(p) {
    p.append(h("h2", { text: "Voice" }), h("p", { class: "lead", text: "Talk to Cybok and hear answers out loud. Runs in your browser — free, no setup." }));
    if (!sttSupported) p.append(h("div", { class: "announcement warning", style: { width: "100%" }, html: `${icon("alert")}<div>Speech recognition isn't available in this browser. Use Chrome or Edge for voice input.</div>` }));
    const vs = h("select", { class: "select" }, h("option", { value: "", text: "Browser default" }));
    const fill = () => {
      vs.innerHTML = '<option value="">Browser default</option>';
      voices().forEach((v) => vs.append(h("option", { value: v.name, text: `${v.name} (${v.lang})` })));
      vs.value = state.settings.voice_name || "";
    };
    fill();
    if (ttsSupported) speechSynthesis.onvoiceschanged = fill;
    vs.addEventListener("change", () => save({ voice_name: vs.value }));
    const rate = h("input", { type: "range", min: "0.5", max: "2", step: "0.1", value: state.settings.voice_rate || 1, style: { width: "170px" } });
    rate.addEventListener("change", () => save({ voice_rate: parseFloat(rate.value) }));
    p.append(h("div", { class: "set-group" },
      row("Read answers aloud", "Automatically speak every new answer.", toggle("voice_autospeak")),
      row("Voice", "Voices come from your device.", vs),
      row("Speaking speed", "", rate),
      row("Test voice", "", h("button", { class: "btn sm", html: icon("volume", "sm") + "Play sample", onclick: (e) => speak("Hello! I'm Cybok, your AI workspace. How can I help you today?", { button: e.currentTarget }) }))));
    p.append(h("p", { class: "small muted", text: "Tip: press the headphones button next to the message box for a hands-free voice conversation. Your browser will ask for microphone permission the first time." }));
  },

  privacy(p) {
    p.append(h("h2", { text: "Privacy & Data" }), h("p", { class: "lead", text: "Your conversations and files are private to your account." }));
    p.append(h("div", { class: "set-group" },
      row("Save chat history", "Off: new chats are temporary and removed when you sign out.", toggle("save_history")),
      row("Export my data", "Download all your chats, settings and metadata as JSON.", h("a", { class: "btn sm", href: "/api/account/export", html: icon("download", "sm") + "Export" })),
      row("Shared links", "Manage conversations you've shared publicly.", h("button", { class: "btn sm", text: "Manage", onclick: () => manageShares() }))));
    p.append(h("div", { class: "set-group danger" },
      row("Delete all conversations", "Permanently delete every chat, including archived and trashed ones.", h("button", {
        class: "btn sm danger", text: "Delete all", onclick: async () => {
          if (!await confirmDialog({ title: "Delete all conversations?", message: "Every conversation will be permanently deleted. Files and images in your Library are kept. This can't be undone.", confirm: "Delete everything", danger: true })) return;
          try { const r = await api("/api/chats?scope=all", { method: "DELETE" }); emit("conversations-changed"); emit("navigate", "/app"); toast(`${r.deleted} conversations deleted`, { type: "success" }); }
          catch (e) { toast(e.message, { type: "error" }); }
        },
      }))));
    p.append(h("p", { class: "small muted", html: 'Messages are sent to the AI provider of the model you pick to generate answers. <a href="/terms" target="_blank">Read the privacy notice</a>.' }));
  },

  notifications(p) {
    p.append(h("h2", { text: "Notifications" }), h("p", { class: "lead", text: "Choose how Cybok keeps you in the loop." }));
    p.append(h("div", { class: "set-group" },
      row("E-mail notifications", state.mailConfigured ? "Security alerts like password and e-mail changes." : "Security e-mails (e-mail sending isn't configured on this server yet).", toggle("email_notifications")),
      row("Desktop notifications", "Notify me when an answer is ready while Cybok is in the background.", toggle("system_notifications", async (on) => {
        if (!on) return true;
        if (!("Notification" in window)) { toast("Notifications aren't supported in this browser.", { type: "error" }); return false; }
        const perm = await Notification.requestPermission();
        if (perm !== "granted") { toast("Notification permission was blocked in the browser.", { type: "error" }); return false; }
        new Notification("Cybok notifications are on", { body: "We'll let you know when answers are ready.", icon: "/static/img/icon-192.png" });
        return true;
      }))));
  },

  shortcuts(p) {
    p.append(h("h2", { text: "Keyboard shortcuts" }), h("p", { class: "lead", text: "Work faster with your keyboard." }));
    const list = h("div", { class: "kbd-list" });
    [["Search everything", "Ctrl K"], ["New chat", "Ctrl Shift O"], ["Toggle sidebar", "Ctrl B"], ["Image mode", "Ctrl Shift I"], ["Focus message box", "Shift Esc"],
      ["Stop generating", "Esc"], ["Copy last answer", "Ctrl Shift C"], ["New line", "Shift Enter"], ["Rename chat in sidebar", "F2"], ["Open settings", "Ctrl ,"], ["Show shortcuts", "Ctrl /"]]
      .forEach(([l, k]) => list.append(h("div", {}, h("span", { text: l }), h("span", { html: k.split(" ").map((x) => `<kbd>${x}</kbd>`).join("") }))));
    p.append(list);
  },

  about(p) {
    const a = state.app;
    p.append(h("div", { class: "about-hero" },
      h("img", { src: "/static/img/logo.jpg", alt: "Cybok logo" }),
      h("div", { class: "wordmark", text: "CYBOK" }),
      h("p", { class: "muted", style: { margin: "6px 0 0" }, text: "Your AI. Your Workspace." })));
    p.append(h("div", { class: "set-group" },
      row("Version", "", h("span", { class: "badge gray", text: a.version || "1.0.0" })),
      row("Creator", a.creator_description || "", h("b", { text: a.creator || "Saif Mughal" })),
      row("AI models", "Free, openly licensed models via their official providers.", h("span", { class: "small muted", text: `${state.models.filter((m) => m.available).length} available` })),
      row("Terms & privacy", "", h("a", { class: "btn sm", href: "/terms", target: "_blank", text: "Read" }))));
    const models = h("div", { class: "set-group" });
    state.models.forEach((m) => models.append(row(m.name, `${m.family} · ${m.provider}`, h("span", { class: `badge ${m.available ? "green" : "gray"}`, text: m.available ? "Ready" : (m.needs || "").includes("key") ? "Needs free key" : "Needs Ollama" }))));
    p.append(h("div", { class: "label", text: "Third-party models used by Cybok", style: { margin: "4px 0 8px" } }), models);
    p.append(h("div", { class: "credit", text: "Manufactured by Saif Mughal" }));
  },
};

function clear(el) { el.innerHTML = ""; return el; }

async function manageShares() {
  const body = h("div", {}, h("div", { class: "skeleton", style: { height: "50px" } }));
  const m = modal({ title: "Shared links", body, wide: true });
  try {
    const r = await api("/api/shares");
    body.innerHTML = "";
    if (!r.shares.length) { body.append(h("p", { text: "You haven't shared any conversations." })); return; }
    r.shares.forEach((c) => {
      const line = h("div", { class: "list-card" }, h("div", { class: "lt" }, h("b", { text: c.title }), h("small", { text: location.origin + c.share_url })),
        h("a", { class: "btn sm", href: c.share_url, target: "_blank", text: "Open" }),
        h("button", {
          class: "btn sm danger", text: "Disable", onclick: async () => {
            await api(`/api/chats/${c.id}/share`, { method: "POST", body: { enabled: false } });
            line.remove(); emit("conversations-changed"); toast("Link disabled", { type: "success" });
          },
        }));
      body.append(line);
    });
  } catch (e) { m.close(); toast(e.message, { type: "error" }); }
}

async function deleteAccount() {
  const u = state.user;
  const input = h("input", { class: "input", type: u.has_password ? "password" : "text", placeholder: u.has_password ? "Your password" : "Type DELETE" });
  const go = h("button", { class: "btn danger", text: "Delete my account forever" });
  const m = modal({
    title: "Delete your account?",
    body: h("div", {}, h("p", { text: "This permanently deletes your account, all conversations, uploaded files, generated images, logos and settings. This cannot be undone." }), input),
    footer: [h("button", { class: "btn", text: "Cancel", onclick: () => m.close() }), go],
  });
  go.addEventListener("click", async () => {
    try {
      await api("/api/account/delete", { method: "POST", body: u.has_password ? { password: input.value } : { confirm: input.value } });
      location.href = "/?deleted=1";
    } catch (e) { toast(e.message, { type: "error" }); }
  });
  if (isMobile()) input.focus();
}
