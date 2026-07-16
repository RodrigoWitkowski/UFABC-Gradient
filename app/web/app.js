const studentIdStorageKey = "gradient_student_id";
const legacyStudentIdStorageKey = "trajeto_student_id";
const storedStudentId = window.localStorage.getItem(studentIdStorageKey)
  || window.localStorage.getItem(legacyStudentIdStorageKey);
if (storedStudentId && !window.localStorage.getItem(studentIdStorageKey)) {
  window.localStorage.setItem(studentIdStorageKey, storedStudentId);
  window.localStorage.removeItem(legacyStudentIdStorageKey);
}

const state = {
  courses: [],
  terms: [],
  profile: null,
  ranking: null,
  selectedSections: new Map(),
  studentId: storedStudentId,
};

const elements = {
  form: document.querySelector("#ranking-form"),
  courseOptions: document.querySelector("#course-options"),
  term: document.querySelector("#term"),
  currentTerm: document.querySelector("#current-term"),
  results: document.querySelector("#results"),
  resultMeta: document.querySelector("#result-meta"),
  selectedShelf: document.querySelector("#selected-shelf"),
  controlColumn: document.querySelector(".control-column"),
  button: document.querySelector("#rank-button"),
  historyInput: document.querySelector("#history-pdf"),
  historyLabel: document.querySelector("#history-upload-label"),
  historyStatus: document.querySelector("#history-status"),
  toast: document.querySelector("#toast"),
};

const supportedCourses = new Set(["BCT", "BCH", "BCC"]);
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
  try {
    const [courses, terms] = await Promise.all([fetchJson("/courses"), fetchJson("/terms")]);
    state.courses = courses.filter((course) => supportedCourses.has(course.code));
    state.terms = terms;
    renderCourses();
    renderTerms();
    if (state.studentId) {
      await loadStoredProfile();
    } else {
      selectDefaultCourse();
    }
  } catch (error) {
    showError("Não foi possível iniciar a interface", error.message);
  }
}

function bindEvents() {
  elements.form.addEventListener("submit", handleRankingSubmit);
  elements.courseOptions.addEventListener("change", handleCourseChange);
  elements.historyInput.addEventListener("change", handleHistoryUpload);
  elements.results.addEventListener("click", handleResultAction);
  elements.selectedShelf.addEventListener("click", handleSelectedAction);
  elements.controlColumn.addEventListener("scroll", updateControlFade, { passive: true });
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
    elements.historyStatus.textContent = `${completionSummary}; ${currentSummary}.${replacement}`;
    elements.historyStatus.hidden = false;
    historyStatusTimer = window.setTimeout(() => { elements.historyStatus.hidden = true; }, 9000);
    showToast("Histórico importado e perfil atualizado.");
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
}

async function loadStoredProfile() {
  try {
    state.profile = await fetchJson(`/students/${state.studentId}`);
    fillProfile(state.profile);
    showToast("Perfil local recuperado.");
  } catch (error) {
    window.localStorage.removeItem(studentIdStorageKey);
    state.studentId = null;
    state.profile = null;
    selectDefaultCourse();
    showToast("O perfil anterior não existe mais. Crie um novo perfil.");
  }
}

