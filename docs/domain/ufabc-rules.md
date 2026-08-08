# Regras curriculares da UFABC usadas no projeto

Este documento registra o entendimento de dominio usado pelo sistema de ranking de
turmas. As fontes foram conferidas em 16 de julho de 2026 nas paginas oficiais da
UFABC. Alteracoes futuras nos projetos pedagogicos e documentos complementares devem
gerar novas versoes dos dados, sem sobrescrever as versoes anteriores.

## Escopo

O sistema precisa responder, para cada disciplina ofertada:

> Como esta disciplina e classificada para este curso e esta versao de matriz?

As categorias usadas no ranking sao:

- `mandatory`: obrigatoria;
- `limited`: opcao limitada, chamada de "optativa" em algumas telas do sistema academico;
- `free`: livre;
- `not_applicable`: componente que nao pode ser classificado para a matriz analisada.

O calculo de quantas horas ou creditos faltam para o aluno integralizar o curso nao faz
parte deste modulo. Os totais podem ajudar a identificar uma matriz, mas nao devem ser
usados para classificar uma disciplina ou ranquear uma turma.

## Regra central

A categoria nao pertence globalmente a disciplina. Ela depende da combinacao:

```text
curso + versao da matriz + disciplina
```

Uma mesma disciplina pode ser obrigatoria para um curso, opcao limitada para outro e
livre para um terceiro. Por isso, a categoria fica em `course_curriculum_subjects` e
nunca diretamente em `subjects`.

O codigo oficial da disciplina e o identificador principal. O nome serve para exibicao
e revisao, mas nao deve ser usado sozinho para decidir a categoria, pois nomes e codigos
podem mudar entre catalogos.

## Significado das categorias

### Obrigatoria

Uma disciplina e obrigatoria quando aparece no rol de obrigatorias do Projeto
Pedagogico do Curso (PPC) da matriz selecionada, ou quando uma regra de transicao ou
convalidacao determina que ela cumpre uma obrigatoria dessa matriz.

### Opcao limitada ou optativa

Uma disciplina e de opcao limitada quando aparece no documento complementar oficial
da matriz ou atende a uma regra expressa nesse documento. O numero minimo de creditos
que um aluno precisa cursar nessa categoria nao representa a quantidade de disciplinas
existentes no rol.

Por exemplo, o BC&T 2023 exige apenas uma parte do rol, mas seu documento complementar
de 2025 possui muitas disciplinas de opcao limitada, incluindo:

- obrigatorias de outros cursos de ingresso que nao sejam obrigatorias do BC&T;
- obrigatorias ou opcoes limitadas de cursos de formacao especifica pos-BC&T.

Neste projeto, `limited` e o nome interno da categoria. A interface pode mostrar
"Opcao limitada (optativa)" para ficar compativel com o vocabulario visto pelo aluno.

### Livre

Livre nao e uma lista global e fechada. Para as ofertas de graduacao da UFABC, a regra
pratica e:

```text
se nao e obrigatoria e nao e opcao limitada para a matriz selecionada, entao e livre
```

Essa classificacao deve ser armazenada com `category_source = derived_rule`, para ficar
claro que foi deduzida pela ausencia nas listas de obrigatorias e limitadas. Uma
disciplina nao deve ser marcada como livre apenas porque seu codigo pertence a outro
centro ou porque a planilha de oferta nao cita o curso do aluno.

### Nao aplicavel

`not_applicable` nao e sinonimo de livre. Deve ser usado somente quando nao ha uma
matriz selecionada, o componente nao e uma disciplina aproveitavel ou existe uma regra
oficial que impeca sua classificacao. Uma disciplina regular da UFABC ausente das duas
listas normalmente sera livre, nao `not_applicable`.

## Extensao e atividades complementares

"Extensionista" nao e uma quarta categoria concorrente. E uma caracteristica adicional
da disciplina ou atividade.

Uma disciplina pode ser, ao mesmo tempo:

- obrigatoria e extensionista;
- opcao limitada e extensionista;
- livre e extensionista.

