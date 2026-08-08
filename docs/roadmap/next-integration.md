# Integracao com o UFABC Next

## Escopo confirmado para o v1

No v1 o UFABC Next participa apenas como fonte complementar para popular a base local de
docentes e notas associadas as turmas importadas.

Esse uso e operacional, nao parte da navegacao do aluno:

- a oferta do quadrimestre e importada primeiro;
- a sincronizacao com o Next roda depois, de forma administrativa;
- o ranking consome apenas os snapshots locais ja persistidos.

## O que fica fora do v1

As ideias abaixo continuam importantes, mas ficam somente como intencao de produto e
arquitetura:

- usar dados anonimizados de alunos para melhorar o modelo estatistico;
- usar dados de requisicoes de matricula para calibrar melhor a probabilidade de vaga;
- usar dados adicionais do Next como enriquecimento de vinculos.

Nada disso deve aparecer como dependencia funcional do v1.

## Condicoes para a proxima fase

Antes de ampliar o uso do Next alem de docentes, o projeto precisa definir:

- base legal e governanca dos dados;
- granularidade e anonimização minima;
- estrategia de cache e atualizacao;
- contrato claro entre dados do Next e dados oficiais importados do SIGAA.
