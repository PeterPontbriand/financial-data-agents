# SEC EDGAR FPI / IFRS D0 Mapping Record

**Decision date:** 2026-08-31<br/>
**Status:** corrected design approved for planning; production implementation not yet authorized<br/>
**Placement:** Step 2.5A, after Step 2.5 completion and before Step 2.6<br/>
**Execution plan:** [SEC EDGAR FPI / IFRS Slice Plan](SEC_EDGAR_FPI_IFRS_SLICE_PLAN.md)

## 1. Decision summary

The production SEC EDGAR adapter may be extended in two deliberately separate
increments:

1. accept annual `20-F`, `20-F/A`, `40-F`, and `40-F/A` duration facts for the
   already-approved exact US-GAAP concepts; and
2. add a narrow IFRS duration-fact mapping for annual diluted EPS, weighted
   average diluted shares, operating cash flow, and physical-PP&E capital
   expenditure.

IFRS book value per common share is explicitly deferred. The reviewed proposal's
zero-preferred-share inference is rejected because absence of a Company Facts
value does not establish zero preferred shares, and entity-level Company Facts
does not preserve the dimensional share-class evidence required to prove
ordinary/common equity and ordinary/common shares.

The extension must preserve the existing strict `as_of`, availability,
restatement, duplicate, currency, annual-period, provenance, and no-substitution
rules. Missing or ambiguous evidence remains unavailable; it is never replaced
with zero or a plausible alternate concept.

## 2. Scope and non-scope

### 2.1 Phase A1 — annual-form expansion for existing US-GAAP duration facts

Add `20-F`, `20-F/A`, `40-F`, and `40-F/A` only to the common annual-duration
eligibility used by:

- `us-gaap:NetCashProvidedByUsedInOperatingActivities`;
- `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`;
- `us-gaap:EarningsPerShareDiluted`; and
- the existing approved weighted-average diluted-share concept where the FCF
  strategy requires it.

Do not broaden the balance-sheet/instant-fact form set in A1. In particular, do
not change `_BALANCE_SHEET_FORMS` or treat A1 as approval for foreign-filer BVPS.
ASML's US-GAAP `20-F` reporting is the initial high-signal fixture candidate for
this form-only path.

### 2.2 Phase B1 — narrow IFRS duration-fact mapping

The first IFRS implementation is limited to these exact concepts:

| Project field | Exact IFRS concept | Required meaning and normalization |
| :--- | :--- | :--- |
| Annual diluted EPS | `ifrs-full:DilutedEarningsLossPerShare` | Preserve signed value; annual duration; `<currency>/shares`. |
| Weighted-average diluted shares | `ifrs-full:AdjustedWeightedAverageShares` | Preserve non-negative shares; annual duration; compatible with the EPS period and basis. |
| Operating cash flow | `ifrs-full:CashFlowsFromUsedInOperatingActivities` | Preserve signed value; annual duration; monetary unit. |
| Physical-PP&E CapEx | `ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities` | `positive_expenditure`; reject negative raw values; no `abs()` and no summation. |

There is no alternate-concept precedence list in B1. A missing exact concept is
unavailable. Broader purchases of property, plant, equipment, intangibles, or
other investing assets are not definition-identical to the selected physical-
PP&E project definition and must not be substituted or summed.

### 2.3 Explicitly deferred Phase B2

The following are not approved for implementation in A1 or B1:

- IFRS-derived book value per common/ordinary share;
- a preferred-shares-equal-zero inference based on absent facts;
- use of generic `NumberOfSharesOutstanding` as proof of ordinary/common shares;
- dimensional/context parsing from filing XBRL instances;
- ADR/ADS ratio conversion or currency conversion;
- custom issuer-extension mapping;
- multi-class security allocation; or
- broad concept fallback or fuzzy taxonomy matching.

Phase B2 requires a separate evidence record proving dimensional ordinary-share
capital, preference-share deductions, share-class scope, and security-unit
compatibility. Until then, IFRS Graham Number resolution remains unavailable
unless BVPS is supplied through another already-approved explicit route.

