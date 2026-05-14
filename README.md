# Korean Memory Export Price Tracker

这个项目用韩国海关总署 KCS / 韩国贸易统计数据来计算存储产品出口单价，并输出内存/存储景气度指数。

核心逻辑：

- 出口单价 = 出口金额 USD / 出口重量 kg
- 如果 TRASS 导出文件包含出口数量，则额外计算 出口金额 USD / 出口数量
- 用每个 HS code 的单价指数做固定基期出口额加权合成指数
- 用出口金额同比、出口数量同比、出口单价同比、出口单价环比合成 0-100 的“存储景气度评分”

## 数据来源

- KCS / Korea Customs Service: `https://tradedata.go.kr`
- KCS OpenAPI via Korea Open Data Portal: `http://apis.data.go.kr/1220000/Itemtrade/getItemtradeList`
- TRASS / Korea Trade Statistics Promotion Institute: `https://www.trass.or.kr`

KCS OpenAPI 的品目别进出口实绩按 HS code 返回 `expDlr` 和 `expWgt`，其中重量为净重 kg，出口金额为申报 USD。TRASS 网页查询更适合作为详细 HS code 校验和补充；本项目支持导入 TRASS 导出的 CSV/XLSX。

如果同一个 HS code、同一个月份同时输入了 KCS 和 TRASS，程序会优先选择信息更完整的数据源，避免重复计数。通常 TRASS 有数量字段时优先用 TRASS；如果 TRASS 缺少数量/重量而 KCS 更完整，则回退到 KCS。

## 默认关注 HS code

- SSD: `8471704010`
- DRAM/HBM family: `854232`

HBM 通常需要进一步确认韩国 HSK 10 位编码。建议先用 `854232` 做总量跟踪，再在 TRASS 中查询精确 10 位码后追加到命令参数。

## 快速开始

安装图表依赖：

```bash
python3 -m pip install -r requirements.txt
```

KCS OpenAPI 需要在韩国公共数据门户申请 service key，然后设置环境变量：

```bash
export DATA_GO_KR_SERVICE_KEY="你的 service key"
```

拉取 KCS 月度 HS 数据：

```bash
python3 -m korean_memory_price kcs-fetch \
  --start 202301 \
  --end 202603 \
  --hs 8471704010 \
  --hs 854232 \
  --out data/kcs_memory_trade.csv
```

计算存储出口单价、价格指数和景气度评分：

```bash
python3 -m korean_memory_price price \
  --input data/kcs_memory_trade.csv \
  --out data/memory_unit_prices.csv \
  --index-out data/memory_price_index.csv \
  --score-out data/memory_prosperity_score.csv
```

生成图表：

```bash
python3 -m korean_memory_price chart \
  --prosperity data/memory_prosperity_score.csv \
  --outdir charts
```

一条命令完成 KCS 拉取、价格计算、景气度评分和图表：

```bash
python3 -m korean_memory_price run \
  --start 202301 \
  --end latest \
  --hs 8471704010 \
  --hs 854232 \
  --outdir output/memory
```

`--end latest` 会在每次运行时先尝试当前日历月，再逐月向前回退，直到 KCS OpenAPI 返回可用出口记录。这样当 KCS 更新到本月或上月时，程序会自动纳入最新月份；如果当前月尚未发布，则自动使用 KCS 实际可查到的最新月份。

## 导入 TRASS 导出文件

从 TRASS 的 `Trade Statistics` 或 `Export/Import by Item` 按 HS code 查询后导出 CSV/XLSX：

```bash
python3 -m korean_memory_price trass-import \
  --file downloads/trass_export.xlsx \
  --out data/trass_memory_trade.csv
```

然后可以和 KCS 数据一起计算：

```bash
python3 -m korean_memory_price price \
  --input data/kcs_memory_trade.csv data/trass_memory_trade.csv \
  --out data/memory_unit_prices.csv \
  --index-out data/memory_price_index.csv \
  --score-out data/memory_prosperity_score.csv
```

## 定时查询

KCS 最终月度统计通常在每月 15 日左右更新上月数据。你可以用 cron/launchd 每周跑一次，也可以在每月 11 日、21 日和 16 日各跑一次。

定时任务示例见 [examples/crontab.txt](examples/crontab.txt)。

## 四个景气指标

程序跟踪下面四个指标：

- `export_value_yoy_pct`: 出口金额同比
- `export_quantity_yoy_pct`: 出口数量同比。TRASS 有数量时用数量；只有 KCS 数据时用出口重量 kg 做自动代理。程序会在同一 HS code 内选择稳定单位，避免跨月混用“数量”和“kg”
- `unit_price_yoy_pct`: 出口单价同比
- `unit_price_mom_1m_pct`: 出口单价环比

`charts/memory_indicators.png` 会显示这四个指标的变化。

## 存储景气度评分模型

`memory_prosperity_score.csv` 采用 0-100 分制。模型把出口金额同比作为收入确认项，把出口数量同比作为需求/出货代理，把出口单价同比作为价格周期主指标，把出口单价环比作为拐点和动量指标：

- 出口金额同比，权重 20%，阈值 +/-50%
- 出口数量同比，权重 25%，阈值 +/-35%
- 出口单价同比，权重 35%，阈值 +/-50%
- 出口单价环比，权重 20%，阈值 +/-12%

每个指标会先按阈值归一到 -1 到 +1，再加权映射为 0-100。这样可以降低“出口金额 = 单价 x 数量”带来的双重计分，同时让内存周期中最关键的单价趋势占更高权重。

分档：

- `boom`: >= 75
- `expansion`: >= 60
- `neutral`: >= 45
- `contraction`: >= 30
- `downturn`: < 30

`charts/memory_prosperity_score.png` 会显示存储景气度评分变化。

## 输出解释

`memory_unit_prices.csv`:

- `unit_usd_per_kg`: 单个 HS code 的出口 USD/kg
- `unit_usd_per_quantity`: 如果 TRASS 文件给了数量，则为 USD/quantity
- `export_value_usd`, `export_weight_kg`: 原始出口金额和重量

`memory_price_index.csv`:

- `unit_price_index`: 每个 HS code 以首个有效月份为 100 后，按首个有效出口额固定加权的出口单价指数
- `export_quantity_index`: 每个 HS code 以首个有效月份为 100 后，按首个有效出口额固定加权的出口数量指数
- `unit_price_mom_1m_pct`, `unit_price_yoy_pct`: 出口单价环比和同比
- `export_quantity_yoy_pct`: 出口数量同比
- `export_value_yoy_pct`: 出口金额同比
- `index_weight_method`: 当前为 `fixed_first_valid_export_value`，用来降低 HS 组合变化对“单价指数”的污染；组合和总收入变化由出口金额同比捕捉

`memory_prosperity_score.csv`:

- `memory_score`, `memory_regime`: 存储景气度评分和分档
- `score_confidence`: 当月四个指标中可用指标占比，早期不足 12 个月时通常较低
- `value_score`, `volume_score`, `price_score`, `momentum_score`: 四个子评分，便于判断景气度来自价格、数量、收入还是短期动量
- `memory_score_3m_avg`: 3 个月平滑景气度，用来过滤单月噪声
- `score_mom_1m`, `score_mom_3m`: 景气度评分的 1 个月和 3 个月变化
- `cycle_phase`: 对当前周期状态的文字分类，例如 `broad_based_boom`、`price_led_boom`、`recovery`、`cooling`、`contraction`

注意：这个指数只是量化研究特征，不构成投资建议。
