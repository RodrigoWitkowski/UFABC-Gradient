# Gradient

As definicoes e decisoes de dominio sobre disciplinas obrigatorias, de opcao limitada e
livres estao registradas em [REGRAS_UFABC.md](REGRAS_UFABC.md).
O estudo de importacao do historico e da pagina de matricula esta em
[IMPORTACAO_DADOS_ALUNO.md](IMPORTACAO_DADOS_ALUNO.md).

Backend incremental para importar e normalizar ofertas de turmas da UFABC, manter matrizes
curriculares versionadas, sincronizar dados públicos do UFABC Next e calcular indicadores
estatísticos e rankings explicáveis. A interface para alunos já está disponível; o gerador
de grades completas ainda não foi implementado.

## O que já funciona

- importação configurável de XLSX, XLS e CSV;
- detecção automática da aba de oferta por cabeçalhos;
- preservação do arquivo original por SHA-256 e reprocessamento do mesmo arquivo;
- termos, disciplinas, docentes, aliases, turmas e horários normalizados;
- horários armazenados como encontros separados, incluindo frequência semanal e quinzenal;
- revisão por turma e comparação de docentes, encontros, salas, campus e vagas;
- erros e avisos por linha sem interromper as demais ofertas;
- cursos, matrizes versionadas, requisitos e classificação curricular por curso;
- interface web local para perfil, filtros e ranking de turmas;
- perfis acadêmicos com RA, limite total de créditos, múltiplos cursos, matriz por curso,
  CR, CA, CP, IK e curso principal;
- disciplinas concluídas e em andamento, preferências e restrições do aluno;
- importação substitutiva do Histórico Escolar do SIGAA por RA, sem guardar o PDF bruto;
- sugestão de matriz pelo ano de ingresso, com possibilidade de escolha manual;
- sincronização manual de componentes e reviews do UFABC Next, com cache e auditoria;
- estatísticas gerais e por disciplina dos docentes, com ajuste bayesiano e amostra explícita;
- ranking persistido de turmas com decomposição, explicações e reranking configurável;
- restrições rígidas e preferências flexíveis de horário, turno, campus e docentes;
- API FastAPI, PostgreSQL, Alembic e testes automatizados.

Na planilha `matriculas_2026_3_turmas_ofertadas.xlsx`, o importador seleciona automaticamente a
aba ` turmas sistema atual`. Abas derivadas ou auxiliares não são tratadas como fonte de oferta.

## Executar com Docker

```bash
docker compose up --build
```

Depois da inicialização, abra `http://localhost:8000` para usar a interface web. A página
permite criar o perfil acadêmico, selecionar BCT, BCH e BCC, aplicar filtros e consultar o
ranking. O container da API aplica as migrations antes de iniciar.

A documentação interativa existe, mas fica desativada por padrão. Para desenvolvimento,
defina `API_DOCS_ENABLED=true` e abra `http://localhost:8000/docs`.

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

## Sincronizar o UFABC Next

A sincronização só pode ser iniciada pelo CLI administrativo dentro do container. Não existe
um endpoint HTTP público capaz de disparar chamadas ao Next. Para importar componentes e um
lote de até 25 docentes:

```powershell
docker compose exec api python -m app.cli.sync_ufabc_next --season 2026:3 --include-teacher-reviews --review-limit 25 --confirm-external-requests
```

Cada nova execução seleciona primeiro docentes que ainda não possuem snapshot. Assim, repetir
o comando avança para o lote seguinte em vez de consultar os mesmos IDs. O JSON exibido no
terminal inclui `review_progress`, com totais concluídos e pendentes. A resposta de docente já
contém estatísticas gerais e por disciplina; por isso, o preenchimento inicial não precisa usar
`--include-subject-reviews`.

Para consultar o progresso sem acessar o Next:

```powershell
docker compose exec api python -m app.cli.sync_ufabc_next --season 2026:3 --progress-only
```

Consultar a execução mais recente ou uma execução específica:

```bash
curl http://localhost:8000/sync/ufabc-next/status
curl "http://localhost:8000/sync/ufabc-next/status?run_id=UUID_DA_EXECUCAO"
```

Cada status informa chamadas remotas, cache hits, HTTP retornado, itens recebidos,
correspondências e avisos. Por segurança, a sincronização é sequencial, espera no mínimo cinco
segundos entre chamadas, usa lotes de 25, não repete automaticamente uma chamada com erro e
interrompe a execução ao atingir 30 chamadas remotas ou receber HTTP `429`. Apenas uma execução
pode permanecer ativa. Cada snapshot de docente é confirmado no banco antes da próxima chamada,
portanto um erro no fim do lote não perde o progresso anterior.

O cache de componentes dura 24 horas e o de reviews, 90 dias. Componentes vindos do cache são
usados para descobrir os IDs sem duplicar todos os snapshots de turmas. Ranking, reranking e
testes estatísticos nunca consultam o Next: usam somente dados locais.

