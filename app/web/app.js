const studentIdStorageKey = "gradient_student_id";
const legacyStudentIdStorageKey = "trajeto_student_id";
const rankingViewStorageKey = "gradient_ranking_view_v2";
const selectedSectionsStorageKey = "gradient_selected_sections_v1";
const resultPageSize = 50;
const maxRankingResults = 2000;
const curriculumCategories = ["mandatory", "limited", "free"];
window.localStorage.removeItem("gradient_ranking_view_v1");
const storedStudentId = window.localStorage.getItem(studentIdStorageKey)
  || window.localStorage.getItem(legacyStudentIdStorageKey);
if (storedStudentId && !window.localStorage.getItem(studentIdStorageKey)) {
  window.localStorage.setItem(studentIdStorageKey, storedStudentId);
  window.localStorage.removeItem(legacyStudentIdStorageKey);
}
const storedRankingView = readStorageJson(rankingViewStorageKey);
const matchingStoredView = storedRankingView?.studentId === storedStudentId
  ? storedRankingView
  : null;
const storedCategories = Array.isArray(matchingStoredView?.categories)
  ? matchingStoredView.categories.filter((category) => curriculumCategories.includes(category))
  : curriculumCategories;

const state = {
  terms: [],
  profile: null,
  ranking: null,
  selectedSections: new Map(),
  studentId: storedStudentId,
  visibleResultCount: Number(matchingStoredView?.visibleResultCount) || resultPageSize,
  selectedCategories: new Set(storedCategories),
  selectedShelfExpanded: Boolean(matchingStoredView?.selectedShelfExpanded),
};

const elements = {
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
const weekdays = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
const categoryLabels = {
  mandatory: "Obrigatória",
  limited: "Opção limitada",
  free: "Livre",
  not_applicable: "Não aplicável",
};
const teacherRoleLabels = {
  theory: "Teoria",
  practice: "Prática",
};
const scoreLabels = {
  curriculum_relevance: "Currículo",
  teacher: "Docentes",
  seat_probability: "Demanda",
  schedule_preference: "Horário",
  workload: "Carga",
  campus: "Campus",
};
const scheduleWindows = {
  any: {},
  morning: { latest_end_time: "13:00" },
  afternoon: { earliest_start_time: "12:00", latest_end_time: "19:00" },
  night: { earliest_start_time: "18:00" },
  daytime: { latest_end_time: "19:00" },
  "afternoon-night": { earliest_start_time: "12:00" },
};

let historyStatusTimer;

document.addEventListener("DOMContentLoaded", initialize);

async function initialize() {
  bindEvents();
  syncCategoryFilterInputs();
  updateControlFade();
  try {
    const terms = await fetchJson("/terms");
    state.terms = terms;
    renderTerms();
    if (state.studentId) {
      await loadStoredProfile();
      if (state.studentId) {
        restoreSelectedSections();
        renderSelectedShelf();
        await restoreLatestRanking();
      }
    } else {
      renderEmptyProfileSummary();
    }
  } catch (error) {
    showError("Não foi possível iniciar a interface", error.message);
  }
}

function bindEvents() {
  elements.form.addEventListener("submit", handleRankingSubmit);
  elements.historyInput.addEventListener("change", handleHistoryUpload);
  elements.results.addEventListener("click", handleResultAction);
  elements.selectedShelf.addEventListener("click", handleSelectedAction);
  elements.categoryFilter.addEventListener("change", handleCategoryFilterChange);
  elements.controlColumn.addEventListener("scroll", updateControlFade, { passive: true });
  window.addEventListener("resize", updateControlFade, { passive: true });
  document.querySelectorAll("[data-step-target]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector(`#${button.dataset.stepTarget}`).scrollIntoView({ block: "start" });
      document.querySelectorAll(".step").forEach((step) => step.classList.remove("is-active"));
      button.classList.add("is-active");
    });
  });
}

async function handleHistoryUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  window.clearTimeout(historyStatusTimer);
  elements.historyLabel.classList.add("is-loading");
  elements.historyStatus.hidden = true;
  const formData = new FormData();
  formData.append("file", file);
  if (state.studentId) formData.append("student_id", state.studentId);
  try {
    const result = await fetchJson("/students/history/pdf", {
      method: "POST",
      body: formData,
    });
    state.studentId = result.student.id;
    state.profile = result.student;
    window.localStorage.setItem(studentIdStorageKey, state.studentId);
    fillProfile(state.profile);
    const replacement = result.replaced_existing ? " O histórico anterior foi substituído." : "";
    const repeatedApprovals = result.completed_attempt_count - result.completed_count;
    const completionSummary = repeatedApprovals > 0
      ? `${result.completed_count} disciplinas únicas concluídas (${result.completed_attempt_count} aprovações no histórico)`
      : `${result.completed_count} disciplinas concluídas`;
    const currentSummary = result.in_progress_count === 1
      ? "1 disciplina sendo cursada atualmente"
      : `${result.in_progress_count} disciplinas sendo cursadas atualmente`;
    const warnings = Array.isArray(result.warnings) && result.warnings.length
      ? ` Avisos: ${result.warnings.join(" ")}`
      : "";
    elements.historyStatus.textContent = `${completionSummary}; ${currentSummary}.${replacement}${warnings}`;
    elements.historyStatus.hidden = false;
    historyStatusTimer = window.setTimeout(() => { elements.historyStatus.hidden = true; }, 9000);
    showToast(
      result.student.courses?.length
        ? "Histórico importado e perfil atualizado."
        : "Histórico importado, mas o vínculo de curso ainda não foi identificado.",
    );
  } catch (error) {
    elements.historyStatus.textContent = error.message;
    elements.historyStatus.hidden = false;
    showToast(error.message);
  } finally {
    elements.historyLabel.classList.remove("is-loading");
    event.target.value = "";
  }
}

