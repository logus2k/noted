# PIAAP — Plano de Inteligência Artificial para a Administração Pública

*Draft operational layer for Portugal's National AI Agenda (ANIA).*

**Document status:** Draft v0.1 — synthesis-stage proposal for stakeholder review.
**Anchor:** ANIA Pillar III (Public Administration) + Pillar IV (Governance).
**Companion artefacts:** [portugal_ania_synthesis.md](portugal_ania_synthesis.md) and [comparator_matrix.md](comparator_matrix.md).
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
| Status | Por iniciar |

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
| Status | Por iniciar |

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
| Status | Por iniciar |

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
| Status | Por iniciar |

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
| Status | Inicia-se sob ANIA II.11 (PA Centre of Excellence) |

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
| Status | Por iniciar |

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
| Status | Por iniciar |

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
| Status | Inicia-se com orientações atuais AMA |

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
| Status | Por iniciar |

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
| Status | Por iniciar |

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
| Status | Por iniciar |

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
| Status | Inicia-se com política existente |

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

## Appendix A — Deliverables consolidados

| Pilar | # | Deliverable | Lead | Target |
|---|---|---|---|---|
| **Confiança** | 1.1 | Política de IA no Governo | AMA + CIR | Q4 2026 |
| **Confiança** | 1.2 | Comité de Revisão de IA (CRIA) | AMA + CIR (sec.) | Q1 2027 (estab.); Q4 2027 (maturidade) |
| **Confiança** | 1.3 | Cláusulas CCP para prestadores externos | AMA + DGAEP + IMPIC | Q1 2027 |
| **Confiança** | 1.4 | Estratégia de comunicação IA | AMA + GAVE | Q4 2026 |
| **Pessoas** | 2.1 | Formação fundamental obrigatória | INA + DGAEP + UA | Q4 2026 (lançamento); Q4 2028 (100%) |
| **Pessoas** | 2.2 | Consulta sindical (Circular DGAEP) | DGAEP + Sindicatos | Q1 2027 |
| **Pessoas** | 2.3 | CEIAP + AIDE-PT | AMA + INA + CIR | Q1 2027 |
| **Pessoas** | 2.4 | DIAs + ORIAs designados | AMA + SGPCM | Q4 2026 |
| **Ferramentas** | 3.1 | GovIA Portugal (plataforma) | AMA + IPN + INCM | Q3 2027 (piloto); Q1 2028 (pleno) |
| **Ferramentas** | 3.2 | GovIA Chat | AMA + IPN | Q1 2027 (beta); Q3 2027 (pleno) |
| **Ferramentas** | 3.3 | Orientações Public AI | AMA + CNCS | Q4 2026 |
| **Ferramentas** | 3.4 | Aquisição IA simplificada | IMPIC + ESPap + AMA | Q3 2027 |
| **Ferramentas** | 3.5 | Biblioteca de Casos de Uso + IP | AMA + ESPap | Q2 2027 (beta) |
| **Ferramentas** | 3.6 | RCAIA | AMA + CNPD + CIR | Q3 2027 |
| **Ferramentas** | 3.7 | Política Cloud revista | AMA + CTIC | Q4 2026 |

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
| AMALIA | Modelo de linguagem soberano português (PT-PT) — ANIA II.7 |
| ANIA | Agenda Nacional para a Inteligência Artificial (Jan 2026) |
| CADA | Comissão de Acesso aos Documentos Administrativos |
| CCP | Código dos Contratos Públicos |
| CCT | Carta dos Direitos Fundamentais (UE) |
| CEIAP | Centro de Excelência em IA da Administração Pública |
| CIR | Centro para a Inteligência Artificial Responsável (ANIA IV.3) |
| CNCS | Centro Nacional de Cibersegurança |
| CNPD | Comissão Nacional de Proteção de Dados |
| CRIA | Comité de Revisão de IA |
| CTIC | Conselho para as Tecnologias de Informação na Administração Pública |
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

Este draft de PIAAP é um **artefacto de discussão** preparado para a fase de síntese de ANIA. Antes da publicação como instrumento operacional, deve ser:

1. **Discutido com a tutela política** (Ministro das Finanças + Ministro da Modernização do Estado e da Administração Pública)
2. **Consultado com as Confederações Sindicais** (UGT + CGTP) e respetivas estruturas sindicais da Administração Pública
3. **Validado por uma Comissão Temática** com representação de AMA + Centro para a IA Responsável + DGAEP + INA + CNPD + Provedor de Justiça
4. **Alinhado com a Lei Nacional para a IA** (a aprovar — cf. Recomendação R22 do [portugal_ania_synthesis.md](portugal_ania_synthesis.md))
5. **Cross-checked com o AI Act** (Regulamento (UE) 2024/1689) e respetiva transposição nacional
6. **Calibrado em escopo** com a realidade da Administração Pública Local + Regional (este draft cobre Administração Central; extensão para AP Local/Regional carece de coordenação com ANMP + Câmaras Municipais)

Cronograma proposto para finalização:
- **Janeiro 2027** — versão consultiva publicada para comentário público (30 dias)
- **Março 2027** — versão final aprovada em Conselho de Ministros
- **Abril 2027** — publicação no Diário da República (Resolução do Conselho de Ministros ou Decreto-Lei conforme adequado)

---

*End of piaap_draft.md. This document complements [portugal_ania_synthesis.md](portugal_ania_synthesis.md) and [comparator_matrix.md](comparator_matrix.md). All three artefacts together constitute the synthesis stack for ANIA's 2027 evolution.*
