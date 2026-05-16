# Portugal's National AI Agenda — Synthesis and Critique

**Document type:** Executive synthesis grounded in 17-country comparator analysis.
**Anchor document:** Agenda Nacional para a Inteligência Artificial (ANIA), Action #20 of the Portugal Digital Strategy 2026-27, published January 2026.
**Evidence base:** [comparator_matrix.md](comparator_matrix.md) (Sections A/B/C) + 17 individual country summaries in `data/projects/portugal_ai_agenda/`.
**Companion artefact:** [piaap_draft.md](piaap_draft.md) — operational layer (Plano de IA para a Administração Pública) drafted in parallel and referenced from Recommendation 14.

---

## Executive summary

ANIA is a coherent and EU-anchored strategic document. It correctly positions Portugal under the EU AI Act regime, articulates 4 pillars × 32 initiatives × 6 guiding principles, and commits to a named sovereign LLM ambition (AMALIA). Against the 17 international comparators analysed, however, **ANIA has two structural gaps and approximately 25 specific delivery gaps** that should be addressed in its 2027 refresh and beyond.

### The two structural gaps

1. **No standalone Infrastructure & Data pillar.** Portugal is **the only jurisdiction in the 17-country comparator set** that folds compute / data centres / sovereign cloud / standards into other pillars rather than treating Infrastructure & Data as a coherent programme. 12 of 17 jurisdictions LEAD on this pillar (Brazil PBIA Axis 1, Germany GAIA-X + JUPITER, UK NDL + AIRR, Australia GovAI, Spain Palanca 2+7, France compute+data theme, China state infra, Singapore Compute+Data enablers, USA "Build", Italy Leonardo, Finland LUMI, Japan computing infra); 4 SHARE it; only Portugal folds it in.

2. **No standalone Society pillar.** Portugal folds inclusion + trust + civic-AI into the 6 guiding principles rather than as a structural pillar. 4 jurisdictions LEAD on Society (Germany, Singapore, Australia, China), 11 SHARE it, and Portugal is among 2-3 of 17 that fold-in. **The Society gap is more defensible than the Infrastructure & Data gap** because Portugal's principles framework genuinely operationalises inclusion, but the absence of named civic-AI platforms (à la Germany's Civic Innovation Platform / Brazil's Action 50-51 / Singapore's AI Verify Foundation) is a real omission.

### The five most actionable specific gaps

1. **No PA AI Playbook** — the single largest operational deficit. UK's 118-page Playbook + Australia's 30-page APS AI Plan are the templates. **Addressed in companion artefact** [piaap_draft.md](piaap_draft.md).
2. **No per-ministry CAIO architecture** — Australia mandates a Chief AI Officer per agency by 2026; Brazil has a centralised Federal AI Core; USA mandates per-agency CAIOs via OMB M-25-21.
3. **No AI Review Committee** with cross-watchdog membership — Australia's 6-weekly committee with Information Commissioner + Privacy Commissioner + Ombudsman is the template.
4. **No universal civil-servant AI training mandate with named timeline** — Australia commits to "all APS staff trained within 12 months" (Dec 2025 → Dec 2026); UK's 5-tier civil-servant segmentation is the alternative.
5. **No GovAI-equivalent vendor-agnostic onshore brokerage platform** — Australia's GovAI hosts vendor models including OpenAI GPT onshore for Commonwealth-data-sovereignty use cases.

### Top-5 ranked recommendations (full set of 25 below)

| # | Recommendation | Effort | When | Source |
|---|---|---|---|---|
| **R12** | **Publish a Portuguese PA AI Playbook (PIAAP)** | M | 2026 H2 | UK Playbook + Australia APS AI Plan |
| **R2** | **Brazil-Portugal parallel-LLM coordination (AMALIA PT-PT + PBIA Action 9 PT-BR)** | L | 2026-2028 | Brazil PBIA (bilateral) |
| **R13** | **Per-ministry CAIO + separate AI Accountable Official** | S | 2026 H2 | Australia APS Plan |
| **R14** | **AI Review Committee (CNPD + Provedor de Justiça + CADA + sectoral)** | S | 2026 H2 | Australia APS Plan |
| **R22** | **Pass a Portuguese AI Law** | L | 2027-2028 | Japan Act No. 53/2025 |

