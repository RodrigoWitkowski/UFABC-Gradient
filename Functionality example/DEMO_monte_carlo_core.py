from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable
import heapq
import math
import random
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile


@dataclass(frozen=True)
class Student:
    id: str
    affiliated_course: str | None
    shift: str
    cp: float
    ca: float
    passed_subject: bool = False


@dataclass(frozen=True)
class Subject:
    code: str
    name: str
    seats: int
    shift: str
    specific_course: str | None = None
    reserve_fraction: float = 0.0


@dataclass(frozen=True)
class OfficialCalibration:
    source_name: str
    update_date: str
    latest_period: str
    total_students: int
    p_bcc: float
    p_bct: float
    p_other: float
    p_noturno: float


@dataclass(frozen=True)
class MockPopulationConfig:
    population_size: int = 1600
    observed_population_fraction: float = 0.50
    p_bcc: float = 0.22
    p_bct: float = 0.55
    p_other: float = 0.23
    p_noturno: float = 0.58
    request_weight_bcc: float = 3.0
    request_weight_bct: float = 1.25
    request_weight_other: float = 0.65
    request_weight_same_shift: float = 1.35
    request_weight_specific_course_affiliation_multiplier: float = 8.0
    passed_probability_same_course: float = 0.38
    passed_probability_other_course: float = 0.12
    passed_probability_no_affiliation: float = 0.05
    passed_probability_general_subject: float = 0.16


@dataclass(frozen=True)
class SimulationEstimate:
    probability: float
    ci_low: float
    ci_high: float
    uncertainty: float
    known_competitors: int
    unknown_in_base_competitors: int
    unknown_outside_base_competitors: int


@dataclass(frozen=True)
class MockWorld:
    world_population: list[Student]
    observed_population: list[Student]
    true_requesters: list[Student]


ODF_TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
ODF_TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
ODF_NS = {"table": ODF_TABLE_NS, "text": ODF_TEXT_NS}
SPINNER_FRAMES = "|/-\\"


def student_from_dict(data: dict) -> Student:
    return Student(
        id=str(data["id"]),
        affiliated_course=data.get("affiliated_course"),
        shift=str(data["shift"]),
        cp=float(data["cp"]),
        ca=float(data["ca"]),
        passed_subject=bool(data.get("passed_subject", False)),
    )


def subject_from_dict(data: dict) -> Subject:
    return Subject(
        code=str(data["code"]),
        name=str(data["name"]),
        seats=int(data["seats"]),
        shift=str(data["shift"]),
        specific_course=data.get("specific_course"),
        reserve_fraction=float(data.get("reserve_fraction", 0.0)),
    )


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_only.lower().split())


def extract_cell_text(cell: ET.Element) -> str:
    paragraphs = ["".join(item.itertext()).strip() for item in cell.findall(".//text:p", ODF_NS)]
    return "\n".join(part for part in paragraphs if part)


def load_official_calibration(path: Path) -> OfficialCalibration | None:
    if not path.exists():
        return None

    rows: list[list[str]] = []
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))

    table = root.find(".//table:table", ODF_NS)
    if table is None:
        return None

    for row in table.findall("table:table-row", ODF_NS):
        values: list[str] = []
        for cell in list(row):
            tag = cell.tag.rsplit("}", 1)[-1]
            repeat = int(cell.attrib.get(f"{{{ODF_TABLE_NS}}}number-columns-repeated", "1"))
            if tag == "covered-table-cell":
                values.extend([""] * repeat)
                continue

            text = extract_cell_text(cell)
            span = int(cell.attrib.get(f"{{{ODF_TABLE_NS}}}number-columns-spanned", "1"))
            values.append(text)
            values.extend([""] * (span - 1))
            if repeat > 1:
                values.extend([text] * (repeat - 1))

        if any(values):
            rows.append(values)

    if len(rows) < 6:
        return None

    latest_period = next((value for value in reversed(rows[3][2:]) if value), "ultimo periodo")
    update_line = rows[0][0]
    update_date = update_line.split(":", 1)[1].strip() if ":" in update_line else "desconhecida"

    total_pair: list[int] | None = None
    bcc_students = 0
    bct_students = 0

    for row in rows[5:]:
        campus = normalize_label(row[0].strip())
        course = normalize_label(row[1].strip())
        numbers = [int(value) for value in row[2:] if value.isdigit()]
        if len(numbers) < 2:
            continue

        latest_pair = numbers[-2:]
        total_latest = latest_pair[0] + latest_pair[1]

        if campus == "total":
            total_pair = latest_pair
            continue
        if course == "bacharelado em ciencia da computacao":
            bcc_students += total_latest
        elif course == "bacharelado em ciencia e tecnologia":
            bct_students += total_latest

    if total_pair is None:
        return None

    total_students = total_pair[0] + total_pair[1]
    if total_students <= 0:
        return None

    other_students = max(total_students - bcc_students - bct_students, 0)
    return OfficialCalibration(
        source_name=path.name,
        update_date=update_date,
        latest_period=latest_period,
        total_students=total_students,
        p_bcc=bcc_students / total_students,
        p_bct=bct_students / total_students,
        p_other=other_students / total_students,
        p_noturno=total_pair[1] / total_students,
    )


