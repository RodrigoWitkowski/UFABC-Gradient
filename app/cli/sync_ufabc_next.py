import argparse

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
    parser.add_argument("--review-limit", type=int, default=10)
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    options = UfabcNextSyncRequest(
        season=args.season,
        include_teacher_reviews=args.include_teacher_reviews,
        include_subject_reviews=args.include_subject_reviews,
        review_limit=args.review_limit,
        force_refresh=args.force_refresh,
    )
    with SessionLocal() as session:
        client = UfabcNextClient(get_settings(), UfabcNextDatabaseCache(session))
        try:
            run = UfabcNextSyncService(session, client).sync(options)
        finally:
            client.close()
    print(UfabcNextSyncRunRead.model_validate(run).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
