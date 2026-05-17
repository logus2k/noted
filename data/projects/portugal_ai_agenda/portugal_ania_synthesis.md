# Portugal's National AI Agenda — Synthesis and Critique

**Document type:** Executive synthesis grounded in 17-country comparator analysis.
**Anchor document:** Agenda Nacional para a Inteligência Artificial (ANIA), Action #20 of the Portugal Digital Strategy 2026-27, published January 2026.
**Evidence base:** [comparator_matrix.md](comparator_matrix.md) (Sections A/B/C) + 17 individual country summaries in `data/projects/portugal_ai_agenda/`.
**Companion artefact:** [piaap_draft.md](piaap_draft.md) — operational layer (Plano de IA para a Administração Pública) drafted in parallel and referenced from Recommendation 14.

---

## Executive summary

ANIA is a coherent and EU-anchored strategic document. It correctly positions Portugal under the EU AI Act regime, articulates 4 Eixos × 32 initiatives × 6 guiding principles, and commits to a named sovereign LLM ambition (AMALIA). Against the **16 international comparators analysed (17 jurisdictions including Portugal as anchor in the matrix)**, **ANIA covers 4 of the 6 common-denominator pillars at LEAD strength** (Infrastructure & Data via Eixo I; Talent & R&D via Eixo III + II.1-II.5; Business Adoption via Eixo II; Governance & International via Eixo IV) but has **two structural gaps** plus **28 specific delivery refinements (R1-R28)** that should be addressed in its 2027 refresh and beyond.

### The two structural gaps

1. **No standalone Public Administration pillar; PA-AI is distributed across three Eixos.** Portugal's PA-AI initiatives sit in **Eixo II (II.11 Centro de Excelência IA na AP + II.12 Concursos nacionais IA para AP + II.13 Guia CCP)** alongside Business-Adoption initiatives, in **Eixo III (III.1 Plano acelerado de formação de IA na AP / Doutor AP)**, and in **Eixo IV (IV.4-IV.7 governance + EU AI Act implementation)**. 10 of 17 jurisdictions LEAD on PA as a standalone pillar (UK Playbook, Australia APS Plan, Brazil PBIA Axis 3, Italy PA pillar, Spain Palanca 6, China "AI+ Governance", Qatar Smart-Govt, UAE "Govt of the Future", Singapore Govt enablers, USA CAIOC); 7 SHARE it (including Portugal). The distributed approach makes PA-AI delivery harder to track, fund, and operationally coordinate, even though Eixo II principle (3) elevates "Public Administration as a catalyst" rhetorically.

2. **No standalone Society pillar.** Portugal folds inclusion + trust + civic-AI into the 6 guiding principles + initiative III.8 (AI literacy action for citizens) rather than as a structural pillar. 4 jurisdictions LEAD on Society (Germany, Singapore, Australia, China), 11 SHARE it, and Portugal is among 2 of 17 (with USA) that fold-in. **Caveat:** USA folds-in deliberately (political minimalism on inclusion); Portugal's folding-in is harder to defend given its EU-anchored inclusion commitments and the absence of named civic-AI platforms (à la Germany's Civic Innovation Platform / Brazil's planned Actions 50-51 / Singapore's AI Verify Foundation).

**What ANIA does NOT have a gap on (correction vs earlier draft of this synthesis):** Infrastructure & Data. The official RCM 2/2026 text confirms **Eixo I (Infraestrutura e Dados)** is a standalone pillar with 4 named initiatives — I.1 Advanced Computing and AI Factory (EuroHPC/Deucalion), I.2 Gigafactory, I.3 Data spaces in critical areas, I.4 National Data Centre Plan. Portugal is comfortably in the 13-jurisdiction LEAD majority on this pillar; the recommendations below extend and deepen Eixo I rather than create a missing pillar.

### The five most actionable specific gaps

1. **No consolidated PA AI Playbook** — the single largest operational deficit. ANIA's PA-AI initiatives (II.11 + II.12 + II.13 + III.1 + IV.4-IV.7) exist as a distributed set but are not stitched into one operational document the way UK's 118-page Playbook or Australia's 30-page APS AI Plan are. **Addressed in companion artefact** [piaap_draft.md](piaap_draft.md), which builds on II.11 (Centro de Excelência IA na AP) rather than creating a new institution.
2. **No per-ministry CAIO architecture** — Australia mandates a Chief AI Officer per agency by 2026; Brazil has a centralised Federal AI Core; USA mandates per-agency CAIOs via OMB M-25-21. ANIA II.11 establishes the Centre of Excellence but does not mandate ministry-level CAIOs.
3. **No AI Review Committee** with cross-watchdog membership — Australia's 6-weekly committee with Information Commissioner + Privacy Commissioner + Ombudsman is the template. ANIA IV.4 (EU AI Act implementation) defines competent authorities but does not establish a recurring cross-watchdog review forum.
4. **No universal civil-servant AI training mandate with named timeline** — Australia commits to "all APS staff trained within 12 months" (Dec 2025 → Dec 2026); UK's 5-tier civil-servant segmentation is the alternative. ANIA III.1 (Doutor AP) trains an advanced cohort, not the universal civil-servant base.
5. **No GovAI-equivalent vendor-agnostic onshore brokerage platform** — Australia's GovAI hosts vendor models including OpenAI GPT onshore for Commonwealth-data-sovereignty use cases. ANIA II.11 implies platform consolidation but does not name a vendor-agnostic brokerage layer.

### Top-5 ranked recommendations (full set of 25 below)

| # | Recommendation | Effort | When | Source |
|---|---|---|---|---|
| **R12** | **Publish a Portuguese PA AI Playbook (PIAAP)** | M | 2026 H2 | UK Playbook + Australia APS AI Plan |
| **R2** | **Brazil-Portugal parallel-LLM coordination (AMALIA PT-PT + PBIA Action 9 PT-BR)** | L | 2026-2028 | Brazil PBIA (bilateral) |
| **R13** | **Per-ministry CAIO + separate AI Accountable Official** | S | 2026 H2 | Australia APS Plan |
| **R14** | **AI Review Committee (CNPD + Provedor de Justiça + CADA + sectoral)** | S | 2026 H2 | Australia APS Plan |
| **R22** | **Pass a Portuguese AI Law** | L | 2027-2028 | Japan Act No. 53/2025 |

The remaining 23 recommendations are grouped by the 6 universal pillars below + a cross-cutting pillar for the Japan AI Strategy 2022 imports (R26-R28).

---

## What ANIA does well (to preserve)

Before listing gaps it is important to anchor what should NOT change in ANIA's evolution:

- **EU AI Act anchoring** — clean, stable, and the right regulatory home for Portugal. Avoid drift toward UK pro-innovation / Australia sector-based / USA activist alternatives, all of which were considered by comparator countries and explicitly rejected by EU members.
- **Single coherent document of 22 pages** — easier for stakeholder communication than Brazil's 66-page PBIA or Germany's 2-document stack or Australia's 3-document stack.
- **6 named guiding principles** as a compact enumeration. Most comparators have implicit principle sets; Portugal's explicit 6 is more citable, and principle (3) "Public Administration as a catalyst" explicitly elevates the PA-AI thread that the structural Eixos then distribute.
- **4-Eixo structure with named Infrastructure & Data layer (Eixo I)** — readable, and crucially Eixo I groups the four foundational initiatives (I.1-I.4) into one coherent programme. The two remaining structural gaps (PA distribution + Society folding-in) are addressable by **consolidating PA-AI as a cross-Eixo programme + adding named Society cross-cutting subsections** (Option B) without breaking the 4-Eixo parsimony.
- **AMALIA as named sovereign Portuguese LLM** (II.7) — a strong identity move for the ~10M PT-PT speakers globally. Now correctly understood as the PT-PT complement to Brazil's PT-BR ambition, not in competition with it.
- **CPLP framing** as a natural diplomatic positioning for Portugal — even if currently under-operationalised in IV.7, the framing is correct.
- **Action #20 of Portugal Digital Strategy 2026-27 (EDN) positioning** — situates ANIA within a coherent national digital agenda rather than as a free-standing AI document. PIAAP and other operational layers should similarly anchor in the EDN action plans where possible.