function updateControlFade() {
  elements.controlColumn.classList.toggle("is-scrolled", elements.controlColumn.scrollTop > 6);
  const remainingScroll = elements.controlColumn.scrollHeight
    - elements.controlColumn.scrollTop
    - elements.controlColumn.clientHeight;
  elements.controlColumn.classList.toggle("is-at-bottom", remainingScroll < 6);
}

async function loadStoredProfile() {
  try {
    state.profile = await fetchJson(`/students/${state.studentId}`);
    fillProfile(state.profile);
    showToast("Perfil local recuperado.");
  } catch (error) {
    window.localStorage.removeItem(studentIdStorageKey);
    window.localStorage.removeItem(rankingViewStorageKey);
    window.localStorage.removeItem(selectedSectionsStorageKey);
    state.studentId = null;
    state.profile = null;
    renderEmptyProfileSummary();
    showToast("O perfil anterior não existe mais. Crie um novo perfil.");
  }
}

function renderTerms() {
  if (!state.terms.length) {
    elements.term.value = "";
    elements.currentTerm.textContent = "Nenhuma oferta ativa importada";
    return;
  }
  const term = state.terms[0];
  elements.term.value = term.code;
  elements.currentTerm.textContent = `${term.year} · ${term.term_number}º quadrimestre`;
}

function fillProfile(profile) {
  renderProfileSummary(profile);
  const hard = profile.preferences?.hard_constraints || {};
  const soft = profile.preferences?.soft_preferences || {};
  restoreChecks("allowed_campus", hard.allowed_campuses);
  setValue("#period-window", inferScheduleWindow(hard));
  document.querySelector("#avoid-friday").checked = Number(soft.avoid_friday || 0) > 0;
}

function renderEmptyProfileSummary() {
  elements.profileSummary.innerHTML = `
    <div class="empty-state compact-empty-state">
      <h3>O ranking começa pelo histórico.</h3>
      <p>Importe o PDF do SIGAA para liberar seu vínculo, seu CP e a análise das turmas.</p>
    </div>`;
}

function renderProfileSummaryLegacy(profile) {
  const courses = Array.isArray(profile.courses) ? profile.courses : [];
  const completedCount = Array.isArray(profile.completed_subjects) ? profile.completed_subjects.length : 0;
  const inProgressCount = Array.isArray(profile.in_progress_subjects) ? profile.in_progress_subjects.length : 0;
  const courseCards = courses.length
    ? courses.map((course) => `
      <article class="linked-course-card">
        <div class="linked-course-topline">
          <strong>${escapeHtml(course.course_code)}</strong>
          ${course.is_primary ? '<span class="linked-course-badge">Principal</span>' : ""}
        </div>
        <p class="linked-course-name">${escapeHtml(course.course_name)}</p>
        <dl class="linked-course-meta">
          <div><dt>Matriz</dt><dd>${escapeHtml(course.curriculum_version || "Automática")}</dd></div>
          <div><dt>CP</dt><dd>${course.cp === null ? "Sem dado" : formatNumber(course.cp)}</dd></div>
          <div><dt>IK</dt><dd>${course.ik === null ? "Sem dado" : formatNumber(course.ik)}</dd></div>
        </dl>
      </article>
    `).join("")
    : `
      <div class="profile-summary-warning">
        <strong>Nenhum curso foi vinculado automaticamente.</strong>
        <p>Sem curso vinculado, o ranking não consegue aplicar corretamente a prioridade de matrícula.</p>
      </div>`;
  elements.profileSummary.innerHTML = `
    <div class="profile-metrics-grid">
      <article class="profile-metric">
        <span>RA</span>
        <strong>${escapeHtml(profile.ra || "Sem dado")}</strong>
      </article>
      <article class="profile-metric">
        <span>Turno de ingresso</span>
        <strong>${escapeHtml(profile.admission_shift || "Sem dado")}</strong>
      </article>
      <article class="profile-metric">
        <span>CA</span>
        <strong>${profile.ca === null ? "Sem dado" : formatNumber(profile.ca)}</strong>
      </article>
      <article class="profile-metric">
        <span>Limite de créditos</span>
        <strong>${profile.max_quarter_credits === null ? "Sem dado" : formatNumber(profile.max_quarter_credits)}</strong>
      </article>
      <article class="profile-metric">
        <span>Concluídas</span>
        <strong>${completedCount}</strong>
      </article>
      <article class="profile-metric">
        <span>Em andamento</span>
        <strong>${inProgressCount}</strong>
      </article>
    </div>
    <div class="linked-course-list">
      ${courseCards}
    </div>`;
}