def apply_official_calibration(
    cfg: MockPopulationConfig,
    calibration: OfficialCalibration | None,
) -> MockPopulationConfig:
    if calibration is None:
        return cfg
    return replace(
        cfg,
        p_bcc=calibration.p_bcc,
        p_bct=calibration.p_bct,
        p_other=calibration.p_other,
        p_noturno=calibration.p_noturno,
    )


def is_affiliated(student: Student, subject: Subject) -> bool:
    return (
        subject.specific_course is not None
        and student.affiliated_course == subject.specific_course
    )


def is_eligible(student: Student) -> bool:
    return not student.passed_subject


def general_priority_key(student: Student, subject: Subject) -> tuple[int, int, float, float]:
    return (
        int(is_affiliated(student, subject)),
        int(student.shift == subject.shift),
        student.cp,
        student.ca,
    )


def reserve_priority_key(student: Student, subject: Subject) -> tuple[int, float, float]:
    return (
        int(student.shift == subject.shift),
        student.cp,
        student.ca,
    )


def allocate_subject(requesters: Iterable[Student], subject: Subject) -> set[str]:
    requesters = [student for student in requesters if is_eligible(student)]
    if len(requesters) <= subject.seats:
        return {student.id for student in requesters}

    reserved_seats = int(math.floor(subject.seats * subject.reserve_fraction))
    general_seats = subject.seats - reserved_seats
    admitted: set[str] = set()

    if reserved_seats > 0:
        non_affiliated = [student for student in requesters if not is_affiliated(student, subject)]
        non_affiliated.sort(key=lambda student: reserve_priority_key(student, subject), reverse=True)
        admitted.update(student.id for student in non_affiliated[:reserved_seats])

    remaining = [student for student in requesters if student.id not in admitted]
    remaining.sort(key=lambda student: general_priority_key(student, subject), reverse=True)
    admitted.update(student.id for student in remaining[:general_seats])

    missing = subject.seats - len(admitted)
    if missing > 0:
        remaining = [student for student in requesters if student.id not in admitted]
        remaining.sort(key=lambda student: general_priority_key(student, subject), reverse=True)
        admitted.update(student.id for student in remaining[:missing])

    return admitted


def clipped_normal(rng: random.Random, mean: float, std: float, low: float, high: float) -> float:
    return min(max(rng.gauss(mean, std), low), high)


def passed_subject_probability(
    course: str | None,
    subject: Subject,
    cfg: MockPopulationConfig,
) -> float:
    if subject.specific_course is None:
        return cfg.passed_probability_general_subject
    if course == subject.specific_course:
        return cfg.passed_probability_same_course
    if course is None:
        return cfg.passed_probability_no_affiliation
    return cfg.passed_probability_other_course


def generate_mock_student(
    student_id: str,
    rng: random.Random,
    subject: Subject,
    cfg: MockPopulationConfig,
) -> Student:
    course_bucket = rng.choices(
        ["BCC", "BCT", "OTHER"],
        weights=[cfg.p_bcc, cfg.p_bct, cfg.p_other],
        k=1,
    )[0]
    shift = rng.choices(
        ["Noturno", "Diurno"],
        weights=[cfg.p_noturno, 1 - cfg.p_noturno],
        k=1,
    )[0]

    if course_bucket == "BCC":
        cp = clipped_normal(rng, 0.72, 0.16, 0.05, 1.00)
        ca = clipped_normal(rng, 3.05, 0.55, 0.50, 4.00)
    elif course_bucket == "BCT":
        cp = clipped_normal(rng, 0.61, 0.20, 0.02, 1.00)
        ca = clipped_normal(rng, 2.80, 0.60, 0.40, 4.00)
    else:
        cp = clipped_normal(rng, 0.58, 0.21, 0.02, 1.00)
        ca = clipped_normal(rng, 2.75, 0.65, 0.40, 4.00)

    affiliated_course = None if course_bucket == "OTHER" else course_bucket
    passed_subject = rng.random() < passed_subject_probability(affiliated_course, subject, cfg)
    return Student(
        id=student_id,
        affiliated_course=affiliated_course,
        shift=shift,
        cp=round(cp, 3),
        ca=round(ca, 3),
        passed_subject=passed_subject,
    )


