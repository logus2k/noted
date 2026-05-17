# PIAAP — Plano de Inteligência Artificial para a Administração Pública

*Draft operational layer that consolidates ANIA's distributed Public-Administration thread into a single document for the Portuguese civil service.*

**Document status:** Draft v0.2 — synthesis-stage proposal for stakeholder review.

**Positioning.** The PIAAP **does not introduce a parallel strategy**. It consolidates and operationalises the PA-AI initiatives already committed in PAANIA (the 32-initiative Action Plan inside ANIA) and cross-references the broader 2026-27 Action Plan of the Portugal Digital Strategy (EDN), of which ANIA is Action #20. Every deliverable below maps to a named PAANIA initiative (extends it) or to a named cross-cutting EDN deliverable (complements it). New deliverables — i.e. those not currently in PAANIA or EDN — are explicitly marked **[NEW]** and justified.

**Anchoring initiatives in PAANIA:** **II.11** (Centro de Excelência IA na AP), **II.12** (Concursos nacionais IA para AP), **II.13** (Guia de interpretação CCP para aquisição de IA), **III.1** (Plano acelerado de formação de IA na AP / Doutor AP), **IV.3** (Centro para a IA Responsável), **IV.4** (Implementação do EU AI Act), **IV.5** (Sandboxes regulatórias), **IV.6** (Guia de implementação do EU AI Act + ferramentas de avaliação de risco), **IV.7** (Cooperação internacional e diplomacia tecnológica). Plus the foundational Eixo I infrastructure that PIAAP relies on: **I.1** (EuroHPC/Deucalion), **I.3** (Espaços de dados em áreas críticas), **I.4** (Plano Nacional de Centros de Dados).

**Cross-references to EDN action plans:** the EDN (Estratégia Digital Nacional) Plano de Ação 2026-2027 is organised into **20 Ações** across 6 areas (Reforma Tecnológica do Estado, Dados e Interoperabilidade, Serviços Públicos Digitais, Economia e Regulação Digital, Competências Digitais, Inteligência Artificial). ANIA = **Ação 20**. PIAAP defers to the parallel Ações where they cover the same ground:

- **Ação 1** (Arquitetura Comum TIC na AP, lead ARTE) — cloud migration + governance partilhada de infraestruturas TIC
- **Ação 2** (Desenvolvimento da ARTE, DL 96/2025) — Centro de Excelência em IA para a AP é função dentro de ARTE; revisão da CDAP (RCM 94/2024) sob Ação 2.3; parcerias internacionais PALOP sob Ação 2.5
- **Ação 3** (Ecossistema de Inovação Digital na AP, lead ANI) — Polo Colaborativo + Compras Públicas de Inovação (3.3)
- **Ação 4** (Estratégia Nacional de Cibersegurança, lead GNS/CNCS, DL 125/2025) — framework de cibersegurança para a AP
- **Ação 8** (Política Nacional de Dados, lead ARTE+INE) — classificação soberana de dados (8.2); app "Os meus dados na AP" (8.5); execução do Data Act (8.4)
- **Ação 9** (PAGE — Plataforma de Apoio à Gestão do Estado, lead ARTE) — analítica integrada para tomada de decisão pública
- **Ação 10** (Serviços Públicos Digitais do Futuro, lead ARTE) — 13 sub-ações incluindo CMD (10.7), SCAP (10.8), carteira identidade digital gov.pt (10.10), estratégia comunicação canais gov.pt (10.13)
- **Ação 11** (Atendimento Omnicanal, lead ARTE) — Espaços Cidadão Móveis para baixa densidade (11.4)
- **Ação 13** (Revisão Infraestrutura Digital Nacional) — Cloud Soberana (13.1), Plano Nacional Centros de Dados + GigaFactory (13.2), Anel CAM e Anel Açores (13.4)
- **Ação 17** (Pacto de Competências Digitais, lead ARTE) — capacitação digital universal

**Companion artefacts:** [portugal_ania_synthesis.md](portugal_ania_synthesis.md) (the 25-recommendation strategic critique that elevates PIAAP as R12) and [comparator_matrix.md](comparator_matrix.md) (the 17-country evidence base).

**Reference frameworks:** UK *AI Playbook for the UK Government* (Feb 2025, 118 pp, mandatory for UK Civil Service); Australia *AI Plan for the Australian Public Service* (Nov 2025, 30 pp, Trust/People/Tools).

---

## Foreword *(placeholder for Minister of Finance / Minister for Public Administration)*

[Por preencher pelo Ministro tutelar antes da publicação.]

Esperado: declaração ministerial sobre o compromisso do Governo com a adoção responsável e eficaz da IA na Administração Pública portuguesa, alinhada com a ANIA, com a Lei Nacional para a IA (a aprovar) e com o Regulamento (UE) 2024/1689 (AI Act). Modelo: foreword da Sra. Senadora Katy Gallagher no APS AI Plan (Austrália, novembro 2025) — afirma propósito + escopo + obrigação política + chamamento ao serviço público.

---

## Vision

> O Estado português usará Inteligência Artificial de forma segura, responsável e produtiva para melhorar a entrega de serviços públicos, aumentar a eficiência e satisfação dos cidadãos, e capacitar os funcionários públicos.

**Operational targets (24 months from publication):**

- Cada Ministério tem um **Diretor de IA (DIA)** designado e um **Oficial de Responsabilização de IA (ORIA)** separado.
- **100% dos funcionários públicos** completam formação em fundamentos de IA.
- **Plataforma GovIA Portugal** em operação com acesso universal ao chat seguro (**GovIA Chat**).
- **Comité de Revisão de IA (CRIA)** estabelecido, reunindo a cada 6 semanas com 12+ casos de uso de alto risco avaliados.
- **Registo Central de Avaliações de Impacto de IA (RCAIA)** publicado e acessível interministerialmente.

---

## Scope

