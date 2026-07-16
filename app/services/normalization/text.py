import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any

WHITESPACE_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
TERM_RE = re.compile(r"(?<!\d)(20\d{2})\s*[:._-]\s*([1-3])(?!\d)")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "null"}:
        return None
    return WHITESPACE_RE.sub(" ", text)


def strip_accents(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )


def normalize_text(value: Any) -> str:
    text = clean_text(value) or ""
    text = strip_accents(text).casefold()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_header(value: Any) -> str:
    normalized = normalize_text(value)
    return re.sub(r"\s+\d+$", "", normalized)


def normalize_code(value: Any) -> str | None:
    text = clean_text(value)
    if text is None:
        return None
    return re.sub(r"\s+", "", strip_accents(text).upper())


def parse_optional_int(value: Any) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    try:
        return int(float(text.replace(",", ".")))
    except ValueError as exc:
        raise ValueError(f"valor inteiro invalido: {text}") from exc


def normalize_term_code(value: str) -> str:
    match = TERM_RE.search(value)
    if match is None:
        raise ValueError(f"quadrimestre nao identificado em: {value}")
    return f"{match.group(1)}:{match.group(2)}"


def infer_term_code(*candidates: str | Path | None) -> str:
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            return normalize_term_code(str(candidate))
        except ValueError:
            continue
    raise ValueError("informe o quadrimestre no formato AAAA:N")


def generated_course_code(name: str) -> str:
    normalized = normalize_text(name)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10].upper()
    return f"AUTO-{digest}"
