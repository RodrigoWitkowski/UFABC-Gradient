import { escapeHtml, formatCampusName, formatNumber } from "../shared/format.js";

export function renderEmptyProfileSummary(elements) {
  elements.profileSummary.innerHTML = `
    <div class="empty-state compact-empty-state">
      <h3>O ranking comeca pelo historico.</h3>
      <p>Importe o PDF do SIGAA para liberar seu vinculo, seu CP e a analise das turmas.</p>
    </div>`;
}

export function renderProfileSummary(elements, profile) {
  const courses = Array.isArray(profile.courses) ? profile.courses : [];
  const completedCount = Array.isArray(profile.completed_subjects)
    ? profile.completed_subjects.length
    : 0;
  const inProgressCount = Array.isArray(profile.in_progress_subjects)
    ? profile.in_progress_subjects.length
    : 0;
  const identityFacts = [
    renderProfileFact("RA", profile.ra || "Sem dado", { data: true }),
    renderProfileFact("Turno", profile.admission_shift || "Sem dado"),
    renderProfileFact("Campus", formatCampusName(profile.campus) || "Sem dado"),
    renderProfileFact("Ingresso", profile.admission_year || "Sem dado", { data: true }),
  ].join("");
  const progressMetrics = [
    renderProfileStat("CA", profile.ca === null ? "Sem dado" : formatNumber(profile.ca)),
    renderProfileStat(
      "Limite",
      profile.max_quarter_credits === null
        ? "Sem dado"
        : formatNumber(profile.max_quarter_credits),
    ),
    renderProfileStat("Concluidas", String(completedCount)),
    renderProfileStat("Em andamento", String(inProgressCount)),
  ].join("");
  const courseCards = courses.length
    ? courses.map((course, index) => `
      <article class="course-summary-card">
        <div class="course-summary-head">
          <div class="course-summary-copy">
            <p class="course-summary-kicker">${course.is_primary ? "Curso principal" : `Vinculo adicional ${index + 1}`}</p>
            <div class="course-summary-title-row">
              <h4 class="course-summary-title">${escapeHtml(course.course_code)}</h4>
              <span class="linked-course-badge${course.is_primary ? "" : " is-secondary"}">
                ${course.is_primary ? "Principal" : "Vinculo"}
              </span>
            </div>
            <p class="course-summary-name">${escapeHtml(course.course_name)}</p>
          </div>
        </div>
        <dl class="course-summary-meta">
          ${renderCourseMeta("Matriz", course.curriculum_version || "Automatica")}
          ${renderCourseMeta("CP", course.cp === null ? "Sem dado" : formatNumber(course.cp), { data: true })}
        </dl>
      </article>
    `).join("")
    : `
      <div class="profile-summary-warning">
        <strong>Nenhum curso foi vinculado automaticamente.</strong>
        <p>Sem curso vinculado, o ranking nao consegue aplicar corretamente a prioridade de matricula.</p>
      </div>`;
  elements.profileSummary.innerHTML = `
    <div class="profile-summary-stack">
      <section class="profile-history-card">
        <div class="profile-summary-heading">
          <div>
            <h3>Dados do historico</h3>
            <p>O PDF do SIGAA vira a fonte oficial do seu perfil. Aqui nao existe edicao manual.</p>
          </div>
        </div>
        <div class="profile-fact-list">
          ${identityFacts}
        </div>
        <div class="profile-stat-grid">
          ${progressMetrics}
        </div>
      </section>
      <section class="profile-summary-block">
        <div class="profile-summary-heading">
          <div>
            <h3>${courses.length === 1 ? "Curso vinculado" : "Cursos vinculados"}</h3>
            <p>O ranking usa a matriz e o CP do seu vinculo para estimar sua prioridade de matricula.</p>
          </div>
        </div>
        <div class="linked-course-list">
          ${courseCards}
        </div>
      </section>
    </div>`;
}

function renderProfileFact(label, value, options = {}) {
  return `
    <article class="profile-fact-row">
      <span class="profile-fact-label">${escapeHtml(label)}</span>
      <strong class="profile-fact-value${options.data ? " is-data" : ""}" title="${escapeHtml(value)}">
        ${escapeHtml(value)}
      </strong>
    </article>`;
}

function renderProfileStat(label, value) {
  return `
    <article class="profile-stat-card">
      <span class="profile-stat-label">${escapeHtml(label)}</span>
      <strong class="profile-stat-value" title="${escapeHtml(value)}">${escapeHtml(value)}</strong>
    </article>`;
}

function renderCourseMeta(label, value, options = {}) {
  return `
    <div class="course-summary-meta-item">
      <dt>${escapeHtml(label)}</dt>
      <dd class="${options.data ? "is-data" : ""}" title="${escapeHtml(value)}">${escapeHtml(value)}</dd>
    </div>`;
}
