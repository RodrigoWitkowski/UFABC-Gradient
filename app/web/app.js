const state = {
  courses: [],
  terms: [],
  profile: null,
  studentId: window.localStorage.getItem("trajeto_student_id"),
};

const elements = {
  form: document.querySelector("#ranking-form"),
  courseOptions: document.querySelector("#course-options"),
  term: document.querySelector("#term"),
  currentTerm: document.querySelector("#current-term"),
  results: document.querySelector("#results"),
  resultMeta: document.querySelector("#result-meta"),
  button: document.querySelector("#rank-button"),
  apiStatus: document.querySelector("#api-status"),
  statusDot: document.querySelector(".status-dot"),
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

document.addEventListener("DOMContentLoaded", initialize);

async function initialize() {
  bindEvents();
  try {
    const [health, courses, terms] = await Promise.all([
      fetchJson("/health"),
      fetchJson("/courses"),
      fetchJson("/terms"),
    ]);
    setApiStatus(health.status === "ok");
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
    setApiStatus(false);
    showError("Não foi possível iniciar a interface", error.message);
  }
}

function bindEvents() {
  elements.form.addEventListener("submit", handleRankingSubmit);
  elements.courseOptions.addEventListener("change", handleCourseChange);
  document.querySelector("#ca").addEventListener("change", suggestCreditLimit);
  document.querySelectorAll("[data-step-target]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector(`#${button.dataset.stepTarget}`).scrollIntoView({ block: "start" });
      document.querySelectorAll(".step").forEach((step) => step.classList.remove("is-active"));
      button.classList.add("is-active");
    });
  });
}

async function loadStoredProfile() {
  try {
    state.profile = await fetchJson(`/students/${state.studentId}`);
    fillProfile(state.profile);
    showToast("Perfil local recuperado.");
  } catch (error) {
    window.localStorage.removeItem("trajeto_student_id");
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
  setValue("#ca", profile.ca);
  setValue("#max-quarter-credits", profile.max_quarter_credits);
  setValue("#cr", profile.cr);
  setValue("#accumulated-credits", profile.accumulated_credits);

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
  suggestCreditLimit();
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
    max_quarter_credits: decimalValue("#max-quarter-credits"),
  };
  if (!state.studentId) {
    const created = await fetchJson("/students", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(basicProfile),
    });
    state.studentId = created.id;
    window.localStorage.setItem("trajeto_student_id", created.id);
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
    cr: decimalValue("#cr"),
    ca: decimalValue("#ca"),
    max_quarter_credits: decimalValue("#max-quarter-credits"),
    accumulated_credits: decimalValue("#accumulated-credits"),
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
  elements.results.innerHTML = `
    <div class="loading-state" aria-label="Calculando ranking">
      <div class="skeleton result-skeleton"></div>
      <div class="skeleton result-skeleton"></div>
      <div class="skeleton result-skeleton"></div>
    </div>`;
}

function renderRanking(ranking) {
  elements.results.setAttribute("aria-busy", "false");
  elements.resultMeta.hidden = false;
  elements.resultMeta.innerHTML = `<strong>${ranking.item_count}</strong> turmas exibidas`;
  if (!ranking.items.length) {
    elements.results.innerHTML = `
      <div class="empty-state">
        <h3>Nenhuma turma passou pelos filtros.</h3>
        <p>Libere outro campus ou uma faixa de horário maior e tente novamente.</p>
      </div>`;
    return;
  }

  const knownDemand = ranking.items.filter((item) => item.seat_probability.estimated_probability !== null);
  elements.results.innerHTML = `
    <div class="ranking-summary">
      <div class="summary-cell"><span>Turmas compatíveis</span><strong>${ranking.candidate_count}</strong></div>
      <div class="summary-cell"><span>Exibidas</span><strong>${ranking.item_count}</strong></div>
      <div class="summary-cell"><span>Demanda disponível</span><strong>${knownDemand.length}/${ranking.item_count}</strong></div>
    </div>
    <div class="ranking-list">
      ${ranking.items.map((item) => renderRankingCard(item, ranking.config.weights)).join("")}
    </div>`;
}

function renderRankingCard(item, weights) {
  const section = item.section;
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
      return `${escapeHtml(role)}: ${escapeHtml(teacher.name)}`;
    }).join(" · ")
    : "Docente ainda não informado";
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
            <p class="subject-code">${escapeHtml(section.subject.code)}</p>
            <h3>${escapeHtml(section.subject.name)}</h3>
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
            <p>${teachers}</p>
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

function setApiStatus(online) {
  elements.apiStatus.textContent = online ? "Sistema local conectado" : "Sistema indisponível";
  elements.statusDot.classList.toggle("is-online", online);
  elements.statusDot.classList.toggle("is-offline", !online);
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

function suggestCreditLimit() {
  const input = document.querySelector("#max-quarter-credits");
  if (input.value.trim()) return;
  const ca = decimalValue("#ca");
  if (ca !== null) input.value = Math.ceil(20 + (2 * ca));
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
