import { SITE_ROOT, sitePath } from "./site.js";

function setStatus(message) {
  document.querySelectorAll("[data-reader-pwa-status]").forEach((element) => {
    element.textContent = message;
  });
}

function isIOS() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
    || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function isStandalone() {
  return matchMedia("(display-mode: standalone)").matches
    || navigator.standalone === true;
}

export function controllerChangeTransition(hasBeenControlled, updateWasAcceptedHere) {
  return {
    hasBeenControlled: true,
    shouldReload: Boolean(hasBeenControlled || updateWasAcceptedHere),
  };
}

export function initPWA() {
  const installButtons = [...document.querySelectorAll('[data-reader-action="install"]')];
  const installHelp = document.querySelector("[data-reader-install-help]");
  const updateNotice = document.querySelector("[data-reader-update]");
  let installPrompt = null;
  let waitingWorker = null;
  let reloading = false;
  let updateAccepted = false;

  const updateOnlineStatus = () => setStatus(navigator.onLine ? "在线阅读" : "离线阅读");
  window.addEventListener("online", updateOnlineStatus);
  window.addEventListener("offline", updateOnlineStatus);
  updateOnlineStatus();

  if (isIOS() && !isStandalone() && installHelp) installHelp.hidden = false;

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    installButtons.forEach((button) => { button.hidden = false; });
  });

  window.addEventListener("appinstalled", () => {
    installPrompt = null;
    installButtons.forEach((button) => { button.hidden = true; });
    setStatus("已安装，可离线阅读");
  });

  document.addEventListener("click", async (event) => {
    const action = event.target.closest("[data-reader-action]")?.dataset.readerAction;
    if (action === "install") {
      event.preventDefault();
      if (!installPrompt) {
        if (installHelp) installHelp.hidden = false;
        return;
      }
      await installPrompt.prompt();
      await installPrompt.userChoice;
      navigator.storage?.persist?.().catch(() => false);
      installPrompt = null;
      installButtons.forEach((button) => { button.hidden = true; });
    } else if (action === "reload-update" && waitingWorker) {
      event.preventDefault();
      updateAccepted = true;
      waitingWorker.postMessage({ type: "SKIP_WAITING" });
    } else if (action === "dismiss-update") {
      event.preventDefault();
      if (updateNotice) updateNotice.hidden = true;
    }
  });

  if (!("serviceWorker" in navigator) || location.protocol === "file:") return;
  let hasBeenControlled = Boolean(navigator.serviceWorker.controller);

  navigator.serviceWorker.addEventListener("controllerchange", () => {
    const transition = controllerChangeTransition(hasBeenControlled, updateAccepted);
    hasBeenControlled = transition.hasBeenControlled;
    if (reloading || !transition.shouldReload) return;
    reloading = true;
    window.location.reload();
  });

  const showUpdate = (worker) => {
    waitingWorker = worker;
    if (updateNotice) updateNotice.hidden = false;
  };

  window.addEventListener("load", async () => {
    try {
      const registration = await navigator.serviceWorker.register(sitePath("sw.js"), { scope: SITE_ROOT });
      await navigator.serviceWorker.ready;
      setStatus(navigator.onLine ? "可离线使用" : "离线阅读");
      if (registration.waiting && navigator.serviceWorker.controller) showUpdate(registration.waiting);
      registration.addEventListener("updatefound", () => {
        const worker = registration.installing;
        worker?.addEventListener("statechange", () => {
          if (worker.state === "installed" && navigator.serviceWorker.controller) showUpdate(worker);
        });
      });
    } catch {
      setStatus(navigator.onLine ? "离线功能暂不可用" : "当前未缓存此页面");
    }
  }, { once: true });
}