A coluna de extensionistas mostrada no resumo academico acompanha horas de extensao,
mas nao substitui a classificacao curricular. Atividades complementares tambem nao sao
disciplinas e ficam fora do ranking de turmas.

## Versoes inicialmente relevantes

### BC&T 2015

A tabela de carga horaria fornecida pelo usuario corresponde ao PPC 2015 do BC&T. A
correspondencia e exata: 1.080 horas obrigatorias, 684 horas de opcao limitada, 516
horas livres e 120 horas complementares. Esses numeros sao usados apenas para
identificar a matriz.

Regras de classificacao dessa versao:

- o Anexo 1 do PPC define as disciplinas obrigatorias;
- o Ato Decisorio ConsEPE 232/2022 fornece a lista oficial atualizada de 291
  disciplinas de opcao limitada;
- as demais disciplinas aproveitaveis sao livres.

Portanto, a importacao do BC&T 2015 materializa as obrigatorias do PPC e as opcoes
limitadas do Ato 232. A regra `derived_rule` fica reservada para a classificacao livre
das disciplinas ausentes das duas listas.

### BC&T 2023

Regras de classificacao dessa versao:

- o PPC 2023 define o rol de obrigatorias;
- o Documento Complementar I atualizado em 2025 define as opcoes limitadas;
- o documento divide as opcoes limitadas entre disciplinas de outros cursos de ingresso
  e disciplinas dos cursos especificos pos-BC&T;
- as demais disciplinas aproveitaveis sao livres.

BC&T 2015 e BC&T 2023 devem coexistir no banco. A matriz de 2023 nao pode substituir a
de 2015 para alunos antigos.

### BC&H 2022

Regras de classificacao dessa versao:

- o PPC 2022 define as obrigatorias;
- o Documento Complementar I define o rol de opcoes limitadas;
- o rol inclui obrigatorias dos outros cursos de ingresso e obrigatorias dos cursos de
  formacao especifica pos-BC&H, alem das disciplinas explicitamente listadas;
- as demais disciplinas aproveitaveis sao livres.

O codigo interno do curso sera `BCH`, mantendo `BC&H` como nome de exibicao oficial.

### BCC 2023

O BCC e um curso de formacao especifica vinculado ao BC&T. Para a matriz BCC 2023:

- as obrigatorias do BC&T que compoem o PPC do BCC continuam academicamente
  obrigatorias na trajetoria combinada;
- o PPC 2023 define as obrigatorias especificas do BCC;
- o Anexo I do Ato Decisorio CG numero 44/2023 define as opcoes limitadas;
- as demais disciplinas aproveitaveis sao livres;
- as regras e a tabela de transicao do Anexo II devem ser usadas para codigos antigos e
  convalidacoes.

Ingressantes anteriores a 2023 podem seguir uma matriz anterior ou optar pela matriz
2023, conforme as regras de transicao. Por isso, o sistema sugere uma versao pelo ano de
ingresso, mas deve permitir selecao manual.

## Alunos associados a mais de um curso

As classificacoes de cada curso devem ser preservadas separadamente. Exemplo:

```json
{
  "subject": "MCCC001-23",
  "classifications": [
    {"course": "BCT", "version": "2023", "category": "limited"},
    {"course": "BCC", "version": "2023", "category": "mandatory"}
  ]
}
```

O sistema nao deve apagar uma classificacao para produzir outra categoria unica. Quando
o ranking precisar de um valor consolidado, deve aplicar a estrategia escolhida pelo
aluno, como curso principal, maior progresso em qualquer curso ou pesos por curso.

## Prioridade para conseguir vaga em uma turma

A classificacao curricular e a prioridade de matricula sao conceitos diferentes. A
categoria responde como a disciplina conta no curso; a prioridade responde em que ordem
as solicitacoes disputam as vagas.

Para a primeira fase de matriculas, a versao de regra `consepe-260-2023` e aplicada a
partir de `2024:1`. A ordem e lexicografica: um criterio anterior e avaliado antes do
seguinte, em vez de todos serem somados em uma unica nota.

Turmas ofertadas pelos cursos interdisciplinares de ingresso, incluindo BC&T e BC&H:

