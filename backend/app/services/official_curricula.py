import json
from dataclasses import dataclass
from importlib import resources

from sqlalchemy.orm import Session

from app.schemas.curriculum import CurriculumImportRequest
from app.services.curriculum import CurriculumService


@dataclass(frozen=True)
class OfficialCurriculumImportResult:
    course_code: str
    version: str
    explicit_subjects: int


def load_official_curricula() -> list[CurriculumImportRequest]:
    data_directory = resources.files("app.data").joinpath("curricula")
    payloads = []
    for resource in sorted(data_directory.iterdir(), key=lambda item: item.name):
        if resource.name.endswith(".json"):
            with resource.open(encoding="utf-8") as source:
                payloads.append(CurriculumImportRequest.model_validate(json.load(source)))
    if not payloads:
        raise RuntimeError("nenhuma matriz curricular oficial encontrada")
    return payloads


def import_official_curricula(session: Session) -> list[OfficialCurriculumImportResult]:
    service = CurriculumService(session)
    results = []
    for payload in load_official_curricula():
        curriculum = service.import_curriculum(payload)
        results.append(
            OfficialCurriculumImportResult(
                course_code=curriculum.course.code,
                version=curriculum.version,
                explicit_subjects=len(curriculum.subjects),
            )
        )
    return results