---

## Methodology

Each country in the comparator set was analysed against a consistent template (header / quantitative anchors / structure / distinctive mechanisms / "what country X does that Portugal does NOT" / "what Portugal does that X does NOT" / style comparison / critique-lens conclusion). The **16 comparator countries** are: Argentina, USA, Finland, Qatar, UAE, Spain, Sweden, France, UK (2 docs consolidated), Italy, China, Singapore, Japan (2 docs consolidated: AI Strategy 2022 + AI Basic Plan 2025), Australia (3 docs consolidated), Germany (2 docs consolidated), and Brazil. Combined with Portugal as the anchor, this yields **17 jurisdictions in the matrix columns**. Each comparator was selected for offering a distinct national approach to a similar policy challenge; together they triangulate the design space Portugal sits in.

Cells in the comparator matrix (Section A/B/C) cite back to the country summaries. Recommendations below cite both the comparator matrix row and the source country (or countries) the move is drawn from.

A quote from UK's AI Opportunities Action Plan captures the framing question every comparator wrestles with: *"If this is to benefit the UK we must be an AI maker, not just an AI taker."* Portugal at its scale cannot be an AI maker on the same terms as the UK, USA, or China — but it can be a credible **AI maker in named wedges** (Portuguese-language LLM, Atlantic-Lusophone data sovereignty, AI for wildfire prediction, AI for ocean biodiversity, AI for healthcare via SNS24). The recommendations below operationalise that wedge-based AI-maker positioning.

---

## Recommendations grouped by universal pillar

### Pillar 1 — Infrastructure & Data (extending ANIA Eixo I)

**The structural framing:** ANIA's Eixo I (Infraestrutura e Dados) is a standalone pillar with 4 named initiatives (I.1 EuroHPC/AI Factory + I.2 Gigafactory + I.3 Data spaces in critical areas + I.4 National Data Centre Plan). The 4 recommendations below are **extensions and deep-dives within Eixo I**, not the creation of a missing pillar. They sharpen named deliverables (GAIA-X node, Standardisation Roadmap, SME compute access) and connect Eixo I to AMALIA (II.7) for full sovereign-AI stack coherence.

#### R1 — Anchor a Portuguese GAIA-X node + Atlantic-Lusophone Data Space

| Field | Value |
|---|---|
| Source | Germany (GAIA-X), Brazil (Sovereign Cloud Action 27), Australia (GovAI), UK (NDL) |
| Anchor ANIA initiative | I.3 (Data spaces in critical areas) + I.4 (National Data Centre Plan) — extends; cross-references **EDN Ação 8.7** (alinhamento com iniciativas europeias de espaços de dados, lead ARTE), **Ação 13.1** (Cloud Soberana) and **Ação 13.4** (Anel CAM + Anel Açores submarine cables — physical layer for an Atlantic-Lusophone Data Space) |
| Effort | M-L |
| When | 2026-2028 |
| Lead | APDC + INESC-TEC + AMA + IPN |
| Key risk | EU-data-space duplication if not aligned with European Data Strategy |

Germany leads GAIA-X. Brazil names Sovereign Cloud (Action 27) + IND (National Data Infrastructure) at Federal-Government scale. ANIA I.3 commits to sectoral data spaces (health, education, industry, PA) aligned with the European Data Spaces foreseen in DEP, and I.4 finalises the National Data Centre Plan. Portugal should **explicitly anchor a Portuguese GAIA-X node within the I.3 data-space programme** + Atlantic-Lusophone Data Space federation, positioning Portugal as the EU-side hub for Lusophone data sovereignty (CPLP variant of federated data infrastructure). The Açores can host a low-temperature ambient data centre node under I.4; mainland Portugal provides the EU-compliant compute layer; CPLP partner countries federate via the same standards. *Matrix references: A.4 row 4, C.1 row 2.*

#### R2 — Brazil-Portugal parallel-LLM coordination (AMALIA PT-PT + PBIA Action 9 PT-BR)

| Field | Value |
|---|---|
| Source | Brazil PBIA Action 9 |
| Anchor ANIA initiative | II.7 (AMALIA continuation) — adds bilateral coordination layer |
| Effort | L |
| When | 2026-2028 |
| Lead | MCTES + FCT + INESC-TEC ↔ MCTI + CGEE + CIT Digital (Brazil) |
| Key risk | Linguistic-variant mixing degrades both models |

**Critical framing:** AMALIA (PT-PT) and Brazil's PBIA Action 9 LLM (PT-BR) remain **separate models**. European and Brazilian Portuguese differ in vocabulary, clitic placement, gerund use, formal address, phonology, and idiomatic register sufficiently that a single mixed-corpus model would underperform on both audiences. The bilateral coordination is on **shared infrastructure and methodology, not a merged model**:

- Shared compute partnerships (Brazil's Top-5 supercomputer target + Portugal's Deucalion + reciprocal EuroHPC access)
- Shared safety + evaluation methodologies (per-variant Portuguese benchmarks)
- Shared RLHF protocols + alignment frameworks
- Bilateral training-pipeline knowledge transfer
- Joint CPLP umbrella for PALOP variants (each closer to PT-PT with local lexicon)
- Coordinated international advocacy for Portuguese-language AI representation

This is the **single highest-leverage cross-comparator opportunity in the entire 17-country set**. No other pairing in this comparator set has shared language family + named sovereign-LLM initiatives + diplomatic umbrella (CPLP). *Matrix references: A.4 row 2, C.1 row 4.*

#### R3 — Commission a Portuguese AI Standardisation Roadmap (DIN + DKE analogue)

| Field | Value |
|---|---|
| Source | Germany DIN+DKE Standardisation Roadmap |
| Anchor ANIA initiative | IV.6 (EU AI Act implementation guide + standards + risk-assessment tools) — extends with named roadmap deliverable |
| Effort | M |
| When | 2026 H2 → 2027 H1 |
| Lead | IPQ + APQ + IPN-LIT + IT + IST |
| Key risk | Duplicating EU CEN-CENELEC work without value-add |

Germany's DIN + DKE published an AI Standardisation Roadmap at the 2020 Digital Summit. It maps current and future standardisation needs (safety, robustness, transparency, non-discrimination) and drives subsequent implementation programmes. Portugal should commission an equivalent via IPQ + APQ + IPN-LIT + IT + IST, contributing Portuguese specifics into EU CEN-CENELEC standardisation work. *Matrix reference: A.4 row 6, C.1 row 5.*

#### R4 — Formalise Deucalion access for SMEs + researchers + anchor EuroHPC industrial computer participation

| Field | Value |
|---|---|
| Source | Germany (JUPITER + EuroHPC industrial computer), Brazil (Action 4 Pro-Infra AI) |
| Anchor ANIA initiative | I.1 (Advanced Computing and AI Factory/EuroHPC) + I.2 (Gigafactory) — extends with named access policy. **Dual-anchored at EDN Ação 13.2 (Plano Nacional de Centros de Dados + GigaFactory + revisão da Estratégia Nacional de Semicondutores RCM 12/2024)** |
| Effort | M |
| When | 2026 H2 onwards |
| Lead | FCT + FCCN + MACC |
| Key risk | Deucalion saturation; need clear allocation policy |

