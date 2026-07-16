# Importacao de dados do aluno

Este documento registra as decisoes sobre o historico do SIGAA e o HTML do sistema de
matriculas. O importador de PDF esta ativo; o importador de HTML ainda nao foi implementado.

## Historico do SIGAA em PDF

O PDF analisado possui texto extraivel e estrutura suficiente para recuperar:

- RA, curso, matriz, campus e turno de ingresso;
- CR, CA, CP, IK e coeficientes relacionados;
- disciplina, codigo, quadrimestre, situacao, conceito, categoria e creditos;
- disciplinas em andamento;
- convalidacoes e equivalencias.

O arquivo tambem contem dados pessoais que o ranking nao precisa, como documentos de
identidade e data de nascimento. O fluxo implementado e:

1. o aluno envia o PDF;
2. o servidor extrai somente os dados academicos;
3. os registros validados sao associados ao perfil pelo RA;
4. CA, CR, CP e IK sao atualizados e o limite e calculado por `ceil(20 + 2 * CA)`;
5. uma nova importacao do mesmo RA substitui o historico anterior;
6. o PDF bruto e descartado, mantendo apenas hash, data de emissao e resultado da
   importacao para evitar duplicidade.

As situacoes aprovadas, dispensadas ou incorporadas devem marcar o componente ou sua
equivalencia como concluido. `MATR` deve entrar como disciplina em andamento. Reprovacoes
continuam elegiveis para recomendacao e nao podem ser tratadas como conclusao.

A extracao precisa validar codigos e totais, pois quebras de linha do PDF podem separar o
codigo da turma, o codigo da disciplina ou partes do nome. A importacao nao deve ser salva
silenciosamente quando houver linhas ambiguas.

## Extensao do UFABC Next

A descricao publica da extensao informa que ela faz scraping do SIGAA e que versoes
recentes passaram a usar cookies para consumir o historico. Isso nao demonstra a existencia
de uma API publica de historico para terceiros. Nao foi localizado um repositorio publico
do codigo atual da extensao.

Para este projeto, importar o PDF e mais seguro do que pedir cookie ou senha do SIGAA. Uma
integracao com o Next so deve ser considerada se os mantenedores publicarem e autorizarem
um endpoint apropriado. Toda requisicao futura ao Next deve ser manual, limitada, armazenada
em cache e anunciada antes de ser executada.

## HTML do sistema de matriculas

O HTML fornecido e uma fonte util para a demanda porque contem vagas, solicitacoes,
horarios, T-P-I e docentes de teoria e pratica. A amostra possui cerca de 1.100 ofertas,
compativel com a ordem de grandeza da planilha importada.

O HTML bruto nao pode ser armazenado nem enviado diretamente ao backend: ele contem RA e
tokens de autenticidade/CSRF da sessao. A implementacao recomendada e um importador no
navegador que:

1. recebe o HTML colado ou selecionado pelo aluno;
2. remove tokens, RA e qualquer campo de sessao antes de transmitir dados;
3. envia somente JSON normalizado de turma, vagas, solicitacoes, docentes e horarios;
4. registra `captured_at` como horario da captura, sem chama-lo de atualizacao oficial;
5. deduplica snapshots por quadrimestre, turma e hash do conteudo sanitizado.

O importador sera somente leitura e nunca fara uma solicitacao de matricula em nome do
aluno. As categorias exibidas nessa pagina podem depender da matriz selecionada e nao devem
sobrescrever as classificacoes curriculares obtidas dos PPCs oficiais.

## Decisao atual

A importacao do HTML de matricula e tecnicamente valiosa para demanda e pode ser a proxima
fonte implementada. Ela deve seguir o desenho de sanitizacao descrito acima.