The remaining 20 recommendations are grouped by the 6 universal pillars below.

---

## What ANIA does well (to preserve)

Before listing gaps it is important to anchor what should NOT change in ANIA's evolution:

- **EU AI Act anchoring** — clean, stable, and the right regulatory home for Portugal. Avoid drift toward UK pro-innovation / Australia sector-based / USA activist alternatives, all of which were considered by comparator countries and explicitly rejected by EU members.
- **Single coherent document of 22 pages** — easier for stakeholder communication than Brazil's 66-page PBIA or Germany's 2-document stack or Australia's 3-document stack.
- **6 named guiding principles** as a compact enumeration. Most comparators have implicit principle sets; Portugal's explicit 6 is more citable.
- **4-pillar structure** — readable. The structural gaps are addressable by adding cross-cutting Infrastructure + Society subsections within each pillar (Option B) without breaking the parsimony.
- **AMALIA as named sovereign Portuguese LLM** — a strong identity move for the ~10M PT-PT speakers globally. Now correctly understood as the PT-PT complement to Brazil's PT-BR ambition, not in competition with it.
- **CPLP framing** as a natural diplomatic positioning for Portugal — even if currently under-operationalised, the framing is correct.
- **Action #20 of Portugal Digital Strategy 2026-27 positioning** — situates ANIA within a coherent national digital agenda rather than as a free-standing AI document. This is good integration.

---

## Methodology

Each country in the comparator set was analysed against a consistent template (header / quantitative anchors / structure / distinctive mechanisms / "what country X does that Portugal does NOT" / "what Portugal does that X does NOT" / style comparison / critique-lens conclusion). The 17 comparators are: Argentina, USA, Finland, Qatar, UAE, Spain, Sweden, France, UK, Italy, China, Singapore, Japan, Australia (3 docs consolidated), Germany (2 docs consolidated), and Brazil. Each comparator was selected for offering a distinct national approach to a similar policy challenge; together they triangulate the design space Portugal sits in.

Cells in the comparator matrix (Section A/B/C) cite back to the country summaries. Recommendations below cite both the comparator matrix row and the source country (or countries) the move is drawn from.

A quote from UK's AI Opportunities Action Plan captures the framing question every comparator wrestles with: *"If this is to benefit the UK we must be an AI maker, not just an AI taker."* Portugal at its scale cannot be an AI maker on the same terms as the UK, USA, or China — but it can be a credible **AI maker in named wedges** (Portuguese-language LLM, Atlantic-Lusophone data sovereignty, AI for wildfire prediction, AI for ocean biodiversity, AI for healthcare via SNS24). The recommendations below operationalise that wedge-based AI-maker positioning.

---

## Recommendations grouped by universal pillar

### Pillar 1 — Infrastructure & Data

**The structural framing:** Portugal needs to elevate Infrastructure & Data either to a standalone 5th pillar or, at minimum, to a strong cross-cutting layer mandated within each of the existing 4 pillars (see *Pillar selection / omission* section below). The 4 recommendations in this pillar assume the latter and can be re-grouped under a 5th pillar if Option A is adopted at final-report time.

#### R1 — Anchor a Portuguese GAIA-X node + Atlantic-Lusophone Data Space

| Field | Value |
|---|---|
| Source | Germany (GAIA-X), Brazil (Sovereign Cloud Action 27), Australia (GovAI), UK (NDL) |
| Anchor ANIA initiative | II.9 (data infrastructure) + extends |
| Effort | M-L |
| When | 2026-2028 |
| Lead | APDC + INESC-TEC + AMA + IPN |
| Key risk | EU-data-space duplication if not aligned with European Data Strategy |

Germany leads GAIA-X. Brazil names Sovereign Cloud (Action 27) + IND (National Data Infrastructure) at Federal-Government scale. Portugal should explicitly anchor a Portuguese GAIA-X node + Atlantic-Lusophone Data Space federation, positioning Portugal as the EU-side hub for Lusophone data sovereignty (CPLP variant of federated data infrastructure). The Açores can host a low-temperature ambient data centre node; mainland Portugal provides the EU-compliant compute layer; CPLP partner countries federate via the same standards. *Matrix references: A.4 row 4, C.1 row 2.*