Este Plano aplica-se a todas as entidades da Administração Pública Central. Aplica-se aos seguintes níveis de utilização de IA:

1. **Acesso a IA generativa de uso geral** (ChatGPT, Claude, Gemini) — para informação OFICIAL e não classificada
2. **Plataformas centralizadas onshore** (GovIA Portugal + GovIA Chat) — para dados internos e processamento sob soberania portuguesa
3. **Soluções customizadas por agência** — para fluxos de trabalho especializados

Não aplica-se a usos de IA em domínios militar, defesa, intelligence e enforcement, que mantêm os seus regimes de supervisão existentes.

### Âmbito Local e Regional — fase 2 (deferida)

**Esta v0.3 cobre Administração Pública Central** (Ministérios, Direções-Gerais, Institutos Públicos, agências centrais — ~700.000 funcionários estimados). A extensão para Administração Pública Local (308 Câmaras Municipais + 3.000+ Juntas de Freguesia + serviços municipalizados) e Regional (Açores + Madeira + 5 CCDR continentais) **fica explicitamente deferida para a fase 2 do PIAAP**, dada a necessidade de:

1. **Coordenação institucional com a ANMP** (Associação Nacional de Municípios Portugueses) e **ANAFRE** (Associação Nacional de Freguesias) para co-desenho do enquadramento aplicável a entidades de autonomia administrativa
2. **Adaptação do mandato CDAP** (Conselho para o Digital na AP, RCM 94/2024 revisto em EDN Ação 2.3) para refletir a representação dos Governos Regionais e da AP Local — atualmente a CDAP cobre apenas a AP Central
3. **Calibração proporcional dos entregáveis** — particularmente 2.1 (formação universal: ~50.000 funcionários adicionais na AP Local segundo dados INE 2024), 2.4 (DIA/ORIA: cada Câmara Municipal não tem escala para nomear cargo dedicado; modelo intermunicipal via CIMs / Áreas Metropolitanas pode ser apropriado), e 3.1-3.2 (GovIA Portugal + Chat: arquitetura federada incluindo nós municipais)
4. **Cross-reference com EDN Ação 11** (Atendimento Omnicanal — inclui Lojas de Cidadão + Espaços Cidadão geridos pela ARTE com presença local) e **Ação 8.6** (plataformas de gestão urbana para 129 municípios + 5 Gémeos Digitais) que já operam no nível local
5. **Articulação com o Plano de Transformação Digital da Administração Pública Local** (instrumento PRR distinto, gerido pelo IFAP/CCDR) para evitar duplicação de instrumentos

**Cronograma proposto para fase 2 (PIAAP-L/R):** consulta com ANMP iniciada em 2027 H1; documento publicado para discussão pública em 2027 H2; aprovação em Conselho de Ministros em 2028 H1.

---

## Three pillars

### Pilar 1 — Confiança (Trust)

> Transparência, ética e governance.

### Pilar 2 — Pessoas (People)

> Construção de capacidade e engagement com funcionários.

### Pilar 3 — Ferramentas (Tools)

> Acesso, infraestrutura e suporte.

Estes três pilares são **interdependentes**: ferramentas sem pessoas capacitadas geram falhas; pessoas sem ferramentas adequadas perdem produtividade; ambos sem governance perdem confiança pública. O sucesso de cada pilar depende do sucesso dos outros.

---

## Chapter 1 — Os 10 Princípios da IA na Administração Pública Portuguesa

*(Adaptado do UK AI Playbook + alinhado com ANIA 6 Princípios + AI Act Article 26 deployer obligations.)*

1. **Compreender o que a IA pode e não pode fazer.** Antes de adotar IA, o funcionário público compreende as capacidades + limitações + casos de erro do sistema. Probabilístico ≠ determinístico.

2. **Usar a IA legal e éticamente.** Conformidade com RGPD, Lei n.º 27/2021 (Carta Portuguesa de Direitos Humanos na Era Digital), AI Act, Código dos Contratos Públicos, e Código do Procedimento Administrativo.

3. **Conhecer como gerir os riscos da IA.** Sistemática de avaliação de impacto (RCAIA), incluindo riscos de bias, fairness, segurança, robustez, proteção de dados.

4. **Usar a IA de forma segura e responsável.** Princípios de "Sustainability by Design" e "Ethics by Design" desde a fase de design. Não delegar decisões consequentes a sistemas autónomos sem supervisão humana competente.

5. **Ter o controlo humano relevante (meaningful).** Identificar pontos de decisão onde o funcionário público mantém julgamento substantivo (não apenas confirmação reflexa). Distinguir IA-em-loop / IA-em-loop / IA-fora-do-loop conforme o caso de uso.

6. **Compreender como gerir o ciclo de vida completo das ferramentas de IA.** Da especificação à descomissão, com monitorização contínua de drift, performance, e impacto.

7. **Usar a ferramenta certa para o trabalho.** Não toda solução requer IA. Triagem inicial: o problema é determinístico, regulamentado, com dados estruturados? Considerar abordagens não-IA primeiro.

8. **Ser aberto e colaborativo.** Partilhar lições, casos de uso, e ativos de IA através do **GovIA Use Case Library** (cf. Pilar 3). Reduzir duplicação interministerial.

9. **Trabalhar com a equipa certa em IA.** Multidisciplinaridade: técnicos + juristas + especialistas de domínio + utilizadores finais + funcionários representativos.

10. **Cumprir os requisitos legais e regulamentares.** Conformidade com AI Act (Regulamento (UE) 2024/1689), RGPD, e legislação setorial. Documentação completa para auditoria.

---

## Pillar 1 — Confiança (Trust): 4 deliverables

### 1.1 Atualização da Política de IA no Governo

