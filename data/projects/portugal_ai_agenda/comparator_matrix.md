# Cross-Comparator Matrix — Portugal ANIA + 16 International AI Strategy Comparators

**Purpose.** This document is the analytical database underpinning the Portugal ANIA synthesis. Every claim in the synthesis document and the PIAAP draft cites back to a row here. Three sections:

- **Section A — PESTLE tables** (6 tables) — macro-environmental scan: each country's stance on Political / Economic / Social / Technological / Legal / Environmental factors.
- **Section B — Pillar-coverage matrix** (1 table) — how each country's actual plan structure maps to the 6 common-denominator universal pillars (Infrastructure & Data / Talent & R&D / Business Adoption / Public Administration / Society / Governance & International).
- **Section C — Per-pillar deep-dive tables** (6 tables) — for each universal pillar, the named mechanisms each country has actually committed to.

**Cell format.** Hierarchical: bold verdict (1-5 words) + optional drill-down phrase + (where useful) source citation. Per-country evidence lives in the corresponding `<country>_summary.md` files; cells are pointers, not full evidence.

## Jurisdiction key (column headers)

| Code | Country | Source summary | Primary document(s) |
|---|---|---|---|
| **PT** | **Portugal (anchor)** | — (the subject) | National Artificial Intelligence Agenda (ANIA, Jan 2026) |
| AR | Argentina | [argentina_summary.md](argentina_summary.md) | Digital Agenda (Oct 2018) — caveat: not AI-specific |
| US | United States | [usa_summary.md](usa_summary.md) | America's AI Action Plan (Jul 2025) |
| FI | Finland | [finland_summary.md](finland_summary.md) | AI 4.0 Programme final report (Dec 2022) |
| QA | Qatar | [qatar_summary.md](qatar_summary.md) | Digital Agenda 2030 (2024) — caveat: not AI-specific |
| AE | UAE | [uae_summary.md](uae_summary.md) | National Strategy for AI 2031 (Oct 2018) |
| ES | Spain | [spain_summary.md](spain_summary.md) | Estrategia de Inteligencia Artificial (2024) |
| SE | Sweden | [sweden_summary.md](sweden_summary.md) | AI Strategy + Action Plan annex (2026) |
| FR | France | [france_summary.md](france_summary.md) | Aghion-Bouverot Commission Report (Mar 2024) |
| GB | United Kingdom | [uk_summary.md](uk_summary.md) | AI Opportunities Action Plan (Jan 2025) + AI Playbook (Feb 2025) |
| IT | Italy | [italy_summary.md](italy_summary.md) | Italian Strategy for AI 2024–2026 (Jun 2024) |
| CN | China | [china_summary.md](china_summary.md) | State Council Opinion on "AI+" Action (Aug 2025) |
| SG | Singapore | [singapore_summary.md](singapore_summary.md) | NAIS 2.0 (Dec 2023) |
| JP | Japan | [japan_summary.md](japan_summary.md) | AI Basic Plan (Dec 2025, under Act No. 53/2025) |
| AU | Australia | [australia_summary.md](australia_summary.md) | BCA Accelerating (Jun 2025) + National AI Plan + APS AI Plan (Nov 2025) |
| DE | Germany | [germany_summary.md](germany_summary.md) | AI Strategy 2020 Update + BMBF Aktionsplan 2023 |
| BR | Brazil | [brazil_summary.md](brazil_summary.md) | PBIA "AI for the Good of All" (2025) |

**Reading guide.** Tables in Sections A and C use dimensions-as-rows × jurisdictions-as-columns. The PT (Portugal) column is the anchor; every other column shows the comparator's stance on the same dimension. The intent is to make ANIA's gaps and strengths visible at a glance per dimension.

---

# Section A — PESTLE Macro-Environmental Scan

## A.1 — Political

