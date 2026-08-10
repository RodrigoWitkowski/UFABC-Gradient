const appVersion = "20260810.1";

import * as api from "./api.js?v=20260810.1";
import * as profile from "./profile/render.js?v=20260810.1";
import * as rankingConstants from "./ranking/constants.js?v=20260810.1";
import * as state from "./state.js?v=20260810.1";
import * as format from "./shared/format.js?v=20260810.1";
import * as storage from "./shared/storage.js?v=20260810.1";

window.GradientModules = {
  api,
  format,
  profile,
  rankingConstants,
  state,
  storage,
};

import(`./legacy-app.js?v=${appVersion}`).catch((error) => {
  console.error("Gradient failed to initialize.", error);
  const message = document.createElement("div");
  message.setAttribute("role", "alert");
  message.style.cssText = [
    "position:fixed",
    "right:16px",
    "bottom:16px",
    "z-index:9999",
    "max-width:320px",
    "padding:12px 14px",
    "border-radius:12px",
    "background:#7d1d1d",
    "color:#fff",
    "font:600 14px/1.4 system-ui,sans-serif",
    "box-shadow:0 12px 32px rgba(0,0,0,.22)",
  ].join(";");
  message.textContent = "A interface falhou ao iniciar. Recarregue a página sem cache.";
  document.body.append(message);
});
