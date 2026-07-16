# UFABC Class Ranking

As definicoes e decisoes de dominio sobre disciplinas obrigatorias, de opcao limitada e
livres estao registradas em [REGRAS_UFABC.md](REGRAS_UFABC.md).

Backend incremental para importar e normalizar ofertas de turmas da UFABC, manter matrizes
curriculares versionadas e, nas próximas fases, calcular rankings explicáveis. Esta entrega não
inclui o ranking, a integração com o UFABC Next nem o gerador de grades.

## O que já funciona

- importação configurável de XLSX, XLS e CSV;
- detecção automática da aba de oferta por cabeçalhos;
- preservação do arquivo original por SHA-256 e reprocessamento do mesmo arquivo;
- termos, disciplinas, docentes, aliases, turmas e horários normalizados;
- horários armazenados como encontros separados, incluindo frequência semanal e quinzenal;
- revisão por turma e comparação de docentes, encontros, salas, campus e vagas;
- erros e avisos por linha sem interromper as demais ofertas;
- cursos, matrizes versionadas, requisitos e classificação curricular por curso;
- perfis acadêmicos com múltiplos cursos, matriz por curso, CR, CP, IK e curso principal;
- disciplinas concluídas e em andamento, preferências e restrições do aluno;
- sugestão de matriz pelo ano de ingresso, com possibilidade de escolha manual;
- API FastAPI, PostgreSQL, Alembic e testes automatizados.

Na planilha `matriculas_2026_3_turmas_ofertadas.xlsx`, o importador seleciona automaticamente a
aba ` turmas sistema atual`. Abas derivadas ou auxiliares não são tratadas como fonte de oferta.

## Executar com Docker

```bash
docker compose up --build
```

A API fica em `http://localhost:8000` e a documentação interativa em
`http://localhost:8000/docs`. O container da API aplica as migrations antes de iniciar.

Configuração local opcional:

```bash
cp .env.example .env
```

## Importar a planilha

O quadrimestre é inferido do nome do arquivo ou da aba. Também pode ser informado explicitamente.

```bash
curl -X POST http://localhost:8000/imports/offers \
  -F "file=@matriculas_2026_3_turmas_ofertadas.xlsx" \
  -F "term=2026:3"
```

Para uma planilha com cabeçalhos diferentes, envie o mapeamento canônico:

```bash
curl -X POST http://localhost:8000/imports/offers \
  -F "file=@oferta.csv" \
  -F "term=2026:3" \
  -F 'column_mapping={"section_code":"cod_turma","subject_code":"cod_disciplina","subject_name":"nome","theory_schedule":"horario"}'
```

Consultar o lote e as turmas:

```bash
curl http://localhost:8000/imports/UUID_DO_LOTE
curl "http://localhost:8000/terms/2026:3/sections?limit=100"
```

## Importar uma matriz curricular

As quatro matrizes oficiais iniciais ja acompanham o projeto. Com os containers
reconstruidos, importe BC&T 2015, BC&T 2023, BC&H 2022 e BCC 2023 com:

```bash
docker compose exec api python -m app.cli.import_curricula
```

O comando pode ser repetido: ele atualiza as mesmas versoes sem duplicar registros.
Para auditar ou regenerar os JSON a partir dos PDFs oficiais armazenados localmente:

```bash
.venv/Scripts/python scripts/build_curriculum_data.py --skip-download
```

Esse gerador acessa apenas documentos publicos oficiais da UFABC. Ele nao consulta a
API do UFABC Next.

```bash
curl -X POST http://localhost:8000/curriculums/import \
  -H "Content-Type: application/json" \
  -d '{
    "course": {"code": "BCC", "name": "Bacharelado em Ciência da Computação"},
    "version": "2025",
    "admission_year_start": 2025,
    "subjects": [{
      "code": "MCCC001-23",
      "name": "Algoritmos",
      "category": "mandatory",
      "category_source": "explicit",
      "ideal_term": 3,
      "credits": 4
    }]
  }'
```

A categoria fica em `course_curriculum_subjects`, nunca em `subjects`. Assim, a mesma disciplina
pode ser obrigatória em uma matriz e limitada ou livre em outra.

Listar cursos e matrizes disponíveis:

```bash
curl http://localhost:8000/courses
curl http://localhost:8000/courses/UUID_DO_CURSO/curriculums
```

## Perfil acadêmico

Primeiro crie o perfil básico:

```bash
curl -X POST http://localhost:8000/students \
  -H "Content-Type: application/json" \
  -d '{
    "display_name": "Aluno",
    "admission_year": 2025,
    "admission_shift": "Noturno",
    "campus": "SA"
  }'
```

Depois associe cursos, matrizes e histórico acadêmico. Quando `curriculum_version` não é enviado,
o sistema sugere a matriz compatível com o ano de ingresso.

```bash
curl -X PUT http://localhost:8000/students/UUID_DO_ALUNO/academic-profile \
  -H "Content-Type: application/json" \
  -d '{
    "admission_year": 2025,
    "admission_shift": "Noturno",
    "campus": "SA",
    "cr": 3.1,
    "course_strategy": "weighted_courses",
    "courses": [
      {"course_code": "BCT", "is_primary": false, "weight": 0.4, "cp": 0.72, "ik": 0.68},
      {"course_code": "BCC", "is_primary": true, "weight": 0.6, "cp": 0.38, "ik": 0.41}
    ],
    "completed_subjects": [],
    "in_progress_subjects": [{"code": "MCCC001-23", "term": "2026:3"}],
    "preferences": {
      "hard_constraints": {"allowed_campuses": ["SA"]},
      "soft_preferences": {"prefer_night": 1.0}
    }
  }'
```

Consultar o perfil e a classificação de uma disciplina em cada curso:

```bash
curl http://localhost:8000/students/UUID_DO_ALUNO
curl http://localhost:8000/students/UUID_DO_ALUNO/subjects/MCCC001-23/classifications
```

## Desenvolvimento local

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

Com PostgreSQL disponível e `DATABASE_URL` configurada:

```bash
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn app.main:app --reload
.venv/Scripts/pytest
.venv/Scripts/ruff check app tests
```

Os arquivos originais são gravados em `IMPORT_STORAGE_PATH` e não devem ser versionados. Não há
credenciais do SIGAA nem chamadas ao UFABC Next nesta fase.