def generate_population(
    subject: Subject,
    cfg: MockPopulationConfig,
    rng: random.Random,
    size: int,
) -> list[Student]:
    return [
        generate_mock_student(f"student_{index:04d}", rng, subject, cfg)
        for index in range(size)
    ]


def effective_world_population_size(cfg: MockPopulationConfig) -> int:
    fraction = min(max(cfg.observed_population_fraction, 1e-6), 1.0)
    return max(cfg.population_size, int(round(cfg.population_size / fraction)))


def request_weight(student: Student, subject: Subject, cfg: MockPopulationConfig) -> float:
    if not is_eligible(student):
        return 0.0

    if student.affiliated_course == "BCC":
        weight = cfg.request_weight_bcc
    elif student.affiliated_course == "BCT":
        weight = cfg.request_weight_bct
    else:
        weight = cfg.request_weight_other

    if subject.specific_course is not None and student.affiliated_course == subject.specific_course:
        weight *= cfg.request_weight_specific_course_affiliation_multiplier
    if student.shift == subject.shift:
        weight *= cfg.request_weight_same_shift
    return weight


def weighted_sample_without_replacement(
    population: list[Student],
    weights: list[float],
    count: int,
    rng: random.Random,
) -> list[Student]:
    if count > len(population):
        raise ValueError("Amostra maior que a populacao disponivel.")
    if count == 0:
        return []

    weighted_candidates: list[tuple[float, Student]] = []
    for student, weight in zip(population, weights):
        if weight <= 0:
            continue
        uniform = max(rng.random(), 1e-12)
        weighted_candidates.append((math.log(uniform) / weight, student))

    if count > len(weighted_candidates):
        raise ValueError("Nao ha alunos elegiveis suficientes para a amostra.")

    return [
        student
        for _key, student in heapq.nlargest(count, weighted_candidates, key=lambda item: item[0])
    ]


def build_weighted_pool(
    population: list[Student],
    subject: Subject,
    cfg: MockPopulationConfig,
    excluded_ids: set[str] | None = None,
) -> tuple[list[Student], list[float]]:
    excluded_ids = excluded_ids or set()
    students: list[Student] = []
    weights: list[float] = []
    for student in population:
        if student.id in excluded_ids:
            continue
        weight = request_weight(student, subject, cfg)
        if weight <= 0:
            continue
        students.append(student)
        weights.append(weight)
    return students, weights


def create_mock_world(
    subject: Subject,
    target: Student,
    total_requests: int,
    cfg: MockPopulationConfig,
    seed: int = 123,
) -> MockWorld:
    rng = random.Random(seed)
    world_population = generate_population(
        subject,
        cfg,
        rng,
        size=effective_world_population_size(cfg),
    )
    observed_population = rng.sample(world_population, cfg.population_size)
    eligible_population, eligible_weights = build_weighted_pool(world_population, subject, cfg)
    if total_requests - 1 > len(eligible_population):
        raise ValueError("Requisicoes demais para a populacao elegivel gerada.")

    competitors = weighted_sample_without_replacement(
        eligible_population,
        eligible_weights,
        total_requests - 1,
        rng,
    )
    return MockWorld(
        world_population=world_population,
        observed_population=observed_population,
        true_requesters=[replace(target, passed_subject=False)] + competitors,
    )


def choose_known_profiles(
    true_requesters: list[Student],
    target_id: str,
    coverage: float,
    seed: int,
    observed_student_ids: set[str],
) -> dict[str, Student]:
    rng = random.Random(seed)
    competitors = [
        student
        for student in true_requesters
        if student.id != target_id and student.id in observed_student_ids
    ]
    known_count = int(round(len(competitors) * coverage))
    selected = rng.sample(competitors, known_count) if known_count else []

    result = {student.id: student for student in selected}
    target = next(student for student in true_requesters if student.id == target_id)
    result[target.id] = target
    return result