function renderCourses() {
  if (!state.courses.length) {
    elements.courseOptions.innerHTML = `
      <div class="error-state">
        <strong>Cursos não encontrados.</strong>
        <p>Importe as matrizes de BCT, BCH ou BCC antes de continuar.</p>
      </div>`;
    return;
  }

  const descriptions = {
    BCT: "Interdisciplinar de ingresso",
    BCH: "Interdisciplinar de ingresso",
    BCC: "Formação específica pós-BCT",
  };
  elements.courseOptions.innerHTML = state.courses.map((course) => {
    const versions = `<option value="">Automática pelo ano</option>` + course.curriculum_versions.map((curriculum) => `
      <option value="${escapeHtml(curriculum.version)}">Matriz ${escapeHtml(curriculum.version)}</option>
    `).join("");
    return `
      <article class="course-card" data-course-code="${escapeHtml(course.code)}">
        <div class="course-select-row">
          <input class="course-enabled" id="course-${escapeHtml(course.code)}" type="checkbox"
            value="${escapeHtml(course.code)}" aria-label="Selecionar ${escapeHtml(course.code)}">
          <label for="course-${escapeHtml(course.code)}">
            <strong>${escapeHtml(course.code)}</strong>
            <small>${escapeHtml(descriptions[course.code] || course.name)}</small>
          </label>
          <label class="primary-course">
            <input type="radio" name="primary_course" value="${escapeHtml(course.code)}" disabled>
            <span>Principal</span>
          </label>
        </div>
        <div class="course-detail">
          <label>Matriz<select class="course-version">${versions}</select></label>
          <label>CP<input class="course-cp" type="number" min="0" max="1" step="0.000001"
            placeholder="0 a 1" inputmode="decimal"></label>
          <label>IK<input class="course-ik" type="number" min="0" max="1" step="0.000001"
            placeholder="Opcional" inputmode="decimal"></label>
        </div>
      </article>`;
  }).join("");
}

function renderTerms() {
  if (!state.terms.length) {
    elements.term.value = "";
    elements.currentTerm.textContent = "Nenhuma oferta importada";
    return;
  }
  const term = state.terms[0];
  elements.term.value = term.code;
  elements.currentTerm.textContent = `${term.year} · ${term.term_number}º quadrimestre`;
}

function selectDefaultCourse() {
  const bct = document.querySelector('[data-course-code="BCT"] .course-enabled');
  if (bct) {
    bct.checked = true;
    updateCourseCard(bct.closest(".course-card"));
    selectPrimary("BCT");
  }
}

function fillProfile(profile) {
  setValue("#ra", profile.ra);
  setValue("#display-name", profile.display_name);
  setValue("#admission-year", profile.admission_year);
  setValue("#admission-shift", profile.admission_shift);
  setValue("#student-campus", profile.campus);
  setDecimalDisplay("#ca", profile.ca, 4);
  setDecimalDisplay("#max-quarter-credits", profile.max_quarter_credits, 0);

  document.querySelectorAll(".course-card").forEach((card) => {
    const saved = profile.courses.find((course) => course.course_code === card.dataset.courseCode);
    const enabled = card.querySelector(".course-enabled");
    enabled.checked = Boolean(saved);
    updateCourseCard(card);
    if (!saved) return;
    setElementValue(card.querySelector(".course-version"), saved.curriculum_version);
    setElementValue(card.querySelector(".course-cp"), saved.cp);
    setElementValue(card.querySelector(".course-ik"), saved.ik);
    if (saved.is_primary) selectPrimary(saved.course_code);
  });

  const hard = profile.preferences?.hard_constraints || {};
  const soft = profile.preferences?.soft_preferences || {};
  restoreChecks("allowed_campus", hard.allowed_campuses);
  setValue("#period-window", inferScheduleWindow(hard));
  document.querySelector("#avoid-friday").checked = Number(soft.avoid_friday || 0) > 0;
}

function restoreChecks(name, values) {
  if (!Array.isArray(values) || !values.length) return;
  document.querySelectorAll(`input[name="${name}"]`).forEach((input) => {
    input.checked = values.includes(input.value);
  });
}

function handleCourseChange(event) {
  const card = event.target.closest(".course-card");
  if (!card) return;
  if (event.target.classList.contains("course-enabled")) {
    updateCourseCard(card);
    if (event.target.checked && card.dataset.courseCode === "BCC") {
      ensureCourseSelected("BCT");
      selectPrimary("BCC");
      showToast("BCT também foi selecionado como curso de ingresso do BCC.");
    }
    ensurePrimaryCourse();
  }
}

