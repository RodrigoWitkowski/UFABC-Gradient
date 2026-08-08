# Gradient UFABC

Aplicacao web para alunos de graduacao da UFABC planejarem matricula com foco em
probabilidade de conseguir vaga.

## Escopo do v1

O v1 foi reduzido ao fluxo real do produto:

- aluno importa o historico do SIGAA em PDF;
- backend extrai e persiste o perfil academico;
- equipe importa a oferta do quadrimestre;
- equipe sincroniza dados de docentes do UFABC Next para enriquecer a base local;
- aluno visualiza o ranking de turmas com probabilidade, nota de docentes e explicacoes.

O aluno nao cria perfil manualmente e nao edita RA, turno, campus, ano de ingresso,
CA, CP ou vinculos. O historico importado e a fonte oficial desses dados.

## Estrutura do repositorio

```text
backend/
  app/
  alembic/
  scripts/
  tests/

frontend/
  assets/
  src/
  index.html

docs/
  architecture/
  domain/
  roadmap/

samples/
```

## Rodando localmente

Subir aplicacao e banco:

```bash
docker compose up --build
```

Servicos padrao:

- app: `http://localhost:8000`
- postgres: `localhost:5432`

Para rodar testes locais do backend:

```bash
cd backend
python -m pytest
```

## Superficie da API

Fluxo publico do aluno:

- `POST /students/history/pdf`
- `GET /students/{id}`
- `GET /terms`
- `GET /terms/{term}/sections`
- `POST /rankings/sections`
- `GET /rankings/{id}`
- `GET /health`

Fluxo administrativo/interno:

- `POST /admin/imports/offers`
- `GET /admin/imports/{id}`
- `POST /admin/curriculums/import`
- `GET /admin/courses`
- `GET /admin/courses/{course_id}/curriculums/{version}`
- `POST /admin/statistics/rebuild`
- `GET /admin/statistics/status`
- `POST /admin/statistics/teachers/evaluate`
- `GET /admin/integrations/ufabc-next/status`
- `POST /admin/students`
- `PUT /admin/students/{id}/academic-profile`
- `POST /admin/rankings/{id}/rerank`

Os endpoints administrativos existem para importacao, suporte e operacao interna. Eles
nao fazem parte da navegacao normal do aluno.

## Next no v1

No v1 o UFABC Next entra apenas como enriquecimento de docentes e notas, sempre para
popular a base local depois que a oferta ja foi importada.

Nao usamos Next no v1 para:

- dados cadastrais de alunos;
- historico escolar;
- requisicoes de matricula.

O roadmap dessa integracao futura esta em [docs/roadmap/next-integration.md](docs/roadmap/next-integration.md).

## Documentacao

- [Arquitetura do fluxo de historico](docs/architecture/student-data-import.md)
- [Regras de matricula e prioridade](docs/domain/ufabc-rules.md)
- [Roadmap da integracao com o Next](docs/roadmap/next-integration.md)