ANIA I.1 commits to expanding national supercomputing capacity (Deucalion + EuroHPC alignment) and I.2 commits to attracting a national Gigafactory. Today, only ~5% of MareNostrum5 capacity (research) + 8-9% (innovation) is allocated to Portugal — explicitly flagged as insufficient in the ANIA text. Brazil names AI service centres (Action 4 Pro-Infra AI for ICTs) as the SME-and-researcher compute access mechanism. Germany commits to expanding national HPC (JUPITER) + EuroHPC industrial computer. Portugal should **formalise SME and researcher access pathways to Deucalion under I.1** (named percentage allocations + booking procedure + reimbursement scheme) + position the I.2 Gigafactory as anchor partner in the EuroHPC industrial computer initiative. *Matrix references: A.4 row 1, C.1 rows 1+7.*

### Pillar 2 — Talent & R&D

#### R5 — Name 4 Portuguese AI Centres of Excellence with regional federalism

| Field | Value |
|---|---|
| Source | Germany (6 named: DFKI/BIFOLD/Lamarr/ScaDS.AI/MCML/TUEAI), Brazil (CPA + INCT-AI), Japan (3 named: RIKEN AIP + AIST AIRC + NICT) |
| Anchor ANIA initiative | II.5 (Sectoral AI Centres — already commits to consortium-based innovation in Health, Education, Industrial sectors) — extends with named geographic federalism + 4-centre architecture |
| Effort | M-L |
| When | 2026 H2 → 2027 |
| Lead | FCT + CCDR (regional coordination commissions) + universities |
| Key risk | Federalism mapping (Portugal NUTS-II ≠ German Länder) |

Germany names 6 federal-Länder co-funded AI Centres of Excellence with explicit geographic distribution (Berlin, Munich, Dresden-Leipzig, Tübingen, Dortmund-St.Augustin, Kaiserslautern-Saarbrücken). Brazil has CPA (Applied Research Centers in AI) + INCT-AI. Portugal should name **4 Portuguese AI Centres of Excellence** with domain specialisation:

- **Coimbra (UC + INESC-TEC)** — Health AI
- **Lisbon (IST + INESC-ID)** — Energy + Aerospace AI
- **Porto (U.Porto + INESC-TEC)** — Industry 4.0 AI
- **Aveiro (UA + IT)** — Telecoms + Materials AI

Federal-equivalent funding via FCT + Regional Coordination Commissions (CCDRs) co-funding. *Matrix reference: C.2 row 2.*

#### R6 — Establish a Portuguese AI Breakthrough Programme (SPRIND-equivalent)

| Field | Value |
|---|---|
| Source | Germany SPRIND + UK ARIA + USA DARPA |
| Anchor ANIA initiative | II.1 (Support for fundamental research projects, particularly of national strategic interest) + II.2 (Strengthen collaboration with international networks) — extends with mission-management agency layer |
| Effort | M |
| When | 2027-2028 |
| Lead | FCT + ANI + Conselho Coordenador de C&T |
| Key risk | Programme-director autonomy if it remains under standard public-sector governance |

Germany has SPRIND (Federal Agency for Disruptive Innovation), modelled on DARPA + ARIA. Portugal should establish an AI Breakthrough Programme with DARPA-style mission-management autonomy + 5-7 year horizons + programme-director discretion. Anchor it within FCT or ANI but ring-fence governance. Initial mission examples: Portuguese-language LLM at frontier scale; wildfire-prediction AI; ocean-biodiversity AI; Atlantic-cable AI security. *Matrix references: C.2 row 1, Section C.3 row 4.*

#### R7 — National AI Skills Compact (industry + academia + government)

| Field | Value |
|---|---|
| Source | Australia BCA Action 3 |
| Anchor ANIA initiative | III.2 (National Smart Skills Framework — already maps existing/emerging skills) + III.3 (Recognition and expansion of Micro-credentials and CTESP) — extends with industry-academia-government compact + IEFP/ANQEP coordination + EDN Ação 17 (Pacto de Competências Digitais) integration |
| Effort | S-M |
| When | 2026 H2 → 2027 H1 |
| Lead | ANQEP + IEFP + universities + AIP + COTEC |
| Key risk | Stakeholder co-design fatigue |

Australia's BCA proposes a National AI Skills Compact modelled on NSW's Digital Skills Compact, with two streams: (a) national AI apprenticeship model (drawing on Germany's dual VET + Singapore's AIAP); (b) industry-led microcredentials. Portugal should establish a Portuguese AI Skills Compact integrating ANIA III.1/III.2 + IEFP + universities + industry. *Matrix reference: C.2 row 4.*

#### R8 — Portuguese AI Olympiad + Lifes-equivalent teacher training

| Field | Value |
|---|---|
| Source | Brazil (AI Olympiad Action 14; Lifes Action 15) |
| Anchor ANIA initiative | III.7 ("AI Generation" campaign to motivate young people) + III.8 (AI literacy action for citizens) — extends with school-level Olympiad track + teacher-training laboratories under ESEs; EDN Ação 18 (Programa Nacional Raparigas STEM) and Ação 19 (Digital e IA na Educação) as parallel coordination layers |
| Effort | S |
| When | 2026 H2 (Olympiad) + 2027 (Lifes) |
| Lead | DGE + Olimpíadas Portuguesas de Informática + ESEs |
| Key risk | Low initial participation; needs sustained promotion |

Brazil's AI Olympiad (Action 14) + Lifes (Interdisciplinary Laboratories for Educator Training, Action 15) are concrete national-mobilisation mechanisms for AI literacy and teacher AI training. Portugal should mirror via Olimpíadas Portuguesas de IA + ESE-anchored AI teacher-training laboratories. *Matrix references: C.5 row 1, C.2 row 6.*

### Pillar 3 — Business Adoption

#### R9 — PME 4.0 AI Uptake Programme (Mittelstand 4.0 analogue)

| Field | Value |
|---|---|
| Source | Germany Mittelstand 4.0 Centres + Brazil Action 44 + Australia AI Adopt Program |
| Anchor ANIA initiative | II.9 (AI in SMEs — using IFIC) + II.10 (PME.IA — National Platform of AI Products for SMEs, low-code/no-code) — extends with regional advisor network per NUTS-II + EDN Ação 14.2 (Coaching 4.0 Vouchers PME, lead ARTE) as the voucher-instrument vehicle |
| Effort | M |
| When | 2026 H2 → 2028 |
| Lead | IAPMEI + AIP + sectoral associations + IEFP |
| Key risk | Reaches only digitally-advanced PMEs; rural PME exclusion |

Germany's Mittelstand 4.0 Centres of Excellence + AI trainer programme set the template. Brazil's Action 44 (AI for MSMEs + MEIs) + Action 49 (Brasil Mais Produtivo) localise it. Australia's NAIC + AI Adopt Program is the operational analogue. Portugal needs a PME 4.0 / ENI AI Uptake Programme operated via IAPMEI + AIP + sectoral associations with train-the-trainer pathways + AI advisor networks per NUTS-II region. *Matrix reference: C.3 row 2.*

#### R10 — AI Commercialisation Accelerator Portugal (AICA + Catapult + Embrapii analogues)