#### R2 — Brazil-Portugal parallel-LLM coordination (AMALIA PT-PT + PBIA Action 9 PT-BR)

| Field | Value |
|---|---|
| Source | Brazil PBIA Action 9 |
| Anchor ANIA initiative | II.7 (AMALIA) + extends |
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
| Anchor ANIA initiative | IV.6 + extends |
| Effort | M |
| When | 2026 H2 → 2027 H1 |
| Lead | IPQ + APQ + IPN-LIT + IT + IST |
| Key risk | Duplicating EU CEN-CENELEC work without value-add |

Germany's DIN + DKE published an AI Standardisation Roadmap at the 2020 Digital Summit. It maps current and future standardisation needs (safety, robustness, transparency, non-discrimination) and drives subsequent implementation programmes. Portugal should commission an equivalent via IPQ + APQ + IPN-LIT + IT + IST, contributing Portuguese specifics into EU CEN-CENELEC standardisation work. *Matrix reference: A.4 row 6, C.1 row 5.*

#### R4 — Expand Deucalion access for SMEs + researchers + anchor EuroHPC industrial computer participation

| Field | Value |
|---|---|
| Source | Germany (JUPITER + EuroHPC industrial computer), Brazil (Action 4 Pro-Infra AI) |
| Anchor ANIA initiative | II.4 + extends |
| Effort | M |
| When | 2026 H2 onwards |
| Lead | FCT + FCCN + MACC |
| Key risk | Deucalion saturation; need clear allocation policy |

Brazil names AI service centres (Action 4 Pro-Infra AI for ICTs) as the SME-and-researcher compute access mechanism. Germany commits to expanding national HPC (JUPITER) + EuroHPC industrial computer. Portugal should formalise SME and researcher access pathways to Deucalion + participate as anchor partner in any EuroHPC industrial computer initiative. *Matrix reference: A.4 row 1, C.1 rows 1+7.*

### Pillar 2 — Talent & R&D

#### R5 — Name 4 Portuguese AI Centres of Excellence with regional federalism

| Field | Value |
|---|---|
| Source | Germany (6 named: DFKI/BIFOLD/Lamarr/ScaDS.AI/MCML/TUEAI), Brazil (CPA + INCT-AI) |
| Anchor ANIA initiative | II.3 + extends |
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
| Anchor ANIA initiative | II.2 + extends |
| Effort | M |
| When | 2027-2028 |
| Lead | FCT + ANI + Conselho Coordenador de C&T |
| Key risk | Programme-director autonomy if it remains under standard public-sector governance |

Germany has SPRIND (Federal Agency for Disruptive Innovation), modelled on DARPA + ARIA. Portugal should establish an AI Breakthrough Programme with DARPA-style mission-management autonomy + 5-7 year horizons + programme-director discretion. Anchor it within FCT or ANI but ring-fence governance. Initial mission examples: Portuguese-language LLM at frontier scale; wildfire-prediction AI; ocean-biodiversity AI; Atlantic-cable AI security. *Matrix references: C.2 row 1, Section C.3 row 4.*

#### R7 — National AI Skills Compact (industry + academia + government)

| Field | Value |
|---|---|
| Source | Australia BCA Action 3 |
| Anchor ANIA initiative | I.1, I.2, III.1, III.2 + extends |
| Effort | S-M |
| When | 2026 H2 → 2027 H1 |
| Lead | ANQEP + IEFP + universities + AIP + COTEC |
| Key risk | Stakeholder co-design fatigue |

Australia's BCA proposes a National AI Skills Compact modelled on NSW's Digital Skills Compact, with two streams: (a) national AI apprenticeship model (drawing on Germany's dual VET + Singapore's AIAP); (b) industry-led microcredentials. Portugal should establish a Portuguese AI Skills Compact integrating ANIA III.1/III.2 + IEFP + universities + industry. *Matrix reference: C.2 row 4.*

#### R8 — Portuguese AI Olympiad + Lifes-equivalent teacher training

