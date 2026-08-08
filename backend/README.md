# Backend

API FastAPI responsavel por:

- importar historico do SIGAA e atualizar o perfil academico persistido;
- importar ofertas de turma e curriculos;
- sincronizar snapshots de docentes do UFABC Next;
- calcular e persistir rankings de matricula.

## Pastas principais

```text
backend/
  app/
    api/
    integrations/
    models/
    offers/
    ranking/
    students/
    teachers/
  alembic/
  scripts/
  tests/
```

## Executando localmente

Com o ambiente Python configurado:

```bash
python -m pytest
```

Migracoes:

```bash
alembic upgrade head
```

## Dominios

- `app/students/`: leitura do historico, parser de PDF e persistencia do perfil.
- `app/ranking/`: interface do ranking.
- `app/offers/`: fachada de importacao de ofertas.
- `app/teachers/`: fachada de estatisticas de docentes.
- `app/integrations/ufabc_next/`: fachada da integracao com o Next.

Parte da implementacao ainda vive em `app/services/` por compatibilidade durante a
reorganizacao, mas a superficie nova do projeto ja esta agrupada por dominio.

## Contrato do v1

Fluxo do aluno:

1. `POST /students/history/pdf`
2. `GET /students/{id}`
3. `POST /rankings/sections`
4. `GET /rankings/{id}`

Fluxos internos:

- ofertas em `/admin/imports/...`
- curriculos em `/admin/...`
- operacao estatistica em `/admin/statistics/...`
- status do Next em `/admin/integrations/ufabc-next/status`

## Observacao sobre o Next

No v1 o Next serve apenas para enriquecer dados de docentes. Qualquer extensao futura
para dados de alunos ou requisicoes deve ficar fora do fluxo principal ate existir desenho
de produto e governanca de dados apropriados.