| Field | Value |
|---|---|
| Lead | AMA + Centro para a IA Responsável + Secretaria-Geral da Presidência do Conselho de Ministros |
| Deliverable | Política Portuguesa para o Uso Responsável de IA no Governo (publicação) |
| Target | Q4 2026 |
| Anchor | PAANIA **IV.4** (Implementação do EU AI Act — definição de autoridades competentes e modelo de coordenação) + **IV.3** (Centro para a IA Responsável) |
| Status | Por iniciar; depende da entrada em vigor de IV.4 |

A política substitui orientações ad-hoc atualmente em vigor. Incorpora:

- Requisitos de governance (DIA + ORIA + CRIA)
- Mandato de avaliação de impacto para casos de uso de alto risco (alinhado com AI Act Article 26)
- Requisitos de transparência (PT-ATRS)
- Acompanhamento de mudança organizacional + consulta com sindicatos

Modelos de referência: APS AI Plan (Austrália) "AI in government policy and guidance updates" (Dec 2025); Australian Government AI impact assessment tool.

### 1.2 Comité de Revisão de IA (CRIA)

| Field | Value |
|---|---|
| Lead | AMA + Centro para a IA Responsável (secretaria) |
| Deliverable | CRIA constituído + reuniões a cada 6 semanas + 12 casos avaliados em 12 meses |
| Target | Estabelecimento Q1 2027; primeira reunião Q2 2027; maturidade plena final de 2027 |
| Anchor | PAANIA **IV.3** (Centro para a IA Responsável — funções de coordenação ecossistémica) + **IV.4** (autoridades competentes) — adiciona fórum recorrente multi-watchdog **[NEW operational mechanism]** |
| Status | Por iniciar |

O CRIA é o **órgão pan-watchdog de revisão de casos de uso de alto risco** na Administração Pública portuguesa. Composição:

- **Centro para a IA Responsável** (presidência, secretaria)
- **Comissão Nacional de Proteção de Dados (CNPD)** — proteção de dados pessoais
- **Provedor de Justiça** — direitos dos cidadãos
- **Comissão de Acesso aos Documentos Administrativos (CADA)** — transparência
- **ERSE / ANACOM / ASAE** — representante rotativo de regulação setorial
- **AMA** — representante operacional da Administração Pública
- **Universidade representativa** — perícia técnica independente

Funções:

- **Revisão de casos de uso de alto risco** antes da implementação (não-vinculativa mas pública)
- **Análise temática profunda** (deep-dives) sobre tendências sistémicas
- **Resposta a incidentes** e recomendações pós-evento
- **Publicação de pareceres** anuais consolidados

Modelo: AI Review Committee, APS AI Plan (Austrália) — cadência de 6 semanas, composição multi-watchdog, revisão de 1-2 casos de alto risco iniciais escalonando até maturidade plena.

### 1.3 Expectativas Claras dos Prestadores de Serviços Externos

| Field | Value |
|---|---|
| Lead | AMA + DGAEP + IMPIC (Instituto dos Mercados Públicos, do Imobiliário e da Construção) |
| Deliverable | Cláusulas-tipo para contratos públicos relativas ao uso de IA por prestadores |
| Target | Q1 2027 |
| Anchor | PAANIA **II.13** (Guia prático de interpretação do Código dos Contratos Públicos para aquisição de IA pela AP) — esta iniciativa **já cobre o âmbito**; PIAAP fornece o template de cláusulas operacionais |
| Status | A integrar diretamente no entregável de II.13 |

Cláusulas a incorporar no Código dos Contratos Públicos (CCP) e nos modelos de cadernos de encargos:

- **Obrigação de declaração**: prestadores devem declarar qualquer uso de IA na entrega de serviços ao Estado
- **Responsabilidade integral**: o prestador permanece totalmente responsável pelo serviço prestado, independentemente do uso de IA generativa
- **Transparência e auditoria**: dados de treino, modelos utilizados, e métricas de performance disponíveis para auditoria
- **Conformidade com PIAAP**: prestadores aderem aos princípios deste Plano para serviços prestados ao Estado

Modelo: APS AI Plan (Austrália) — "Digital Sourcing ClauseBank" + Commonwealth Contracting Suite + Management Advisory Services and People Panels.

### 1.4 Estratégia de Comunicação sobre IA

| Field | Value |
|---|---|
| Lead | AMA + GAVE + Secretaria-Geral PCM |
| Deliverable | Plano de comunicação interno + materiais + canais |
| Target | Q4 2026 (lançamento); contínuo |
| Anchor | EDN **Ação 10.13** (estratégia de comunicação e promoção dos canais digitais gov.pt, lead ARTE); apoia a difusão de PAANIA III.6 (National AI Week) **[NEW PA-specific operational layer]** |
| Status | Por iniciar; alinhar com cronograma de Ação 10.13 (2S 2025 → 2S 2026) |

Mensagens consistentes para funcionários públicos sobre:

- O que a IA pode ser usada para (e o que não pode)
- Como aceder às ferramentas (GovIA Chat, plataforma GovIA Portugal)
- Onde obter ajuda em caso de dúvidas
- O que fazer quando algo não funciona como esperado
- Direitos do funcionário em relação a sistemas algorítmicos que afetem o seu trabalho

Canais: intranet AMA, formação INA, masterclasses periódicas, briefings ministeriais, "AI Office Hours" mensais.

---

## Pillar 2 — Pessoas (People): 4 deliverables

### 2.1 Formação Fundamental Obrigatória

| Field | Value |
|---|---|
| Lead | INA + DGAEP + Universidade Aberta |
| Deliverable | Módulo "Fundamentos de IA na Administração Pública" — completado por 100% dos funcionários em 18 meses |
| Target | Q4 2026 (lançamento); 100% conclusão Q4 2028 |
| Anchor | PAANIA **III.1** (Plano acelerado de formação de IA na AP / Doutor AP) — **estende** III.1 da coorte avançada (especialistas + lideranças) para mandato universal de fundamentos para todos os funcionários da AP Central |
| Status | III.1 a iniciar 1S 2026; PIAAP propõe escalada universal a partir de Q4 2026 |