| Field | Value |
|---|---|
| Source | Brazil (AI Olympiad Action 14; Lifes Action 15) |
| Anchor ANIA initiative | I.3 + extends |
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
| Anchor ANIA initiative | II.13 + extends |
| Effort | M |
| When | 2026 H2 → 2028 |
| Lead | IAPMEI + AIP + sectoral associations + IEFP |
| Key risk | Reaches only digitally-advanced PMEs; rural PME exclusion |

Germany's Mittelstand 4.0 Centres of Excellence + AI trainer programme set the template. Brazil's Action 44 (AI for MSMEs + MEIs) + Action 49 (Brasil Mais Produtivo) localise it. Australia's NAIC + AI Adopt Program is the operational analogue. Portugal needs a PME 4.0 / ENI AI Uptake Programme operated via IAPMEI + AIP + sectoral associations with train-the-trainer pathways + AI advisor networks per NUTS-II region. *Matrix reference: C.3 row 2.*

#### R10 — AI Commercialisation Accelerator Portugal (AICA + Catapult + Embrapii analogues)

| Field | Value |
|---|---|
| Source | Australia AICA (BCA Action 15) + UK Catapult Network + Brazil Embrapii integration |
| Anchor ANIA initiative | II.6 + extends |
| Effort | M |
| When | 2027 |
| Lead | ANI + COTEC + CoLABs |
| Key risk | Yet-another-bridge-organisation; needs explicit consolidation mandate |

Australia BCA Action 15 proposes an AI Commercialisation Accelerator (AICA) modelled on UK Catapult Network. Brazil integrates via Embrapii. Portugal already has the institutional bones (ANI + COTEC + CoLABs) but needs consolidation into a named "AI Bridge Portugal" with explicit IP-protection and commercialisation pathways. *Matrix reference: C.3 row 4.*

#### R11 — AI for Portuguese Sectoral Champions

| Field | Value |
|---|---|
| Source | UK named champions in life sciences/financial services/creative industries + Australia sectoral focus |
| Anchor ANIA initiative | II.5, II.7, II.8 + extends |
| Effort | L |
| When | 2026-2030 |
| Lead | Per-sector ministry + AICEP for FDI attraction |
| Key risk | Sectoral picking-winners critique |

UK names AI Sector Champions in life sciences, financial services, creative industries. Portugal's natural picks (per ANIA's strengths analysis): **Health & Pharmaceuticals + Tourism + Blue Economy + Footwear/Textiles + Aerospace (via Edisoft)**. Each champion programme has named industry lead, public-funding line, export ambition, and 3-year milestones. *Matrix reference: A.2 row 7, C.3 row 3.*

### Pillar 4 — Public Administration (highest-leverage gap area)

#### R12 — Publish the PIAAP (Plano de IA para a Administração Pública)

| Field | Value |
|---|---|
| Source | UK AI Playbook (118pp, mandatory) + Australia APS AI Plan (30pp Trust/People/Tools) |
| Anchor ANIA initiative | II.11 + extends to operational layer |
| Effort | M |
| When | 2026 H2 (publication) → 2027 H2 (full operationalisation) |
| Lead | AMA + DGAEP + INA + Centro para a IA Responsável |
| Key risk | Stakeholder resistance from line ministries used to discretion |

**The single highest-leverage recommendation in this synthesis.** Portugal needs an operational PA layer to ANIA. The PIAAP follows Australia APS Plan structure (Trust / People / Tools × ~11 deliverables) but adopts UK Playbook's 10 principles + case-studies appendix. **Detailed draft in companion artefact [piaap_draft.md](piaap_draft.md).** *Matrix reference: C.4 row 3.*

#### R13 — Per-ministry CAIO + separate AI Accountable Official

| Field | Value |
|---|---|
| Source | Australia APS Plan + USA OMB M-25-21 + Brazil Federal AI Core |
| Anchor ANIA initiative | New under II.11 |
| Effort | S |
| When | 2026 H2 |
| Lead | AMA + Ministério das Finanças |
| Key risk | Role conflation in smaller ministries |