A integração pode ser desligada com `UFABC_NEXT_ENABLED=false`. Timeout, retries, backoff,
intervalo mínimo e TTLs são configurados pelas variáveis `UFABC_NEXT_*` do `.env.example`.
O sistema não persiste a lista de alunos matriculados, RA, login, e-mail, SIAPE ou chaves
internas recebidas nos payloads.

O projeto não agenda chamadas automaticamente. Para a carga inicial, execute no máximo um lote
por hora. Com os 545 docentes identificados em `2026:3`, são necessárias aproximadamente 546
chamadas no total: uma de componentes e uma para cada docente, divididas em 22 lotes.

## Estatísticas de docentes

Depois de sincronizar reviews, reconstrua as tabelas derivadas. Esse endpoint lê somente os
snapshots já salvos no PostgreSQL e não faz chamadas ao UFABC Next:

```bash
curl -X POST http://localhost:8000/statistics/rebuild \
  -H "Content-Type: application/json" \
  -d '{"prior_weight":20}'
curl http://localhost:8000/statistics/status
```

O sistema usa as contagens de conceitos `A`, `B`, `C`, `D`, `F` e `O`. O valor `count` é a
amostra; o campo auxiliar `amount` do UFABC Next não é usado como denominador. Para evitar que
três avaliações perfeitas superem automaticamente centenas de avaliações boas, a taxa ajustada
é calculada assim:

```text
taxa ajustada = (contagem + peso do prior * taxa de referência)
                / (tamanho da amostra + peso do prior)
```

O `prior_weight` padrão é 20. Quanto menor a amostra, maior a aproximação à distribuição de
referência; com amostras grandes, o resultado se aproxima da taxa observada. A resposta sempre
expõe contagens, amostra, confiança, taxas brutas, taxas ajustadas e pesos usados.

Exemplo de avaliação combinando o histórico geral e o histórico na disciplina:

```bash
curl -X POST http://localhost:8000/statistics/teachers/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "teacher_id":"UUID_DO_DOCENTE",
    "subject_id":"UUID_DA_DISCIPLINA",
    "mode":"blended",
    "metric":"ab_rate",
    "use_bayesian_adjustment":true
  }'
```

Modos disponíveis:

- `all_history`: usa todo o histórico conhecido do docente;
- `same_subject`: usa somente o histórico do docente naquela disciplina;
- `blended`: combina os dois, aumentando o peso específico conforme sua amostra;
- `recent_history`: reservado, mas atualmente retorna indisponível porque os snapshots públicos
  não separam as avaliações por quadrimestre.

As métricas de pontuação são `a_rate`, `ab_rate`, `failure_rate`, `fo_rate` e `mean_grade`.
Para `failure_rate` e `fo_rate`, uma taxa menor gera pontuação maior. Os pesos padrão da média
são `A=4`, `B=3`, `C=2`, `D=1`, `F=0` e `O=0`.

## Ranking de turmas

O ranking usa um perfil acadêmico já cadastrado e as turmas ativas de um quadrimestre:

```bash
curl -X POST http://localhost:8000/rankings/sections \
  -H "Content-Type: application/json" \
  -d '{
    "term":"2026:3",
    "student_id":"UUID_DO_ALUNO",
    "result_limit":100
  }'
```

Cada resultado representa uma turma específica e retorna seis notas separadas:

- relevância curricular para cada curso e matriz do aluno;
- estatística dos docentes;
- disponibilidade estimada por vagas e demanda;
- compatibilidade básica de turno;
- carga da disciplina;
- compatibilidade de campus.

A nota de compatibilidade `N` e todos os seus componentes ficam entre 0 e 100. A configuração
padrão usa a seguinte soma ponderada:

```text
N = 0,35 R + 0,25 D + 0,25 V + 0,10 H + 0,05 C + 0,00 K
```

Os símbolos representam:

- `R`, relevância curricular: obrigatória no quadrimestre ideal = 100; obrigatória = 90;
  opção limitada = 60; livre = 30; não aplicável ou sem classificação = 0. Se o aluno possui
  vários cursos, essas notas são combinadas pela estratégia escolhida no perfil.
- `D`, docentes: média das notas dos professores da turma. Por padrão é usada a taxa ajustada
  de conceitos A ou B. Para cada conceito `g`, `p̃_g = (n_g + 20q_g) / (n + 20)`, em que `n_g`
  é a contagem observada, `n` é a amostra e `q_g` é a taxa de referência. O histórico específico
  da disciplina recebe peso `r = n_s / (n_s + 20)` e é combinado ao histórico geral por
  `p_AB = r p_AB,s + (1-r) p_AB,g`. Finalmente, `D = 100 p_AB`.
- `V`, disponibilidade: `V = 100 min(vagas / solicitações, 1)`. Se a demanda ainda não existe,
  é usada a nota neutra 50. Esse valor não é uma promessa pessoal de matrícula.
