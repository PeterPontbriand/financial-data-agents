# Free Cash Flow & Earnings Growth Provider Mapping Record

**Status:** D0 evidence checkpoint complete and approved; D1 authorized next  
**Scope:** SEC EDGAR required annual actuals only  
**Prepared:** 2026-08-27  
**Governing design:** `STEP_2_4_FCF_EARNINGS_GROWTH_DESIGN.md`  
**Production changes:** None

## 1. Decision summary

This record defines the approved deliberately narrow mapping for D1-D5.
Production support remains disabled until the applicable implementation slice
adds and verifies each capability.

| Capability | D0 disposition | Exact SEC concept |
| :--- | :--- | :--- |
| Annual operating cash flow | Supported candidate | `us-gaap:NetCashProvidedByUsedInOperatingActivities` |
| Annual capital expenditures | Supported candidate | `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` |
| Annual diluted EPS | Supported candidate with the split-basis reconciliation rule in Section 5 | `us-gaap:EarningsPerShareDiluted` |
| Market capitalization | Unsupported | None approved |
| FY1/FY2 consensus EPS | Unsupported | None approved |

The supported candidate requires all three annual facts to pass the common
identity, period, unit, currency, scope, availability, duplicate, and
restatement rules below. An unlisted concept or evidence shape returns typed
unavailability; it is never guessed, summed, converted, or silently replaced.

## 2. Evidence base

Authoritative sources reviewed on 2026-08-27:

1. SEC, **EDGAR Application Programming Interfaces (APIs)**. The SEC documents
   Company Facts as company-level, standard-taxonomy XBRL facts grouped by unit;
   facts can cover forms including 10-K, 10-Q, 20-F, and 40-F. The API updates
   after filing dissemination and does not make all filing shapes semantically
   interchangeable.  
   <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
2. SEC, **EDGAR XBRL Guide, January 2026**. The guide identifies
   `NetCashProvidedByUsedInOperatingActivities` as the appropriate total for a
   disclosure of net cash provided by or used in operating activities and
   distinguishes it from totals spanning more than operating activity.  
   <https://www.sec.gov/file/xbrl-guide-2026-01-16>
3. SEC US-GAAP taxonomy definitions exposed in Company Facts:
   `NetCashProvidedByUsedInOperatingActivities` is cash inflow/outflow from
   operating activities; `PaymentsToAcquirePropertyPlantAndEquipment` is cash
   outflow to acquire long-lived physical operating assets, including
   self-constructed assets; `EarningsPerShareDiluted` is income available per
   common share including dilutive potential shares.
4. SEC, **Company Tickers** and **Company Tickers Exchange**, for the public
   ticker-to-CIK identity files.  
   <https://www.sec.gov/file/company-tickers>  
   <https://www.sec.gov/file/company-tickers-exchange>
5. SEC, **Webmaster Frequently Asked Questions**, for EDGAR acceptance-date and
   acceptance-time meaning. The SEC states that acceptance time is assigned in
   Eastern time and also cautions that it does not publish a separate timestamp
   for when filing content first became available on sec.gov.  
   <https://www.sec.gov/about/webmaster-frequently-asked-questions>

Representative official JSON payloads reviewed on 2026-08-27:

| Security | CIK | Evidence observed |
| :--- | :--- | :--- |
| Microsoft (`MSFT`) | `0000789019` | USD annual operating cash flow, PP&E acquisition payments, and diluted EPS; comparative periods repeat in later 10-K filings. |
| Coca-Cola (`KO`) | `0000021344` | USD annual observations for all three candidate concepts. |
| Apple (`AAPL`) | `0000320193` | 52/53-week annual periods, a historical transition from `PaymentsToAcquireProductiveAssets` to the candidate PP&E concept, and split-adjusted EPS re-presentations. |
| JPMorgan Chase (`JPM`) | `0000019617` | Annual operating cash flow and diluted EPS, no candidate PP&E concept, and multiple tickers for one CIK. This is an unsupported complete-strategy shape. |

The representative payloads are research evidence, not production fixtures.
D1-D3 must add minimal deterministic mocked excerpts that retain only the fields
needed to prove the approved rules; tests must not call EDGAR.

## 3. Common SEC eligibility and identity rules

### 3.1 Security identity

The initial supported identity shape is:

1. normalize the requested ticker to uppercase;
2. require an exact entry in the current SEC ticker file;
3. resolve that entry to its zero-padded CIK;
4. require the Company Facts `cik` and entity to match that CIK; and
5. require that CIK to have exactly one listed ticker in the SEC mapping.