## 3. Accounting-taxonomy regime selection

The adapter must not classify an issuer for all time merely because any
historical fact exists under `us-gaap` or `ifrs-full`. That rule becomes stale
when an issuer changes filing taxonomy or reporting regime.

For each requested analysis:

1. resolve one immutable analysis-scoped SEC snapshot containing the Company
   Facts payload and the submissions/accession availability evidence used by all
   requested fields;
2. identify the latest eligible annual filing/accession available at the
   effective `as_of` boundary;
3. select the filing taxonomy/regime evidenced by that accession;
4. require the requested annual observation span to be homogeneous under the
   selected taxonomy and compatible concepts; and
5. return unavailable/ambiguous when the regime cannot be established or the
   requested span crosses an unproved accounting-basis transition.

The snapshot prevents field-by-field network retrieval from silently combining
payload versions. It is immutable within one analysis and records retrieval time,
CIK, accession evidence, taxonomy namespace, and payload identifiers/checksums
needed for auditability. Production cache persistence is not part of Step 2.5A.

## 4. Shared eligibility and evidence rules

The existing Step 2.4 mapping remains authoritative except where this record
explicitly expands it. Each accepted fact must still satisfy:

- the requested ticker resolves to one unambiguous CIK/security identity;
- the fact belongs to the selected taxonomy regime and exact approved concept;
- its form is an approved annual form or amendment;
- `fp` is `FY` where the provider supplies it consistently;
- start/end dates describe one completed annual duration, including a 52/53-week
  fiscal year rather than quarterly, YTD, TTM, or instant data;
- period end and public availability do not exceed effective `as_of`;
- currency/unit/scope are compatible across the selected observation;
- later comparative facts are grouped by exact period dates and treated as
  restatements/re-presentations rather than extra fiscal years; and
- disagreeing equal-rank facts remain `ambiguous_fact`.

All four B1 fields are duration facts. Balance-sheet instants remain outside B1.
The existing conservative acceptance-time lookup and filed-date fallback apply
unchanged.

## 5. Per-share security-unit gate

Foreign private issuers introduce a security-unit risk that is separate from
accounting taxonomy. Filing EPS and weighted-average shares can describe issuer
ordinary shares while the market quote describes an ADR/ADS representing a
different number of ordinary shares, and the quote currency can differ from the
filing currency.

Therefore:

- issuer-level monetary FCF and FCF growth may resolve when their own fact,
  currency, period, and taxonomy requirements are satisfied;
- per-share growth comparisons require EPS and weighted-average shares to share
  a proven issuer-share basis across the requested span;
- any comparison with a market quote requires affirmative evidence that the
  quoted security is the same unit as the filing per-share value, or a separately
  approved explicit ADR/ADS ratio and currency-conversion policy; and
- the first implementation is limited to proven ordinary-share / 1:1 quoted-unit
  shapes. Missing unit evidence makes the per-share or quote-dependent output
  unavailable without invalidating independently supported issuer-level facts.

Ticker text, issuer name, absence of a ratio field, or a provider's generic
`shares` unit is not proof of 1:1 compatibility.

## 6. Representative evidence matrix

The following live Company Facts reconnaissance was reviewed on 2026-08-31. It
is discovery evidence, not a committed deterministic fixture and not permission
for tests to call the network.

| Issuer | Filing/taxonomy shape | B1 observations | Design consequence |
| :--- | :--- | :--- | :--- |
| Nutrien (`NTR`) | IFRS foreign private issuer | Exact diluted EPS, adjusted weighted-average shares, operating cash flow, physical-PP&E CapEx, and parent equity appear through 2024; generic shares also appear. | Positive B1 candidate; parent equity plus generic shares still does not prove IFRS BVPS or zero preferred shares. |
| SAP (`SAP`) | IFRS foreign private issuer | Exact diluted EPS, adjusted weighted-average shares, operating cash flow, and parent equity appear; selected physical-PP&E CapEx concept is absent. | Proves exact-concept unavailability must remain valid; do not substitute a broader combined CapEx concept. |
| Novo Nordisk (`NVO`) | IFRS foreign private issuer / ADR | Exact diluted EPS, adjusted weighted-average shares, operating cash flow, physical-PP&E CapEx, and generic shares appear; selected parent-equity evidence is absent. | Useful B1/ADR negative boundary; no IFRS BVPS inference. |
| ASML (`ASML`) | US-GAAP `20-F` filer | Existing exact US-GAAP duration concepts appear under foreign annual forms. | Positive A1 form-expansion candidate; does not by itself authorize IFRS mappings or instant-fact expansion. |

