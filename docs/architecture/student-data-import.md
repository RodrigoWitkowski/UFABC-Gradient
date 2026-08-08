# Fluxo de importacao do historico

## Objetivo

No v1 o historico do SIGAA e a unica fonte oficial do perfil academico do aluno.
O app nao oferece edicao manual de dados academicos.

## O que e extraido

Da importacao do PDF salvamos apenas o que afeta o produto:

- RA;
- nome exibido, quando presente;
- ano de ingresso;
- turno de ingresso;
- campus;
- CA;
- CR;
- creditos acumulados;
- disciplinas concluidas;
- disciplinas em andamento;
- vinculo principal e vinculos adicionais identificados pela matriz;
- CP por vinculo;
- metadados operacionais da importacao, como hash e data de emissao.

O PDF bruto nao e persistido.

## Regras do fluxo

1. O aluno envia o PDF em `POST /students/history/pdf`.
2. O backend faz parsing e normalizacao.
3. O perfil e localizado preferencialmente pelo `student_id` informado ou pelo RA extraido.
4. O perfil persistido e atualizado com os dados do historico.
5. Uma nova importacao do mesmo aluno substitui os dados academicos anteriores.
6. O limite de creditos continua sendo derivado de `ceil(20 + 2 * CA)`.

## O que nao entra no v1

- edicao manual de perfil pelo aluno;
- importacao automatica de historico por Next;
- leitura de cookies, senha ou sessao do SIGAA;
- dependencia de HTML da matricula para montar o perfil.

## Preferencias de ranking

Preferencias de filtro e ordenacao, como campus aceito e evitar sexta-feira, nao fazem
parte do perfil academico oficial. No frontend atual elas ficam no cliente e entram apenas
na requisicao do ranking.
