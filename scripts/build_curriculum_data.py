from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "var" / "curriculum-sources"
DEFAULT_OUTPUT_DIR = ROOT / "app" / "data" / "curricula"
CODE_PATTERN = r"[A-Z]{3,4}[0-9]{3,4}-[0-9]{2}"
ROW_START_PATTERN = re.compile(rf"(?m)^(?P<code>{CODE_PATTERN})\s+")


@dataclass(frozen=True)
class SourceDocument:
    key: str
    filename: str
    url: str
    approval: str


SOURCES = {
    document.key: document
    for document in (
        SourceDocument(
            key="bct-2015-ppc",
            filename="bct-2015.pdf",
            url=(
                "https://www.ufabc.edu.br/images/consepe/resolucoes/"
                "3---Reviso-do-PP-do-Bacharelado-em-Cincia-e-Tecnologia-"
                "Esta-verso-contempla-as-retificaes.pdf"
            ),
            approval="Resolucao ConsEPE 188/2015",
        ),
        SourceDocument(
            key="bct-2015-limited",
            filename="bct-2015-limited.pdf",
            url=(
                "https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/"
                "consepe_ato_decisorio_232_anexo.pdf"
            ),
            approval="Ato Decisorio ConsEPE 232/2022",
        ),
        SourceDocument(
            key="bct-2023-ppc",
            filename="bct-2023.pdf",
            url=(
                "https://www.ufabc.edu.br/images/consepe/atos_decisorios/"
                "anexo_do_ad_consepe_249_-_ppc_bct_2023_-aprovado_consepe_-_"
                "final_pos_errata_12_23.pdf"
            ),
            approval="Ato Decisorio ConsEPE 249/2023",
        ),
        SourceDocument(
            key="bct-2023-limited",
            filename="bct-2023-limited.pdf",
            url=(
                "https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/"
                "comissao_ato_decisorio_70_anexo1.pdf"
            ),
            approval="Ato Decisorio CG 70/2025",
        ),
        SourceDocument(
            key="bch-2022-ppc",
            filename="bch-2022.pdf",
            url=(
                "https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/"
                "consepe_ato_decisorio_236_anexo.pdf"
            ),
            approval="Ato Decisorio ConsEPE 236/2022",
        ),
        SourceDocument(
            key="bch-2022-limited",
            filename="bch-2022-limited.pdf",
            url="https://prograd.ufabc.edu.br/cg/2023/BCH_Doc_Comp_I_v2.pdf",
            approval="Ato Decisorio CG 22/2022",
        ),
        SourceDocument(
            key="bcc-2023-ppc",
            filename="bcc-2023.pdf",
            url=(
                "https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/"
                "consepe_ato_decisorio_267_anexo.pdf"
            ),
            approval="Ato Decisorio ConsEPE 267/2023",
        ),
        SourceDocument(
            key="bcc-2023-limited",
            filename="bcc-2023-limited.pdf",
            url=(
                "https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/"
                "cg_ato-decisorio_044_anexo-01.pdf"
            ),
            approval="Ato Decisorio CG 44/2023",
        ),
    )
}

BCH_2022_MANDATORY = (
    ("BCL0306-15", "Biodiversidade: Interacoes entre Organismos e Ambiente", 3),
    ("BHO0001-19", "Introducao as Humanidades e as Ciencias Sociais", 2),
    ("BHO0002-19", "Introducao ao Pensamento Economico", 3),
    ("BHO0101-15", "Estado e Relacoes de Poder", 4),
    ("BHO0102-15", "Desenvolvimento e Sustentabilidade", 4),
    ("BHO1102-19", "Introducao a Economia", 3),
    ("BHO1335-15", "Formacao do Sistema Internacional", 4),
    ("BHP0001-15", "Etica e Justica", 4),
    ("BHP0202-15", "Pensamento Critico", 4),
    ("BHP0202-19", "Temas e Problemas em Filosofia", 3),
    ("BHQ0001-15", "Identidade e Cultura", 3),
    ("BHQ0002-15", "Estudos Etnico-Raciais", 3),
    ("BHQ0003-15", "Interpretacoes do Brasil", 4),
    ("BHQ0004-19", "Estudos de Genero", 3),
    ("BHQ0301-15", "Territorio e Sociedade", 4),
    ("BHS0005-19", "Praticas em Ciencias e Humanidades", 3),
    ("BIN0406-15", "Introducao a Probabilidade e a Estatistica", 3),
    ("BIQ0602-15", "Estrutura e Dinamica Social", 3),
    ("BIR0004-15", "Bases Epistemologicas da Ciencia Moderna", 3),
    ("BIR0603-15", "Ciencia, Tecnologia e Sociedade", 3),
    ("BIS0003-15", "Bases Matematicas", 4),
    ("BIS0005-15", "Bases Computacionais da Ciencia", 2),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_missing_sources(source_dir: Path) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=90) as client:
        for document in SOURCES.values():
            destination = source_dir / document.filename
            if destination.exists():
                continue
            response = client.get(document.url)
            response.raise_for_status()
            destination.write_bytes(response.content)


