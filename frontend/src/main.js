import * as api from "./api.js";
import * as profile from "./profile/render.js";
import * as rankingConstants from "./ranking/constants.js";
import * as state from "./state.js";
import * as format from "./shared/format.js";
import * as storage from "./shared/storage.js";

window.GradientModules = {
  api,
  format,
  profile,
  rankingConstants,
  state,
  storage,
};

await import("./legacy-app.js");