- `H`, horário: 100 quando o turno coincide com o do aluno, 25 quando difere e 50 quando falta
  informação. Preferências opcionais de dias e horários entram como média ponderada adicional.
- `C`, carga: `C = max(100 - 15 max(créditos - 6, 0), 0)`. Até seis créditos recebe 100.
- `K`, campus: 100 para campus preferido, 25 para outro e 50 sem informação. Quando o aluno
  fornece uma lista explícita de campi preferidos, um campus fora dela recebe 0. O peso padrão
  de `K` é zero, então campus não altera `N` enquanto o aluno não configurar pesos diferentes.

Disciplinas concluídas ou em andamento são excluídas por padrão. Uma disciplina ausente das
listas de obrigatórias e limitadas usa a regra `free` da matriz. Quando a demanda é zero, ela
é tratada como ainda indisponível, e não como ausência de concorrência.

A porcentagem atual é apenas a disponibilidade agregada `vagas / solicitações`, com confiança
baixa. Cada turma também informa a análise individual da Resolução ConsEPE 260/2023: curso,
turno, CP e CA, nessa ordem. Campus continua sendo filtro ou preferência logística; CR e IK não
participam dessa classificação. `personalized_probability` permanece vazio porque transformar
a prioridade em porcentagem exige conhecer ou estimar a distribuição dos demais solicitantes.
O resultado nunca deve ser interpretado como garantia de matrícula.

Consultar um ranking salvo ou criar outro com pesos diferentes:

```bash
curl http://localhost:8000/rankings/UUID_DO_RANKING

curl -X POST http://localhost:8000/rankings/UUID_DO_RANKING/rerank \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "weights": {
        "curriculum_relevance":1,
        "teacher":0,
        "seat_probability":0,
        "schedule_preference":0,
        "workload":0,
        "campus":0
      }
    }
  }'
```

O reranking cria um novo registro e preserva o anterior para comparação. Nenhuma dessas
operações importa planilhas ou faz chamadas externas.

### Filtros e preferências

As preferências salvas no perfil são usadas quando `hard_constraints` e `soft_preferences`
não aparecem na configuração do ranking. Quando aparecem, substituem integralmente as
preferências salvas. Isso permite experimentar sem alterar o perfil.

Restrições rígidas eliminam a turma:

```json
{
  "config": {
    "hard_constraints": {
      "allowed_shifts": ["Noturno"],
      "excluded_weekdays": ["friday"],
      "allowed_campuses": ["SA"],
      "earliest_start_time": "19:00",
      "latest_end_time": "23:00",
      "excluded_teacher_ids": [],
      "excluded_subject_ids": [],
      "max_subject_credits": 6
    }
  }
}
```

Os dias também podem ser números: segunda é `0`, sexta é `4` e domingo é `6`.
`max_subject_credits` limita uma disciplina individual; o limite de créditos da grade inteira
será responsabilidade do gerador de grades.

Preferências flexíveis não eliminam turmas, apenas modificam as notas de turno e campus:

```json
{
  "config": {
    "soft_preferences": {
      "prefer_night": 1.0,
      "avoid_friday": 0.8,
      "avoid_early_classes": 1.0,
      "preferred_earliest_start": "19:00",
      "prefer_fewer_campus_days": 0.6,
      "preferred_campuses": ["SA"]
    }
  }
}
```

As intensidades variam de `0` a `1`. Preferências que dependem da combinação de várias
turmas, como evitar janelas entre aulas, serão calculadas na etapa de geração de grades.

## Perfil acadêmico

Primeiro crie o perfil básico:

```bash
curl -X POST http://localhost:8000/students \
  -H "Content-Type: application/json" \
  -d '{
    "ra": "11234567890",
    "display_name": "Aluno",
    "admission_year": 2025,
    "admission_shift": "Noturno",
    "campus": "SA"
  }'
```

Importar ou substituir o histórico do aluno. RA, CA, CR, disciplinas e limite total de
créditos são extraídos ou calculados nesse processo:

```bash
curl -X POST http://localhost:8000/students/history/pdf \
  -F "file=@historico.pdf" \
  -F "student_id=UUID_DO_ALUNO"
```

Depois ajuste cursos, matrizes e preferências. Quando `curriculum_version` não é enviado,
o sistema sugere a matriz compatível com o ano de ingresso.

```bash
curl -X PUT http://localhost:8000/students/UUID_DO_ALUNO/academic-profile \
  -H "Content-Type: application/json" \
  -d '{
    "ra": "11234567890",
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

As planilhas originais de oferta são gravadas em `IMPORT_STORAGE_PATH` e não devem ser
versionadas. O PDF bruto do histórico é descartado após a extração. Não há credenciais
do SIGAA ou do UFABC Next armazenadas pelo projeto.