def extract_page_text(path: Path, page_indexes: list[int] | None = None) -> list[str]:
    reader = PdfReader(path)
    indexes = page_indexes if page_indexes is not None else list(range(len(reader.pages)))
    return [reader.pages[index].extract_text() or "" for index in indexes]


def normalize_row_block(value: str) -> str:
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    return " ".join(value.split())


def row_blocks(page_texts: list[str]) -> list[str]:
    blocks: list[str] = []
    for page_text in page_texts:
        matches = list(ROW_START_PATTERN.finditer(page_text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(page_text)
            blocks.append(normalize_row_block(page_text[match.start() : end]))
    return blocks


def parse_tp_rows(page_texts: list[str], *, expected_count: int) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        rf"^(?P<code>{CODE_PATTERN})\s+(?P<name>.+?)\s+"
        r"(?P<t>[0-9]+)\s+(?P<p>[0-9]+)(?:\s|$)"
    )
    for block in row_blocks(page_texts):
        match = pattern.match(block)
        if match is None:
            continue
        code = match.group("code")
        name = match.group("name").rstrip(" *")
        rows[code] = {
            "code": code,
            "name": name,
            "credits": int(match.group("t")) + int(match.group("p")),
        }
    if len(rows) != expected_count:
        raise ValueError(f"esperadas {expected_count} linhas, extraidas {len(rows)}")
    return list(rows.values())


def parse_bcc_mandatory_rows(page_texts: list[str]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        rf"^(?P<code>{CODE_PATTERN})\s+(?P<name>.+?)\s+"
        r"(?P<credits>[0-9]+)\s+\([0-9]+-[0-9]+-[0-9]+-[0-9]+\)"
    )
    for block in row_blocks(page_texts):
        match = pattern.match(block)
        if match is None:
            continue
        code = match.group("code")
        rows[code] = {
            "code": code,
            "name": match.group("name"),
            "credits": int(match.group("credits")),
        }
    if len(rows) != 27:
        raise ValueError(f"esperadas 27 obrigatorias especificas do BCC, extraidas {len(rows)}")
    return list(rows.values())


def source_metadata(source_dir: Path, source_keys: list[str]) -> list[dict[str, str]]:
    result = []
    for key in source_keys:
        document = SOURCES[key]
        result.append(
            {
                "key": key,
                "url": document.url,
                "approval": document.approval,
                "retrieved_on": "2026-07-15",
                "sha256": sha256(source_dir / document.filename),
            }
        )
    return result


def curriculum_subject(
    row: dict[str, Any],
    *,
    category: str,
    source_key: str,
    requirement_group: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"source_key": source_key}
    if requirement_group is not None:
        metadata["requirement_group"] = requirement_group
    return {
        "code": row["code"],
        "name": row["name"],
        "category": category,
        "category_source": "explicit",
        "ideal_term": None,
        "recommended_term": None,
        "credits": row["credits"],
        "valid_from": None,
        "valid_until": None,
        "metadata": metadata,
    }


def build_payload(
    *,
    course_code: str,
    course_name: str,
    version: str,
    admission_year_start: int,
    admission_year_end: int | None,
    mandatory: list[dict[str, Any]],
    mandatory_source: str,
    limited: list[dict[str, Any]],
    limited_source: str,
    source_dir: Path,
    mandatory_groups: dict[str, str] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    subjects: dict[str, dict[str, Any]] = {}
    for row in mandatory:
        subjects[row["code"]] = curriculum_subject(
            row,
            category="mandatory",
            source_key=mandatory_source,
            requirement_group=(mandatory_groups or {}).get(row["code"]),
        )
    for row in limited:
        if row["code"] in subjects:
            raise ValueError(f"disciplina simultaneamente obrigatoria e limitada: {row['code']}")
        subjects[row["code"]] = curriculum_subject(
            row,
            category="limited",
            source_key=limited_source,
        )
    return {
        "course": {"code": course_code, "name": course_name},
        "version": version,
        "admission_year_start": admission_year_start,
        "admission_year_end": admission_year_end,
        "valid_from": None,
        "valid_until": None,
        "unlisted_subject_category": "free",
        "materialize_unlisted_subjects": False,
        "metadata": {
            "official": True,
            "classification_only": True,
            "source_documents": source_metadata(
                source_dir, [mandatory_source, limited_source]
            ),
            "notes": notes or [],
        },
        "subjects": sorted(subjects.values(), key=lambda item: item["code"]),
        "requirements": [],
        "replace_existing": True,
    }


def build_curricula(source_dir: Path) -> dict[str, dict[str, Any]]:
    source_text = lambda key, pages=None: extract_page_text(  # noqa: E731
        source_dir / SOURCES[key].filename, pages
    )

    bct_2015_mandatory = parse_tp_rows(source_text("bct-2015-ppc", [38]), expected_count=26)
    bct_2015_limited = parse_tp_rows(source_text("bct-2015-limited"), expected_count=291)
    bct_2023_mandatory = parse_tp_rows(
        source_text("bct-2023-ppc", [55, 56]), expected_count=24
    )
    # The official annex has 307 rows, with NHI5011-13 repeated in both groups.
    bct_2023_limited = parse_tp_rows(source_text("bct-2023-limited"), expected_count=306)
    bch_2022_mandatory = [
        {"code": code, "name": name, "credits": credits}
        for code, name, credits in BCH_2022_MANDATORY
    ]
    if sum(item["credits"] for item in bch_2022_mandatory) != 72:
        raise ValueError("a transcricao das obrigatorias do BCH nao totaliza 72 creditos")
    bch_2022_limited = parse_tp_rows(source_text("bch-2022-limited"), expected_count=270)
    bcc_specific_mandatory = parse_bcc_mandatory_rows(source_text("bcc-2023-ppc", [53]))
    bcc_limited = parse_tp_rows(source_text("bcc-2023-limited"), expected_count=73)
    bcc_mandatory = [*bct_2023_mandatory, *bcc_specific_mandatory]
    bcc_groups = {
        item["code"]: "bct_base" for item in bct_2023_mandatory
    } | {item["code"]: "bcc_specific" for item in bcc_specific_mandatory}

    return {
        "bct-2015.json": build_payload(
            course_code="BCT",
            course_name="Bacharelado em Ciencia e Tecnologia",
            version="2015",
            admission_year_start=2015,
            admission_year_end=2022,
            mandatory=bct_2015_mandatory,
            mandatory_source="bct-2015-ppc",
            limited=bct_2015_limited,
            limited_source="bct-2015-limited",
            source_dir=source_dir,
        ),
        "bct-2023.json": build_payload(
            course_code="BCT",
            course_name="Bacharelado em Ciencia e Tecnologia",
            version="2023",
            admission_year_start=2023,
            admission_year_end=None,
            mandatory=bct_2023_mandatory,
            mandatory_source="bct-2023-ppc",
            limited=bct_2023_limited,
            limited_source="bct-2023-limited",
            source_dir=source_dir,
        ),
        "bch-2022.json": build_payload(
            course_code="BCH",
            course_name="Bacharelado em Ciencias e Humanidades",
            version="2022",
            admission_year_start=2022,
            admission_year_end=None,
            mandatory=bch_2022_mandatory,
            mandatory_source="bch-2022-ppc",
            limited=bch_2022_limited,
            limited_source="bch-2022-limited",
            source_dir=source_dir,
            notes=["Obrigatorias transcritas do quadro grafico do PPC 2022."],
        ),
        "bcc-2023.json": build_payload(
            course_code="BCC",
            course_name="Bacharelado em Ciencia da Computacao",
            version="2023",
            admission_year_start=2023,
            admission_year_end=None,
            mandatory=bcc_mandatory,
            mandatory_source="bcc-2023-ppc",
            limited=bcc_limited,
            limited_source="bcc-2023-limited",
            source_dir=source_dir,
            mandatory_groups=bcc_groups,
            notes=[
                "Inclui as obrigatorias do BCT que formam a base do BCC.",
                "Trabalho de Conclusao de Curso nao foi incluido por nao possuir sigla na tabela.",
            ],
        ),
    }


def write_curricula(curricula: dict[str, dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in curricula.items():
        destination = output_dir / filename
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera as matrizes oficiais usadas pelo projeto.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--skip-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.skip_download:
        download_missing_sources(args.source_dir)
    write_curricula(build_curricula(args.source_dir), args.output_dir)


if __name__ == "__main__":
    main()
