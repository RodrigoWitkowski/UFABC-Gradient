from __future__ import annotations

from pathlib import Path
import sys

from DEMO_monte_carlo_core import (
    MockPopulationConfig,
    Student,
    Subject,
    apply_official_calibration,
    choose_known_profiles,
    create_mock_world,
    deterministic_truth,
    format_probability_row,
    load_official_calibration,
    make_progress_callback,
    print_calibration_block,
    print_population_block,
    print_probability_notes,
    print_probability_table_header,
    print_subject_block,
    print_target_block,
    simulate_probability_with_next,
    summarize_students,
)


def run_playground() -> None:
    target = Student(
        id="ME",
        affiliated_course="BCT",
        shift="Noturno",
        cp=0.65,
        ca=2.85,
        passed_subject=False,
    )
    subject = Subject(
        code="MCCC008-23",
        name="Inteligencia Artificial A1-Noturno",
        seats=90,
        shift="Noturno",
        specific_course="BCC",
        reserve_fraction=0.20,
    )
    calibration = load_official_calibration(Path(__file__).with_name("prograd14.ods"))
    cfg = apply_official_calibration(MockPopulationConfig(), calibration)

    total_requests = 250
    simulations = 2_000
    coverages = [0.00, 0.25, 0.50, 0.75, 0.90, 1.00]

    world = create_mock_world(subject, target, total_requests, cfg, seed=123)
    requester_ids = {student.id for student in world.true_requesters}
    observed_student_ids = {student.id for student in world.observed_population}
    observed_requester_count = sum(
        student.id in observed_student_ids
        for student in world.true_requesters
        if student.id != target.id
    )

    print("=" * 76)
    print("PLAYGROUND - NEXT + MONTE CARLO")
    print("=" * 76)
    print_subject_block(subject)
    print_target_block(target)
    print_calibration_block(
        cfg,
        calibration,
        observed_fraction_label=f"{cfg.observed_population_fraction:.0%} do mundo sintetico",
    )
    print_population_block(
        observed_summary=summarize_students(world.observed_population),
        requester_summary=summarize_students(world.true_requesters),
        total_requests=total_requests,
        observed_requester_count=observed_requester_count,
        truth=deterministic_truth(world.true_requesters, target.id, subject),
        world_summary=summarize_students(world.world_population),
        observed_fraction=cfg.observed_population_fraction,
    )

    print_probability_table_header(simulations)
    for index, coverage in enumerate(coverages):
        known_profiles = choose_known_profiles(
            world.true_requesters,
            target.id,
            coverage,
            seed=500 + index,
            observed_student_ids=observed_student_ids,
        )
        progress_callback = (
            make_progress_callback(f"Cobertura {coverage:.0%}")
            if sys.stdout.isatty()
            else None
        )
        estimate = simulate_probability_with_next(
            subject=subject,
            target=target,
            requester_ids=requester_ids,
            known_profiles=known_profiles,
            observed_population=world.observed_population,
            cfg=cfg,
            simulations=simulations,
            seed=900 + index,
            progress_callback=progress_callback,
        )
        print(format_probability_row(coverage, estimate))

    print_probability_notes()

    print("Brinque alterando")
    print("-" * 76)
    print("target.cp = 0.70 / 0.90")
    print("target.ca = 2.50 / 3.50")
    print("total_requests = 120 / 250 / 400")
    print("subject.seats = 40 / 90 / 120")
    print("subject.reserve_fraction = 0.0 / 0.20")
    print("cfg.request_weight_bcc = 1.0 / 3.0 / 5.0")
    print("cfg.request_weight_specific_course_affiliation_multiplier = 4.0 / 8.0 / 12.0")
    print("cfg.observed_population_fraction = 0.25 / 0.50 / 0.80")
    print("cfg.passed_probability_same_course = 0.25 / 0.50")
    print("simulations = 1_000 / 2_000 / 10_000")


if __name__ == "__main__":
    run_playground()
