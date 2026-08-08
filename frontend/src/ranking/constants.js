export const weekdays = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"];

export const categoryLabels = {
  mandatory: "Obrigatoria",
  limited: "Opcao limitada",
  free: "Livre",
  not_applicable: "Nao aplicavel",
};

export const teacherRoleLabels = {
  theory: "Teoria",
  practice: "Pratica",
};

export const scoreLabels = {
  curriculum_relevance: "Curriculo",
  teacher: "Docentes",
  seat_probability: "Demanda",
  schedule_preference: "Horario",
  workload: "Carga",
  campus: "Campus",
};

export const scheduleWindows = {
  any: {},
  morning: { latest_end_time: "13:00" },
  afternoon: { earliest_start_time: "12:00", latest_end_time: "19:00" },
  night: { earliest_start_time: "18:00" },
  daytime: { latest_end_time: "19:00" },
  "afternoon-night": { earliest_start_time: "12:00" },
};