Australia's APS Plan separates **Chief AI Officer** (drives adoption + strategic change) from **AI Accountable Official** (governance + compliance). USA mandates per-agency CAIOs via M-25-21. Brazil has a centralised Federal AI Core. Portugal should mandate per-ministry CAIO + separate AI Accountable Official by end-2026, with small ministries permitted to combine roles. *Matrix reference: C.4 row 1.*

#### R14 — AI Review Committee (cross-watchdog)

| Field | Value |
|---|---|
| Source | Australia APS Plan AI Review Committee |
| Anchor ANIA initiative | IV.4 + new |
| Effort | S |
| When | 2026 H2 → full maturity 2027 |
| Lead | Centro para a IA Responsável (secretariat) + member bodies |
| Key risk | Slow throughput; needs <6-weekly cadence |

Australia's AI Review Committee meets every 6 weeks, provides non-binding advice on high-risk AI uses, draws membership from Information Commissioner + Privacy Commissioner + Ombudsman + sectoral. Portuguese analogue: **CNPD + Provedor de Justiça + CADA + ERSE + ANACOM + ASAE sectoral**, with Centro para a IA Responsável as secretariat. Anchor under ANIA IV.4 with explicit EU AI Act Article 26 alignment. *Matrix reference: C.4 row 4.*

#### R15 — GovAI Portugal (vendor-agnostic onshore AI brokerage platform)

| Field | Value |
|---|---|
| Source | Australia GovAI + Brazil Sovereign Cloud + UK i.AI Incubator |
| Anchor ANIA initiative | II.9 + new |
| Effort | M |
| When | 2027 H1 |
| Lead | AMA + IPN + INCM |
| Key risk | Procurement complexity; vendor-lock-in if not truly multi-model |

Australia's GovAI is a vendor-agnostic onshore platform hosting multiple LLMs (including onshore OpenAI GPT). Distinct from AMALIA (sovereign LLM ambition): **GovAI Portugal is the day-to-day platform every ministry uses; AMALIA is the long-term sovereign-LLM identity**. This pair architecture is the right design for Portugal. *Matrix reference: C.4 row 5.*

#### R16 — Mandatory universal civil-servant AI training within 12-18 months

| Field | Value |
|---|---|
| Source | Australia APS Plan (mandatory all-APS within 12 months) + UK 5-tier civil-servant segmentation |
| Anchor ANIA initiative | III.1 + new mandate |
| Effort | S |
| When | 2026 H2 → 2028 H1 |
| Lead | INA + DGAEP + Centro para a IA Responsável |
| Key risk | Variable-quality delivery without standardised curriculum |

Australia mandates "all APS staff trained in AI fundamentals within 12 months" of policy update. UK Playbook has 5-tier segmentation (executive / technical lead / digital / general / specialist). Portugal should mandate equivalent: every PA staff member (~700K state employees) completes AI fundamentals training within 18 months of PIAAP publication. Curriculum delivered via INA + DGAEP + Universidade Aberta. *Matrix reference: C.4 row 2.*

#### R17 — Central register of AI impact assessments

| Field | Value |
|---|---|
| Source | Australia APS Plan central register + UK ATRS |
| Anchor ANIA initiative | IV.6 + new |
| Effort | S-M |
| When | 2027 H1 |
| Lead | AMA + CNPD |
| Key risk | Update lag rendering register stale |

Australia mandates a central register of completed AI impact assessments (FOCI, IRAP, cyber-security, impact) so that agencies can reference/reuse prior evaluations rather than re-conducting. UK's ATRS is the mandatory transparency analogue. Portugal should establish a **Registo Central de Avaliações de Impacto de IA** under AMA, with EU AI Act Article 29 alignment. *Matrix references: C.4 rows 6+7, A.5 row 5.*

### Pillar 5 — Society

**Structural framing:** Whether Society becomes a standalone 5th pillar (Option A) or stays folded-into the 6 principles + cross-cutting (Option B) is the **pillar-selection question** deferred to final-report discussion (see *Pillar selection / omission* section below). The 4 recommendations below assume either structure.

#### R18 — Establish the Observatório Português de IA no Trabalho e na Sociedade