1. disciplina obrigatoria para o curso interdisciplinar de ingresso;
2. mesmo turno de ingresso do aluno e da turma;
3. CP em ordem decrescente;
4. CA em ordem decrescente.

Turmas ofertadas por cursos de formacao especifica, como o BCC:

1. vinculo ou reserva no curso para o qual a disciplina seja obrigatoria ou limitada;
2. mesmo turno de ingresso do aluno e da turma;
3. CP em ordem decrescente;
4. CA em ordem decrescente.

Nas turmas de formacao especifica, 20% das vagas sao reservadas para alunos sem o
vinculo prioritario. Nesse grupo, sao considerados turno do curso de ingresso, CP do
curso de ingresso e CA, nessa ordem.

Consequencias para o projeto:

- turno tem dois usos independentes: preferencia de horario no ranking e criterio oficial
  de prioridade para a vaga;
- campus pode filtrar ou favorecer uma turma por conveniencia, mas nao participa da ordem
  inicial de alocacao; o Art. 17 apenas limita eventual remanejamento a outra turma do
  mesmo horario e campus;
- CP e por curso; para o grupo de nao vinculados de um curso especifico, usa-se o CP do
  curso interdisciplinar de ingresso;
- CA e global no perfil e aparece depois do CP;
- CR nao aparece na ordem de alocacao de turmas regulares da Resolucao 260;
- CR e creditos acumulados podem ser preservados do historico para usos academicos futuros,
  mas nao sao solicitados nem exibidos no formulario de matricula deste projeto;
- CP proximo de 1 e favoravel dentro do mesmo grupo, mas nao garante vaga porque curso e
  turno vem antes, e os coeficientes dos outros solicitantes nao sao conhecidos.

O sistema separa duas saidas. `estimated_probability` e apenas a disponibilidade agregada
`vagas / solicitacoes`, com confianca baixa. `personalized_probability` permanece vazia
enquanto nao houver uma distribuicao anonimizada dos solicitantes ou historico suficiente
para calibrar o modelo. A analise individual ainda exibe o grupo de disputa e os criterios
curso, turno, CP e CA, sem inventar uma porcentagem.

Na segunda e terceira fases, ajuste e reajuste, as vagas sao ocupadas por ordem de
solicitacao. Existem tambem regras especiais para ingressantes e grupos com vaga garantida;
essas condicoes precisam ser informadas explicitamente antes de entrarem em uma estimativa
individual.

## Limite de creditos por quadrimestre

O limite e do conjunto de disciplinas solicitado pelo aluno, nao de cada disciplina. De
acordo com o Art. 8 da Resolucao ConsEPE 260/2023:

```text
C = 20 + 2 * CA
```

Se o resultado nao for inteiro, ele e arredondado para o primeiro inteiro superior. O
valor de uma disciplina para esse limite e `T + P`; componentes integralizadores como
estagio, TCC, TG e monografia nao entram na soma. O CA e extraido do historico do SIGAA e
o perfil armazena o limite calculado com aritmetica decimal e arredondamento para cima. A
verificacao da soma e aplicada as turmas fixadas e tambem sera usada pelo futuro gerador
de grades.

## Codigos de disciplina e turma

O codigo como `BCL0306-15` identifica o componente curricular. Um codigo como
`NA1BCL0306-15SA` identifica uma turma especifica daquele componente em uma oferta. A
mesma disciplina pode ter varias turmas, docentes e horarios; por isso os dois codigos
sao corretos e devem ser exibidos separadamente.

## O que nao determina a categoria

Os seguintes dados nao sao fontes suficientes para classificar uma disciplina:

- quantidade de creditos que ainda falta ao aluno;
- prefixo do codigo da disciplina;
- centro academico que oferece a turma;
- campo de curso ou reserva presente na planilha de turmas;
- campus, turno, professor ou horario;
- o fato de a disciplina possuir horas extensionistas.

Esses dados podem afetar outros componentes do ranking, mas nao a categoria curricular.

## Precedencia das fontes