**Mandato:** todos os funcionários da Administração Pública Central (estimado 700.000 pessoas) completam formação de fundamentos de IA dentro de 18 meses da publicação do PIAAP.

Currículo (4-6 horas de e-learning + 2 horas de presencial):

- O que é IA generativa (e o que não é)
- Casos de uso aprovados vs. proibidos na Administração Pública
- Proteção de dados pessoais (RGPD) e dados confidenciais
- Direitos do cidadão e do funcionário
- Como reportar incidentes
- Acesso prático ao GovIA Chat

**Variantes especializadas** para 5 tiers (modelo UK Playbook adaptado):

- Tier 1 — Liderança executiva (DIA + ORIA + Ministros)
- Tier 2 — Quadros técnicos (CIOs, técnicos de informática)
- Tier 3 — Quadros digitais (utilizadores intensivos)
- Tier 4 — Quadros gerais (utilizadores ocasionais)
- Tier 5 — Especialistas em IA (cientistas de dados, engenheiros)

Modelo de referência: APS AI Plan (Austrália) — mandatory foundational AI literacy training implementada nos primeiros 12 meses; UK Playbook — 5-tier civil-servant segmentation.

### 2.2 Consulta e Engagement com Funcionários

| Field | Value |
|---|---|
| Lead | DGAEP + Sindicatos (FESAP, STE, SINTAP) + INA |
| Deliverable | Circular DGAEP com normas de consulta sindical em mudanças relacionadas com IA |
| Target | Q1 2027 |
| Anchor | Fora do âmbito do EDN Plano de Ação 2026-27 (Concertação Social + ACT operam noutro quadro); complementa PAANIA **IV.1** (linha "AI Economics and Work Impact") **[NEW operational mechanism, anchored em legislação laboral pré-existente]** |
| Status | Por iniciar |

Normas de consulta para todas as mudanças relacionadas com IA que afetem o trabalho dos funcionários públicos:

- Consulta prévia significativa (com tempo para influenciar a decisão antes da sua tomada)
- Alinhamento com Convenção Coletiva de Trabalho dos funcionários públicos
- Identificação de impactos por género, identidade cultural, situação de deficiência, e outros grupos
- Mecanismos de "voice" dos funcionários no design e operação dos sistemas

Modelo: APS AI Plan (Austrália) — "Circular setting out clear standards for consultation on AI-related workplace changes" + alinhamento com APS Enterprise Agreements.

### 2.3 Centro de Excelência em IA da Administração Pública (CEIAP) + Função de Aceleração de Adoção (AIDE-PT)

| Field | Value |
|---|---|
| Lead | AMA + INA + Centro para a IA Responsável |
| Deliverable | CEIAP estabelecido com equipa multidisciplinar (técnica + jurídica + UX + transformação organizacional) |
| Target | Q1 2027 |
| Anchor | PAANIA **II.11** (AI Centre of Excellence in PA) — esta iniciativa **é** o CEIAP; o EDN Ação 3 confirma que o Centro de Excelência é função alojada **dentro da ARTE, I. P.** (não nova entidade). PIAAP fornece o desenho operacional (composição, mandato, função de aceleração AIDE-PT) |
| Status | II.11 a iniciar 1S 2026 (entidade responsável: ARTE) |

CEIAP funciona como **função central de aceleração de adoção**: identifica casos de uso de alto valor, resolve bloqueios sistémicos, partilha lições, e captura conhecimento institucional. Modelo: AI delivery and enablement (AIDE), APS AI Plan (Austrália).

Atividades:

- Carteira de casos de uso prioritários cross-ministerial
- Orientações práticas para barreiras comuns de adoção
- Reuniões trimestrais com DIAs
- Métricas de adoção por Ministério
- "Show-and-tell" mensal de implementações

### 2.4 Diretores de IA (DIAs) + Oficiais de Responsabilização de IA (ORIAs)

| Field | Value |
|---|---|
| Lead | AMA + Secretaria-Geral PCM (designações) |
| Deliverable | Todos os Ministérios + agências centrais com DIA designado |
| Target | Q4 2026 |
| Anchor | PAANIA **II.11** (CEIAP fornece coordenação central) + EDN **Ação 2.3** (revisão do **CDAP — Conselho para o Digital na Administração Pública**, criado por RCM 94/2024) — rede de DIAs ancora-se na composição revista do CDAP, evitando criar órgão paralelo. Adiciona figura por ministério **[NEW governance layer]** |
| Status | Por iniciar; depende da revisão do CDAP (2S 2025 → 1S 2026) |

**Designação de DIA por cada Ministério e agência central da Administração Pública** (modelo Australia APS AI Plan + USA OMB M-25-21):

- DIA é cargo de liderança sénior (Director-Geral ou equivalente)
- Responsabilidades: acelerar adoção, advogar mudança estratégica, partilhar boas práticas, supervisionar adoção/experimentação/inovação
- ORIA é cargo separado, com foco em governance e conformidade
- Em ministérios pequenos, podem ser combinados na mesma pessoa
- Grupo de trabalho de DIAs com encontros bimensais coordenados pelo CEIAP

---

## Pillar 3 — Ferramentas (Tools): 7 deliverables

### 3.1 GovIA Portugal — Plataforma Central de IA

| Field | Value |
|---|---|
| Lead | AMA + IPN + INCM |
| Deliverable | Plataforma central onshore com brokerage multi-modelo |
| Target | Piloto Q3 2027; rollout pleno Q1 2028 |
| Anchor | PAANIA **II.11** (CEIAP) — adiciona entregável de plataforma vendor-agnostic + **I.4** (Plano Nacional de Centros de Dados) para alojamento + **I.1** (Deucalion/EuroHPC) para cargas pesadas + EDN **Ação 13.1** (Plano para o Desenvolvimento de uma Cloud Soberana, lead Governo, conclusão 1S 2026) — GovIA Portugal **deve ancorar-se na Cloud Soberana** como infraestrutura subjacente, evitando duplicação. **[NEW platform deliverable within Centre of Excellence]** |
| Status | Por iniciar; depende do Plano Cloud Soberana (Ação 13.1) |