| Field | Value |
|---|---|
| Source | Germany AI Observatory for Work and Society |
| Anchor ANIA initiative | IV.2 + new |
| Effort | M |
| When | 2026 H2 → 2027 |
| Lead | DGEEP + Centro para a IA Responsável + UGT + CGTP + CIP |
| Key risk | Capture by single stakeholder constituency |

Germany has a Federal AI Observatory in the Ministry of Labour focused on AI's labour and society impact. It develops indicators, monitors trends, includes unions + civil society + business + science. Portugal should establish a named equivalent under DGEEP (Directorate-General for Employment) + Centro para a IA Responsável + tripartite social-dialogue representation (UGT + CGTP + CIP). *Matrix reference: C.5 row 4.*

#### R19 — Civic-AI participation platforms (Germany Civic AI triad + Brazil Action 50-51 analogues)

| Field | Value |
|---|---|
| Source | Germany (Civic Innovation Platform + Civic Data Lab + Civic Tech Labs for Green) + Brazil (Action 50-51 planned) |
| Anchor ANIA initiative | III.4 + new |
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
| Anchor ANIA initiative | III.4 + new |
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
| Anchor ANIA initiative | IV.5 + new |
| Effort | L |
| When | 2027-2028 (legislative cycle) |
| Lead | Assembleia da República + Ministério da Justiça + Ministério da Economia |
| Key risk | EU AI Act pre-emption; needs to complement not duplicate |

