/* Shared app state + a tiny event bus so modules stay decoupled. */
export const state = {
  user: null,
  settings: {},
  models: [],
  defaultModel: null,
  currentModel: null,
  conversations: [],
  current: null, // current conversation object
  messages: [],
  streaming: null, // { controller, assistantId }
  attachments: [], // [{id, name, ext, kind, uploading, url}]
  imageMode: false,
  tempNext: false,
  limits: {},
  imageStyles: [],
  imageSizes: [],
  app: {},
  mailConfigured: false,
};

const bus = new EventTarget();
export const on = (name, fn) => bus.addEventListener(name, (e) => fn(e.detail));
export const emit = (name, detail) => bus.dispatchEvent(new CustomEvent(name, { detail }));

export const modelBySlug = (slug) => state.models.find((m) => m.slug === slug);
