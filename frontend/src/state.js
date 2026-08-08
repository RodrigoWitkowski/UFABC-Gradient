import { readStorageJson } from "./shared/storage.js";

export const studentIdStorageKey = "gradient_student_id";
export const legacyStudentIdStorageKey = "trajeto_student_id";
export const rankingViewStorageKey = "gradient_ranking_view_v2";
export const selectedSectionsStorageKey = "gradient_selected_sections_v1";
export const resultPageSize = 50;
export const maxRankingResults = 2000;
export const curriculumCategories = ["mandatory", "limited", "free"];

export function initializeStoredStudentId() {
  window.localStorage.removeItem("gradient_ranking_view_v1");
  const storedStudentId = window.localStorage.getItem(studentIdStorageKey)
    || window.localStorage.getItem(legacyStudentIdStorageKey);
  if (storedStudentId && !window.localStorage.getItem(studentIdStorageKey)) {
    window.localStorage.setItem(studentIdStorageKey, storedStudentId);
    window.localStorage.removeItem(legacyStudentIdStorageKey);
  }
  return storedStudentId;
}

export function buildInitialState(storedStudentId) {
  const storedRankingView = readStorageJson(rankingViewStorageKey);
  const matchingStoredView = storedRankingView?.studentId === storedStudentId
    ? storedRankingView
    : null;
  const storedCategories = Array.isArray(matchingStoredView?.categories)
    ? matchingStoredView.categories.filter((category) => curriculumCategories.includes(category))
    : curriculumCategories;

  return {
    terms: [],
    profile: null,
    ranking: null,
    selectedSections: new Map(),
    studentId: storedStudentId,
    selectedTerm: typeof matchingStoredView?.term === "string" ? matchingStoredView.term : null,
    visibleResultCount: Number(matchingStoredView?.visibleResultCount) || resultPageSize,
    selectedCategories: new Set(storedCategories),
    selectedShelfExpanded: Boolean(matchingStoredView?.selectedShelfExpanded),
  };
}

export function queryElements() {
  return {
    form: document.querySelector("#ranking-form"),
    term: document.querySelector("#term"),
    currentTerm: document.querySelector("#current-term"),
    results: document.querySelector("#results"),
    resultMeta: document.querySelector("#result-meta"),
    selectedShelf: document.querySelector("#selected-shelf"),
    categoryFilter: document.querySelector("#category-filter"),
    profileSummary: document.querySelector("#profile-summary"),
    controlColumn: document.querySelector(".control-column"),
    button: document.querySelector("#rank-button"),
    historyInput: document.querySelector("#history-pdf"),
    historyLabel: document.querySelector("#history-upload-label"),
    historyStatus: document.querySelector("#history-status"),
    toast: document.querySelector("#toast"),
  };
}
