from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import json
import sys

from DEMO_monte_carlo_core import (
    MockPopulationConfig,
    OfficialCalibration,
    Student,
    Subject,
    choose_known_profiles,
    deterministic_truth,
    format_probability_row,
    load_official_calibration,
    make_progress_callback,
    print_population_block,
    print_probability_notes,
    print_probability_table_header,
    print_subject_block,
    print_target_block,
    simulate_probability_with_next,
    student_from_dict,
    subject_from_dict,
    summarize_students,
)


@dataclass(frozen=True)
class ExternalScenario:
    subject: Subject
    target: Student
    requester_ids: set[str]
    observed_population: list[Student]
    cfg: MockPopulationConfig
    simulations: int
    coverages: list[float]
    known_profiles: dict[str, Student] | None
    true_requesters: list[Student] | None
    observed_population_fraction: float | None
    calibration: OfficialCalibration | None


def load_external_scenario(path: Path) -> ExternalScenario:
    data = json.loads(path.read_text(encoding="utf-8"))
    cfg = replace(MockPopulationConfig(), **data.get("config_overrides", {}))
    calibration = load_official_calibration(path.with_name("prograd14.ods"))

    known_profiles_data = data.get("known_profiles")
    known_profiles = None
    if known_profiles_data is not None:
        known_profiles = {
            student.id: student
            for student in (student_from_dict(item) for item in known_profiles_data)
        }

    true_requesters_data = data.get("true_requesters")
    true_requesters = None
    if true_requesters_data is not None:
        true_requesters = [student_from_dict(item) for item in true_requesters_data]

    scenario = ExternalScenario(
        subject=subject_from_dict(data["subject"]),
        target=student_from_dict(data["target"]),
        requester_ids={str(item) for item in data["requester_ids"]},
        observed_population=[student_from_dict(item) for item in data["observed_population"]],
        cfg=cfg,
        simulations=int(data.get("simulations", 2_000)),
        coverages=[float(item) for item in data.get("coverages", [0.00, 0.25, 0.50, 0.75, 0.90, 1.00])],
        known_profiles=known_profiles,
        true_requesters=true_requesters,
        observed_population_fraction=(
            float(data["observed_population_fraction"])
            if "observed_population_fraction" in data
            else None
        ),
        calibration=calibration,
    )

    if scenario.target.id not in scenario.requester_ids:
        raise ValueError("O target precisa estar dentro de requester_ids.")
    return scenario


def print_inference_block(
    cfg: MockPopulationConfig,
    calibration: OfficialCalibration | None,
    observed_population_fraction: float | None,
) -> None:
    print("Parametros de inferencia")
    print("-" * 76)
    if calibration is not None:
        print(f"Base oficial auxiliar  : {calibration.source_name} ({calibration.latest_period})")
    if observed_population_fraction is not None:
        print(f"Base observada local   : {observed_population_fraction:.0%} do mundo estimado")
    print(
        "Pesos de requisicao    : "
        f"BCC {cfg.request_weight_bcc:.2f} | "
        f"BCT {cfg.request_weight_bct:.2f} | "
        f"Outros {cfg.request_weight_other:.2f}"
    )
    print(f"Mesmo turno            : x{cfg.request_weight_same_shift:.2f}")
    print(
        "Curso da materia       : "
        f"x{cfg.request_weight_specific_course_affiliation_multiplier:.2f} se afiliado"
    )
    print()


def print_external_report(scenario: ExternalScenario) -> None:
    observed_summary = summarize_students(scenario.observed_population)
    requester_summary = None
    truth = None
    observed_requester_count = sum(
        requester_id in {student.id for student in scenario.observed_population}
        for requester_id in scenario.requester_ids
        if requester_id != scenario.target.id
    )

    if scenario.true_requesters is not None:
        requester_summary = summarize_students(scenario.true_requesters)
        truth = deterministic_truth(scenario.true_requesters, scenario.target.id, scenario.subject)
    else:
        requester_summary = {
            "bcc": 0,
            "bct": 0,
            "outros": 0,
            "noturno": 0,
            "diurno": 0,
        }

    print("=" * 76)
    print("PLAYGROUND - NEXT + MONTE CARLO (DADOS EXTERNOS)")
    print("=" * 76)
    print_subject_block(scenario.subject)
    print_target_block(scenario.target)
    print_inference_block(
        scenario.cfg,
        scenario.calibration,
        scenario.observed_population_fraction,
    )

    if scenario.true_requesters is not None:
        print_population_block(
            observed_summary=observed_summary,
            requester_summary=requester_summary,
            total_requests=len(scenario.requester_ids),
            observed_requester_count=observed_requester_count,
            truth=truth,
            observed_fraction=scenario.observed_population_fraction,
        )
    else:
        print("Base observada")
        print("-" * 76)
        print(
            f"Alunos observados      : {observed_summary['total']} | "
            f"elegiveis {observed_summary['eligible']} | "
            f"ja passaram {observed_summary['passed']}"
        )
        print(
            f"Requisitantes do Next  : {len(scenario.requester_ids)} | "
            f"na base {observed_requester_count} | "
            f"fora da base {len(scenario.requester_ids) - observed_requester_count}"
        )
        print()

    observed_student_ids = {student.id for student in scenario.observed_population}
    print_probability_table_header(scenario.simulations)

    if scenario.known_profiles is not None:
        in_base_total = sum(
            requester_id in observed_student_ids
            for requester_id in scenario.requester_ids
            if requester_id != scenario.target.id
        )
        known_total = sum(
            requester_id in scenario.known_profiles
            for requester_id in scenario.requester_ids
            if requester_id != scenario.target.id and requester_id in observed_student_ids
        )
        coverage = known_total / in_base_total if in_base_total else 1.0
        estimate = simulate_probability_with_next(
            subject=scenario.subject,
            target=scenario.target,
            requester_ids=scenario.requester_ids,
            known_profiles=scenario.known_profiles,
            observed_population=scenario.observed_population,
            cfg=scenario.cfg,
            simulations=scenario.simulations,
            seed=900,
            progress_callback=(
                make_progress_callback("Cobertura real")
                if sys.stdout.isatty()
                else None
            ),
        )
        print(format_probability_row(coverage, estimate))
    else:
        for index, coverage in enumerate(scenario.coverages):
            known_profiles = choose_known_profiles(
                (
                    scenario.true_requesters
                    if scenario.true_requesters is not None
                    else [
                        scenario.target,
                        *[
                            student
                            for student in scenario.observed_population
                            if student.id in scenario.requester_ids and student.id != scenario.target.id
                        ],
                    ]
                ),
                scenario.target.id,
                coverage,
                seed=500 + index,
                observed_student_ids=observed_student_ids,
            )
            estimate = simulate_probability_with_next(
                subject=scenario.subject,
                target=scenario.target,
                requester_ids=scenario.requester_ids,
                known_profiles=known_profiles,
                observed_population=scenario.observed_population,
                cfg=scenario.cfg,
                simulations=scenario.simulations,
                seed=900 + index,
                progress_callback=(
                    make_progress_callback(f"Cobertura {coverage:.0%}")
                    if sys.stdout.isatty()
                    else None
                ),
            )
            print(format_probability_row(coverage, estimate))

    print_probability_notes()


def main() -> None:
    default_path = Path(__file__).with_name("DEMO_monte_carlo_external_data.json")
    scenario_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
    if not scenario_path.exists():
        raise SystemExit(
            "Arquivo de entrada nao encontrado. "
            "Use: python DEMO_monte_carlo_external_data.py <cenario.json>"
        )
    print_external_report(load_external_scenario(scenario_path))


if __name__ == "__main__":
    main()