The requested ticker and resolved CIK both remain in provenance. A missing or
ambiguous ticker mapping is unavailable, not a provider guess. A CIK associated
with multiple listed securities or share classes is unsupported in this first
mapping because Company Facts supplies entity-wide standard-taxonomy facts and
does not prove that diluted EPS belongs to the requested listed class. Examples
observed include `BRK-A`/`BRK-B`, `GOOG`/`GOOGL`, and the common/preferred and
note tickers associated with JPMorgan's CIK.

### 3.2 Filing and period shape

An accepted annual candidate must have:

- namespace `us-gaap` and the exact approved concept;
- `form` equal to `10-K` or `10-K/A`;
- `fp` equal to `FY`;
- parseable `start`, `end`, `filed`, and `accn` fields;
- a duration consistent with one completed company fiscal year, including a
  52/53-week year, rather than a quarter, year-to-date, TTM, or instant fact;
- `end <= effective_as_of`; and
- an approved `available_at <= effective_as_of`.

Exact `start` and `end` dates identify the fiscal period. The Company Facts
`fy` field is retained as provider evidence but is not used as the observation's
fiscal-year label: representative payloads attach the current filing's `fy` to
comparative prior-year facts. The project fiscal-year label is the calendar year
containing the exact period end unless a later evidence record approves a more
specific issuer fiscal-year identity source.

Forms 20-F, 40-F, 6-K, 10-Q, and their amendments are unsupported by this
mapping. IFRS concepts, custom issuer extensions, frames, instant facts, and
facts with dimensions or scope that cannot be established as consolidated are
also unsupported.

### 3.3 Units, currency, and scope

- Operating cash flow and capital expenditures accept one ISO-like three-letter
  monetary unit key such as `USD`; that key becomes the fact currency.
- Diluted EPS accepts the matching `<currency>/shares` unit key such as
  `USD/shares`.
- All three facts in an annual observation must share the same currency.
- No currency conversion is performed.
- Company Facts covers facts applying to the entire filing entity. Any
  dimensional, segment, subsidiary, continuing-operations-only, or
  class-specific shape outside that company-level API surface is unsupported.

## 4. Required cash-flow mappings

### 4.1 Operating cash flow

| Mapping field | Approved candidate rule |
| :--- | :--- |
| Provider and capability | `sec_edgar` / annual operating cash flow |
| Exact source concept | `us-gaap:NetCashProvidedByUsedInOperatingActivities` only |
| Selection precedence | No alternate concept; exact concept or unavailable |
| Financial meaning | Net cash inflow or outflow from all operating activities, including discontinued operations when present in the filer total |
| Sign transform | Not applicable; preserve the signed raw value |
| Period rules | Common annual eligibility in Section 3; duration must be one completed fiscal year |
| Units/currency/scope | Monetary ISO-like unit; consolidated entire-entity fact; currency must match CapEx and EPS |
| Availability | Section 6 |
| Restatements/duplicates | Section 6 |
| Security identity | Section 3.1 |

Explicitly unsupported operating-cash-flow shapes include
`NetCashProvidedByUsedInOperatingActivitiesContinuingOperations`,
`NetCashProvidedByUsedInContinuingOperations`, totals covering operating plus
investing or financing activity, subtotals/components, custom extensions, and
any attempt to synthesize the total by summing cash-flow-statement lines.

### 4.2 Capital expenditures

| Mapping field | Approved candidate rule |
| :--- | :--- |
| Provider and capability | `sec_edgar` / annual capital expenditures |
| Exact source concept | `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` only |
| Selection precedence | No alternate concept; exact concept or unavailable |
| Financial meaning | Cash paid to acquire long-lived physical PP&E used in operations, including construction of self-constructed assets |
| Included | Acquisitions and capital improvements within the exact taxonomy concept |
| Excluded | Acquired businesses, financial investments, proceeds from asset sales, leases without cash purchase evidence, working capital, and separately tagged intangible/software expenditure not included by the filer in the exact PP&E concept |
| Sign transform | `positive_expenditure`: normalized CapEx equals the non-negative raw value |
| Period rules | Common annual eligibility in Section 3; exact period must match operating cash flow |
| Units/currency/scope | Monetary ISO-like unit; consolidated entire-entity fact; currency must match operating cash flow and EPS |
| Availability | Section 6 |
| Restatements/duplicates | Section 6 |
| Security identity | Section 3.1 |

