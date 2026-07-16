import argparse
import json

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.schemas.ufabc_next import UfabcNextSyncRequest, UfabcNextSyncRunRead
from app.services.ufabc_next import UfabcNextClient, UfabcNextSyncService
from app.services.ufabc_next.cache import UfabcNextDatabaseCache


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sincroniza e persiste dados publicos do UFABC Next."
    )
    parser.add_argument("--season", required=True, help="Quadrimestre no formato 2026:3")
    parser.add_argument("--include-teacher-reviews", action="store_true")
    parser.add_argument("--include-subject-reviews", action="store_true")
    parser.add_argument("--review-limit", type=int, default=25)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument(
        "--confirm-external-requests",
        action="store_true",
        help="Confirma conscientemente que esta execucao pode chamar a API do UFABC Next.",
    )
    parser.add_argument(
        "--progress-only",
        action="store_true",
        help="Mostra o progresso salvo sem fazer requisicoes externas.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.progress_only and not args.confirm_external_requests:
        raise SystemExit(
            "Use --confirm-external-requests para autorizar o lote ou --progress-only "
            "para consultar apenas o banco local."
        )
    options = UfabcNextSyncRequest(
        season=args.season,
        include_teacher_reviews=args.include_teacher_reviews,
        include_subject_reviews=args.include_subject_reviews,
        review_limit=args.review_limit,
        force_refresh=args.force_refresh,
    )
    with SessionLocal() as session:
        client = UfabcNextClient(get_settings(), UfabcNextDatabaseCache(session))
        service = UfabcNextSyncService(session, client)
        if args.progress_only:
            print(json.dumps(service.review_progress(), ensure_ascii=False, indent=2))
            client.close()
            return
        print(
            "Gradient: iniciando lote controlado; cada chamada e resposta aparecera "
            "no request_log final.",
            flush=True,
        )
        try:
            run = service.sync(options)
        finally:
            client.close()
        result = UfabcNextSyncRunRead.model_validate(run).model_dump(mode="json")
        result["review_progress"] = service.review_progress()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