**GovIA Portugal** é a plataforma vendor-agnostic para o Governo português. Características:

- Brokerage multi-modelo: acesso a modelos de OpenAI, Anthropic, Mistral, Google, Aleph Alpha, e outros — todos hospedados em infraestrutura sob soberania portuguesa ou da UE
- Selectivo de modelo conforme caso de uso (modelo grande para tarefas complexas; modelo pequeno para tarefas rotineiras)
- Biblioteca de casos de uso (cf. 3.5)
- Ambientes de desenvolvimento e teste
- Acesso a infraestrutura HPC (Deucalion + EuroHPC)
- Repositórios de dados governamentais autorizados

**Distinção crítica:** GovIA Portugal não é AMALIA. AMALIA é o LLM soberano português (PT-PT, ambição de longo prazo). GovIA Portugal é a plataforma operacional do dia-a-dia que cada ministério usa imediatamente.

Modelo: GovAI, APS AI Plan (Austrália) — centralised AI hosting service com onshore OpenAI GPT instance.

### 3.2 GovIA Chat — Acesso Universal a IA Segura

| Field | Value |
|---|---|
| Lead | AMA + IPN |
| Deliverable | Interface de chat seguro universalmente acessível para todos os funcionários da Administração Pública |
| Target | Beta Q1 2027; rollout pleno Q3 2027 |
| Anchor | PAANIA **II.11** (CEIAP) — front-end consumer-friendly da plataforma GovIA Portugal (3.1); autenticação via EDN **Ação 10.7** (melhoria da Chave Móvel Digital e Assinatura Digital, lead ARTE) + **Ação 10.10** (carteira de identidade digital gov.pt, lead ARTE); integração com app móvel gov.pt sob EDN **Ação 10.11** **[NEW universal-access deliverable]** |
| Status | Por iniciar |

GovIA Chat é a versão consumer-friendly do GovIA Portugal — uma interface de chat que cada funcionário público pode usar para tarefas rotineiras dentro dos limites OFICIAL/Reservado. Características:

- Autenticação via Cartão de Cidadão / Chave Móvel Digital
- Respostas auditáveis (log de prompts + respostas)
- Acesso opcional a dados governamentais autorizados (com permissões controladas)
- Conformidade com PSPF (Protective Security Policy Framework) equivalente português

Modelo: GovAI Chat, APS AI Plan (Austrália) — secure generative AI for everyone in the public service.

### 3.3 Orientações para Serviços Públicos e Empresariais de IA

| Field | Value |
|---|---|
| Lead | AMA + Centro Nacional de Cibersegurança (CNCS) |
| Deliverable | Orientações claras sobre uso de ChatGPT, Claude, Gemini (e equivalentes) com informação OFICIAL |
| Target | Q4 2026 (revisão completa) |
| Anchor | PAANIA **IV.6** (Guia de implementação do EU AI Act, normas, ferramentas de avaliação de risco) — adiciona camada operacional específica para a AP + EDN **Ação 4** (Estratégia Nacional de Cibersegurança / **ENC**, aprovada em anexo ao DL 125/2025, lead GNS/CNCS) para classificação de informação + EDN **Ação 8.2** (Modelo de Classificação Soberana dos Dados da AP) |
| Status | Inicia-se com orientações atuais AMA; alinhar com ENC + Ação 8.2 |

Orientações específicas sobre quando funcionários públicos podem (e quando não podem) usar serviços públicos de IA generativa (ChatGPT, Claude, Gemini, etc.):

- Tabela clara de classificação de dados ↔ ferramentas permitidas
- Salvaguardas técnicas recomendadas (browser plug-ins de bloqueio de upload)
- Casos de uso aprovados vs. casos de uso proibidos
- Procedimento para excecionar casos de uso

Modelo: PSPF Policy Advisory 1 — OFFICIAL Information Use with Generative AI (Department of Home Affairs, Austrália, outubro 2025); UK Government Generative AI Framework.

### 3.4 Aquisição de Ferramentas de IA

| Field | Value |
|---|---|
| Lead | IMPIC + ESPap + AMA |
| Deliverable | Subcategorias específicas de IA no Portal Base.gov.pt + contratos-modelo |
| Target | Q3 2027 |
| Anchor | PAANIA **II.13** (Guia de interpretação do CCP para aquisição de IA) — esta iniciativa já cobre a interpretação; PIAAP adiciona infra-estrutura procedimental ancorada em EDN **Ação 3.3** (Programa "Compras Públicas de Inovação", lead ANI — assistência técnica + co-participação na fase inicial de desenvolvimento). Não existe Ação EDN dedicada ao Portal Base.gov.pt; sub-categorias IA introduzem-se via mecanismo CPI. |
| Status | A coordenar com cronograma de II.13 (1S 2026) e Ação 3.3 (em curso desde 2S 2025) |

Caminhos de aquisição simplificados para produtos e serviços de IA:

- **Subcategorias específicas de IA** no Portal Base.gov.pt + Sistema de Aquisições da Administração Pública (SAAP)
- **Contrato-Modelo de IA** (adaptação do AI Model Contract, Austrália, outubro 2025)
- **Cláusulas de IA** no CCP + Caderno de Encargos Tipo
- **Lista de fornecedores qualificados** com avaliação de adequação

Modelo: BuyICT AI subcategories + AI Model Contract, APS AI Plan (Austrália).

### 3.5 Biblioteca de Casos de Uso + Reutilização de Propriedade Intelectual

