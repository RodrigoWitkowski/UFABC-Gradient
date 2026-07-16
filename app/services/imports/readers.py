from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pandas import DataFrame

from app.services.imports.column_mapping import mapping_score

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv"}


@dataclass(frozen=True, slots=True)
class OfferTable:
    dataframe: DataFrame
    source_sheet: str | None


def _read_csv(path: Path) -> DataFrame:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
                sep=None,
                engine="python",
            )
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise ValueError("nao foi possivel ler o CSV")


def read_offer_table(path: Path, sheet_name: str | None = None) -> OfferTable:
    extension = path.suffix.casefold()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"formato nao suportado: {extension}")
    if extension == ".csv":
        return OfferTable(_read_csv(path), None)

    with pd.ExcelFile(path) as excel:
        selected_sheet = sheet_name
        if selected_sheet is None:
            candidates: list[tuple[int, str]] = []
            for candidate in excel.sheet_names:
                headers = list(pd.read_excel(excel, sheet_name=candidate, nrows=0).columns)
                valid, score = mapping_score(headers)
                if valid:
                    candidates.append((score, candidate))
            if not candidates:
                raise ValueError("nenhuma aba contem as colunas obrigatorias de oferta")
            selected_sheet = max(candidates)[1]
        if selected_sheet not in excel.sheet_names:
            raise ValueError(f"aba nao encontrada: {selected_sheet}")

        dataframe = pd.read_excel(
            excel,
            sheet_name=selected_sheet,
            dtype=str,
            keep_default_na=False,
        )
    return OfferTable(dataframe, selected_sheet)