Japan passed **Act No. 53 of 2025** — the only national jurisdiction in the 17-country comparator set with dedicated AI primary legislation. The Act establishes principles, the AI Strategic Headquarters, the AI Basic Plan obligation, and gives parliamentary anchor for AI policy. Portugal could pass a Lei Nacional para a Inteligência Artificial that (a) transposes EU AI Act provisions, (b) names CNPD + Centro para a IA Responsável + AESIA-equivalent (or Portugal's chosen body) as competent authorities, (c) mandates the PIAAP, (d) commits AMALIA funding, (e) establishes the AI Review Committee. *Matrix references: A.5 rows 1+4.*

#### R23 — CPLP AI Framework Arrangement + Brazil-Portugal Tech Prosperity Deal

| Field | Value |
|---|---|
| Source | Australia (Tech Prosperity Deal with USA, MoU Singapore, Framework India) + Brazil (S-S framing) |
| Anchor ANIA initiative | IV.7 + new |
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

Per user direction (2026-05-16), the question of whether ANIA's 4-pillar structure should evolve is **explicitly deferred for discussion at final-report time**. Three options to weigh, with the evidence base above:

| Option | Approach | Risk | Benefit |
|---|---|---|---|
| **A — 6-pillar evolution** | Replace 4 ANIA pillars with the 6 universal pillars (Infrastructure & Data / Talent & R&D / Business Adoption / Public Administration / Society / Governance & International) | Most disruptive; requires legal/document revision | Maximum alignment with international peers; ANIA gaps disappear by construction |
| **B — Hybrid (4 visible + cross-cutting layers)** | Keep ANIA's 4 pillars but mandate cross-cutting Infrastructure + Society sub-sections within each, with named lead coordinators | Cross-cutting often gets de-prioritised in implementation | Preserves ANIA's stakeholder communication advantage + addresses both structural gaps |
| **C — Status quo (defend 4-pillar parsimony)** | Keep ANIA's 4 pillars as-is, rely on 6 guiding principles + cross-cutting language | Vulnerable to the gap-analysis evidence above; risks ANIA looking under-specified vs peers in international comparisons | Lowest disruption; preserves current institutional commitments |

The evidence in the matrix (B.1 row 1: Portugal is *the only* 17-jurisdiction folder-in for Infrastructure & Data) makes Option C the hardest to defend. The recommendation will be drafted at final-report time after explicit user discussion.

---

## Sequencing — when to do what

| Horizon | What |
|---|---|
| **2026 H2 (before year-end)** | R7 (Skills Compact draft), R8 (Olympiad announcement + Lifes scoping), R12 (PIAAP publication), R13 (CAIO+AAO mandate), R14 (AI Review Committee establishment), R16 (training mandate decree), R23 (Brazil-Portugal Tech Prosperity Deal negotiation), R24 (AI Verify adoption decision) |
| **2027 H1** | R3 (Standardisation Roadmap), R5 (4 AI Centres named), R10 (AI Bridge consolidation), R15 (GovAI Portugal pilot), R17 (Central register live), R18 (Observatório established), R19 (Civic-AI platforms), R23 (CPLP AI Framework signed), R25 (PT-ATRS draft) |
| **2027 H2 → 2028** | R1 (GAIA-X node anchored), R2 (Brazil-Portugal parallel-LLM coordination launched), R6 (AI Breakthrough Programme), R11 (Sectoral Champions kickoff), R15 (GovAI full rollout), R22 (Portuguese AI Law passage) |
| **2028 → 2030** | R2 (LLM coordination scale-up), R4 (Deucalion industrial computer expansion), R11 (Sectoral Champions outcomes), R21 (Atlantic-Lusophone cultural corpus) |

---

## Annex — Recommendation × matrix-row × source-country cross-reference

| Rec # | Title | Matrix rows | Primary source country |
|---|---|---|---|
| R1 | GAIA-X Portuguese node + Atlantic-Lusophone Data Space | A.4 r4, C.1 r2 | DE, BR, AU, GB |
| R2 | Brazil-Portugal parallel-LLM coordination | A.4 r2, C.1 r4 | BR |
| R3 | Portuguese AI Standardisation Roadmap | A.4 r6, C.1 r5 | DE |
| R4 | Deucalion access + EuroHPC industrial computer | A.4 r1, C.1 r1+r7 | DE, BR |
| R5 | 4 Portuguese AI Centres of Excellence | C.2 r2 | DE, BR |
| R6 | Portuguese AI Breakthrough Programme | C.2 r1, C.3 r4 | DE (SPRIND), GB (ARIA), US (DARPA) |
| R7 | National AI Skills Compact | C.2 r4 | AU (BCA Action 3) |
| R8 | Portuguese AI Olympiad + Lifes-equivalent | C.5 r1, C.2 r6 | BR |
| R9 | PME 4.0 AI Uptake Programme | C.3 r2 | DE (Mittelstand 4.0), BR (Action 44), AU (AI Adopt) |
| R10 | AI Commercialisation Accelerator Portugal | C.3 r4 | AU (AICA), GB (Catapult) |
| R11 | AI for Portuguese Sectoral Champions | A.2 r7, C.3 r3 | GB, AU |
| R12 | PIAAP (PA AI Playbook) | C.4 r3 | GB (Playbook), AU (APS Plan) |
| R13 | Per-ministry CAIO + AAO | C.4 r1 | AU (APS Plan), US (M-25-21), BR (AI Core) |
| R14 | AI Review Committee | C.4 r4 | AU (APS Plan) |
| R15 | GovAI Portugal | C.4 r5 | AU (GovAI), BR (Sovereign Cloud) |
| R16 | Universal civil-servant training mandate | C.4 r2 | AU (APS Plan), GB (Playbook tier model) |
| R17 | Central register of AI impact assessments | C.4 r6+r7, A.5 r5 | AU (APS Plan), GB (ATRS) |
| R18 | Observatório Português de IA | C.5 r4 | DE (AI Observatory) |
| R19 | Civic-AI participation platforms | C.5 r5 | DE (Civic AI triad), BR (Action 50-51) |
| R20 | (folded under R8) | — | — |
| R21 | Atlantic-Lusophone cultural-heritage AI | C.5 r6 | GB (Rec 13), AU, BR |
| R22 | Portuguese AI Law | A.5 r1+r4 | JP (Act No. 53/2025) |
| R23 | CPLP AI Framework + Brazil-Portugal Tech Prosperity Deal | A.1 r7, C.6 r3 | AU (Tech Prosperity Deal), BR |
| R24 | Adopt AI Verify | A.4 r3, C.6 r7 | SG |
| R25 | PT-ATRS (Algorithmic Transparency Standard) | A.5 r5, C.4 r7 | GB (ATRS) |

---

*End of portugal_ania_synthesis.md. Companion artefact: [piaap_draft.md](piaap_draft.md).*
