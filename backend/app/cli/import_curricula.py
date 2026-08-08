from app.db.session import SessionLocal
from app.services.official_curricula import import_official_curricula


def main() -> None:
    with SessionLocal() as session:
        results = import_official_curricula(session)
        session.commit()
    for result in results:
        print(
            f"{result.course_code} {result.version}: "
            f"{result.explicit_subjects} classificacoes explicitas"
        )


if __name__ == "__main__":
    main()