| Field | Value |
|---|---|
| Lead | AMA + ESPap |
| Deliverable | GovIA Use Case Library — biblioteca pesquisável de casos de uso + IP reutilizável |
| Target | Beta Q2 2027 |
| Anchor | PAANIA **II.12** (Concursos nacionais de IA para AP — produz casos de uso anualmente) + **II.11** (CEIAP curadoria) + EDN **Ação 9 PAGE — Plataforma de Apoio à Gestão do Estado** (lead ARTE, 1S 2026 → 1S 2027) — a Biblioteca de Casos de Uso de IA deve estar **integrada arquiteturalmente com PAGE** (mesma plataforma cross-ministerial de dados + casos de uso para gestão pública) |
| Status | Por iniciar; depende dos primeiros ciclos de II.12 + arquitetura PAGE (Ação 9.1, 2S 2025 → 1S 2026) |

Plataforma onde Ministérios e agências:

- **Publicam casos de uso implementados** (com avaliação de impacto + lições aprendidas)
- **Partilham código + propriedade intelectual** (sob acordo de reutilização Commonwealth-style)
- **Pesquisam casos de uso por sector / problema / tecnologia** antes de iniciar novos projetos

Reduz duplicação de gastos. Modelo: GovAI Use Case Library (Austrália) — 20+ APS use cases já catalogados; UK i.AI Incubator open-source GitHub.

### 3.6 Registo Central de Avaliações de Impacto de IA (RCAIA)

| Field | Value |
|---|---|
| Lead | AMA + CNPD + Centro para a IA Responsável |
| Deliverable | RCAIA operacional + obrigatório para casos de uso de alto risco |
| Target | Q3 2027 |
| Anchor | PAANIA **IV.6** (Guia de implementação do EU AI Act + ferramentas de avaliação de risco) — adiciona registo central reutilizável; integra com AIPD existentes (RGPD Art. 35) + EDN **Ação 8.5** (redesenho da aplicação "Os meus dados na Administração Pública", lead ARTE, integrada no portal gov.pt) — o RCAIA expõe-se ao cidadão pela mesma porta da app "Os meus dados" **[NEW central-register deliverable]** |
| Status | Por iniciar; alinhar com cronograma de Ação 8.5 (1S 2026 → 1S 2027) |

Registo centralizado de avaliações de impacto completadas para sistemas de IA na Administração Pública:

- **Avaliações de impacto de proteção de dados (AIPD)** sob RGPD Article 35
- **Avaliações de risco de cibersegurança**
- **Avaliações de impacto sob AI Act** Article 26 (deployer obligations)
- **Avaliações de Foreign Ownership, Control or Influence (FOCI)** para fornecedores

Cada ministério pode **referenciar e reutilizar avaliações já feitas** por outros ministérios, acelerando adoção e reduzindo custo.

Modelo: Central register of generative AI assessments, APS AI Plan (Austrália).

### 3.7 Política de Cloud para a Administração Pública

| Field | Value |
|---|---|
| Lead | AMA + Conselho para as Tecnologias de Informação na Administração Pública (CTIC) |
| Deliverable | Política de Cloud da Administração Pública revista + alinhada com IA |
| Target | Q4 2026 (revisão) |
| Anchor | PAANIA **I.4** (Plano Nacional de Centros de Dados) + EDN **Ação 1.3** (Plano de centralização e migração para soluções em cloud, lead ARTE, 2S 2026) + EDN **Ação 13.1** (Plano Cloud Soberana, lead Governo, 2S 2025 → 1S 2026) + EDN **Ação 13.2** (Plano Nacional de Centros de Dados — dual-anchor com PAANIA I.4) |
| Status | Inicia-se com política existente; tripla coordenação Ação 1.3 + 13.1 + 13.2 + PAANIA I.4 |

Política de cloud da Administração Pública atualizada para:

- Suporte a cargas de trabalho de IA
- Compromissos de soberania de dados (UE + Portugal)
- Conformidade com PSPF equivalente português
- Aceleração de migração de sistemas legacy
- Eficiência energética

Modelo: APS AI Plan (Austrália) "New whole-of-government cloud policy" (Dec 2025).

---

## Implementation timeline

| Periódo | Pilar 1 — Confiança | Pilar 2 — Pessoas | Pilar 3 — Ferramentas |
|---|---|---|---|
| **Q4 2026** | Política de IA publicada; estratégia de comunicação | DIAs+ORIAs designados; formação fundamental lançada | Orientações Public AI revistas; Política Cloud revista |
| **Q1 2027** | Cláusulas CCP para prestadores; primeira reunião CRIA | Circular DGAEP consulta sindical; CEIAP estabelecido | GovIA Chat beta |
| **Q2-Q3 2027** | CRIA em operação regular | DIAs em operação; formação a 50% conclusão | GovIA Portugal piloto; Biblioteca de Casos de Uso beta; RCAIA operacional; AI Model Contract |
| **Q4 2027 — 2028** | CRIA maturidade plena | Formação a 100% conclusão; CEIAP operacional pleno | GovIA Portugal rollout pleno; reutilização IP em operação; aquisição AI simplificada |

---

## Appendix A — Deliverables consolidados + ancoragem PAANIA/EDN