Zero is valid. A negative raw value contradicts this concept's cash-outflow
mapping and is rejected as ambiguous; `abs()` is prohibited.

Explicitly unsupported CapEx shapes include
`PaymentsToAcquireProductiveAssets`,
`PaymentsToAcquireOtherPropertyPlantAndEquipment`, custom issuer extensions,
precomputed provider free cash flow, and any sum of plausible acquisition or
investment concepts. Apple's older `PaymentsToAcquireProductiveAssets` history
illustrates why concept substitution is unsafe: its definition can include
software and other intangible assets, so it is not identical to the selected
physical-PP&E definition. A period without the exact approved concept has
unavailable CapEx and therefore unavailable derived FCF.

## 5. Annual diluted-EPS mapping and split reconciliation

| Mapping field | Approved candidate rule |
| :--- | :--- |
| Provider and capability | `sec_edgar` / completed annual diluted EPS |
| Exact source concept | `us-gaap:EarningsPerShareDiluted` only |
| Selection precedence | No basic-EPS or TTM fallback |
| Financial meaning | Net income/loss available per common share including dilutive potential common shares |
| Sign transform | None; retain positive, zero, or negative EPS |
| Period rules | Common annual eligibility in Section 3; exact period must match the two cash-flow facts |
| Units/currency/scope | `<currency>/shares`; entire-entity non-dimensional fact; currency must match cash-flow facts |
| Availability | Section 6 |
| Restatements/duplicates | Section 6 plus the common-basis rule below |
| Security identity | Section 3.1; multi-ticker CIKs are unsupported |

`EarningsPerShareBasic`, TTM facts, quarterly/YTD facts, custom concepts, and
dimensional or class-specific EPS are unsupported.

### 5.1 Common split/accounting basis

Company Facts does not attach a normalized split-basis identifier to each EPS
observation. Apple demonstrates that selecting the latest value independently
for each period can mix bases: its FY2018 diluted EPS appears as `11.91` in the
2018 and 2019 filings and as split-adjusted `2.98` in the 2020 filing, while
still older periods are not all re-presented in that 2020 filing.

For a selected CAGR span:

1. retain every eligible candidate for each exact annual period;
2. detect each remeasurement event where a later filing reports a different
   EPS value for the same exact period, concept, unit, and scope;
3. let the latest such event affecting any candidate at or before the selected
   span define the minimum common-basis filing/availability boundary; and
4. require every EPS period in the span to have been reported or re-presented
   on or after that boundary.

If an older endpoint was not re-presented on the common basis, the requested
span is unavailable rather than mixing pre-split and post-split EPS. Identical
repeated values are duplicates, not remeasurements. The project applies no
independent arithmetic split adjustment.

This rule is intentionally conservative. If deterministic D3 fixtures show
that the provider payload cannot implement it without ambiguity, D3 must stop
and return the EPS series as unsupported rather than weakening the predicate.

## 6. Availability, amendments, restatements, and duplicates

### 6.1 Public availability

For each accession:

1. use the matching submissions `acceptanceDateTime` when available, honor an
   explicit offset or `Z` designator, and normalize it to UTC; only a legacy
   timestamp lacking an offset is interpreted in SEC Eastern time;
2. otherwise use the end of the SEC `filed` date in `America/New_York`, converted
   to UTC, as a conservative coarse availability boundary; and
3. retain which source was used in provenance.

The fallback does not claim an exact dissemination time. It deliberately makes
the fact unavailable until the entire official filed date has elapsed. A
missing or malformed accession, filed date, or period date is unsupported.

Submissions history can reference older shard files. D1-D3 may retrieve those
shards to obtain exact acceptance times; if they do not, the conservative filed
date fallback remains required. A wall-clock retrieval time is never used as a
historical publication timestamp.

### 6.2 Candidate selection

After common eligibility filtering:

1. group by semantic field, CIK, exact period start/end, concept, units,
   currency, accounting scope, and EPS basis where applicable;
2. discard facts not yet available at `effective_as_of`;
3. select the latest eligible `available_at` for each exact period;
4. when equally ranked facts have identical normalized values, select by the
   lexically stable accession/provider fact identifier and retain the duplicate
   count in lineage; and
5. when equally ranked facts disagree, return `ambiguous_fact`.