Quando houver divergencia, o importador deve aplicar esta ordem:

1. PPC oficial da versao para o rol de obrigatorias;
2. documento complementar vigente para o rol de opcoes limitadas;
3. regras e tabelas oficiais de transicao ou convalidacao;
4. Catalogo de Disciplinas para codigo, nome, T-P-E-I e metadados;
5. regra derivada de disciplina livre quando ela nao estiver nas categorias anteriores.

Cada entrada importada deve guardar, sempre que possivel:

- URL e titulo da fonte;
- ato ou resolucao de aprovacao;
- data em que a fonte foi consultada;
- se a categoria e explicita ou derivada;
- observacao de transicao ou convalidacao aplicada.

## Fontes oficiais

- [Pagina central dos cursos](https://prograd.ufabc.edu.br/cursos)
- [Projetos pedagogicos do BC&T](https://prograd.ufabc.edu.br/bct/pps)
- [PPC 2015 do BC&T](https://www.ufabc.edu.br/images/consepe/resolucoes/3---Reviso-do-PP-do-Bacharelado-em-Cincia-e-Tecnologia-Esta-verso-contempla-as-retificaes.pdf)
- [Opcoes limitadas do BC&T 2015, Ato ConsEPE 232/2022](https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/consepe_ato_decisorio_232_anexo.pdf)
- [PPC 2023 do BC&T](https://www.ufabc.edu.br/images/consepe/atos_decisorios/anexo_do_ad_consepe_249_-_ppc_bct_2023_-aprovado_consepe_-_final_pos_errata_12_23.pdf)
- [Opcoes limitadas do BC&T 2023, atualizadas em 2025](https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/comissao_ato_decisorio_70_anexo1.pdf)
- [Projeto pedagogico e documentos do BC&H](https://prograd.ufabc.edu.br/bch/projeto-pedagogico)
- [PPC 2022 do BC&H](https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/consepe_ato_decisorio_236_anexo.pdf)
- [Opcoes limitadas do BC&H 2022](https://prograd.ufabc.edu.br/cg/2023/BCH_Doc_Comp_I_v2.pdf)
- [Projeto pedagogico e documentos do BCC](https://prograd.ufabc.edu.br/cursos/bcc)
- [PPC 2023 do BCC](https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/consepe_ato_decisorio_267_anexo.pdf)
- [Opcoes limitadas do BCC 2023](https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/cg_ato-decisorio_044_anexo-01.pdf)
- [Transicao do BCC 2023](https://www.ufabc.edu.br/images/stories/comunicacao/Boletim/cg_ato-decisorio_044_anexo-02.pdf)
- [Catalogos de Disciplinas](https://prograd.ufabc.edu.br/catalogos-de-disciplinas)
- [Resolucao ConsEPE 260/2023](https://www.ufabc.edu.br/images/consepe/resolucoes/resoluo_260_-_estabelece_normas_e_critrios_para_a_solicitao_e_cancelamento_de_matrculas_em_disciplinas_da_grad_revoga_e_subst_131_n_202_e_n_219_assinada.pdf)
- [Perguntas frequentes sobre matriculas](https://prograd.ufabc.edu.br/sisu/217-aluno/7615-duvidas-frequentes-matricula-em-disciplinas)

## Dados oficiais materializados

Os arquivos em `app/data/curricula` materializam:

- BC&T 2015: 26 obrigatorias e 291 opcoes limitadas;
- BC&T 2023: 24 obrigatorias e 306 opcoes limitadas;
- BC&H 2022: 22 obrigatorias e 270 opcoes limitadas;
- BCC 2023: 51 obrigatorias, incluindo a base do BC&T, e 73 opcoes limitadas;
- livres: nao possuem lista nem quantidade fixa. Toda disciplina regular ausente das
  listas de obrigatorias e opcoes limitadas da matriz e classificada como `free`, com
  `category_source = derived_rule`.

Os totais de integralizacao nao foram importados como requisitos.

Nenhuma regra deste documento foi obtida da API do UFABC Next. As fontes usadas aqui
sao documentos publicos oficiais da UFABC.