function renderProfileSummary(profile) {
  const courses = Array.isArray(profile.courses) ? profile.courses : [];
  const completedCount = Array.isArray(profile.completed_subjects)
    ? profile.completed_subjects.length
    : 0;
  const inProgressCount = Array.isArray(profile.in_progress_subjects)
    ? profile.in_progress_subjects.length
    : 0;
  const summaryMetrics = [
    renderProfileMetric("RA", profile.ra || "Sem dado", { compact: true, data: true }),
    renderProfileMetric(
      "Turno de ingresso",
      profile.admission_shift || "Sem dado",
      { compact: true },
    ),
    renderProfileMetric(
      "Campus",
      formatCampusName(profile.campus) || "Sem dado",
      { compact: true },
    ),
    renderProfileMetric(
      "Ano de ingresso",
      profile.admission_year || "Sem dado",
      { data: true },
    ),
    renderProfileMetric(
      "CA",
      profile.ca === null ? "Sem dado" : formatNumber(profile.ca),
      { data: true },
    ),
    renderProfileMetric(
      "Limite de creditos",
      profile.max_quarter_credits === null
        ? "Sem dado"
        : formatNumber(profile.max_quarter_credits),
      { data: true },
    ),
    renderProfileMetric("Concluidas", String(completedCount), { data: true }),
    renderProfileMetric("Em andamento", String(inProgressCount), { data: true }),
  ].join("");
  const courseCards = courses.length
    ? courses.map((course, index) => `
      <section class="linked-course-block">
        <article class="linked-course-card">
          <div class="linked-course-topline">
            <div class="linked-course-copy">
              <p class="linked-course-kicker">${course.is_primary ? "Curso principal" : `Vinculo adicional ${index + 1}`}</p>
              <strong>${escapeHtml(course.course_code)}</strong>
            </div>
            <span class="linked-course-badge${course.is_primary ? "" : " is-secondary"}">
              ${course.is_primary ? "Principal" : "Vinculo"}
            </span>
          </div>
          <p class="linked-course-name">${escapeHtml(course.course_name)}</p>
        </article>
        <div class="profile-metrics-grid profile-course-metrics-grid">
          ${renderProfileMetric(
            "Matriz",
            course.curriculum_version || "Automatica",
            { compact: true, data: true },
          )}
          ${renderProfileMetric(
            "CP",
            course.cp === null ? "Sem dado" : formatNumber(course.cp),
            { data: true },
          )}
          ${renderProfileMetric(
            "IK",
            course.ik === null ? "Sem dado" : formatNumber(course.ik),
            { data: true },
          )}
        </div>
      </section>
    `).join("")
    : `
      <div class="profile-summary-warning">
        <strong>Nenhum curso foi vinculado automaticamente.</strong>
        <p>Sem curso vinculado, o ranking nao consegue aplicar corretamente a prioridade de matricula.</p>
      </div>`;
  elements.profileSummary.innerHTML = `
    <div class="profile-summary-stack">
      <section class="profile-summary-block">
        <div class="profile-summary-heading">
          <div>
            <h3>Dados do historico</h3>
            <p>Esses dados vem do PDF do SIGAA e passam a ser a fonte oficial do seu perfil.</p>
          </div>
        </div>
        <div class="profile-metrics-grid">
          ${summaryMetrics}
        </div>
      </section>
      <section class="profile-summary-block">
        <div class="profile-summary-heading">
          <div>
            <h3>${courses.length === 1 ? "Curso vinculado" : "Cursos vinculados"}</h3>
            <p>O ranking usa matriz, CP e IK do seu vinculo para estimar sua prioridade de matricula.</p>
          </div>
        </div>
        <div class="linked-course-list">
          ${courseCards}
        </div>
      </section>
    </div>`;
}

function restoreChecks(name, values) {
  const inputs = [...document.querySelectorAll(`input[name="${name}"]`)];
  if (!inputs.length) return;
  if (!Array.isArray(values) || !values.length) {
    inputs.forEach((input) => { input.checked = true; });
    return;
  }
  inputs.forEach((input) => {
    input.checked = values.includes(input.value);
  });
}

async function handleRankingSubmit(event) {
  event.preventDefault();
  setLoading(true);
  setActiveStep("results-panel");
  renderLoading();
  try {
    validateForm();
    await saveProfile();
    const ranking = await fetchJson("/rankings/sections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildRankingRequest()),
    });
    renderRanking(ranking);
    document.querySelector("#results-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showError("Não foi possível montar o ranking", error.message);
    showToast(error.message);
  } finally {
    setLoading(false);
  }
}

function validateForm() {
  if (!state.studentId || !state.profile) {
    throw new Error("Importe seu histórico do SIGAA antes de montar o ranking.");
  }
  if (!Array.isArray(state.profile.courses) || !state.profile.courses.length) {
    throw new Error(
      "O histórico importado ainda não gerou um curso vinculado. Verifique as matrizes e o PDF importado.",
    );
  }
  if (!selectedValues("allowed_campus").length) throw new Error("Selecione ao menos um campus.");
  if (!elements.term.value) {
    throw new Error("Nenhuma oferta ativa do proximo quadrimestre foi importada ainda.");
  }
}