function ensureCourseSelected(code) {
  const card = document.querySelector(`[data-course-code="${code}"]`);
  if (!card) return;
  card.querySelector(".course-enabled").checked = true;
  updateCourseCard(card);
}

function updateCourseCard(card) {
  const enabled = card.querySelector(".course-enabled").checked;
  const primary = card.querySelector('input[name="primary_course"]');
  card.classList.toggle("is-selected", enabled);
  primary.disabled = !enabled;
  if (!enabled) primary.checked = false;
}

function selectPrimary(code) {
  const primary = document.querySelector(`input[name="primary_course"][value="${code}"]`);
  if (primary && !primary.disabled) primary.checked = true;
}

function ensurePrimaryCourse() {
  const selected = [...document.querySelectorAll(".course-card.is-selected")];
  const checkedPrimary = document.querySelector('input[name="primary_course"]:checked');
  if (!checkedPrimary && selected.length) {
    selected[0].querySelector('input[name="primary_course"]').checked = true;
  }
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
  if (!elements.form.reportValidity()) throw new Error("Revise os campos obrigatórios.");
  const selectedCourses = document.querySelectorAll(".course-card.is-selected");
  if (!selectedCourses.length) throw new Error("Selecione pelo menos um curso.");
  if (!document.querySelector('input[name="primary_course"]:checked')) {
    throw new Error("Marque um curso como principal.");
  }
  if (!selectedValues("allowed_campus").length) throw new Error("Selecione ao menos um campus.");
  if (!elements.term.value) throw new Error("Nenhuma oferta de próximo quadrimestre foi importada.");
}

