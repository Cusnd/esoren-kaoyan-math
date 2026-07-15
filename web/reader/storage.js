export const PREFERENCES_KEY = "math1.reader.preferences.v1";
export const PROGRESS_KEY = "math1.reader.progress.v1";

const memory = new Map();
const listeners = new Map();
let persistent = true;

function notify(key, value) {
  const callbacks = listeners.get(key);
  callbacks?.forEach((callback) => callback(value));
  window.dispatchEvent(
    new CustomEvent("math1:storage", { detail: { key, value, persistent } }),
  );
}

function parse(raw, fallback) {
  if (typeof raw !== "string" || raw.length === 0) return fallback;
  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function readJSON(key, fallback) {
  if (memory.has(key)) return memory.get(key);
  if (!persistent) return fallback;

  try {
    const value = parse(window.localStorage.getItem(key), fallback);
    memory.set(key, value);
    return value;
  } catch {
    persistent = false;
    return fallback;
  }
}

export function writeJSON(key, value) {
  memory.set(key, value);
  if (persistent) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Private browsing, disabled storage, and quota failures must never block reading.
      persistent = false;
    }
  }
  notify(key, value);
  return persistent;
}

export function subscribeJSON(key, callback) {
  const callbacks = listeners.get(key) ?? new Set();
  callbacks.add(callback);
  listeners.set(key, callbacks);
  return () => {
    callbacks.delete(callback);
    if (callbacks.size === 0) listeners.delete(key);
  };
}

export function hasPersistentStorage() {
  return persistent;
}

window.addEventListener("storage", (event) => {
  if (!event.key || !listeners.has(event.key)) return;
  const previous = memory.get(event.key) ?? null;
  const value = parse(event.newValue, previous);
  memory.set(event.key, value);
  notify(event.key, value);
});