| Pilar | # | Deliverable | Lead | Target | Âncora PAANIA / EDN |
|---|---|---|---|---|---|
| **Confiança** | 1.1 | Política de IA no Governo | AMA + CIR | Q4 2026 | PAANIA IV.4 + IV.3 |
| **Confiança** | 1.2 | Comité de Revisão de IA (CRIA) | AMA + CIR (sec.) | Q1 2027 (estab.); Q4 2027 (maturidade) | PAANIA IV.3 + IV.4 — fórum multi-watchdog **[NEW]** |
| **Confiança** | 1.3 | Cláusulas CCP para prestadores externos | AMA + DGAEP + IMPIC | Q1 2027 | PAANIA **II.13** (entregável central) |
| **Confiança** | 1.4 | Estratégia de comunicação IA | AMA + GAVE | Q4 2026 | EDN **Ação 10.13** (canais gov.pt) + apoia PAANIA III.6 **[NEW]** |
| **Pessoas** | 2.1 | Formação fundamental obrigatória | INA + DGAEP + UA | Q4 2026 (lançamento); Q4 2028 (100%) | PAANIA **III.1** — estende para mandato universal |
| **Pessoas** | 2.2 | Consulta sindical (Circular DGAEP) | DGAEP + Sindicatos | Q1 2027 | Fora do EDN (Concertação Social + ACT) + complementa PAANIA IV.1 **[NEW]** |
| **Pessoas** | 2.3 | CEIAP + AIDE-PT | AMA + INA + CIR | Q1 2027 | PAANIA **II.11** (CEIAP é função dentro de ARTE per EDN Ação 3) |
| **Pessoas** | 2.4 | DIAs + ORIAs designados | AMA + SGPCM | Q4 2026 | PAANIA II.11 + EDN **Ação 2.3** (revisão do CDAP/RCM 94/2024) **[NEW]** |
| **Ferramentas** | 3.1 | GovIA Portugal (plataforma) | AMA + IPN + INCM | Q3 2027 (piloto); Q1 2028 (pleno) | PAANIA II.11 + I.4 + I.1 + EDN **Ação 13.1 (Cloud Soberana)** **[NEW]** |
| **Ferramentas** | 3.2 | GovIA Chat | AMA + IPN | Q1 2027 (beta); Q3 2027 (pleno) | PAANIA II.11 + EDN **Ação 10.7 (CMD)** + **10.10** + **10.11** **[NEW]** |
| **Ferramentas** | 3.3 | Orientações Public AI | AMA + CNCS | Q4 2026 | PAANIA IV.6 + EDN **Ação 4 (ENC)** + **Ação 8.2** |
| **Ferramentas** | 3.4 | Aquisição IA simplificada | IMPIC + ESPap + AMA | Q3 2027 | PAANIA **II.13** + EDN **Ação 3.3 (CPI)** |
| **Ferramentas** | 3.5 | Biblioteca de Casos de Uso + IP | AMA + ESPap | Q2 2027 (beta) | PAANIA II.12 + II.11 + EDN **Ação 9 (PAGE)** |
| **Ferramentas** | 3.6 | RCAIA | AMA + CNPD + CIR | Q3 2027 | PAANIA IV.6 + RGPD AIPD + EDN **Ação 8.5 ("Os meus dados na AP")** **[NEW]** |
| **Ferramentas** | 3.7 | Política Cloud revista | AMA + CTIC | Q4 2026 | PAANIA I.4 + EDN **Ações 1.3 + 13.1 + 13.2** |

**Síntese de ancoragem (atualizada com Plano de Ação 2026-27 da EDN, 20 Ações):**

- **9 entregáveis ancoram em iniciativas PAANIA existentes** (II.11×4, II.13×2, II.12×1, III.1×1, IV.4×1, IV.6×2, I.4×2, I.1×1, IV.3×2 — múltiplas refs/entregável)
- **11 dos 15 entregáveis** têm **âncora EDN identificada e verificada por número de Ação** (apenas 2.1, 2.2, 2.3 e 1.3 ficam sem âncora EDN: 2.1 e 2.3 porque PAANIA III.1 e II.11 já cobrem; 2.2 porque consulta sindical opera fora do EDN; 1.3 porque PAANIA II.13 é o entregável central)
- **6 entregáveis marcados [NEW]** como camadas operacionais não diretamente presentes em PAANIA nem EDN (CRIA, comunicação interna AP, consulta sindical, DIAs/ORIAs, GovIA Portugal+Chat, RCAIA) — todos justificados por evidência UK Playbook + Australia APS Plan
- **Nenhum entregável duplica iniciativas existentes em PAANIA ou EDN**
- **Dependências de cronograma identificadas:** PIAAP 3.1 depende de Ação 13.1 Cloud Soberana (1S 2026); PIAAP 3.5 depende de Ação 9 PAGE (1S 2026 → 1S 2027); PIAAP 2.4 depende de Ação 2.3 revisão CDAP (2S 2025 → 1S 2026)

---

## Appendix B — Case studies *(placeholder for early implementations)*

À medida que pilotos forem completados nos primeiros 18 meses, esta secção será atualizada com 4-6 estudos de caso documentados, mostrando:

- Caso de uso concreto + Ministério implementador
- Tecnologia + fornecedor + custo
- Avaliação de impacto antes/depois
- Lições aprendidas (incluindo o que não funcionou)
- Reutilização recomendada

Casos prioritários candidatos (a confirmar com cada Ministério):

1. **SNS24** — triagem de chamadas com IA + transcrição médica (SNS / SPMS)
2. **AT — Autoridade Tributária** — assistência ao contribuinte + classificação de reembolsos
3. **Segurança Social** — deteção de fraude em prestações sociais
4. **IEFP** — matching de candidatos a ofertas de emprego
5. **DGRF** — previsão de risco de incêndio rural
6. **DGEEC** — previsão de abandono escolar
7. **DGS** — análise epidemiológica e farmacovigilância

Modelo: APS AI Plan (Austrália) cita Department of Veterans' Affairs AI-enhanced search; UK Playbook cita 6 estudos de caso (Disability Living Allowance triage, AI Caseworker, etc.).

---

## Appendix C — Glossário