async function saveProfile() {
  const basicProfile = {
    ra: valueOrNull("#ra"),
    display_name: valueOrNull("#display-name"),
    admission_year: numberValue("#admission-year"),
    admission_shift: valueOrNull("#admission-shift"),
    campus: valueOrNull("#student-campus"),
  };
  if (!state.studentId) {
    const created = await fetchJson("/students", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(basicProfile),
    });
    state.studentId = created.id;
    window.localStorage.setItem(studentIdStorageKey, created.id);
  }

  state.profile = await fetchJson(`/students/${state.studentId}/academic-profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildAcademicProfile()),
  });
}

function buildAcademicProfile() {
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
    ra: valueOrNull("#ra"),
    admission_year: numberValue("#admission-year"),
    admission_shift: valueOrNull("#admission-shift"),
    campus: valueOrNull("#student-campus"),
    cr: state.profile?.cr ?? null,
    ca: decimalValue("#ca"),
    accumulated_credits: state.profile?.accumulated_credits ?? null,
    course_strategy: "primary_course",
    courses: selectedCoursePayloads(),
    completed_subjects: completed,
    in_progress_subjects: inProgress,
    preferences: buildPreferences(),
  };
}

function selectedCoursePayloads() {
  const primary = document.querySelector('input[name="primary_course"]:checked')?.value;
  return [...document.querySelectorAll(".course-card.is-selected")].map((card) => ({
    course_code: card.dataset.courseCode,
    curriculum_version: card.querySelector(".course-version").value || null,
    is_primary: card.dataset.courseCode === primary,
    cp: decimalElementValue(card.querySelector(".course-cp")),
    ik: decimalElementValue(card.querySelector(".course-ik")),
  }));
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
    result_limit: 50,
    config: {
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
  elements.selectedShelf.hidden = true;
  elements.results.innerHTML = `
    <div class="loading-state" aria-label="Calculando ranking">
      <div class="skeleton result-skeleton"></div>
      <div class="skeleton result-skeleton"></div>
      <div class="skeleton result-skeleton"></div>
    </div>`;
}

function renderRanking(ranking) {
  state.ranking = ranking;
  state.selectedSections.clear();
  renderRankingView();
}

function renderRankingView() {
  const ranking = state.ranking;
  if (!ranking) return;
  elements.results.setAttribute("aria-busy", "false");
  elements.resultMeta.hidden = false;
  const visibleItems = ranking.items.filter((item) => isCompatibleWithSelection(item));
  elements.resultMeta.innerHTML = `<strong>${visibleItems.length}</strong> turmas sem conflito`;
  renderSelectedShelf();
  if (!ranking.items.length) {
    elements.results.innerHTML = `
      <div class="empty-state">
        <h3>Nenhuma turma passou pelos filtros.</h3>
        <p>Libere outro campus ou uma faixa de horário maior e tente novamente.</p>
      </div>`;
    return;
  }
  if (!visibleItems.length) {
    elements.results.innerHTML = `
      <div class="empty-state">
        <h3>Nenhuma outra turma cabe nos horários escolhidos.</h3>
        <p>Remova uma turma fixada para liberar os horários conflitantes.</p>
      </div>`;
    return;
  }

  const knownDemand = visibleItems.filter((item) => item.seat_probability.estimated_probability !== null);
  elements.results.innerHTML = `
    <div class="ranking-summary">
      <div class="summary-cell"><span>Após filtros</span><strong>${ranking.candidate_count}</strong></div>
      <div class="summary-cell"><span>Sem conflito</span><strong>${visibleItems.length}</strong></div>
      <div class="summary-cell"><span>Demanda disponível</span><strong>${knownDemand.length}/${visibleItems.length}</strong></div>
    </div>
    <div class="ranking-list">
      ${visibleItems.map((item) => renderRankingCard(item, ranking.config.weights)).join("")}
    </div>`;
}

function handleResultAction(event) {
  const button = event.target.closest(".select-section");
  if (!button || !state.ranking) return;
  const item = state.ranking.items.find((candidate) => candidate.section.id === button.dataset.sectionId);
  if (!item) return;
  const credits = getItemCredits(item);
  const limit = decimalValue("#max-quarter-credits");
  const selectedCredits = [...state.selectedSections.values()]
    .reduce((total, selected) => total + (getItemCredits(selected) || 0), 0);
  if (limit !== null && credits !== null && selectedCredits + credits > limit) {
    showToast(`Essa turma ultrapassaria seu limite total de ${formatNumber(limit)} créditos.`);
    return;
  }
  state.selectedSections.set(item.section.id, item);
  renderRankingView();
}

function handleSelectedAction(event) {
  const button = event.target.closest("[data-remove-section]");
  if (!button) return;
  state.selectedSections.delete(button.dataset.removeSection);
  renderRankingView();
}

function renderSelectedShelf() {
  const selected = [...state.selectedSections.values()];
  elements.selectedShelf.hidden = selected.length === 0;
  if (!selected.length) {
    elements.selectedShelf.innerHTML = "";
    return;
  }
  const knownCredits = selected.map(getItemCredits).filter((value) => value !== null);
  const totalCredits = knownCredits.reduce((total, value) => total + value, 0);
  const limit = decimalValue("#max-quarter-credits");
  const creditSummary = limit === null
    ? `${formatNumber(totalCredits)} créditos selecionados`
    : `${formatNumber(totalCredits)} de ${formatNumber(limit)} créditos`;
  elements.selectedShelf.innerHTML = `
    <div class="selected-shelf-header">
      <strong>Turmas fixadas</strong>
      <span>${creditSummary}</span>
    </div>
    <div class="selected-list">
      ${selected.map((item) => `
        <span class="selected-chip" title="${escapeHtml(formatSectionDisplayName(item.section))}">
          ${escapeHtml(item.section.subject.code)} · ${escapeHtml(item.section.code)}
          <button type="button" data-remove-section="${escapeHtml(item.section.id)}" aria-label="Remover ${escapeHtml(item.section.subject.name)}">×</button>
        </span>
      `).join("")}
    </div>`;
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

function renderRankingCard(item, weights) {
  const section = item.section;
  const sectionDisplayName = formatSectionDisplayName(section);
  const seat = item.seat_probability;
  const priority = seat.priority;
  const probability = seat.estimated_probability;
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
  const explanations = [...item.explanations, ...seat.warnings]
    .filter(Boolean)
    .map((text) => `<li>${escapeHtml(text)}</li>`)
    .join("");
  const scoreBreakdown = Object.entries(item.score_breakdown)
    .filter(([key]) => Number(weights[key] || 0) > 0)
    .map(([key, score]) => `<li>${escapeHtml(scoreLabels[key] || key)}: ${Math.round(score)} × ${Math.round(weights[key] * 100)}%</li>`)
    .join("");
  const requests = seat.requests === null ? "?" : seat.requests;
  const seats = seat.seats === null ? "?" : seat.seats;
  const meterWidth = probability === null ? 0 : Math.round(probability * 100);

  return `
    <article class="ranking-card" style="--position:${Math.min(item.position, 12)}">
      <div class="rank-number" aria-label="Posição ${item.position}">${item.position}</div>
      <div class="card-main">
        <div class="card-topline">
          <div>
            <p class="subject-code"><span>Disciplina</span>${escapeHtml(section.subject.code)}</p>
            <h3>${escapeHtml(sectionDisplayName)}</h3>
          </div>
          <div class="total-score"><strong>${Math.round(item.total_score)}</strong><span>compatibilidade</span></div>
        </div>
        <div class="tag-row">
          <span class="tag">Turma ${escapeHtml(section.code)}</span>
          <span class="tag">${escapeHtml(section.campus || "Campus ?")}</span>
          <span class="tag">${escapeHtml(section.shift || "Turno ?")}</span>
          ${classifications}
        </div>
        <div class="card-details">
          <div class="detail-box">
            <span class="detail-label">Quando e com quem</span>
            ${meetings}
            <div class="teacher-list">${teachers}</div>
          </div>
          <div class="detail-box">
            <span class="detail-label">Demanda da turma</span>
            <div class="availability-head">
              <span>${seats} vagas / ${requests} solicitações</span>
              <strong>${formatPercent(probability)}</strong>
            </div>
            <div class="meter" aria-hidden="true"><span style="--meter-width:${meterWidth}%"></span></div>
            <p class="availability-caption">Não é sua chance pessoal.</p>
          </div>
        </div>
        <div class="priority-strip" aria-label="Critérios de prioridade">
          ${criteria}
          <span class="tag">Grupo: ${escapeHtml(formatPool(priority.competition_pool))}</span>
        </div>
        <button class="select-section" type="button" data-section-id="${escapeHtml(section.id)}">
          Fixar esta turma e remover conflitos
        </button>
        <details class="card-disclosure">
          <summary>Por que esta turma ficou aqui?</summary>
          <ul class="explanation-list">
            <li><strong>Fórmula de compatibilidade</strong></li>
            ${scoreBreakdown}
            ${explanations}
          </ul>
        </details>
      </div>
    </article>`;
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

function selectedValues(name) {
  return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map((input) => input.value);
}

function valueOrNull(selector) {
  const value = document.querySelector(selector).value.trim();
  return value || null;
}

function numberValue(selector) {
  return Number(document.querySelector(selector).value);
}

function decimalValue(selector) {
  return decimalElementValue(document.querySelector(selector));
}

function decimalElementValue(element) {
  const value = element.value.trim().replace(",", ".");
  return value === "" ? null : Number(value);
}

function setValue(selector, value) {
  setElementValue(document.querySelector(selector), value);
}

function setElementValue(element, value) {
  if (element && value !== null && value !== undefined) element.value = value;
}

function setDecimalDisplay(selector, value, maximumFractionDigits) {
  const element = document.querySelector(selector);
  if (!element) return;
  element.value = value === null || value === undefined
    ? ""
    : Number(value).toLocaleString("pt-BR", { maximumFractionDigits });
}

function formatPercent(value) {
  return value === null || value === undefined ? "Sem dados" : `${Math.round(value * 100)}%`;
}

function formatNumber(value) {
  return Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 4 });
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