| Dimension | PT | AR | US | FI | QA | AE | ES | SE | FR | GB | IT | CN | SG | JP | AU | DE | BR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Issuing body** | Government internal | Sec. Gov. Digital (JGM) | White House OSTP | TEM + Steering Group | MCIT | Office of Minister of State for AI | MTDFP (Escrivá) | Government Offices | French AI Commission (independent) | DSIT + Clifford (AP); GDS (PB) | AGID | State Council (NDRC coord.) | Smart Nation + IMDA | Cabinet Decision under Act 53/2025 | BCA (industry) + DISR (NAP) + Finance/DTA/APSC (APS) | Bundesregierung (Strategy); BMBF (Aktionsplan) | MCTI + CGEE + CCT |
| **Head signatory / foreword** | Government collective | María Inés Baqué | Kratsios + Sacks + Rubio | Jussi Herlin (Kone), Minister Lintilä | PM Sheikh Mohammed + MCIT Min | HE Omar Sultan Al Olama (first AI Minister) | José Luis Escrivá | PM Ulf Kristersson + Min. Slottner | Philippe Aghion + Anne Bouverot | Peter Kyle MP / Feryal Clark + D. Knott | Government collective via AGID | State Council | DPM Lawrence Wong (now PM) | Cabinet | Sen. Ayres + Charlton (NAP); Sen. Gallagher (APS) | Stark-Watzinger MdB (Aktionsplan) | President Lula + Min. Luciana Santos |
| **Political-party / values framing** | Centre-right coalition (PSD/CDS) — implicit | Macri government (centre-right 2018) | Trump 2nd-term Republican | Cross-coalition (Rinne/Marin/Orpo era) | Royal/monarchic | Federal monarchy | PSOE-Sumar centre-left | Moderate-led centre-right coalition | Macron / Renaissance | Labour (Starmer) post-Brexit | Meloni / FdI centre-right | CCP state-led | PAP technocratic | LDP | Labor (Albanese) — "fairness, inclusion, opportunity" explicit | Grand coalition (2020); FDP/Greens/SPD (2023) | PT social-democratic (Lula) |
| **Inter-ministerial coordination model** | Implicit (Action #20 of PT Digital Strategy) | Limited | CAIOC + EO 14179 | TEM Steering Group | Top-down royal-court | Minister of AI as central node | Cross-ministerial under MTDFP | Government Offices central | Per-recommendation Ministry assigned | Per-rec. Lead + GDS for Playbook | Foundation under PM Office (planned) | NDRC + 5-Year Plan | Smart Nation Group integrated | AI Strategic HQ under PM | NAP cross-min. + APS Plan = Finance/DTA/APSC | BMBF leads; distributed | CIT Digital + Federal Govt AI Core (SGD/MGI) |
| **Cross-party / opposition acceptance** | No explicit statement | Unclear | Partisan (one-administration) | Strong (multi-coalition continuity) | N/A | N/A | Mixed | Negotiated cross-aisle | Independent commission credibility | **All 50 recs accepted by govt** (CP 1242) | Mixed | N/A | N/A | **Strong — AI Act passed bipartisan** | Labor-dominant framing | **Strong cross-coalition continuity** | Government-led, opposition critique limited |
| **Sovereign-AI positioning** | Hybrid Development/Application | Applier (digital agenda baseline) | Frontier / dominance | Twin-transition + carbon-handprint | Hub / applier | "AI Centennial 2071" hub | Development (ALIA + AESIA) | Applier + responsible | Frontier (Mistral + WAIO) | **"AI maker, not AI taker"** | Applier + sovereign LMM | State-led "AI+" framing | Hub + responsible-applier | Trustworthy-AI PDCA | "AI maker" (BCA quotes UK); Capture/Spread/Keep Safe (NAP) | **"AI Made in Europe"** + Industry 4.0 wedge | "AI for the Good of All" + Global South lead |
| **Lead bilateral diplomatic priority** | EU + CPLP (implicit) | Regional / OAS | Indo-Pacific + UK | EU + Nordic | GCC + global hubs | USA + Saudi + China (multi-vector) | EU + Iberoamérica | EU + Nordic | **Germany (priority)** + EU + Africa | USA + Japan + Singapore | EU + Mediterranean | BRICS + Global South | USA + ASEAN + UK | USA + Hiroshima AI Process | USA (Tech Prosperity Deal) + Singapore + India + UK + ROK | **France (priority)** + Canada + Japan + ROK | Latin America + Africa + CPLP + India |

## A.2 — Economic

| Dimension | PT | AR | US | FI | QA | AE | ES | SE | FR | GB | IT | CN | SG | JP | AU | DE | BR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Headline GDP / productivity target** | **€18-22B/yr added + 2.7pp productivity** | Not quantified | Frontier-leadership (not € target) | Twin-transition, no headline figure | Digital-economy GDP contribution | AI contributes US$96B by 2031 (~14% non-oil GDP) | **Tabla 6 per-initiative €** | Not quantified | **€27B/5yr value-creation goal** | **£400B AI boost by 2030** | Not quantified at €-level | Not € — strategic missions | S$5B SG NAIS 1.0 baseline + expansion | Not € — qualitative + Hiroshima | **$116B GDP + 4.3pp labour productivity by 2030** + $19B/yr public-sector value | **5B by 2025** total Federal AI commitment | Not € — R$ 23B BRL 2024-28 |
| **Total committed AI budget (line-itemed)** | Not itemised | Not itemised | Not itemised at headline | TEM-funded but not aggregated | Not itemised | Not itemised | **Tabla 6 itemises Palancas** | Itemised in Action Plan annex | **€27B/5yr aggregate** | £14B+ AI infrastructure investments announced | Not € — qualitative | Not € — strategic actions | S$1B+ NAIS 2.0 announcements | Not yen — qualitative | **A$460M existing + A$1B NRF + A$950M RDTI** | **€5B by 2025** (€3B initial + €2B Future Pkg) | **R$ 23.03B 2024-28 with % per axis** |
| **Multi-year horizon** | Through 2027 (under Digital Strategy) | 5-year (2018-23) | Through 2030 | 10-year strategy + 2027 milestones | 2030 | 2031 | 2026 horizon | 2026-30 | 5-year (to 2029) | Through 2030 + 2035 quant. | 2024-26 (3-year) | Through 2030 | NAIS 2.0 to 2030 | 2025-30 multi-stage | 3-year phased (Jul 2025-Jun 2028) | 2025 deadline | **2024-28 (5-year)** |
| **Statutory body backing numbers** | Not named | Not named | OSTP / OMB | TEM analytics | Not named | UAE Stats Authority | INE + Tabla 6 | Statistics Sweden / KOMM | **Conseil d'analyse économique** | NAO + Public First citations | ISTAT (implicit) | NDRC + NBS | MAS + IMDA studies | Cabinet Office analytics | **Productivity Commission** (named, explicit) | Federal Statistical Office; Plattform Lernende Systeme | **EPE** (energy) + **CGEE** + **ABC** |
| **R&D-spend target** | 3% GDP (national, not AI-specific) | Not specified | Not specified | High EU benchmark | Not specified | Not specified | EU 3% by 2030 | Aligned with EU 3% | Aligned with EU 3% | Increase via UKRI | EU 3% by 2030 | **3% by 2025** (national) | Strong NRF + RIE | Aligned with EU/G7 | **3% by 2035** (BCA Action 14) | Aligned with EU 3% | Aligned with national S&T policy |
| **Market-position framing** | "Hybrid Development/Application" | Applier (regional) | Frontier dominance | Applier + sustainability leader | Applier + hub | Hub + Centennial frontier | Development | Applier + responsible | Frontier challenger | **"AI maker, not AI taker"** | Applier + sovereign LMM | Applier + state-led frontier | Applier-hub + trust | Trustworthy applier | "Fast follower + smart adapter" (BCA) | "AI Made in Europe" + Mittelstand | Global South lead + applier |
| **AI patent / publication baseline** | Mid-tier EU | Latin America regional | **#1 publications + patents** | EU top-tier per-capita | Emerging | Emerging | Top-tier EU | Strong per-capita | Top-tier EU | **3rd-largest AI market globally** | Top-tier EU | **#2 publications, rising patents** | High per-capita | Top-tier (3rd-4th globally) | 17th Global AI Index 2024 | **5th publications globally** | Top-20 publications, weak patent translation |

## A.3 — Social

| Dimension | PT | AR | US | FI | QA | AE | ES | SE | FR | GB | IT | CN | SG | JP | AU | DE | BR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Universal AI training mandate** | Not mandated | Not mandated | Federal workforce-AI training (CAIOs) | Sectoral upskilling | Digital literacy general | Not mandated | Sectoral | Sectoral | Sectoral via universities | 5-tier civil-servant segmentation (PB) | Not mandated | Workforce reskilling state-led | Skills Future credits universal | Sectoral via MEXT | **All APS staff foundational training mandated within 12 months** | National Skills Strategy + sectoral | Public-servant qualification (Action 26) |
| **Inclusion dimensions named** | Implicit (6 principles) | Gender + rural + agritech + K-12 explicit | Worker-displacement focus | Twin-transition + youth | Sectoral | Demographic | Regional + gender | Strong worker-voice | Diversity + regional | Gender (Rec 16) + regional via AIGZs | Mezzogiorno (regional South) | Rural + elderly | **Creators/Practitioners/Users + senior citizens + disabled** | Gender + sectoral + ageing population | **First Nations + women + regional + disability + ageing** — Indigenous Data Sovereignty named | Gender (#mintmagie) + sectoral; Civic AI for marginalised | **Cultural + regional + peoples' diversity** + low-income (CadÚnico) |
| **Worker voice / union anchoring** | Not explicit | Not explicit | Limited (federal-side) | Strong (Nordic model) | Not applicable | Not applicable | Sectoral collective bargaining | **Strong (Nordic model)** | Comité dialogue | Workforce framing only | Sectoral | State-managed | NTUC anchored | Sectoral | **Explicit union consultation mandate** (APS Plan + NAP) | **Strong (Mitbestimmung + AI Observatory)** | Strong (CUT + workforce protection framing) |
| **Public trust framing / AI anxiety** | Implicit | Limited | Limited | Strong civic dialogue | Branding-heavy | Branding-heavy | Strong | Strong + UAI Seal-equivalent | Strong civic dialogue | Strong (NAO + AISI) | Moderate | State-managed | Strong (AI Verify) | Strong (Trustworthy AI) | **Explicit: "Australians most nervous globally about AI"** | **Strong (Plattform Lernende Systeme + Sustainable AI Brand)** | Strong — democracy + info-integrity framing |
| **AI literacy programmes** | Implicit | Some K-12 | Federal training | **Elements of AI (originated FI)** | Digital Agenda baseline | School curricula | "Aprende IA" + civic | Sectoral | "France IA" outreach | National AI Literacy initiative | Sectoral | State curricula | **AI Apprenticeship Programme + Skills Future** | School curriculum integration | National AI Skills Compact (BCA Action 3) | **Elements of AI patronage + AI Campus** | **Brazilian AI Olympiad + AI Diffusion Program** |
| **Civic-AI participation platform** | Not named | Not named | Limited | Strong civic | Not named | Not named | Sectoral | Sectoral | Sectoral | Not named | Not named | State-managed | **AI Verify Foundation 90+ corp members** | Sectoral | Limited | **Civic Innovation Platform + Civic Data Lab + Civic Tech Labs for Green** | Action 50-51 named (planned) |
| **Gender focus** | Implicit | Explicit (women + rural) | Limited | Strong | Limited | Moderate | Sectoral | Strong | Diversity | Rec 16: AI/data science = 22% women target | Sectoral | Limited | Sectoral | Sectoral | **STEM gender equity in procurement** | **#mintmagie + STEM Action Plan 2.0** | **PNPD/Lifes gender focus** |

## A.4 — Technological

| Dimension | PT | AR | US | FI | QA | AE | ES | SE | FR | GB | IT | CN | SG | JP | AU | DE | BR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **National HPC / sovereign compute** | Deucalion (EuroHPC) | Limited | Frontier + DOE labs | LUMI (EuroHPC) | National data centres | Hub ambition | MareNostrum (EuroHPC) | Berzelius + Dardel | Jean Zay + Adastra | **AIRR 20× expansion + AIGZs** | Leonardo (EuroHPC) | National supercomputing top global | NSCC | ABCI + Fugaku | Mapping compute + commercial expansion | **JUPITER exascale Q4 2024 + Gauss + LRZ + HLRS** | **Top-5 worldwide supercomputer target (Action 1)** + Sinapad 6.2 Pflop/s |
| **Sovereign LLM** | **AMALIA (PT-PT, named)** | Absent | Frontier private (OpenAI/Anthropic) | Absent | Absent | Falcon (private) | **ALIA (named, state-funded)** | Absent | **Mistral + Bull/Atos** | Frontier ambition via Sovereign AI unit | **LMM (planned)** | Multi-vendor state-supported | Absent (multi-model brokerage) | Limited (Sakana AI) | Brokerage (GovAI) not LLM | **Aleph Alpha Luminous + Stable Diffusion (market-led)** | **LLM in PT-BR (Action 9, named)** |
| **AI Safety Institute** | Centro IA Responsável (advisory) | Absent | NIST-AISI | Sectoral | Absent | Limited | AESIA (named) | Absent | INRIA + ANSSI sectoral | **AISI (UK, pre-deployment evals)** | Sectoral | State-managed | **AI Verify Foundation** | **AISI Japan** | **AISI (NAP Action 7) + BCA proposes AAISI (PPP variant)** | Sectoral (BSI + Cyber Agency + ZITiS) | National Center for Algorithmic Transparency (Action 51, planned) |
| **Sovereign data infrastructure / cloud** | Implicit | Limited | Federal cloud (FedRAMP) | EU Data Spaces | National | UAE Data Centre | EU Data Spaces | EU Data Spaces | EU Data Spaces + Mistral compute | **National Data Library (NDL)** | EU Data Spaces | National | TDM-permissive + Trusted Data Sharing | EU-bridge | GovAI (vendor-agnostic brokerage) | **GAIA-X (federated, Germany-led)** | **Sovereign Cloud (Action 27) + IND (National Data Infrastructure)** |
| **AI procurement instrument** | Standard CCP | Standard | OMB M-25-21/22 (federal) | Standard EU | Standard | Standard | Standard EU | Standard EU + ATR | Per-rec Ministry | **AI Knowledge Hub + Crown Commercial Service** | Standard EU | State-managed | **AI Verify-aligned procurement** | Standard JP | **BuyICT AI subcategories + AI Model Contract Oct 2025** | KOINNO + Federal procurement | Public-procurement AI (Action 35) |
| **Standards roadmap** | EU AI Act-derived | Limited | NIST AI RMF | EU-aligned | Standard | UAI Seal | EU + AENOR | EU + SIS | EU + AFNOR | Algorithmic Transparency Recording Std (ATRS) | EU + UNI | National + GB-T | **Model AI Governance Framework 2.0** | METI standards | DTA technical std for govt AI | **AI Standardisation Roadmap (DIN + DKE)** | **Brazilian Guides for Responsible AI (Action 50)** |
| **TEFs / regulatory sandboxes** | Implicit | Absent | NIST + sectoral | EU TEFs | Sectoral | Limited | EU TEFs | Strong sandboxes (Reallabore-like) | EU TEFs | National AI Sandbox | EU TEFs | State pilot zones | **AI Verify sandboxes** | METI sandboxes | National AI Sandbox commitment | **4 EU TEFs anchored + Reallabore network** | Pilot environments via AI Core (Action 24) |

## A.5 — Legal

| Dimension | PT | AR | US | FI | QA | AE | ES | SE | FR | GB | IT | CN | SG | JP | AU | DE | BR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Primary regulatory anchor** | **EU AI Act** | Civil law general | **Sector-based (anti-EU AI Act)** | EU AI Act | Sector-based | Sector-based | **EU AI Act** | EU AI Act | EU AI Act | **Pro-innovation principles + sector regulators (post-Brexit)** | **EU AI Act** | Generative AI Interim Measures + algorithm filing | **Model AI Governance Framework + sector-based** | **Act No. 53/2025 (AI Act, dedicated)** | **Sector-based + existing tech-neutral law (NOT EU AI Act path)** | EU AI Act + research-exemption push | **Bill 2338/23 pending + LGPD-anchored** |
| **Copyright / TDM stance** | EU CDSM Art. 4 (opt-out, default) | Limited | Activist + fair-use leaning | EU CDSM | Limited | Limited | EU CDSM | EU CDSM | EU CDSM | **TDM exception with opt-out (proposed)** | EU CDSM | Permissive for state-aligned | **TDM-permissive (singular EU+ jurisdiction)** | TDM exception (Copyright Act Art. 30-4) | **NAP explicitly rules OUT TDM exception (protect creators)** vs BCA pushes for it | TDM via EU CDSM | TDM under review (AGD) |
| **Privacy law** | RGPD | LGPD (Argentina) | Sectoral (CCPA, HIPAA) | GDPR | PDPL | DIFC DPL | GDPR + LOPDGDD | GDPR | GDPR + Loi Inf. Lib. | UK GDPR + DPA 2018 | GDPR + Codice Privacy | PIPL | PDPA | APPI | Privacy Act 1988 (modernisation) | GDPR + BDSG | **LGPD (Lei Geral de Proteção de Dados)** |
| **AI-specific legislation** | Absent | Absent | Executive orders | Absent | Absent | Absent | AESIA decree | Absent | Absent | Future legislation paused | Absent | Generative AI Interim Measures | Absent (Model framework) | **Act No. 53/2025 (dedicated AI Act)** | Absent (sectoral) | Absent (EU AI Act transposition) | **Bill 2338/23 in Congress** |
| **Algorithmic transparency standard** | Implicit | Absent | OMB transparency (federal) | EU-aligned | Absent | Limited | EU AI Act-aligned | EU AI Act-aligned | EU AI Act-aligned | **ATRS (Algorithmic Transparency Recording Standard, mandatory in-scope)** | EU AI Act-aligned | Algorithm filing requirement | "Being clear about AI-generated content" (voluntary) | Trustworthy AI guidelines | "Being clear about AI-generated content" (NAIC voluntary) | Sectoral via standardisation roadmap | National Center for Algorithmic Transparency (planned, Action 51) |
| **Liability framework** | EU AI Act + Product Liability Dir. | Civil law | Sectoral tort | EU AI Act + PLD | Sectoral | Sectoral | EU AI Act + PLD | EU AI Act + PLD | EU AI Act + PLD | Common law | EU AI Act + PLD | State-administered | Common law + sectoral | Civil law + sectoral | Sectoral (no horizontal AI liability) | EU AI Act + PLD + product safety review | Civil law + LGPD |
| **Oversight body** | CNPD + ANACOM sectoral | Limited | FTC + sectoral | DPA Finland | CIRT-Qatar | UAE Data Office | AEPD + AESIA | IMY | CNIL | ICO + AISI + sectoral | Garante + AGCOM | CAC + NDRC | PDPC + IMDA | PIPC + DPA | **AI Review Committee (APS Plan)** + OAIC + sectoral | BSI + BfDI + sectoral | ANPD + sectoral + national centre |

## A.6 — Environmental

| Dimension | PT | AR | US | FI | QA | AE | ES | SE | FR | GB | IT | CN | SG | JP | AU | DE | BR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Renewable energy share / target** | ~60% renewable | Mixed | Mixed (state-vary) | Strong (75%+) | Gas-dominant | Solar push (Masdar) | ~50% renewable | Strong (60%+) | Nuclear-dominant low-carbon | ~40% low-carbon | ~40% renewable | Coal-dominant + renewable expansion | Limited domestic | ~25% renewable | Renewable expansion + transition | ~50% renewable + Energiewende | **89.2% renewable (2023, EPE)** |
| **Data centre sustainability stance** | Implicit | Limited | Mixed | Strong | Hub framing | Hub | **Palanca 2 sustainable DCs** | **Sustainable DC + Energy Performance Act** | EU-aligned | Sustainability + AI Energy Council | Implicit | Limited explicit | Trusted + carbon-neutral pilots | Sectoral | **National DC principles + CDC LiquidCore + 100% net-zero electricity** | **Green ICT + EMAS digital platform + data centre energy review** | **Action 7 Sustainable AI Pro-Infra + Action 41 N/NE renewable DCs** |
| **Water cooling / efficiency** | Limited | Limited | Mixed | Cold-climate advantage | Limited | Limited | Sectoral | Sectoral | Sectoral | UK water dialogue | Sectoral | Limited | Implicit | Sectoral | **CDC LiquidCore near-zero water** | Standardisation focus | **Hydroelectric reservoir cooling potential** |
| **Sustainable AI brand / framing** | Implicit | Limited | Limited | **"Twin transition" + carbon handprint** | Hub-branding | Hub-branding | EU Green Deal | Strong | EU Green Deal | AI Energy Council | EU Green Deal | Limited | Trusted-AI sustainable | Sectoral | **"Net-zero data centre principles" + sustainable AI** | **"Sustainable AI Brand" + Sustainability-by-Design + Ethics-by-Design** | **"AI for Good of All" sustainability differentiator** |
| **AI for climate / environment focus** | Implicit | Some | Limited | Strong (twin transition) | Limited | Sectoral | EU-aligned | Strong | EU + Aghion-Bouverot | Climate-tech focus | EU-aligned | Limited | **AI for SDGs framing** | Sectoral | **National AI principles + Indigenous Kakadu case study** | **KI-Leuchttürme + Recycling/Circular Economy AI Hub + Sustainable AI + Resource-efficient AI** | **SIPEC Climate Prediction (Action 40) + Amazon biome AI (Imm. Action 25)** |
| **Carbon handprint / footprint target** | Implicit | Limited | Limited | **Carbon handprint named** | Limited | Limited | EU-aligned | EU-aligned | EU-aligned | Limited | EU-aligned | Limited | Singapore Green Plan | Sectoral | DC sustainability principles | **CO2-saving potential study commissioned + Resource-efficient AI initiative** | Net-zero alignment via PTE (Ecological Transition Plan) |
| **Energy-efficient AI research focus** | Implicit | Absent | Limited | Strong | Limited | Limited | Sectoral | Strong (Berzelius energy KPIs) | Sectoral | Sectoral | Sectoral | State-managed | **Green AI initiatives** | Sectoral | Sectoral | **AI electronics + NeuroTEC II + neuromorphic + Pilot innovation competition "Energy-efficient AI system"** | Energy efficiency embedded in Axis 1 Sustainable AI program |

---

# Section B — Pillar-Coverage Matrix (Common-Denominator Framework)

When all 17 country plans' surface structures (pillars / axes / priorities / sections / themes) are collapsed to a common denominator, **6 universal pillars** emerge that every plan covers in some proportion. This table shows **how each country's plan structurally maps** to those 6 pillars.

**Prominence legend:**
- **● LEAD** — country has a standalone pillar / axis / section dedicated to this universal pillar
- **◐ SHARED** — covered substantively but merged with another pillar
- **○ FOLDED-IN** — covered implicitly via guiding principles or scattered initiatives, not as a structural pillar
- **— ABSENT** — not addressed (or addressed only marginally)

The cell text gives the country's actual pillar/axis name (where present) plus the prominence marker.

| Universal Pillar | PT | AR | US | FI | QA | AE | ES | SE | FR | GB | IT | CN | SG | JP | AU | DE | BR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **1. Infrastructure & Data** | Scattered ○ | Digital infra ◐ | "Build" ● | Compute+data ◐ | Digital infra ● | Smart govt ◐ | Palanca 2+7 ● | Computing+data ● | Compute+data theme ● | "Foundations" §1.1+§1.2 ● | Implicit ○ | State infra ◐ | Compute+Data enablers ● | Computing infra ● | BCA Infra+Data + NAP Action 1 ● | Aktionsplan Ch. 2 + GAIA-X ● | Axis 1 (25.2%) ● |
| **2. Talent & R&D** | Pillar I (Talent) ● | Talent area ◐ | "Innovate" ◐ | Talent area ◐ | Skills area ◐ | Skills area ◐ | Palanca 1 ● | Talent area ● | Talent + R&D theme ● | §1.3 (Talent) ● | Research + Education ● | "AI+ Science" ● | Talent enablers ● | R&D + Talent pillars ● | BCA Skills + R&D; NAP Action 5 ● | Minds + Research priorities ● | Axis 2 (Diffusion/Training) ● |
| **3. Business Adoption** | Pillar II (Application) ● | Business area ◐ | "Innovate" ◐ | "Apply AI" ● | Sectoral areas ◐ | Sectoral areas ◐ | Palanca 4+5 ● | Business area ● | Business theme ● | §2 "Change lives" ◐ | Business objective ● | "AI+ Industry/Consumption" ● | Industry enablers ● | "Use of AI" pillar ● | NAP Spread (Action 4) + BCA Adoption ● | Transfer & Application priority ● | Axis 4 (59.9%) ● |
| **4. Public Administration** | Pillar III (PA) ● | Digital govt ◐ | CAIOC (within Innovate) ◐ | PA initiatives ◐ | Smart-govt pillar ● | "Govt of the Future" ● | Palanca 6 ● | PA area ● | PA recommendations ◐ | **Playbook (entire 118 pp)** ● | PA objective ● | "AI+ Governance" ● | Govt enablers ● | PA initiatives ◐ | **Entire APS AI Plan** ● | Implicit in Transfer & Application ◐ | Axis 3 + Federal AI Core ● |
| **5. Society** | 6 principles ○ | Gender+rural+K-12 ◐ | Worker-displacement only ○ | Twin-transition + citizens ◐ | Digital citizenship ◐ | UAI Seal branding ○ | Palanca 8 humanistic ◐ | Worker voice + inclusion ● | Society theme ◐ | §2 "Change lives" partial ◐ | Education objective ◐ | "AI+ Welfare + Consumption" ● | **Creators/Practitioners/Users trichotomy** ● | Society/Trust pillars ◐ | **NAP "Spread the Benefits" + Indigenous Data Sovereignty** ● | **"Society" priority + Civic AI initiatives** ● | 5 pillars of "AI for Good of All" + CadÚnico actions ◐ |
| **6. Governance & International** | Pillar IV (Governance) ● | Governance area ◐ | "Lead Internationally" ● | Regulation + intl coop ◐ | Governance area ◐ | Strategy oversight ◐ | Palanca 8 + AESIA ● | Regulation + intl ◐ | Regulation + intl theme ● | §3 "Secure future" ● | Governance objective ● | "AI+ Governance + Global Coop" ● | **AI Verify Foundation + global** ● | **Act No. 53/2025 + Hiroshima Process** ● | NAP "Keep Safe" (Action 7-9) ● | Regulatory framework + Intl coop ● | Axis 5 (Reg + Gov) ● |

## B.1 — Pillar coverage summary (counts across 17 jurisdictions)

| Universal Pillar | LEAD ● | SHARED ◐ | FOLDED-IN ○ | ABSENT — | Portugal status |
|---|---|---|---|---|---|
| **1. Infrastructure & Data** | 12 | 4 | 1 (PT) | 0 | **○ FOLDED-IN** — Portugal is among the 1 of 17 without a standalone pillar |
| **2. Talent & R&D** | 14 | 3 | 0 | 0 | ● LEAD |
| **3. Business Adoption** | 14 | 3 | 0 | 0 | ● LEAD |
| **4. Public Administration** | 11 | 6 | 0 | 0 | ● LEAD |
| **5. Society** | 4 | 11 | 2 (PT+US+AE) | 0 | **○ FOLDED-IN** — Portugal is among 2-3 of 17 without a standalone pillar |
| **6. Governance & International** | 14 | 3 | 0 | 0 | ● LEAD |

**Headline finding from B.1:** Portugal's ANIA has **two structural gaps vs the common-denominator framework**:

1. **Infrastructure & Data** — Portugal is the **only jurisdiction in this 17-country comparator set** that folds Infrastructure & Data into other pillars rather than giving it standalone status. Every other plan (12 LEAD + 4 SHARED) treats this as either a dedicated pillar or a substantive shared section. The implication is that ANIA's compute, data-space, sovereign-cloud, and standards commitments are diffuse and harder to track / measure / fund as a coherent programme.

2. **Society** — Portugal folds inclusion + trust + civic-AI into its 6 guiding principles rather than as a structural pillar. 4 jurisdictions LEAD on Society (China, Singapore, Australia, Germany), 11 SHARE it, and Portugal is among just 2-3 that FOLD-IN. **Caveat:** US and UAE also fold-in but for different reasons (US deliberate political minimalism; UAE branding-heavy approach). Portugal's folding-in is harder to defend given its EU-anchored inclusion commitments.

Both gaps are flagged for discussion in the final report (per user note 2026-05-16: *"we can discuss the pillars selection/omission"*). Possible resolutions:
- **Option A — Adopt the 6-pillar universal structure** in ANIA evolution (most invasive)
- **Option B — Keep 4 visible pillars but mandate cross-cutting Infrastructure + Society sub-sections** (compromise)
- **Option C — Defend 4-pillar parsimony** and rely on principles + cross-cutting language (status quo; weakest)

---

*Section B complete. Section C (Per-pillar deep-dives) follows.*