async function saveProfile() {
  if (!state.studentId || !state.profile) {
    throw new Error("Importe seu histórico do SIGAA antes de montar o ranking.");
  }
  state.profile = await fetchJson(`/students/${state.studentId}/academic-profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildAcademicProfile()),
  });
  fillProfile(state.profile);
}

function buildAcademicProfile() {
  if (!state.profile) throw new Error("Perfil acadêmico indisponível.");
  const completed = state.profile?.completed_subjects?.map((subject) => ({
    code: subject.code,
    name: subject.name,
    term: subject.term,
    grade: subject.grade,
    credits: subject.credits,
    metadata: subject.metadata || {},
  })) || [];
  const inProgress = state.profile?.in_progress_subjects?.map((subject) => ({
    code: subject.code,
    name: subject.name,
    term: subject.term,
  })) || [];

  return {
    ra: state.profile.ra,
    admission_year: state.profile.admission_year,
    admission_shift: state.profile.admission_shift,
    campus: state.profile.campus,
    cr: state.profile?.cr ?? null,
    ca: state.profile?.ca ?? null,
    accumulated_credits: state.profile?.accumulated_credits ?? null,
    course_strategy: state.profile.course_strategy,
    courses: state.profile.courses.map((course) => ({
      course_code: course.course_code,
      curriculum_version: course.curriculum_version,
      is_primary: course.is_primary,
      weight: course.weight,
      cp: course.cp,
      ik: course.ik,
    })),
    completed_subjects: completed,
    in_progress_subjects: inProgress,
    preferences: buildPreferences(),
  };
}

function buildPreferences() {
  const hard = buildHardConstraints();
  const soft = buildSoftPreferences();
  return {
    hard_constraints: hard,
    soft_preferences: soft,
  };
}

function buildRankingRequest() {
  return {
    term: elements.term.value,
    student_id: state.studentId,
    result_limit: maxRankingResults,
    config: {
      sort_mode: "probability_first",
      hard_constraints: buildHardConstraints(),
      soft_preferences: buildSoftPreferences(),
    },
  };
}

function buildHardConstraints() {
  const campuses = selectedValues("allowed_campus");
  const scheduleWindow = scheduleWindows[document.querySelector("#period-window").value] || {};
  return {
    allowed_campuses: campuses.length === 2 ? [] : campuses,
    ...scheduleWindow,
  };
}

function buildSoftPreferences() {
  const campuses = selectedValues("allowed_campus");
  return {
    avoid_friday: document.querySelector("#avoid-friday").checked ? 1 : 0,
    preferred_campuses: campuses.length === 1 ? campuses : [],
  };
}

function renderLoading() {
  elements.results.setAttribute("aria-busy", "true");
  elements.resultMeta.hidden = true;
  renderSelectedShelf();
  elements.results.innerHTML = `
    <div class="loading-state" aria-label="Calculando ranking">
      <div class="skeleton result-skeleton"></div>
      <div class="skeleton result-skeleton"></div>
      <div class="skeleton result-skeleton"></div>
    </div>`;
}

function renderEmptyResultsState(title, message, hints = []) {
  const visibleHints = Array.isArray(hints) ? hints.filter(Boolean).slice(0, 3) : [];
  const hintList = visibleHints.length
    ? `
      <ul class="empty-hint-list">
        ${visibleHints.map((hint) => `<li>${escapeHtml(hint)}</li>`).join("")}
      </ul>`
    : "";
  elements.results.innerHTML = `
    <div class="empty-state compact-empty-state empty-results-state">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(message)}</p>
      ${hintList}
    </div>`;
}

function renderRanking(ranking, { resetVisible = true, persist = true } = {}) {
  state.ranking = ranking;
  if (resetVisible) state.visibleResultCount = resultPageSize;
  refreshSelectedSections(ranking);
  if (persist) persistRankingView();
  renderRankingView();
}

function renderRankingView() {
  const ranking = state.ranking;
  if (!ranking) return;
  elements.results.setAttribute("aria-busy", "false");
  elements.resultMeta.hidden = false;
  const compatibleItems = ranking.items.filter((item) => isCompatibleWithSelection(item));
  const filteredItems = compatibleItems.filter((item) => itemMatchesCategoryFilters(item));
  const visibleItems = filteredItems.slice(0, state.visibleResultCount);
  elements.resultMeta.innerHTML = `<strong>${visibleItems.length}/${filteredItems.length}</strong> turmas exibidas`;
  renderSelectedShelf();
  if (!ranking.items.length) {
    elements.resultMeta.hidden = true;
    renderEmptyResultsState(
      "Nenhuma turma candidata foi encontrada.",
      "O ranking nao encontrou turmas elegiveis na oferta ativa atual.",
      ranking.warnings,
    );
    return;
  }
  if (!compatibleItems.length) {
    elements.resultMeta.hidden = true;
    renderEmptyResultsState(
      "Nenhuma outra turma cabe nos horarios escolhidos.",
      "Remova uma turma fixada para liberar os horarios conflitantes.",
    );
    return;
  }
  if (!filteredItems.length) {
    elements.resultMeta.hidden = true;
    renderEmptyResultsState(
      "Nenhuma turma corresponde aos tipos selecionados.",
      "Marque obrigatorias, limitadas ou livres nas preferencias.",
    );
    return;
  }

  const knownProbability = filteredItems.filter(
    (item) => rankingProbabilityValue(item.seat_probability) !== null,
  );
  const personalizedProbability = filteredItems.filter(
    (item) => item.seat_probability.personalized_probability !== null,
  );
  elements.results.innerHTML = `
    <div class="ranking-summary">
      <div class="summary-cell"><span>No ranking</span><strong>${ranking.item_count}</strong></div>
      <div class="summary-cell"><span>Tipos selecionados</span><strong>${filteredItems.length}</strong></div>
      <div class="summary-cell"><span>Probabilidade calculada</span><strong>${knownProbability.length}/${filteredItems.length}</strong></div>
      <div class="summary-cell"><span>Estimativa pessoal</span><strong>${personalizedProbability.length}</strong></div>
    </div>
    <div class="ranking-list">
      ${visibleItems.map((item) => renderRankingCard(item, ranking.config.weights, ranking.item_count)).join("")}
    </div>
    ${renderResultControls(visibleItems.length, filteredItems.length)}`;
}

function handleResultAction(event) {
  const resultAction = event.target.closest("[data-results-action]");
  if (resultAction && state.ranking) {
    const compatibleItems = state.ranking.items.filter((item) => isCompatibleWithSelection(item));
    const filteredCount = compatibleItems.filter((item) => itemMatchesCategoryFilters(item)).length;
    state.visibleResultCount = resultAction.dataset.resultsAction === "all"
      ? filteredCount
      : Math.min(state.visibleResultCount + resultPageSize, filteredCount);
    persistRankingView();
    renderRankingView();
    return;
  }
  const button = event.target.closest(".select-section");
  if (!button || !state.ranking) return;
  const item = state.ranking.items.find((candidate) => candidate.section.id === button.dataset.sectionId);
  if (!item) return;
  const credits = getItemCredits(item);
  const limit = state.profile?.max_quarter_credits === null || state.profile?.max_quarter_credits === undefined
    ? null
    : Number(state.profile.max_quarter_credits);
  const selectedCredits = [...state.selectedSections.values()]
    .reduce((total, selected) => total + (getItemCredits(selected) || 0), 0);
  if (limit !== null && credits !== null && selectedCredits + credits > limit) {
    showToast(`Essa turma ultrapassaria seu limite total de ${formatNumber(limit)} créditos.`);
    return;
  }
  state.selectedSections.set(item.section.id, item);
  persistSelectedSections();
  renderRankingView();
}

function handleSelectedAction(event) {
  const toggle = event.target.closest("[data-toggle-selected]");
  if (toggle) {
    state.selectedShelfExpanded = !state.selectedShelfExpanded;
    persistRankingView();
    renderSelectedShelf();
    return;
  }
  const button = event.target.closest("[data-remove-section]");
  if (!button) return;
  state.selectedSections.delete(button.dataset.removeSection);
  persistSelectedSections();
  if (state.ranking) renderRankingView();
  else renderSelectedShelf();
}

function renderSelectedShelf() {
  const selected = [...state.selectedSections.values()];
  elements.selectedShelf.hidden = selected.length === 0;
  elements.selectedShelf.classList.toggle("is-expanded", state.selectedShelfExpanded);
  if (!selected.length) {
    elements.selectedShelf.innerHTML = "";
    return;
  }
  const knownCredits = selected.map(getItemCredits).filter((value) => value !== null);
  const totalCredits = knownCredits.reduce((total, value) => total + value, 0);
  const limit = state.profile?.max_quarter_credits === null || state.profile?.max_quarter_credits === undefined
    ? null
    : Number(state.profile.max_quarter_credits);
  const creditSummary = limit === null
    ? `${formatNumber(totalCredits)} créditos selecionados`
    : `${formatNumber(totalCredits)} de ${formatNumber(limit)} créditos`;
  elements.selectedShelf.innerHTML = `
    <div class="selected-shelf-header">
      <div>
        <strong>Turmas fixadas</strong>
        <span>${creditSummary}</span>
      </div>
      <button class="selected-expand" type="button" data-toggle-selected
        aria-expanded="${state.selectedShelfExpanded}">
        ${state.selectedShelfExpanded ? "Recolher" : "Expandir"}
      </button>
    </div>
    <div class="selected-list">
      ${selected.map((item) => renderSelectedSection(item)).join("")}
    </div>`;
}

function renderSelectedSection(item) {
  const section = item.section;
  const teachers = section.teachers.length
    ? section.teachers.map((teacher) => teacher.name).join(", ")
    : "Docente não informado";
  const meetings = section.meetings.length
    ? [...section.meetings].sort(compareMeetings).map((meeting) => (
      `${weekdays[meeting.weekday] || "Dia"} ${shortTime(meeting.start_time)}–${shortTime(meeting.end_time)}`
    )).join(" · ")
    : "Horário não informado";
  return `
    <article class="selected-chip" title="${escapeHtml(formatSectionDisplayName(section))}">
      <div class="selected-chip-topline">
        <span>${escapeHtml(section.subject.code)} · ${escapeHtml(section.code)}</span>
        <button type="button" data-remove-section="${escapeHtml(section.id)}"
          aria-label="Remover ${escapeHtml(section.subject.name)}">×</button>
      </div>
      ${state.selectedShelfExpanded ? `
        <strong class="selected-chip-name">${escapeHtml(formatSectionDisplayName(section))}</strong>
        <p>${escapeHtml(meetings)}</p>
        <p>${escapeHtml(teachers)}</p>
      ` : ""}
    </article>`;
}

function renderResultControls(visibleCount, totalCount) {
  const remaining = totalCount - visibleCount;
  if (remaining <= 0) return "";
  const nextCount = Math.min(resultPageSize, remaining);
  return `
    <div class="result-controls" aria-label="Carregar mais resultados">
      <p>${visibleCount} de ${totalCount} turmas carregadas na tela.</p>
      <div>
        <button type="button" data-results-action="more">Ver mais ${nextCount}</button>
        <button type="button" data-results-action="all">Ver todas</button>
      </div>
    </div>`;
}

function handleCategoryFilterChange() {
  state.selectedCategories = new Set(selectedValues("curriculum_category"));
  state.visibleResultCount = resultPageSize;
  persistRankingView();
  if (state.ranking) renderRankingView();
}

function itemMatchesCategoryFilters(item) {
  return item.curriculum_classifications.some((classification) => (
    state.selectedCategories.has(classification.category)
  ));
}

function syncCategoryFilterInputs() {
  document.querySelectorAll('input[name="curriculum_category"]').forEach((input) => {
    input.checked = state.selectedCategories.has(input.value);
  });
}

async function restoreLatestRanking() {
  const saved = readStorageJson(rankingViewStorageKey);
  if (!saved?.rankingId || saved.studentId !== state.studentId) return;
  try {
    const ranking = await fetchJson(`/rankings/${saved.rankingId}`);
    if (ranking.student_id !== state.studentId || ranking.term !== elements.term.value) {
      window.localStorage.removeItem(rankingViewStorageKey);
      return;
    }
    renderRanking(ranking, { resetVisible: false, persist: false });
  } catch (error) {
    window.localStorage.removeItem(rankingViewStorageKey);
    showToast("O ranking anterior não está mais disponível.");
  }
}

function restoreSelectedSections() {
  const saved = readStorageJson(selectedSectionsStorageKey);
  if (saved?.studentId !== state.studentId || !Array.isArray(saved.items)) return;
  state.selectedSections.clear();
  saved.items.forEach((item) => {
    if (item?.section?.id && item.section.subject && Array.isArray(item.section.meetings)) {
      state.selectedSections.set(item.section.id, item);
    }
  });
}

function refreshSelectedSections(ranking) {
  if (!state.selectedSections.size) return;
  ranking.items.forEach((item) => {
    if (state.selectedSections.has(item.section.id)) {
      state.selectedSections.set(item.section.id, item);
    }
  });
  persistSelectedSections();
}

function persistRankingView() {
  if (!state.studentId) return;
  const previous = readStorageJson(rankingViewStorageKey);
  writeStorageJson(rankingViewStorageKey, {
    studentId: state.studentId,
    rankingId: state.ranking?.id || previous?.rankingId || null,
    visibleResultCount: state.visibleResultCount,
    categories: [...state.selectedCategories],
    selectedShelfExpanded: state.selectedShelfExpanded,
  });
}

function persistSelectedSections() {
  if (!state.studentId) return;
  const items = [...state.selectedSections.values()].map((item) => ({
    position: item.position,
    total_score: item.total_score,
    section: item.section,
    curriculum_classifications: item.curriculum_classifications,
  }));
  writeStorageJson(selectedSectionsStorageKey, { studentId: state.studentId, items });
}

function isCompatibleWithSelection(item) {
  return [...state.selectedSections.values()].every((selected) => (
    selected.section.id !== item.section.id
    && selected.section.subject.id !== item.section.subject.id
    && !sectionsConflict(selected.section, item.section)
  ));
}

function sectionsConflict(first, second) {
  return first.meetings.some((left) => second.meetings.some((right) => (
    left.weekday === right.weekday
    && timeToMinutes(left.start_time) < timeToMinutes(right.end_time)
    && timeToMinutes(right.start_time) < timeToMinutes(left.end_time)
  )));
}

function timeToMinutes(value) {
  const [hours, minutes] = String(value).split(":").map(Number);
  return (hours * 60) + minutes;
}

function getItemCredits(item) {
  const primaryCourse = state.profile?.courses?.find((course) => course.is_primary)?.course_code;
  const preferred = item.curriculum_classifications.find((classification) => (
    classification.course_code === primaryCourse && classification.credits !== null
  ));
  const fallback = item.curriculum_classifications.find((classification) => classification.credits !== null);
  const value = preferred?.credits ?? fallback?.credits;
  if (value !== null && value !== undefined) return Number(value);

  const workload = String(item.section.workload_code || "").split("-").map(Number);
  if (workload.length < 3 || workload.some((part) => !Number.isFinite(part))) return null;
  return workload[0] + workload[1];
}

function formatSectionDisplayName(section) {
  const shift = section.shift === "Matutino" ? "Diurno" : section.shift;
  const campus = section.campus === "SA"
    ? "Santo André"
    : section.campus === "SB" ? "São Bernardo" : section.campus;
  const descriptor = [section.class_group, shift].filter(Boolean).join("-");
  const fallback = [section.subject.name, descriptor, campus ? `(${campus})` : null]
    .filter(Boolean)
    .join(" ");
  return String(section.display_name || fallback)
    .replace(/-Matutino\b/gi, "-Diurno")
    .replace(/\(SA\)\s*$/i, "(Santo André)")
    .replace(/\(SB\)\s*$/i, "(São Bernardo)");
}

function renderRankingCard(item, weights, rankingSize) {
  const section = item.section;
  const sectionDisplayName = formatSectionDisplayName(section);
  const seat = item.seat_probability;
  const priority = seat.priority;
  const aggregateProbability = seat.estimated_probability;
  const probabilityMetric = describeProbabilityMetric(seat);
  const teacherMetric = summarizeTeacherMetric(item);
  const classifications = item.curriculum_classifications
    .filter((classification) => classification.category)
    .map((classification) => `
      <span class="tag is-category">${escapeHtml(classification.course_code)} · ${escapeHtml(categoryLabels[classification.category] || classification.category)}</span>
    `).join("");
  const teachers = section.teachers.length
    ? section.teachers.map((teacher) => {
      const role = teacherRoleLabels[teacher.role] || "Docente";
      return `<p class="teacher-line"><strong>${escapeHtml(role)}:</strong> ${escapeHtml(teacher.name)}</p>`;
    }).join("")
    : '<p class="teacher-line">Docente ainda não informado</p>';
  const meetings = section.meetings.length
    ? [...section.meetings].sort(compareMeetings).map((meeting) => `
      <p>${weekdays[meeting.weekday] || "Dia"} · ${shortTime(meeting.start_time)}–${shortTime(meeting.end_time)}</p>
    `).join("")
    : "<p>Horário não informado</p>";
  const criteria = priority.criteria.map((criterion) => `
    <span class="criterion ${escapeHtml(criterion.status)}" title="${escapeHtml(criterion.explanation)}">
      ${escapeHtml(formatCriterion(criterion))}
    </span>
  `).join("");
  const explanations = [...new Set([
    ...item.explanations,
    ...seat.favorable_factors,
    ...seat.risk_factors,
    ...seat.warnings,
  ])]
    .filter(Boolean)
    .map((text) => `<li>${escapeHtml(text)}</li>`)
    .join("");
  const scoreBreakdown = Object.entries(item.score_breakdown)
    .filter(([key]) => Number(weights[key] || 0) > 0)
    .map(([key, score]) => `<li>${escapeHtml(scoreLabels[key] || key)}: ${Math.round(score)} × ${Math.round(weights[key] * 100)}%</li>`)
    .join("");
  const requests = seat.requests === null ? "?" : seat.requests;
  const seats = seat.seats === null ? "?" : seat.seats;
  const meterWidth = aggregateProbability === null ? 0 : Math.round(aggregateProbability * 100);
  const gradientColor = rankGradientColor(item.position, rankingSize);
  const observedDemandLabel = aggregateProbability === null ? "Sem dados" : formatPercent(aggregateProbability);
  const observedDemandCaption = aggregateProbability === null
    ? "Sem demanda atual observada; a chance pessoal pode vir apenas da base local."
    : "Disponibilidade agregada da turma; nao representa sua chance pessoal.";

  return `
    <article class="ranking-card" style="--position:${Math.min(item.position, 12)};--rank-color:${gradientColor}">
      <div class="rank-number" aria-label="Posição ${item.position}">${item.position}</div>
      <span class="rank-gradient" aria-hidden="true"></span>
      <div class="card-main">
        <div class="card-topline">
          <div>
            <p class="subject-code"><span>Disciplina</span>${escapeHtml(section.subject.code)}</p>
            <h3>${escapeHtml(sectionDisplayName)}</h3>
          </div>
          <div class="total-score"><strong>${Math.round(item.total_score)}</strong><span>compatibilidade geral</span></div>
        </div>
        <div class="tag-row">
          <span class="tag">Turma ${escapeHtml(section.code)}</span>
          <span class="tag">${escapeHtml(section.campus || "Campus ?")}</span>
          <span class="tag">${escapeHtml(section.shift || "Turno ?")}</span>
          ${classifications}
        </div>
        <div class="decision-grid">
          <div class="decision-box">
            <span class="detail-label">Probabilidade de matrícula</span>
            <strong class="decision-value">${escapeHtml(probabilityMetric.value)}</strong>
            <p class="decision-meta">${escapeHtml(probabilityMetric.meta)}</p>
          </div>
          <div class="decision-box">
            <span class="detail-label">Score do professor</span>
            <strong class="decision-value">${escapeHtml(teacherMetric.value)}</strong>
            <p class="decision-meta">${escapeHtml(teacherMetric.meta)}</p>
          </div>
          <div class="decision-box decision-box-reason">
            <span class="detail-label">Motivo da estimativa</span>
            <p class="decision-reason">${escapeHtml(seat.summary)}</p>
          </div>
        </div>
        <div class="card-details">
          <div class="detail-box">
            <span class="detail-label">Quando e com quem</span>
            ${meetings}
            <div class="teacher-list">${teachers}</div>
          </div>
          <div class="detail-box">
            <span class="detail-label">Base observada</span>
            <div class="availability-head">
              <span>${seats} vagas / ${requests} solicitações</span>
              <strong>${observedDemandLabel}</strong>
            </div>
            <div class="meter" aria-hidden="true"><span style="--meter-width:${meterWidth}%"></span></div>
            <p class="availability-caption">${escapeHtml(observedDemandCaption)}</p>
          </div>
        </div>
        <button class="select-section" type="button" data-section-id="${escapeHtml(section.id)}">
          Fixar esta turma e remover conflitos
        </button>
        <details class="card-disclosure">
          <summary>Por que esta turma ficou aqui?</summary>
          <div class="priority-strip" aria-label="Critérios de prioridade">
            ${criteria}
            <span class="tag">Grupo: ${escapeHtml(formatPool(priority.competition_pool))}</span>
          </div>
          <ul class="explanation-list">
            <li><strong>Fórmula de compatibilidade</strong></li>
            ${scoreBreakdown}
            ${explanations}
          </ul>
        </details>
      </div>
    </article>`;
}

function rankGradientColor(position, total) {
  const ratio = total <= 1 ? 0 : Math.min(Math.max((position - 1) / (total - 1), 0), 1);
  const hue = 154 - (142 * ratio);
  return `hsl(${hue.toFixed(1)} 66% 43%)`;
}

function rankingProbabilityValue(seat) {
  return seat.personalized_probability ?? seat.estimated_probability;
}

function describeProbabilityMetric(seat) {
  if (seat.personalized_probability !== null) {
    return {
      value: formatPercent(seat.personalized_probability),
      meta: "estimativa personalizada",
    };
  }
  if (seat.estimated_probability !== null) {
    return {
      value: formatPercent(seat.estimated_probability),
      meta: "referência agregada da turma",
    };
  }
  return {
    value: "Sem dados",
    meta: "probabilidade indisponível",
  };
}

function summarizeTeacherMetric(item) {
  const available = item.teacher_statistics.filter((teacher) => teacher.statistics_available).length;
  const total = item.teacher_statistics.length;
  if (!total) {
    return { value: "Sem docente", meta: "Turma sem docente informado" };
  }
  return {
    value: String(Math.round(item.score_breakdown.teacher)),
    meta: available ? `${available}/${total} docente(s) com histórico` : "Sem histórico docente",
  };
}

function formatCriterion(criterion) {
  if (criterion.code === "course") return criterion.value ? "curso prioritário" : "curso sem prioridade";
  if (criterion.code === "shift") return criterion.value ? "mesmo turno" : "turno diferente";
  if (criterion.code === "cp") return criterion.value === null ? "CP não informado" : `CP ${formatNumber(criterion.value)}`;
  if (criterion.code === "ca") return criterion.value === null ? "CA não informado" : `CA ${formatNumber(criterion.value)}`;
  return criterion.code;
}

function formatPool(pool) {
  const labels = {
    general: "geral",
    specific_linked: "vinculado",
    specific_non_linked_20_percent: "reserva de 20%",
    unknown: "não identificado",
  };
  return labels[pool] || pool;
}

function showError(title, message) {
  elements.results.setAttribute("aria-busy", "false");
  elements.selectedShelf.hidden = true;
  elements.results.innerHTML = `
    <div class="error-state">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(message)}</p>
    </div>`;
}

function setLoading(loading) {
  elements.button.disabled = loading;
  elements.button.querySelector("span").textContent = loading ? "Calculando..." : "Montar meu ranking";
}

function setActiveStep(target) {
  document.querySelectorAll(".step").forEach((step) => {
    step.classList.toggle("is-active", step.dataset.stepTarget === target);
  });
}

let toastTimer;
function showToast(message) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  toastTimer = window.setTimeout(() => { elements.toast.hidden = true; }, 3600);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(formatApiError(payload?.detail) || `Erro ${response.status}`);
  }
  return payload;
}

function formatApiError(detail) {
  if (!detail) return "O servidor não informou o motivo.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  return JSON.stringify(detail);
}

function readStorageJson(key) {
  try {
    const value = window.localStorage.getItem(key);
    return value ? JSON.parse(value) : null;
  } catch (error) {
    return null;
  }
}

function writeStorageJson(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    // The app remains usable when storage is disabled or full.
  }
}

function selectedValues(name) {
  return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map((input) => input.value);
}

function setValue(selector, value) {
  setElementValue(document.querySelector(selector), value);
}

function setElementValue(element, value) {
  if (element && value !== null && value !== undefined) element.value = value;
}

function formatPercent(value) {
  return value === null || value === undefined ? "Sem dados" : `${Math.round(value * 100)}%`;
}

function formatNumber(value) {
  return Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 4 });
}

function renderProfileMetric(label, value, options = {}) {
  const classes = ["profile-metric-value"];
  if (options.compact) classes.push("is-compact");
  if (options.data) classes.push("is-data");
  return `
    <article class="profile-metric">
      <span>${escapeHtml(label)}</span>
      <strong class="${classes.join(" ")}">${escapeHtml(value)}</strong>
    </article>`;
}

function formatCampusName(value) {
  if (value === "SA") return "Santo Andre";
  if (value === "SB") return "Sao Bernardo";
  return value;
}

function shortTime(value) {
  return String(value).slice(0, 5);
}

function compareMeetings(a, b) {
  return a.weekday - b.weekday || a.start_time.localeCompare(b.start_time);
}

function inferScheduleWindow(hard) {
  const earliest = hard.earliest_start_time || null;
  const latest = hard.latest_end_time || null;
  const match = Object.entries(scheduleWindows).find(([, value]) =>
    (value.earliest_start_time || null) === earliest
    && (value.latest_end_time || null) === latest
  );
  return match?.[0] || "any";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
}
