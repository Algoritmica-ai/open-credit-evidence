# Italy obligation registry

Country code: `IT`  
Registry: [`registry.json`](registry.json)  
Last legal-source verification: **15 September 2026**

## Scope assumption

This first version assumes an Italian bank or financial intermediary under Article 106 of the
Italian Banking Act that lends to natural persons, offers consumer and/or mortgage credit, uses
credit-information systems, and uses AI or other automated processing in credit assessment.

The registry is a regulatory perimeter, not an exhaustive legal opinion. Product, entity, borrower,
distribution-channel, outsourcing, and group-specific rules can add or remove obligations.

## Priority IDs for the Credit Evidence Engine

| ID | Why it matters to the engine |
|---|---|
| `IT-TUB-124-BIS-1-TER` | Requires documented and updated creditworthiness procedures and information |
| `IT-TUB-124-BIS-2-BIS-A` | Requires a clear and understandable explanation when automated processing is involved |
| `IT-TUB-124-BIS-2-BIS-B` | Lets the consumer express their position |
| `IT-TUB-124-BIS-2-BIS-C` | Requires a route to human reconsideration |
| `IT-TUB-124-BIS-2-TER` | Requires the lender to obtain explanation information from third-party technology providers |
| `IT-TUB-124-BIS-2-SEXIES` | Requires rejection information and, where relevant, automated-processing and review information |
| `IT-TUB-125-1-QUINQUIES` | Prohibits special-category and social-network data for creditworthiness assessment |
| `IT-TUB-125-4` | Requires credit-database information to be accurate, current, and promptly corrected |
| `IT-TUB-127-TER` | Extends automated-assessment protections to covered financing contracts |
| `IT-SIC-CODE-2019` | Governs private credit-information systems, notices, accuracy, rights and retention |

## 2026 transition

Legislative Decree 212/2025 entered into force on 10 January 2026. Its operator-adaptation deadline
is generally 20 November 2026, or 90 days after the Bank of Italy implementing provisions enter
into force if that is later. Entries affected by this transition are marked `transition`.

Official sources:

- [Legislative Decree 212/2025](https://www.normattiva.it/atto/caricaDettaglioAtto?atto.codiceRedazionale=26G00009&atto.dataPubblicazioneGazzetta=2026-01-09&tipoDettaglio=multivigenza)
- [Italian Banking Act](https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:1993-09-01;385)
- [Bank of Italy note on the CCD2 transition](https://www.bancaditalia.it/pubblicazioni/note-stabilita/2026-0050/Note-di-stabilita-finanziaria-e-vigilanza-n-50.pdf)

## EU baseline

Italy-specific obligations apply alongside the GDPR and, where applicable, the EU AI Act. The
shared FINOS mapping is maintained in [`eu-ai-act-finos-controls.md`](../../docs/regulations/eu-ai-act-finos-controls.md)
rather than duplicated here.

## Non-claims

An evidence pack can demonstrate that particular facts were checked, a summary passed
or failed a materiality rule, and linked technical controls ran. It does not establish that the
lender completed the legally required creditworthiness assessment, delivered a legally sufficient
consumer explanation, complied with every data-protection requirement, or complied with Italian
banking law overall.