Primary discovery references:

- [SEC EDGAR APIs and Company Facts documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [Nutrien Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0001725964.json)
- [SAP Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0001000184.json)
- [Novo Nordisk Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000353278.json)
- [ASML Company Facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000937966.json)
- [IFRS Accounting Taxonomy 2025](https://www.ifrs.org/issued-standards/ifrs-taxonomy/ifrs-accounting-taxonomy-2025/)
- [IFRS XBRL preparer's guide](https://www.ifrs.org/content/dam/ifrs/resources-for/preparers/xbrl-using-the-ifrs-taxonomy-a-preparers-guide-december-2017.pdf)

Before implementation, the useful fragments of this evidence must be minimized,
sanitized, checksummed, and committed as deterministic fixtures. Live payloads
must not become test dependencies or production cache seed data.

## 7. Deterministic test obligations

At minimum, Step 2.5A must prove:

- US-GAAP exact duration concepts accept `20-F`/`40-F` and amendments while
  existing `10-K` behavior remains unchanged;
- balance-sheet forms are not broadened by A1;
- each exact IFRS B1 concept maps independently with its required units, sign,
  period, and provenance;
- missing SAP physical-PP&E CapEx remains unavailable;
- negative raw IFRS CapEx is rejected rather than normalized with `abs()`;
- regime selection follows the latest eligible annual accession at `as_of`, not
  lifetime namespace presence;
- a cross-regime requested span is unavailable unless an explicit common basis
  is proven;
- all fields in one analysis use the same immutable SEC snapshot;
- later filings do not leak across historical `as_of` boundaries;
- ADR/ADS or unknown security-unit evidence blocks quote/per-share comparisons
  without erasing independently valid issuer-level results;
- missing preferred-share evidence never becomes zero; and
- no test performs a real SEC, quote-provider, or LLM call.

Any Golden Suite additions must be versioned, preserve existing case IDs and
historical fixtures, and be added only after the Step 2.5 Gate M corrections and
Step 2.5 closeout establish a stable benchmark-extension workflow.

## 8. Rejected alternatives

| Alternative | Decision | Reason |
| :--- | :--- | :--- |
| Treat any historical US-GAAP fact as a permanent US-GAAP lock | Rejected | Ignores issuer regime changes and the requested `as_of` span. |
| Infer zero preferred shares when no IFRS preferred fact is found | Rejected | Missing evidence is not zero; Company Facts loses dimensions needed for the proof. |
| Use generic outstanding shares for IFRS BVPS | Rejected | Does not prove ordinary/common class, denominator date, or ADR/ADS unit. |
| Expand all annual forms including balance-sheet facts in A1 | Rejected | Duration-field evidence does not establish safe instant/share-capital semantics. |
| Substitute or sum broader IFRS CapEx concepts | Rejected | Changes the project FCF definition and can mix physical PP&E with intangibles or other assets. |
| Fetch Company Facts independently for every field | Rejected | Can mix payload versions and weakens analysis-level reproducibility. |
| Assume ticker quote and filing per-share units are identical | Rejected | Foreign listings and ADR/ADS ratios make that assumption unsafe. |

## 9. Approval boundary

This record approves the corrected design and its placement in the plan. It does
not authorize implementation while Step 2.5 is paused at Gate M, and it does not
change current production support claims. The current Step 2.4 mapping continues
to report `20-F`/`40-F` and IFRS shapes as unavailable until the corresponding
Step 2.5A slice is implemented, verified, reviewed, and approved.
