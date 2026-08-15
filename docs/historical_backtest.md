# Memory prosperity v5 historical backtest

## Test definition

- Data source: KCS monthly item-trade API.
- Core scope: HS/HSK prefix `854232` only.
- Raw history: 2015-01 through 2026-07.
- Scored history: 2016-01 through 2026-07, because YoY inputs require twelve prior months.
- Score observations: 127.
- Target: percentage change in the core chain-linked export unit value index from month `t` to `t+h`.
- Horizons: 1, 3, 6 and 12 months.
- Expansion signal: score >= 60; contraction signal: score < 45.
- Evaluation date: 2026-08-15.

The score at month `t` is paired only with a later index observation, so the target is not used to calculate that month's score. Parameters are fixed before the comparison; this report does not optimize weights against the reported target returns.

## v5 results

| Horizon | Pairs | Correlation | Direction hit rate | Expansion average | Contraction average | Spread | Status |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 month | 126 | 0.318 | 64.6% | +4.87% | -2.00% | +6.87 pp | supportive |
| 3 months | 124 | 0.468 | 76.3% | +15.49% | -5.95% | +21.43 pp | supportive |
| 6 months | 121 | 0.331 | 63.6% | +26.91% | -1.22% | +28.13 pp | supportive |
| 12 months | 115 | 0.045 | 59.7% | +32.12% | +22.29% | +9.83 pp | mixed |

The model provides useful separation at one to six months. The twelve-month correlation is close to zero, so the score should be interpreted as a coincident/short-to-medium-cycle indicator rather than a reliable one-year forecasting signal.

## Comparison with legacy v4

| Horizon | v4 correlation | v5 correlation | v4 hit rate | v5 hit rate | v4 spread | v5 spread |
|---:|---:|---:|---:|---:|---:|---:|
| 1 month | 0.301 | 0.318 | 63.5% | 64.6% | +5.70 pp | +6.87 pp |
| 3 months | 0.439 | 0.468 | 70.6% | 76.3% | +17.43 pp | +21.43 pp |
| 6 months | 0.311 | 0.331 | 61.6% | 63.6% | +22.13 pp | +28.13 pp |
| 12 months | 0.021 | 0.045 | 60.2% | 59.7% | +6.35 pp | +9.83 pp |

Removing the independent export-value weight and replacing hard clipping with smooth normalization modestly improves the one-to-six-month diagnostics. It does not establish causality or make the score a calibrated forecast probability.

## Limitations

- Export unit value is affected by product mix, packaging, capacity and destination, not only market price.
- KCS weight is a proxy for shipment volume; it is not unit or bit shipment.
- HSK ten-digit classifications can change over time, although the core six-digit scope is more stable.
- Future-return windows overlap, so observations are not statistically independent.
- The report uses the latest retrieved historical series and does not model later KCS revisions.
- No external DRAM/NAND contract-price series is bundled, so this validates internal cycle separation rather than agreement with a third-party price benchmark.
