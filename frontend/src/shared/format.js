export function formatPercent(value) {
  return value === null || value === undefined ? "Sem dados" : `${Math.round(value * 100)}%`;
}

export function formatNumber(value) {
  return Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 4 });
}

export function formatCampusName(value) {
  if (value === "SA") return "Santo Andre";
  if (value === "SB") return "Sao Bernardo";
  return value;
}

export function shortTime(value) {
  return String(value).slice(0, 5);
}

export function compareMeetings(a, b) {
  return a.weekday - b.weekday || a.start_time.localeCompare(b.start_time);
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
}