| Field | Value |
|---|---|
| Source | Australia AICA (BCA Action 15) + UK Catapult Network + Brazil Embrapii integration |
| Anchor ANIA initiative | II.5 (Sectoral AI Centres) + II.6 (National platform 'Opportunities in AI') — extends with explicit consolidation mandate ("AI Bridge Portugal" naming layer) + EDN Ação 15 (Apoios à Inovação e Empreendedorismo Digital) as the broader instrument context |
| Effort | M |
| When | 2027 |
| Lead | ANI + COTEC + CoLABs |
| Key risk | Yet-another-bridge-organisation; needs explicit consolidation mandate |

Australia BCA Action 15 proposes an AI Commercialisation Accelerator (AICA) modelled on UK Catapult Network. Brazil integrates via Embrapii. Portugal already has the institutional bones (ANI + COTEC + CoLABs) but needs consolidation into a named "AI Bridge Portugal" with explicit IP-protection and commercialisation pathways. *Matrix reference: C.3 row 4.*

#### R11 — AI for Portuguese Sectoral Champions

| Field | Value |
|---|---|
| Source | UK named champions in life sciences/financial services/creative industries + Australia sectoral focus |
| Anchor ANIA initiative | II.5 (Sectoral AI Centres — Health, Education, Industrial sectors already named; extend with named Portuguese sectoral picks: Health & Pharma, Tourism, Blue Economy, Footwear/Textiles, Aerospace) + EDN Ação 14.4 (Comércio Digital — internacionalização AICEP) as the export-promotion vehicle |
| Effort | L |
| When | 2026-2030 |
| Lead | Per-sector ministry + AICEP for FDI attraction |
| Key risk | Sectoral picking-winners critique |

UK names AI Sector Champions in life sciences, financial services, creative industries. Portugal's natural picks (per ANIA's strengths analysis): **Health & Pharmaceuticals + Tourism + Blue Economy + Footwear/Textiles + Aerospace (via Edisoft)**. Each champion programme has named industry lead, public-funding line, export ambition, and 3-year milestones. *Matrix reference: A.2 row 7, C.3 row 3.*

### Pillar 4 — Public Administration (consolidating ANIA's distributed PA-AI thread)

**The structural framing:** ANIA does not have a standalone PA pillar; instead, PA-AI initiatives are distributed across **Eixo II (II.11 + II.12 + II.13), Eixo III (III.1 Doutor AP), and Eixo IV (IV.4 EU AI Act implementation + IV.5 sandboxes + IV.6 guide + IV.7 intl coop)**. The 6 recommendations below either anchor in those existing initiatives (R12 builds on II.11; R13 extends II.11; R16 extends III.1; R17 extends IV.6) or add named cross-cutting deliverables (R14 AI Review Committee under IV.4; R15 GovAI Portugal as a new platform within II.11). The companion artefact [piaap_draft.md](piaap_draft.md) is the consolidation vehicle.

#### R12 — Publish the PIAAP (Plano de IA para a Administração Pública)

| Field | Value |
|---|---|
| Source | UK AI Playbook (118pp, mandatory) + Australia APS AI Plan (30pp Trust/People/Tools) |
| Anchor ANIA initiative | II.11 (AI Centre of Excellence in PA) + consolidates II.12, II.13, III.1, IV.4-IV.7 into one operational document |
| Effort | M |
| When | 2026 H2 (publication) → 2027 H2 (full operationalisation) |
| Lead | AMA + DGAEP + INA + Centro para a IA Responsável |
| Key risk | Stakeholder resistance from line ministries used to discretion |

**The single highest-leverage recommendation in this synthesis.** Portugal needs an operational PA layer that stitches together ANIA's already-committed PA-AI initiatives. The PIAAP follows Australia APS Plan structure (Trust / People / Tools × ~15 deliverables) but adopts UK Playbook's 10 principles + case-studies appendix. **Detailed draft in companion artefact [piaap_draft.md](piaap_draft.md), which anchors each deliverable to a named existing ANIA / EDN initiative rather than inventing fresh institutions.** *Matrix reference: C.4 row 3.*

#### R13 — Per-ministry CAIO + separate AI Accountable Official

| Field | Value |
|---|---|
| Source | Australia APS Plan + USA OMB M-25-21 + Brazil Federal AI Core |
| Anchor ANIA initiative | II.11 (Centro de Excelência IA na AP) — extends with named per-ministry roles |
| Effort | S |
| When | 2026 H2 |
| Lead | AMA + Ministério das Finanças |
| Key risk | Role conflation in smaller ministries |

Australia's APS Plan separates **Chief AI Officer** (drives adoption + strategic change) from **AI Accountable Official** (governance + compliance). USA mandates per-agency CAIOs via M-25-21. Brazil has a centralised Federal AI Core. Portugal should mandate per-ministry CAIO + separate AI Accountable Official by end-2026, with small ministries permitted to combine roles. *Matrix reference: C.4 row 1.*

#### R14 — AI Review Committee (cross-watchdog)

| Field | Value |
|---|---|
| Source | Australia APS Plan AI Review Committee |
| Anchor ANIA initiative | IV.4 (EU AI Act implementation — competent authorities + coordination model) + IV.3 (Centro para IA Responsável) — adds recurring cross-watchdog forum |
| Effort | S |
| When | 2026 H2 → full maturity 2027 |
| Lead | Centro para a IA Responsável (secretariat) + member bodies |
| Key risk | Slow throughput; needs <6-weekly cadence |

Australia's AI Review Committee meets every 6 weeks, provides non-binding advice on high-risk AI uses, draws membership from Information Commissioner + Privacy Commissioner + Ombudsman + sectoral. Portuguese analogue: **CNPD + Provedor de Justiça + CADA + ERSE + ANACOM + ASAE sectoral**, with Centro para a IA Responsável as secretariat. Anchor under ANIA IV.4 with explicit EU AI Act Article 26 alignment. *Matrix reference: C.4 row 4.*

#### R15 — GovAI Portugal (vendor-agnostic onshore AI brokerage platform)

| Field | Value |
|---|---|
| Source | Australia GovAI + Brazil Sovereign Cloud + UK i.AI Incubator |
| Anchor ANIA initiative | II.11 (Centre of Excellence in PA) — adds a named vendor-agnostic platform deliverable; references I.4 (National Data Centre Plan) for hosting + **EDN Ação 13.1 (Plano para o Desenvolvimento de uma Cloud Soberana)** as the underlying infrastructure to ride |
| Effort | M |
| When | 2027 H1 |
| Lead | AMA + IPN + INCM |
| Key risk | Procurement complexity; vendor-lock-in if not truly multi-model |

Australia's GovAI is a vendor-agnostic onshore platform hosting multiple LLMs (including onshore OpenAI GPT). Distinct from AMALIA (sovereign LLM ambition): **GovAI Portugal is the day-to-day platform every ministry uses; AMALIA is the long-term sovereign-LLM identity**. This pair architecture is the right design for Portugal. *Matrix reference: C.4 row 5.*

#### R16 — Mandatory universal civil-servant AI training within 12-18 months

| Field | Value |
|---|---|
| Source | Australia APS Plan (mandatory all-APS within 12 months) + UK 5-tier civil-servant segmentation |
| Anchor ANIA initiative | III.1 (Plano acelerado de formação de IA na AP / Doutor AP) — extends from advanced cohort to universal civil-servant mandate |
| Effort | S |
| When | 2026 H2 → 2028 H1 |
| Lead | INA + DGAEP + Centro para a IA Responsável |
| Key risk | Variable-quality delivery without standardised curriculum |

Australia mandates "all APS staff trained in AI fundamentals within 12 months" of policy update. UK Playbook has 5-tier segmentation (executive / technical lead / digital / general / specialist). Portugal should mandate equivalent: every PA staff member (~700K state employees) completes AI fundamentals training within 18 months of PIAAP publication. Curriculum delivered via INA + DGAEP + Universidade Aberta. *Matrix reference: C.4 row 2.*

