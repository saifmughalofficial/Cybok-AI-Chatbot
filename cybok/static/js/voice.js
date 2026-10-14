/* Voice: speech-to-text (Web Speech API), text-to-speech (speechSynthesis) and a hands-free voice conversation mode.
   Runs fully in the browser - no API key. Works best in Chrome / Edge. */
import { h, icon, toast } from "./core.js";
import { plainText } from "./markdown.js";
import { state } from "./state.js";

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
export const sttSupported = !!Recognition;
export const ttsSupported = "speechSynthesis" in window;

/* ---------------------------------------------------------------- dictation */
let rec = null;

export function startDictation({ onText, onEnd, continuous = true, lang } = {}) {
  if (!sttSupported) {
    toast("Voice input isn't supported in this browser. Try Chrome or Edge.", { type: "error" });
    return null;
  }
  stopDictation();
  rec = new Recognition();
  rec.lang = lang || navigator.language || "en-US";
  rec.continuous = continuous;
  rec.interimResults = true;
  let finalText = "";
  rec.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) finalText += r[0].transcript;
      else interim += r[0].transcript;
    }
    onText?.(finalText, interim);
  };
  rec.onerror = (e) => {
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      toast("Microphone permission was denied. Allow it in your browser's site settings.", { type: "error", timeout: 6000 });
    } else if (e.error === "no-speech") {
      /* silent */
    } else if (e.error !== "aborted") {
      toast(`Voice input error: ${e.error}`, { type: "error" });
    }
  };
  rec.onend = () => { const t = finalText; rec = null; onEnd?.(t); };
  try { rec.start(); } catch { /* already started */ }
  return rec;
}

export function stopDictation() {
  if (rec) { try { rec.stop(); } catch {} }
}

export const isDictating = () => !!rec;

/* ---------------------------------------------------------------- speech output */
let speakingBtn = null;

export function voices() {
  return ttsSupported ? window.speechSynthesis.getVoices() : [];
}

export function speak(markdown, { onEnd, button } = {}) {
  if (!ttsSupported) { toast("Text-to-speech isn't supported in this browser.", { type: "error" }); return; }
  const synth = window.speechSynthesis;
  if (synth.speaking && button && button === speakingBtn) { stopSpeaking(); return; }
  stopSpeaking();
  const text = plainText(markdown).slice(0, 8000);
  if (!text) { onEnd?.(); return; }
  // Chrome stops long utterances, so speak sentence chunks.
  const chunks = text.match(/[^.!?\n]{1,220}[.!?\n]*|[^.!?\n]+/g) || [text];
  const vname = state.settings.voice_name;
  const voice = voices().find((v) => v.name === vname);
  speakingBtn = button || null;
  button?.classList.add("on");
  chunks.forEach((c, i) => {
    const u = new SpeechSynthesisUtterance(c.trim());
    if (voice) u.voice = voice;
    u.rate = state.settings.voice_rate || 1;
    if (i === chunks.length - 1) u.onend = () => { button?.classList.remove("on"); speakingBtn = null; onEnd?.(); };
    u.onerror = () => { button?.classList.remove("on"); };
    synth.speak(u);
  });
}

export function stopSpeaking() {
  if (ttsSupported) window.speechSynthesis.cancel();
  speakingBtn?.classList.remove("on");
  speakingBtn = null;
}

/* ---------------------------------------------------------------- voice conversation */
export function startVoiceConversation({ send, onClose }) {
  if (!sttSupported) {
    toast("Voice conversation needs speech recognition (Chrome or Edge).", { type: "error" });
    return null;
  }
  const status = h("div", { class: "voice-status", text: "Listening…" });
  const transcript = h("div", { class: "voice-transcript", text: "Say something — Cybok will answer out loud." });
  const endBtn = h("button", { class: "btn lg", html: icon("x") + "<span>End voice chat</span>" });
  const overlay = h("div", { class: "voice-overlay", "data-state": "listening", role: "dialog", "aria-label": "Voice conversation" },
    h("div", { class: "voice-orb" }), status, transcript, endBtn);
  document.body.append(overlay);
  let active = true;

  const setState = (s, label) => { overlay.dataset.state = s; status.textContent = label; };

  const listen = () => {
    if (!active) return;
    setState("listening", "Listening…");
    startDictation({
      continuous: false,
      onText: (final, interim) => { transcript.textContent = (final + " " + interim).trim() || "…"; },
      onEnd: async (text) => {
        if (!active) return;
        text = (text || "").trim();
        if (!text) { setTimeout(listen, 300); return; }
        setState("thinking", "Thinking…");
        transcript.textContent = text;
        try {
          const reply = await send(text);
          if (!active) return;
          if (!reply) { listen(); return; }
          setState("speaking", "Speaking…");
          transcript.textContent = plainText(reply).slice(0, 280) + (reply.length > 280 ? "…" : "");
          speak(reply, { onEnd: () => setTimeout(listen, 250) });
        } catch {
          setTimeout(listen, 800);
        }
      },
    });
  };

  const close = () => {
    active = false;
    stopDictation();
    stopSpeaking();
    overlay.remove();
    document.removeEventListener("keydown", onKey, true);
    onClose?.();
  };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
  document.addEventListener("keydown", onKey, true);
  endBtn.addEventListener("click", close);
  listen();
  return { close };
}