Later 10-K and 10-K/A comparative facts are restatements or re-presentations,
not separate fiscal years. The exact period dates, not Company Facts `fy`, are
the grouping key. A later filing cannot affect an analysis whose `as_of`
precedes its availability.

## 7. Unsupported capability and evidence matrix

| Shape | Disposition | Reason |
| :--- | :--- | :--- |
| Exact three concepts, one-ticker CIK, compatible annual USD facts | Supported candidate | Meets the narrow mapping and compatibility rules |
| Missing exact PP&E concept | Unavailable | No broad CapEx substitution or summation |
| `PaymentsToAcquireProductiveAssets` | Unavailable | Broader definition can include software/intangibles |
| Continuing-operations OCF concept | Unavailable | Not definition-identical to the selected all-operating-activities total |
| Provider/company precomputed FCF | Unavailable | Definition and lineage are not proven identical |
| 10-Q, YTD, quarterly, TTM, or instant fact | Unavailable | Not a completed annual duration |
| 20-F/40-F, IFRS, or custom extension | Unavailable | No approved concept/filing mapping |
| Currency mismatch or non-ISO-like unit | Unavailable | No currency conversion or unit guess |
| Multiple tickers for one CIK | Unavailable | Requested share-class identity and EPS applicability are not proven |
| Conflicting equal-rank duplicates | `ambiguous_fact` | No deterministic evidence-based winner |
| EPS span crossing an unproved split/restatement basis | Unavailable | CAGR inputs are not comparable |
| Market capitalization | Unavailable | No D0 provider mapping reviewed |
| FY1/FY2 analyst consensus EPS | Unavailable | Meaning, horizon, provenance, updates, and licensing are unverified |

JPMorgan is a representative complete-strategy negative case: the reviewed
payload lacks the exact CapEx concept and its CIK maps to multiple listed
securities. Negative operating cash flow itself is valid data and is not the
reason for unavailability.

## 8. D1-D5 implementation constraints and tests

After human approval only:

- **D1** may add the exact operating-cash-flow concept and common annual parser.
- **D2** may add only the exact PP&E concept and `positive_expenditure`
  validation; it must test zero, negative rejection, and unsupported alternates.
- **D3** may reconcile exact annual diluted EPS using the common-basis rule and
  must include an Apple-like split re-presentation fixture.
- **D4** may compose only periods satisfying every compatibility predicate.
- **D5** must reconcile implementation behavior back to this record and retain
  all unsupported shapes as typed unavailability.

Minimum deterministic regressions include:

1. MSFT/KO-like successful annual facts;
2. exact-period comparative duplicates across later 10-K filings;
3. a 10-K/A later restatement before and after an `as_of` boundary;
4. conflicting equal-rank duplicates;
5. filed-date fallback and Eastern-to-UTC conversion;
6. Company Facts `fy` differing from the comparative fact's period-end year;
7. 52/53-week annual duration;
8. missing exact CapEx and unsupported productive-assets CapEx;
9. negative OCF retained and negative PP&E acquisition payment rejected;
10. currency and period mismatch;
11. multi-ticker CIK rejection; and
12. Apple-like pre-split/post-split EPS values that cannot be mixed.

## 9. Approval gate

**Human approval:** Approved  
**Approval date:** 2026-08-27  
**Resulting production tests:** Not applicable until D1-D5

The approval explicitly includes the narrow PP&E definition, the one-ticker-CIK
identity boundary, the availability fallback, and the EPS common-basis rule. D1
is authorized next. Any requested change to those financial semantics returns
this record to D0 review before the affected production implementation proceeds.

## 10. Adoption-risk follow-up

The human reviewer identified a material product risk: these conservative
evidence rules may make the ratio of useful to unavailable investor results too
low for sustained use. There is not yet enough representative production
evidence to forecast that ratio accurately, so D0 does not relax the mappings.

D1-D5 must preserve typed reasons for every unavailable result so later live
validation can measure coverage by exclusion reason. Slice E representative
live validation and the later real-user validation checkpoint should sample a
documented set of intended securities and report, at minimum:

- complete usable strategy results;
- unavailable results grouped by identity, missing exact CapEx, EPS common-basis,
  period/currency compatibility, and provider failure;
- the horizon achieved for usable results; and
- whether the observed useful-result ratio warrants broadening provider evidence
  in a separately reviewed mapping rather than weakening semantics silently.

No target ratio is invented at D0. A persistently low useful-result ratio is a
product-policy review trigger, not permission for an adapter fallback.