#### R17 — Central register of AI impact assessments

| Field | Value |
|---|---|
| Source | Australia APS Plan central register + UK ATRS |
| Anchor ANIA initiative | IV.6 (EU AI Act implementation guide + risk-assessment tools) — adds named central register deliverable |
| Effort | S-M |
| When | 2027 H1 |
| Lead | AMA + CNPD |
| Key risk | Update lag rendering register stale |

Australia mandates a central register of completed AI impact assessments (FOCI, IRAP, cyber-security, impact) so that agencies can reference/reuse prior evaluations rather than re-conducting. UK's ATRS is the mandatory transparency analogue. Portugal should establish a **Registo Central de Avaliações de Impacto de IA** under AMA, with EU AI Act Article 29 alignment. *Matrix references: C.4 rows 6+7, A.5 row 5.*

### Pillar 5 — Society (addressing one of ANIA's two remaining structural gaps)

**The structural framing:** ANIA folds Society into the 6 guiding principles + III.8 (AI literacy action for citizens). Only Portugal and USA fold-in across the 17-jurisdiction set; USA does so deliberately on political-minimalism grounds, Portugal less defensibly given its EU-anchored inclusion commitments. Whether Society becomes a standalone 5th Eixo (Option A) or stays folded-in with named cross-cutting subsections added (Option B — recommended draft direction) is the **pillar-selection question** deferred to final-report discussion (see *Pillar selection / omission* section below).

**Option B operationalisation** (the synthesis recommendation): add a named **"Sociedade e Inclusão" cross-cutting subsection within Eixo IV (Responsabilidade e Ética)**, integrating R18-R21 below as the named civic-AI / observatory / cultural-heritage layer. This avoids breaking the 4-Eixo parsimony while addressing the gap with named operational deliverables. The 4 recommendations below are written to support either structure (Option A or Option B).

#### R18 — Establish the Observatório Português de IA no Trabalho e na Sociedade

| Field | Value |
|---|---|
| Source | Germany AI Observatory for Work and Society |
| Anchor ANIA initiative | IV.1 (Incentives for Responsible AI Research — explicitly includes AI Economics and Work Impact) + IV.3 (Centre for Responsible AI) — adds named observatory + tripartite layer |
| Effort | M |
| When | 2026 H2 → 2027 |
| Lead | DGEEP + Centro para a IA Responsável + UGT + CGTP + CIP |
| Key risk | Capture by single stakeholder constituency |

Germany has a Federal AI Observatory in the Ministry of Labour focused on AI's labour and society impact. It develops indicators, monitors trends, includes unions + civil society + business + science. Portugal should establish a named equivalent under DGEEP (Directorate-General for Employment) + Centro para a IA Responsável + tripartite social-dialogue representation (UGT + CGTP + CIP). *Matrix reference: C.5 row 4.*

#### R19 — Civic-AI participation platforms (Germany Civic AI triad + Brazil Action 50-51 analogues)

| Field | Value |
|---|---|
| Source | Germany (Civic Innovation Platform + Civic Data Lab + Civic Tech Labs for Green) + Brazil (Action 50-51 planned) |
| Anchor ANIA initiative | III.6 (National AI Week) + III.8 (AI literacy action for citizens) — adds participatory civic-AI fora |
| Effort | M |
| When | 2027 |
| Lead | Fundação Calouste Gulbenkian + INCoDe.2030 + Centro para a IA Responsável |
| Key risk | Volunteer-fatigue cycle |

Germany has three named civic-AI initiatives: Civic Innovation Platform (connecting civil society to AI development), Civic Data Lab (preparing civil-society datasets), Civic Tech Labs for Green (participatory green-tech tools). Portugal should mirror via Fundação Calouste Gulbenkian + INCoDe.2030 + AMA partnership, with a Civic AI Forum that runs annually. *Matrix reference: C.5 row 5.*

#### R20 — Universal AI literacy programme + Portuguese AI Olympiad (already R8)

This is folded under R8 above.

#### R21 — Atlantic-Lusophone cultural-heritage AI

| Field | Value |
|---|---|
| Source | Australia (National Archives) + UK (Rec 13 British media training corpus) + Brazil (Amazon biome AI) |
| Anchor ANIA initiative | I.3 (Data spaces in critical areas) — adds cultural-heritage as a named sectoral data space; feeds AMALIA II.7 corpus |
| Effort | M |
| When | 2027-2030 |
| Lead | DGLAB + Biblioteca Nacional + IGESPAR + universities |
| Key risk | Copyright-cleared corpus complexity |

UK Rec 13 proposes a copyright-cleared British media asset training dataset built with National Archives + Natural History Museum + British Library + BBC. Portugal's analogue: Atlantic-Lusophone cultural-heritage AI corpus built with DGLAB + Biblioteca Nacional + IGESPAR + RTP + CPLP partner archives. *Matrix reference: C.5 row 6.*

### Pillar 6 — Governance & International

#### R22 — Pass a Portuguese AI Law

| Field | Value |
|---|---|
| Source | Japan Act No. 53/2025 (only country in comparator set with dedicated AI Act) |
| Anchor ANIA initiative | IV.4 (Implementation of the EU AI Act) — extends from regulatory implementation to dedicated primary legislation |
| Effort | L |
| When | 2027-2028 (legislative cycle) |
| Lead | Assembleia da República + Ministério da Justiça + Ministério da Economia |
| Key risk | EU AI Act pre-emption; needs to complement not duplicate |

