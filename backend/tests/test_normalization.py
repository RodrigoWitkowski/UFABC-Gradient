from app.models.enums import MeetingFrequency, MeetingType
from app.services.normalization.schedule import parse_schedule
from app.services.normalization.text import normalize_code, normalize_term_code, normalize_text


def test_text_and_code_normalization() -> None:
    assert normalize_text("  João  A. da Silva ") == "joao a da silva"
    assert normalize_code(" nhz6015-18 ") == "NHZ6015-18"
    assert normalize_term_code("matriculas_2026_3.xlsx") == "2026:3"


def test_schedule_is_split_into_typed_meetings() -> None:
    meetings = parse_schedule(
        "terça das 08:00 às 10:00, sala A-101, semanal ; "
        "quinta das 10:00 às 12:00, sala S-309-1, quinzenal II",
        campus="SA",
        meeting_type=MeetingType.THEORY,
    )

    assert len(meetings) == 2
    assert meetings[0].weekday == 1
    assert meetings[0].classroom == "A-101"
    assert meetings[0].frequency == MeetingFrequency.WEEKLY
    assert meetings[1].weekday == 3
    assert meetings[1].frequency == MeetingFrequency.BIWEEKLY_II


def test_unknown_schedule_is_rejected() -> None:
    try:
        parse_schedule("horário a definir", campus="SA", meeting_type=MeetingType.THEORY)
    except ValueError as exc:
        assert "nao reconhecido" in str(exc)
    else:
        raise AssertionError("invalid schedule should have failed")
