# External validation report

Evaluation date: 2026-08-15.

## Sources and scope

- The [KOSIS statistical-agency response](https://kosis.kr/civilComplaint/qnaDetail.do?boardIdx=21313) states that Korea's published ICT DRAM exports combine HSK `8542321010` and `8473304060`.
- The [MOTIE August 2025 ICT export report](https://www.motie.go.kr/search/search.do?category=c1&kwd=8%EC%9B%94&site=main) publishes monthly memory, DRAM, NAND Flash, MCP and MCO exports, fixed DRAM/NAND prices, and recent SSD exports.
- Current HSK names and annual tariff changes should be checked against the [Korea Customs Service tariff database](https://www.customs.go.kr/english/ad/ct/CustomsTariffList.do).

The external rows used by the reproducible validator are stored in `benchmarks/motie_2025.csv`. Official export figures are rounded to the table precision of USD 0.1 billion, so exact equality is not expected.

## Classification and aggregation reconciliation

| Official series | Project category | Months | Correlation | Direction match | MAPE |
|---|---|---:|---:|---:|---:|
| ICT memory semiconductors | `ict_memory_semiconductors` | 8 | 0.999999 | 100% | 0.034% |
| ICT DRAM | `ict_dram` | 8 | 0.999997 | 100% | 0.067% |
| NAND Flash | `flash_memory` | 8 | 0.999587 | 100% | 0.727% |
| Memory MCP | `multichip_memory` | 8 | 0.999994 | 100% | 0.112% |
| Memory MCO | `mco_memory` | 8 | 0.999583 | 100% | 0.639% |
| SSD | `solid_state_media` | 4 | 0.999816 | 100% | 0.296% |

The previous `dram = 8542321010` label omitted DRAM modules from the official ICT DRAM scope. Adding `8473304060` closes the gap: for January 2025, DRAM IC exports were USD 1.836 billion and DRAM-module exports were USD 1.415 billion, summing to USD 3.251 billion versus the rounded official USD 3.25 billion.

The core prosperity index deliberately remains `854232` memory IC only. `dram_module`, `ict_dram` and `ict_memory_semiconductors` are reconciliation/context categories and have no prosperity-score weight.

The strong SSD reconciliation means `852351` is a good proxy for the reported SSD export value in this sample. Its legal scope is still solid-state non-volatile media, so the project retains the broader label rather than asserting that every record is an SSD.

## Market-price proxy check

| Market benchmark | Project series | Months | Level correlation | Monthly direction match | Project change | Benchmark change | Result |
|---|---|---:|---:|---:|---:|---:|---|
| DDR4 8Gb fixed price | DRAM IC export unit value | 8 | 0.626 | 42.9% | +20.3% | +307.1% | weak proxy |
| NAND 128Gb fixed price | Flash export unit value | 8 | 0.698 | 57.1% | +35.1% | +54.5% | moderate proxy |

This check confirms the project's main limitation: USD/kg is affected by capacity, generation, packaging, destination and product mix. It can describe Korea's realized export mix and cycle, but it is not a substitute for a like-for-like chip contract or spot price.

## Prosperity-model interpretation

The score uses 65% export-unit-value cycle and 35% export-volume cycle. Export value is retained only as a zero-weight diagnostic because it is approximately unit value multiplied by volume. This reduces duplicate weighting, but does not turn the score into a causal or calibrated forecast.

The internal forward-association diagnostic remains supportive at one, three and six months and mixed at twelve months. Status names include the `_internal` suffix because the evaluation is retrospective, uses overlapping future windows, and is not a held-out out-of-sample test.