Japan passed **Act No. 53 of 2025** — the only national jurisdiction in the 17-country comparator set with dedicated AI primary legislation. The Act establishes principles, the AI Strategic Headquarters, the AI Basic Plan obligation, and gives parliamentary anchor for AI policy. Portugal could pass a Lei Nacional para a Inteligência Artificial that (a) transposes EU AI Act provisions, (b) names CNPD + Centro para a IA Responsável + AESIA-equivalent (or Portugal's chosen body) as competent authorities, (c) mandates the PIAAP, (d) commits AMALIA funding, (e) establishes the AI Review Committee. *Matrix references: A.5 rows 1+4.*

#### R23 — CPLP AI Framework Arrangement + Brazil-Portugal Tech Prosperity Deal

| Field | Value |
|---|---|
| Source | Australia (Tech Prosperity Deal with USA, MoU Singapore, Framework India) + Brazil (S-S framing) |
| Anchor ANIA initiative | IV.7 (Cooperação internacional e diplomacia tecnológica) — extends with named bilateral + multilateral instruments + **EDN Ação 2.5 (Estabelecimento de parcerias internacionais na área do Digital, com referência explícita a países de língua oficial portuguesa, lead Governo de Portugal + ARTE + DGE)** as the operational vehicle |
| Effort | M |
| When | 2026 H2 (Brazil-Portugal bilateral) → 2027 (CPLP) |
| Lead | MNE + Instituto Camões + MCTES |
| Key risk | CPLP partner capacity for instrument-level commitments |

Australia has bilateral instruments at instrument level: Tech Prosperity Deal with USA, MoU with Singapore, Framework Arrangement with India, strategic partnerships with UK + ROK. Portugal should mirror via:
- **Brazil-Portugal Tech Prosperity Deal** — anchor instrument for the bilateral LLM coordination, sovereign-cloud federation, talent exchange (see R2)
- **CPLP AI Framework Arrangement** — multilateral instrument extending the bilateral to all 9 Lusophone countries
- **Spain-Portugal Iberian AI Cooperation** — natural EU-side bilateral for compute + LLM consortium

*Matrix references: A.1 row 7, C.6 row 3.*

#### R24 — Adopt AI Verify (Singapore directly importable)

| Field | Value |
|---|---|
| Source | Singapore NAIS 2.0 + AI Verify Foundation |
| Anchor ANIA initiative | IV.3 + extends |
| Effort | S |
| When | 2026 H2 |
| Lead | Centro para a IA Responsável + IPQ |
| Key risk | Local adaptation requirements (Portuguese language) |

Singapore's **AI Verify** is an open-source toolkit for trustworthy AI testing, with a global Foundation (90+ corporate members). Portugal should adopt it as the technical-testing layer for Centro para a IA Responsável + advocate for Portuguese-language extension. *Matrix references: A.4 row 3, C.6 row 7.*

#### R25 — Mandatory Algorithmic Transparency Standard (PT-ATRS)

| Field | Value |
|---|---|
| Source | UK ATRS (Algorithmic Transparency Recording Standard) |
| Anchor ANIA initiative | IV.4 + IV.6 + new |
| Effort | S-M |
| When | 2027 H1 |
| Lead | Centro para a IA Responsável + AMA |
| Key risk | Compliance lag in smaller agencies |

UK's ATRS is a mandatory transparency standard for in-scope public bodies (publishes the AI tool, its use, its dataset, its risk evaluation). Portugal should establish **Norma Portuguesa de Transparência Algorítmica (NPTA)** under EU AI Act Article 26 deployer obligations. *Matrix references: A.5 row 5, C.4 row 7.*

### Cross-cutting Pillar — Japan AI Strategy 2022 imports (Strategic Objective 0 + Digital Twins + Quantified Education)

The following 3 recommendations are added 2026-05-17 after integration of Japan's AI Strategy 2022 (Apr 2022, pre-statutory Cabinet Office document; superseded operationally by the AI Act + Basic Plan 2025 but contributing conceptual scaffolding worth importing independently). They sit cross-cutting across multiple Eixos rather than under any single one.

#### R26 — Portuguese Strategic Objective 0: National + Planetary Resilience (Crisis-AI axis)

| Field | Value |
|---|---|
| Source | Japan AI Strategy 2022 p.4-18 (Strategic Objective 0) |
| Anchor ANIA initiative | New cross-cutting axis prepended to the 4 Eixos; anchors operationally in II.5 (Sectoral AI Centres — Health/Disaster sectors) + I.3 (Data spaces critical areas — disaster + climate) + IV.1 (Responsible AI research includes "AI Economics and Work Impact"); cross-references EDN Ação 4 (ENC) + Ação 13.4 (Anel CAM + Açores submarine cables) |
| Effort | M-L |
| When | 2026 H2 (axis formalisation) → 2028 (operational deployment) |
| Lead | ANEPC (Autoridade Nacional de Emergência e Proteção Civil) + ICNF + IPMA + DGS + Centro para a IA Responsável |
| Key risk | Cross-Eixo accountability dilution if no single lead designated |

Japan's AI Strategy 2022 prepended **Strategic Objective 0 — National Resilience + Planetary Resilience** to the four 2019-inherited objectives, with named imminent crises: large-scale earthquakes, volcanic eruptions, climate-driven heavy rain, pandemics. Portugal faces directly analogous crises: **annual wildfires** (the single highest-damage recurring event), **Atlantic seismic risk** (1755 Lisbon precedent + active Açores volcanism), **climate-driven floods + drought**, **pandemic preparedness**. The recommendation is to formally prepend a **"Objectivo Estratégico 0 — Resiliência Nacional + Planetária"** to ANIA, operationalised through three streams:

- **AI for wildfire prediction + prevention + response** (ICNF + IPMA + Proteção Civil + universities) — already mentioned in synthesis R6 example missions; this elevates it to a structural axis
- **AI for Atlantic seismic + Açores volcanic monitoring** (IPMA + Universidade dos Açores + INESC-TEC) — Digital Twin coupling per R27 below
- **AI for pandemic preparedness + One Health surveillance** (DGS + INSA Ricardo Jorge + SNS24 integration)

The Japanese frame also includes **"Planetary Resilience"** — "AI for Nature-Positive Economy" — that fits Portugal's Blue Economy + Atlantic biodiversity wedge naturally. *Matrix references: A.6 rows 3+5 (newly enriched 2026-05-17).*

#### R27 — Digital Twin Portugal (architectural primitive for PA, crisis response, and territorial planning)

| Field | Value |
|---|---|
| Source | Japan AI Strategy 2022 p.12-13 (citing Virtual Singapore + India Stack) |
| Anchor ANIA initiative | I.3 (Data spaces critical areas) + I.4 (National Data Centre Plan) — extends; **dual-anchored at EDN Ação 8.6** (Aumento da qualidade e quantidade de dados a nível local — explicitly commits to "Desenvolvimento de 5 Gémeos Digitais para simulação, monitorização e prevenção de situações no mundo real" + plataformas de gestão urbana para 129 municípios) + EDN Ação 9 (PAGE — Plataforma de Apoio à Gestão do Estado) |
| Effort | M |
| When | 2026 H2 (Ação 8.6 starts 2S 2025 → 2S 2026; PIAAP additional gov-AI Digital Twin layer 2027 H1) |
| Lead | ARTE + INE + INESC-TEC + IGESPAR + ANPC |
| Key risk | Fragmentation across 5 separate Gémeos Digitais without unified data-architecture; needs single technical authority |

EDN Ação 8.6 **already commits to 5 Gémeos Digitais** + urban-management platforms for 129 municípios. Japan's AI Strategy 2022 (p.12-13) provides the **over-arching architectural framing** for elevating Digital Twins from sub-deliverables to a **cross-cutting Eixo-I architecture**:

> "Digital Twins are not only a disaster countermeasure but also a foundation for national administration. It can also be a platform for improving the efficiency of private services and creating new services and a flexible lifestyle." [Strategy 2022 p.13]

Three named Portuguese Digital Twin priorities to consolidate the existing EDN Ação 8.6 commitments:

1. **Digital Twin Atlântico-Açores** — seismic + volcanic + meteo + ocean state (links to R26 above + R21 cultural-heritage data; coordinates with the Anel CAM + Anel Açores submarine cables under EDN Ação 13.4)
2. **Digital Twin Floresta + Wildfire** — fuel load + ignition risk + spread prediction + recovery planning (ICNF + universities + IPMA)
3. **Digital Twin Cidades 129** — urban-management data + traffic + utilities + public-service flows for the 129 municipalities under Ação 8.6 (ARTE + ANMP + Câmaras Municipais)

PIAAP deliverable 3.5 (Biblioteca de Casos de Uso) should integrate Digital Twin reference architectures as a named pattern. *Matrix reference: C.1 row 2 (newly enriched 2026-05-17 to capture Strategy 2022 Digital Twin foundation framing).*

#### R28 — Quantified per-cohort annual education targets in Eixo III

| Field | Value |
|---|---|
| Source | Japan AI Strategy 2022 p.28-31 (named annual cohort targets with 2025 realisation) |
| Anchor ANIA initiative | III.2 (National Smart Skills Framework — already maps skills) + III.3 (Micro-credentials + CTESP) + III.6 (National AI Week) — extends with quantified per-cohort annual targets; coordinates with EDN Ação 17 (Pacto de Competências Digitais) |
| Effort | S-M |
| When | 2026 H2 (target-setting + decree) → 2030 (realisation year) |
| Lead | DGES + IEFP + DGEEC + ANQEP + ARTE (Ação 17 coordination) |
| Key risk | Targets without funded delivery vehicles become aspirational metrics |

Japan's AI Strategy 2022 sets the most quantified human-capital targets in the comparator set:

| JP Cohort | JP Annual target | PT analogue target (suggested, ~1/10 to ~1/15 scale per population) |
|---|---|---|
| High-school grads with basic AI/data-science literacy | ~1,000,000 | ~50,000 (Portugal high-school grad cohort is ~85K/yr per INE; aim for 60% AI-literacy coverage) |
| University + technical college grads with elementary AI/DS | ~500,000 | ~25,000 (PT university+CTeSP grad cohort ~75K/yr; aim for 1/3 with elementary AI/DS) |
| Applied AI/DS (specialised fields) | ~250,000 | ~10,000 |
| Expert (innovation-creators) | ~2,000 (of which ~100 top-class) | ~500-1,000 (of which ~25 top-class) |
| Recurrent education for working adults | ~1,000,000 | ~50,000 (coordinate via IEFP + Pacto de Competências Digitais) |

ANIA III.2 + III.3 currently commit to mapping/recognising/expanding without quantified annual cohort targets. Adding these would elevate Eixo III from process commitments to outcome-anchored commitments, matching Japan's pattern while remaining proportional to Portuguese scale. **Realisation target year: 2030.** *Matrix reference: C.2 row 4 (quantified skills-gap row).*

---

## What Portugal should NOT copy (anti-patterns from the comparator set)

These are concrete features observed in comparator countries that Portugal should explicitly avoid:

- **The 3-document fragmented strategic stack (Australia model).** Australia's industry (BCA) + government (NAP) + operational (APS) trio has internal contradictions (TDM exception ban in NAP vs BCA push for one). Portugal should keep PIAAP and ANIA in coordinated parallel, drafted from common premises.
- **Sector-based anti-EU AI Act regulatory stance (UK + Australia models).** Portugal correctly anchors to EU AI Act. The UK pro-innovation principles and Australia sector-based approaches would dilute Portugal's regulatory clarity.
- **The 59.9% concentration on business innovation (Brazil model).** Brazil's R$13.79B Axis 4 is industrial-policy-heavy at the expense of operational PA modernisation. Portugal should keep pillar balance.
- **Frontier-AI ambitions at scale Portugal cannot fund (UK / USA / China).** Portugal's "AI maker" wedges must be **named, narrow, defensible** (Portuguese-language LLM, Atlantic-Lusophone data sovereignty, AI for wildfire prediction, AI for ocean biodiversity, AI for Health via SNS24). General "frontier AI leadership" is not in scope.
- **Single-Minister-of-AI political concentration (UAE model).** UAE's Minister of State for AI is a strong branding move but concentrates risk in one personality. Portugal should distribute via CAIO + AI Accountable Official + AI Review Committee.
- **"Global South lead" framing (Brazil model).** Portugal is an EU member with EU obligations. Adapt to "Atlantic-Lusophone AI Bridge" or "CPLP AI Coordinator" framing instead.
- **Indigenous Data Sovereignty framing wholesale (Australia model).** Portugal does not have an Indigenous population with the same legal status. Adapt to Atlantic-Lusophone cultural-heritage AI + diaspora data + language data.
- **Five Eyes / AUKUS framing (Australia + UK + USA models).** Not applicable. Portugal's natural cluster is NATO + EU + CPLP.
- **Cheap merged-corpus Lusophone LLM (the temptation).** PT-PT and PT-BR are linguistically distinct. AMALIA (PT-PT) and Brazil's Action 9 (PT-BR) must remain separate models. (See R2 above + memory note on this rule.)

---

## Pillar selection / omission — deferred to final-report discussion

Per user direction (2026-05-16), the question of whether ANIA's 4-Eixo structure should evolve is **explicitly deferred for discussion at final-report time**. With the RCM 2/2026 confirmation that Eixo I (Infraestrutura e Dados) IS a standalone pillar, the two remaining structural gaps are (a) PA-AI distributed across three Eixos rather than consolidated, and (b) Society folded into the 6 guiding principles rather than as a standalone pillar. Three options to weigh:

| Option | Approach | Risk | Benefit |
|---|---|---|---|
| **A — 6-pillar evolution** | Replace 4 ANIA Eixos with the 6 universal pillars (Infrastructure & Data / Talent & R&D / Business Adoption / Public Administration / Society / Governance & International) | Most disruptive; requires legal/document revision and breaks the Eixo II "Innovation and Adoption" logic that intentionally pairs business + PA adoption | Maximum alignment with international peers; both remaining gaps disappear by construction |
| **B — Hybrid (4 Eixos + named cross-cutting layers)** | Keep ANIA's 4 Eixos but (i) consolidate PA-AI initiatives (II.11-II.13 + III.1 + IV.4-IV.7) into a named cross-Eixo PA-AI programme operated through PIAAP, and (ii) add a named Society cross-cutting subsection within Eixo IV with civic-AI platform deliverables | Cross-cutting often gets de-prioritised in implementation if no single owner | Preserves ANIA's stakeholder communication advantage + addresses both remaining gaps without breaking the existing Eixo logic |
| **C — Status quo (defend 4-Eixo parsimony)** | Keep ANIA's 4 Eixos as-is, rely on principle (3) "PA as a catalyst" + the 6 guiding principles + the EDN cross-references | Vulnerable to the gap-analysis evidence above; risks ANIA looking under-specified on PA delivery + Society vs peers | Lowest disruption; preserves current institutional commitments |

The evidence in the matrix (B.1 rows 4 and 5: PA distributed across 3 Eixos + Society folded into principles + III.8) makes Option C harder to defend than the status-quo defence would suggest. **Option B is the recommended draft direction** — the PIAAP companion artefact operationalises the PA consolidation half of Option B without requiring a formal RCM revision of ANIA itself. Final recommendation will be drafted after explicit user discussion at final-report time.

---

## Sequencing — when to do what

| Horizon | What |
|---|---|
| **2026 H2 (before year-end)** | R4 (Deucalion SME/researcher access policy formalised), R7 (Skills Compact draft), R8 (Olympiad announcement + Lifes scoping), R9 (PME 4.0 launch via EDN Ação 14.2 Coaching 4.0 Vouchers), R12 (PIAAP publication), R13 (CAIO+AAO mandate), R14 (AI Review Committee establishment), R16 (training mandate decree), R23 (Brazil-Portugal Tech Prosperity Deal negotiation), R24 (AI Verify adoption decision), **R26 (Strategic Objective 0 axis formalisation)**, **R28 (per-cohort education targets decree)** |
| **2027 H1** | R3 (Standardisation Roadmap), R5 (4 AI Centres named), R9 (PME 4.0 advisor network rollout per NUTS-II), R10 (AI Bridge consolidation), R15 (GovAI Portugal pilot, contingent on EDN Ação 13.1 Cloud Soberana), R17 (Central register live), R18 (Observatório established), R19 (Civic-AI platforms via EDN Ação 12 Participa.gov 2.0), R23 (CPLP AI Framework signed), R25 (PT-ATRS draft), **R27 (Digital Twin Portugal additional gov-AI layer, alongside EDN Ação 8.6 5 Gémeos Digitais)** |
| **2027 H2 → 2028** | R1 (GAIA-X node anchored within I.3/I.4 + EDN Ação 13.4 submarine cables), R2 (Brazil-Portugal parallel-LLM coordination launched), R6 (AI Breakthrough Programme), R11 (Sectoral Champions kickoff), R15 (GovAI full rollout), R22 (Portuguese AI Law passage), **R26 (Crisis-AI operational deployment: wildfire + seismic + pandemic streams)** |
| **2028 → 2030** | R2 (LLM coordination scale-up), R4 (Deucalion industrial-computer expansion + Gigafactory I.2 anchor), R11 (Sectoral Champions outcomes), R21 (Atlantic-Lusophone cultural corpus), **R28 (education-target realisation year 2030)** |

---

## Annex — Recommendation × matrix-row × source-country × anchoring ANIA initiative × EDN Ação cross-reference

Each recommendation is anchored to one or more existing PAANIA initiatives (extending what is already in PAANIA) where possible, and cross-referenced to the 2026-27 Plano de Ação da EDN (Estratégia Digital Nacional) where the recommendation also rides on broader EDN deliverables.

| Rec # | Title | Matrix rows | Primary source country | PAANIA anchor(s) | EDN Ação cross-ref |
|---|---|---|---|---|---|
| R1 | GAIA-X Portuguese node + Atlantic-Lusophone Data Space | A.4 r4, C.1 r2 | DE, BR, AU, GB | I.3 + I.4 (extends) | 8.7 + 13.1 + 13.4 |
| R2 | Brazil-Portugal parallel-LLM coordination | A.4 r2, C.1 r4 | BR | II.7 (extends) | — (PAANIA-anchored) |
| R3 | Portuguese AI Standardisation Roadmap | A.4 r6, C.1 r5 | DE | IV.6 (extends) | 8.4 (Data Act diploma) |
| R4 | Deucalion access + EuroHPC industrial computer | A.4 r1, C.1 r1+r7 | DE, BR | I.1 + I.2 (extends) | 13.2 (dual-anchor: DC Plan + GigaFactory + RCM 12/2024 semiconductors) |
| R5 | 4 Portuguese AI Centres of Excellence | C.2 r2 | DE, BR | II.5 (extends) | 3 (Polo Colaborativo, lead ANI) |
| R6 | Portuguese AI Breakthrough Programme | C.2 r1, C.3 r4 | DE (SPRIND), GB (ARIA), US (DARPA) | II.1 + II.2 (extends) | 15.1 (IFIC emerging-tech funds) |
| R7 | National AI Skills Compact | C.2 r4 | AU (BCA Action 3) | III.2 + III.3 (extends) | 17 (Pacto de Competências Digitais, lead ARTE) |
| R8 | Portuguese AI Olympiad + Lifes-equivalent | C.5 r1, C.2 r6 | BR | III.7 + III.8 (extends) | 18 (Raparigas STEM) + 19 (Digital e IA na Educação) |
| R9 | PME 4.0 AI Uptake Programme | C.3 r2 | DE (Mittelstand 4.0), BR (Action 44), AU (AI Adopt) | II.9 + II.10 (extends) | 14.1 + 14.2 (Coaching 4.0 Vouchers PME, lead ARTE/IAPMEI) |
| R10 | AI Commercialisation Accelerator Portugal | C.3 r4 | AU (AICA), GB (Catapult) | II.5 + II.6 (extends) | 15 (Inovação/Empreendedorismo Digital) |
| R11 | AI for Portuguese Sectoral Champions | A.2 r7, C.3 r3 | GB, AU | II.5 (extends with named sectoral picks) | 14.4 (internacionalização AICEP) |
| R12 | PIAAP (PA AI Playbook) | C.4 r3 | GB (Playbook), AU (APS Plan) | II.11 (consolidates II.12, II.13, III.1, IV.4-IV.7) | 1 + 2 + 3 + 4 + 8 + 9 + 10 + 11 (cross-EDN consolidator) |
| R13 | Per-ministry CAIO + AAO | C.4 r1 | AU (APS Plan), US (M-25-21), BR (AI Core) | II.11 (extends) | 2.3 (revisão CDAP/RCM 94/2024) |
| R14 | AI Review Committee | C.4 r4 | AU (APS Plan) | IV.3 + IV.4 (extends) | 4 (ENC) + 2 (ARTE governance) |
| R15 | GovAI Portugal | C.4 r5 | AU (GovAI), BR (Sovereign Cloud) | II.11 + I.4 (new platform within Centre of Excellence) | 13.1 (Cloud Soberana) + 9 (PAGE arquitectura) |
| R16 | Universal civil-servant training mandate | C.4 r2 | AU (APS Plan), GB (Playbook tier model) | III.1 (extends from advanced to universal cohort) | 17 (Pacto Competências) |
| R17 | Central register of AI impact assessments | C.4 r6+r7, A.5 r5 | AU (APS Plan), GB (ATRS) | IV.6 (extends) | 8.5 (app "Os meus dados na AP") |
| R18 | Observatório Português de IA no Trabalho e Sociedade | C.5 r4 | DE (AI Observatory) | IV.1 + IV.3 (extends) | Fora do EDN (Concertação Social) |
| R19 | Civic-AI participation platforms | C.5 r5 | DE (Civic AI triad), BR (Action 50-51) | III.6 + III.8 (extends) | 12 (Participa.gov 2.0, lead ARTE) |
| R20 | (folded under R8) | — | — | — | — |
| R21 | Atlantic-Lusophone cultural-heritage AI | C.5 r6 | GB (Rec 13), AU, BR | I.3 (new sectoral data space) | 8.7 (espaços europeus de dados) |
| R22 | Portuguese AI Law | A.5 r1+r4 | JP (Act No. 53/2025) | IV.4 (extends) | 5 (Legislação pronta para o Digital) + 16 (Regulação) |
| R23 | CPLP AI Framework + Brazil-Portugal Tech Prosperity Deal | A.1 r7, C.6 r3 | AU (Tech Prosperity Deal), BR | IV.7 (extends) | 2.5 (parcerias internacionais com países de língua oficial portuguesa) |
| R24 | Adopt AI Verify | A.4 r3, C.6 r7 | SG | IV.3 + IV.6 (extends) | — (PAANIA-anchored) |
| R25 | PT-ATRS (Algorithmic Transparency Standard) | A.5 r5, C.4 r7 | GB (ATRS) | IV.4 + IV.6 (extends) | 8.5 + 8.2 (classificação soberana de dados) |
| R26 | Portuguese Strategic Objective 0 — National + Planetary Resilience (Crisis-AI axis) | A.6 r3+r5 | JP Strategy 2022 (Strategic Objective 0) | New cross-cutting axis; operationally II.5 + I.3 + IV.1 | 4 (ENC) + 13.4 (Anel CAM + Açores) |
| R27 | Digital Twin Portugal | C.1 r2 | JP Strategy 2022 (Digital Twins p.12-13) + EDN already-committed | I.3 + I.4 (extends; cross-cutting Eixo-I architecture) | **8.6 (5 Gémeos Digitais, dual-anchor) + 9 (PAGE)** |
| R28 | Quantified per-cohort annual education targets in Eixo III | C.2 r4 | JP Strategy 2022 (p.28-31 quantified targets) | III.2 + III.3 + III.6 (extends with per-cohort annual targets, realisation 2030) | 17 (Pacto de Competências Digitais) |

**Recommendation count + EDN coverage summary:** **28 recommendations (R1-R28)** total — 25 original + 3 added 2026-05-17 from Japan AI Strategy 2022 (R26-R28). **25 of 28 recommendations** have a verified EDN Ação cross-reference (only R2 AMALIA-coordination, R18 social-dialogue Observatório, and R24 AI Verify are PAANIA-only or out-of-EDN-scope). R12 PIAAP is the broadest cross-EDN consolidator, riding on 10 distinct EDN Ações. R27 Digital Twin Portugal is the second-broadest, dual-anchored at PAANIA I.3+I.4 and EDN Ação 8.6 + 9.

---

*End of portugal_ania_synthesis.md. Companion artefact: [piaap_draft.md](piaap_draft.md).*