| Termo | Definição |
|---|---|
| AIPD | Avaliação de Impacto sobre Proteção de Dados (RGPD Article 35) |
| AMA | Agência para a Modernização Administrativa |
| AMALIA | Modelo de linguagem soberano português (PT-PT) — PAANIA II.7 |
| ANIA | Agenda Nacional para a Inteligência Artificial (Jan 2026) = EDN Ação 20 |
| ARTE | Agência para a Reforma Tecnológica do Estado (DL 96/2025, headed by CTO do Estado) — entidade operacional dominante do Plano de Ação 2026-27 da EDN |
| CDAP | Conselho para o Digital na Administração Pública (RCM 94/2024, revisão prevista em EDN Ação 2.3) |
| CADA | Comissão de Acesso aos Documentos Administrativos |
| CCP | Código dos Contratos Públicos |
| CCT | Carta dos Direitos Fundamentais (UE) |
| CEIAP | Centro de Excelência em IA da Administração Pública |
| CIR | Centro para a Inteligência Artificial Responsável (ANIA IV.3) |
| CNCS | Centro Nacional de Cibersegurança |
| CNPD | Comissão Nacional de Proteção de Dados |
| CRIA | Comité de Revisão de IA |
| CTIC | Conselho para as Tecnologias de Informação na Administração Pública |
| CTO do Estado | Chief Technology Officer do Estado (criado por DL 96/2025) |
| EDN | Estratégia Digital Nacional (Plano de Ação 2026-27 contém 20 Ações, sendo ANIA a Ação 20) |
| ENC | Estratégia Nacional de Cibersegurança (aprovada em anexo ao DL 125/2025) |
| GNS/CNCS | Gabinete Nacional de Segurança / Centro Nacional de Cibersegurança |
| PAANIA | Plano de Ação da ANIA 2026-2030 (as 32 iniciativas) |
| PAGE | Plataforma de Apoio à Gestão do Estado (EDN Ação 9, lead ARTE) |
| DGAEP | Direção-Geral da Administração e do Emprego Público |
| DGEEP | Direção-Geral de Estatísticas da Educação e Ciência |
| DIA | Diretor de IA (Chief AI Officer per ministry) |
| ESPap | Entidade de Serviços Partilhados da Administração Pública |
| EU AI Act | Regulamento (UE) 2024/1689 |
| FCT | Fundação para a Ciência e a Tecnologia |
| FESAP / STE / SINTAP | Sindicatos representativos da Administração Pública |
| GovIA Chat | Interface de chat de IA universal para funcionários públicos |
| GovIA Portugal | Plataforma central de IA com brokerage multi-modelo |
| IA | Inteligência Artificial |
| IMPIC | Instituto dos Mercados Públicos, do Imobiliário e da Construção |
| INA | Direção-Geral da Qualificação dos Trabalhadores em Funções Públicas (antiga INA — Instituto Nacional de Administração) |
| INCM | Imprensa Nacional-Casa da Moeda |
| IPN | Instituto Pedro Nunes (Coimbra) |
| IPQ | Instituto Português da Qualidade |
| ORIA | Oficial de Responsabilização de IA (AI Accountable Official) |
| PIAAP | Plano de IA para a Administração Pública (este documento) |
| PSPF | Protective Security Policy Framework |
| RCAIA | Registo Central de Avaliações de Impacto de IA |
| RGPD | Regulamento Geral sobre a Proteção de Dados |
| SGPCM | Secretaria-Geral da Presidência do Conselho de Ministros |
| UA | Universidade Aberta |

---

## Note for final-report stakeholder review

Este draft de PIAAP é um **artefacto de discussão** preparado para a fase de síntese de ANIA. **Positioning principle:** o PIAAP **não** é um plano paralelo a PAANIA — é o documento operacional que consolida as iniciativas PAANIA já comprometidas para a Administração Pública (II.11, II.12, II.13, III.1, IV.3-IV.7) num único instrumento, e que se cruza com o Plano de Ação 2026-27 da Estratégia para a Digitalização da Nação (EDN) nas camadas digitais transversais (identidade, procurement, cloud, cibersegurança).

Antes da publicação como instrumento operacional, deve ser:

1. **Discutido com a tutela política** (Ministro das Finanças + Ministro da Modernização do Estado e da Administração Pública)
2. **Consultado com as Confederações Sindicais** (UGT + CGTP) e respetivas estruturas sindicais da Administração Pública
3. **Validado por uma Comissão Temática** com representação de AMA + Centro para a IA Responsável + DGAEP + INA + CNPD + Provedor de Justiça
4. **Alinhado com PAANIA**: confirmar cronogramas dos 9 entregáveis ancorados (II.11, II.12, II.13, III.1, IV.3, IV.4, IV.6, I.1, I.4) com as entidades responsáveis (ARTE, FCT, ANI, INA, AMA, IPQ, ANACOM); evitar duplicação ao longo da entrega
5. **Cruzado com o Plano de Ação 2026-27 da EDN (20 Ações)** — alinhamento confirmado com Ações 1, 2 (CDAP), 3 (CPI), 4 (ENC), 8.2/8.5 (dados), 9 (PAGE), 10.7/10.10/10.11/10.13, 11 (Atendimento Omnicanal), 13.1/13.2 (Cloud Soberana, DC), 17 (Pacto Competências). Esquemas de governance e cronogramas a sincronizar com a ARTE (lead de ≥12 das 20 Ações) e com a revisão da CDAP (Ação 2.3)
6. **Alinhado com a Lei Nacional para a IA** (a aprovar — cf. Recomendação R22 do [portugal_ania_synthesis.md](portugal_ania_synthesis.md))
7. **Cross-checked com o AI Act** (Regulamento (UE) 2024/1689) e respetiva transposição nacional
8. **Calibrado em escopo** com a realidade da Administração Pública Local + Regional (este draft cobre Administração Central; extensão para AP Local/Regional carece de coordenação com ANMP + Câmaras Municipais)

Cronograma proposto para finalização:
- **Janeiro 2027** — versão consultiva publicada para comentário público (30 dias)
- **Março 2027** — versão final aprovada em Conselho de Ministros
- **Abril 2027** — publicação no Diário da República (Resolução do Conselho de Ministros ou Decreto-Lei conforme adequado)

---

*End of piaap_draft.md. This document complements [portugal_ania_synthesis.md](portugal_ania_synthesis.md) and [comparator_matrix.md](comparator_matrix.md). All three artefacts together constitute the synthesis stack for ANIA's 2027 evolution.*