def simulate_probability_with_next(
    subject: Subject,
    target: Student,
    requester_ids: set[str],
    known_profiles: dict[str, Student],
    observed_population: list[Student],
    cfg: MockPopulationConfig,
    simulations: int = 10_000,
    seed: int = 999,
    progress_callback: Callable[[int, int], None] | None = None,
) -> SimulationEstimate:
    if target.id not in requester_ids:
        raise ValueError("O aluno-alvo precisa estar entre os requisitantes.")

    competitor_ids = requester_ids - {target.id}
    observed_student_ids = {student.id for student in observed_population}

    known_competitors = [
        known_profiles[student_id]
        for student_id in competitor_ids
        if student_id in known_profiles
    ]
    unknown_in_base_ids = [
        student_id
        for student_id in competitor_ids
        if student_id not in known_profiles and student_id in observed_student_ids
    ]
    unknown_outside_base_ids = [
        student_id
        for student_id in competitor_ids
        if student_id not in observed_student_ids
    ]
    unknown_ids = unknown_in_base_ids + unknown_outside_base_ids

    if not unknown_ids:
        admitted = allocate_subject([target] + known_competitors, subject)
        probability = float(target.id in admitted)
        return SimulationEstimate(
            probability=probability,
            ci_low=probability,
            ci_high=probability,
            uncertainty=0.0,
            known_competitors=len(known_competitors),
            unknown_in_base_competitors=0,
            unknown_outside_base_competitors=0,
        )

    known_ids = {student.id for student in known_competitors}
    inference_pool, inference_weights = build_weighted_pool(
        observed_population,
        subject,
        cfg,
        excluded_ids=known_ids,
    )
    if len(unknown_ids) > len(inference_pool):
        raise ValueError("Pool de inferencia insuficiente para os perfis desconhecidos.")

    rng = random.Random(seed)
    admitted_count = 0
    update_every = max(1, simulations // 40)
    for index in range(simulations):
        sampled_profiles = weighted_sample_without_replacement(
            inference_pool,
            inference_weights,
            len(unknown_ids),
            rng,
        )
        simulated_requesters = [
            replace(profile, id=requester_id)
            for profile, requester_id in zip(sampled_profiles, unknown_ids)
        ]
        if target.id in allocate_subject([target] + known_competitors + simulated_requesters, subject):
            admitted_count += 1

        current = index + 1
        if progress_callback and (current % update_every == 0 or current == simulations):
            progress_callback(current, simulations)

    probability = admitted_count / simulations
    ci_low, ci_high = wilson_interval(admitted_count, simulations)
    return SimulationEstimate(
        probability=probability,
        ci_low=ci_low,
        ci_high=ci_high,
        uncertainty=(ci_high - ci_low) / 2,
        known_competitors=len(known_competitors),
        unknown_in_base_competitors=len(unknown_in_base_ids),
        unknown_outside_base_competitors=len(unknown_outside_base_ids),
    )


def wilson_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    if trials <= 0:
        return 0.0, 0.0

    phat = successes / trials
    z2 = z * z
    denominator = 1 + z2 / trials
    center = (phat + z2 / (2 * trials)) / denominator
    margin = z * math.sqrt((phat * (1 - phat) + z2 / (4 * trials)) / trials) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def deterministic_truth(true_requesters: list[Student], target_id: str, subject: Subject) -> bool:
    return target_id in allocate_subject(true_requesters, subject)


def course_bucket(student: Student) -> str:
    if student.affiliated_course == "BCC":
        return "bcc"
    if student.affiliated_course == "BCT":
        return "bct"
    return "outros"


def summarize_students(students: list[Student]) -> dict[str, int]:
    summary = Counter()
    summary["total"] = len(students)
    summary["noturno"] = sum(student.shift == "Noturno" for student in students)
    summary["diurno"] = summary["total"] - summary["noturno"]
    summary["passed"] = sum(student.passed_subject for student in students)
    summary["eligible"] = summary["total"] - summary["passed"]

    for student in students:
        bucket = course_bucket(student)
        summary[bucket] += 1
        if student.passed_subject:
            summary[f"{bucket}_passed"] += 1
    return dict(summary)


def fmt_pct(value: float) -> str:
    return f"{value * 100:5.2f}%"


def fmt_ratio(count: int, total: int) -> str:
    if total <= 0:
        return f"{count:>4} (  0.00%)"
    return f"{count:>4} ({count / total * 100:6.2f}%)"


def fmt_course_passed(summary: dict[str, int], bucket: str) -> str:
    return fmt_ratio(summary.get(f"{bucket}_passed", 0), summary.get(bucket, 0))


def clear_progress_line() -> None:
    sys.stdout.write("\r" + (" " * 96) + "\r")
    sys.stdout.flush()


def make_progress_callback(label: str) -> Callable[[int, int], None]:
    state = {"tick": 0}

    def callback(current: int, total: int) -> None:
        frame = SPINNER_FRAMES[state["tick"] % len(SPINNER_FRAMES)]
        state["tick"] += 1
        percent = current / total if total else 1.0
        sys.stdout.write(f"\r{frame} {label:<16} {current:>5}/{total:<5} ({percent:6.2%})")
        sys.stdout.flush()
        if current >= total:
            clear_progress_line()

    return callback


def print_subject_block(subject: Subject) -> None:
    reserved_seats = int(math.floor(subject.seats * subject.reserve_fraction))
    print("Turma")
    print("-" * 76)
    print(f"Codigo                 : {subject.code}")
    print(f"Nome                   : {subject.name}")
    print(f"Turno                  : {subject.shift}")
    print(f"Curso prioritario      : {subject.specific_course or 'Sem vinculo especifico'}")
    print(f"Vagas totais           : {subject.seats}")
    print(f"Vagas gerais           : {subject.seats - reserved_seats}")
    print(f"Vagas reserva          : {reserved_seats} ({subject.reserve_fraction:.0%})")
    print()


def print_target_block(target: Student) -> None:
    print("Aluno-alvo")
    print("-" * 76)
    print(f"Curso                  : {target.affiliated_course or 'Sem vinculo'}")
    print(f"Turno                  : {target.shift}")
    print(f"CP / CA                : {target.cp:.3f} / {target.ca:.3f}")
    print(f"Ja passou na materia   : {'Sim' if target.passed_subject else 'Nao'}")
    print()


def print_calibration_block(
    cfg: MockPopulationConfig,
    calibration: OfficialCalibration | None,
    observed_fraction_label: str | None = None,
) -> None:
    print("Calibracao de populacao")
    print("-" * 76)
    if calibration is None:
        print("Fonte                  : fallback manual do arquivo")
    else:
        print(f"Fonte                  : {calibration.source_name} (atualizada em {calibration.update_date})")
        print(f"Periodo base           : {calibration.latest_period}")
        print(
            f"Matriculas consideradas: {calibration.total_students} "
            "(a planilha conta matriculas, nao pessoas unicas)"
        )
    print(f"Mix de cursos          : BCC {fmt_pct(cfg.p_bcc)} | BCT {fmt_pct(cfg.p_bct)} | Outros {fmt_pct(cfg.p_other)}")
    print(f"Mix de turnos          : Noturno {fmt_pct(cfg.p_noturno)} | Diurno {fmt_pct(1 - cfg.p_noturno)}")
    print(
        "Prob. de ja ter passado: "
        f"mesmo curso {fmt_pct(cfg.passed_probability_same_course)} | "
        f"outro curso {fmt_pct(cfg.passed_probability_other_course)} | "
        f"sem vinculo {fmt_pct(cfg.passed_probability_no_affiliation)}"
    )
    print(
        "Demanda por curso      : "
        f"peso curso da materia x{cfg.request_weight_specific_course_affiliation_multiplier:.1f}"
    )
    if observed_fraction_label is not None:
        print(f"Base observada local   : {observed_fraction_label}")
    print("Regra de historico     : aprovado na materia -> fora da disputa")
    print()


def print_population_block(
    observed_summary: dict[str, int],
    requester_summary: dict[str, int],
    total_requests: int,
    observed_requester_count: int,
    truth: bool | None = None,
    world_summary: dict[str, int] | None = None,
    observed_fraction: float | None = None,
) -> None:
    print("Mundo mock")
    print("-" * 76)
    if world_summary is not None:
        print(
            f"Mundo sintetico total  : {world_summary['total']} alunos | "
            f"elegiveis {fmt_ratio(world_summary['eligible'], world_summary['total'])} | "
            f"ja passaram {fmt_ratio(world_summary['passed'], world_summary['total'])}"
        )
    if observed_fraction is None:
        print(
            f"Base observada         : {observed_summary['total']} alunos | "
            f"elegiveis {fmt_ratio(observed_summary['eligible'], observed_summary['total'])} | "
            f"ja passaram {fmt_ratio(observed_summary['passed'], observed_summary['total'])}"
        )
    else:
        print(
            f"Base observada         : {observed_summary['total']} alunos | "
            f"{fmt_pct(observed_fraction)} do mundo | "
            f"elegiveis {fmt_ratio(observed_summary['eligible'], observed_summary['total'])}"
        )

    if world_summary is not None:
        print(
            f"Cursos no mundo        : "
            f"BCC {fmt_ratio(world_summary['bcc'], world_summary['total'])} | "
            f"BCT {fmt_ratio(world_summary['bct'], world_summary['total'])} | "
            f"Outros {fmt_ratio(world_summary['outros'], world_summary['total'])}"
        )
    print(
        f"Cursos na base         : "
        f"BCC {fmt_ratio(observed_summary['bcc'], observed_summary['total'])} | "
        f"BCT {fmt_ratio(observed_summary['bct'], observed_summary['total'])} | "
        f"Outros {fmt_ratio(observed_summary['outros'], observed_summary['total'])}"
    )
    print(
        f"Turnos na base         : "
        f"Noturno {fmt_ratio(observed_summary['noturno'], observed_summary['total'])} | "
        f"Diurno {fmt_ratio(observed_summary['diurno'], observed_summary['total'])}"
    )
    print(
        f"Aprovados na base      : "
        f"BCC {fmt_course_passed(observed_summary, 'bcc')} | "
        f"BCT {fmt_course_passed(observed_summary, 'bct')} | "
        f"Outros {fmt_course_passed(observed_summary, 'outros')}"
    )
    print(
        f"Requisitantes mock     : {total_requests} | "
        f"BCC {fmt_ratio(requester_summary['bcc'], total_requests)} | "
        f"BCT {fmt_ratio(requester_summary['bct'], total_requests)} | "
        f"Outros {fmt_ratio(requester_summary['outros'], total_requests)}"
    )
    print(
        f"Requisitantes na base  : {observed_requester_count:>4} ({observed_requester_count / total_requests * 100:6.2f}%) | "
        f"fora da base {total_requests - observed_requester_count:>4} "
        f"({(total_requests - observed_requester_count) / total_requests * 100:6.2f}%)"
    )
    print(
        f"Turnos requisitantes   : "
        f"Noturno {fmt_ratio(requester_summary['noturno'], total_requests)} | "
        f"Diurno {fmt_ratio(requester_summary['diurno'], total_requests)}"
    )
    if truth is not None:
        print(f"Verdade secreta        : {'ENTRA' if truth else 'NAO ENTRA'}")
    print()


def print_probability_table_header(simulations: int) -> None:
    print("Cobertura dos perfis -> probabilidade estimada")
    print("-" * 120)
    print(f"Simulacoes por linha   : {simulations}")
    print(
        f"{'Cobertura':>10} | {'Conhec.':>7} | {'Desc.base':>9} | {'Fora base':>9} | "
        f"{'P(entrar)':>10} | {'IC95% MC':>22} | {'+/- MC':>8}"
    )
    print("-" * 120)


def format_probability_row(coverage: float, estimate: SimulationEstimate) -> str:
    interval = f"[{estimate.ci_low * 100:6.2f}%, {estimate.ci_high * 100:6.2f}%]"
    return (
        f"{coverage:>9.0%} | "
        f"{estimate.known_competitors:>7} | "
        f"{estimate.unknown_in_base_competitors:>9} | "
        f"{estimate.unknown_outside_base_competitors:>9} | "
        f"{estimate.probability * 100:>9.2f}% | "
        f"{interval:>22} | "
        f"{estimate.uncertainty * 100:>7.2f}%"
    )


def print_probability_notes() -> None:
    print()
    print("Obs.: o IC95% acima mede so o erro Monte Carlo da simulacao.")
    print("Nao mede a incerteza estrutural causada pelos perfis desconhecidos.")
    print("Desc.base = requisitantes da base local cujo perfil nao entrou nesta linha.")
    print("Fora base = requisitantes de alunos fora da base local; eles nunca viram conhecidos.")
    print()
