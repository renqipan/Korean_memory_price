# Korean Memory Export Price Tracker

这个项目用韩国海关总署 KCS / 韩国贸易统计数据来计算存储产品出口单价，并输出内存/存储景气度指数。

核心逻辑：

- 出口单价 = 出口金额 USD / 出口重量 kg
- 如果 TRASS 导出文件包含出口数量，则额外计算 出口金额 USD / 出口数量
- 用相邻月份共同存在的 HS code、按上期出口额加权，构造链式出口单价指数
- 用出口金额同比、出口数量同比、出口单价同比、出口单价环比合成 0-100 的“存储景气度评分”

## 数据来源

- KCS / Korea Customs Service: `https://tradedata.go.kr`
- KCS OpenAPI via Korea Open Data Portal: `http://apis.data.go.kr/1220000/Itemtrade/getItemtradeList`
- TRASS / Korea Trade Statistics Promotion Institute: `https://www.trass.or.kr`

KCS OpenAPI 的品目别进出口实绩按 HS code 返回 `expDlr` 和 `expWgt`，其中重量为净重 kg，出口金额为申报 USD。TRASS 网页查询更适合作为详细 HS code 校验和补充；本项目支持导入 TRASS 导出的 CSV/XLSX。

如果同一个 HS code、同一个月份同时输入了 KCS 和 TRASS，程序会优先选择信息更完整的数据源，避免重复计数。通常 TRASS 有数量字段时优先用 TRASS；如果 TRASS 缺少数量/重量而 KCS 更完整，则回退到 KCS。

## 默认关注 HS code

- DRAM/HBM: `8542321010` 和 `8542323000`
- NAND/Flash: `8542321030`
- SSD: `8471704010` 和 `8471709000`
- Total memory: 默认拉取 `854232` 大类并合并 SSD 相关编码

HBM、NAND 和 SSD 的精确 HSK 10 位编码可能随韩国海关口径调整。默认分类把 `8542323000` 作为 DRAM/HBM 相关复合结构芯片代理，把 `8542321030` 作为 NAND/Flash 代理，把 `8471709000` 作为当前 KCS 可查到的 SSD/其他存储设备代理；如果你在 TRASS 中确认了更精确编码，可以用 `--category name=hs1,hs2` 追加分类。

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
  --out data/kcs_memory_trade.csv
```

计算存储出口单价、价格指数和景气度评分：

```bash
python3 -m korean_memory_price price \
  --input data/kcs_memory_trade.csv \
  --out data/memory_unit_prices.csv \
  --index-out data/memory_price_index.csv \
  --category-index-out data/memory_category_price_index.csv \
  --score-out data/memory_prosperity_score.csv \
  --overall-out data/memory_overall_prosperity.csv
```

生成图表：

```bash
python3 -m korean_memory_price chart \
  --prosperity data/memory_prosperity_score.csv \
  --category-index data/memory_category_price_index.csv \
  --overall-prosperity data/memory_overall_prosperity.csv \
  --outdir charts
```

一条命令完成 KCS 拉取、价格计算、景气度评分和图表：

```bash
python3 -m korean_memory_price run \
  --start 202301 \
  --end latest \
  --outdir output/memory
```

`--end latest` 会在每次运行时先尝试当前日历月，再逐月向前回退，直到 KCS OpenAPI 返回可用出口记录。这样当 KCS 更新到本月或上月时，程序会自动纳入最新月份；如果当前月尚未发布，则自动使用 KCS 实际可查到的最新月份。

程序运行结束时会在终端打印最新两个月 DRAM/HBM 和 NAND/Flash 的单价指数同比、环比变化，方便快速检查核心内存价格动量。

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
  --category-index-out data/memory_category_price_index.csv \
  --score-out data/memory_prosperity_score.csv \
  --overall-out data/memory_overall_prosperity.csv
```

自定义分类示例：

```bash
python3 -m korean_memory_price run \
  --start 202301 \
  --end latest \
  --category dram_hbm_plus=8542321010,8542323000 \
  --outdir output/memory
```

如果 `--category` 使用已有分类名，例如 `ssd=8471704010`，会覆盖默认 SSD 分类；如果使用新名称，则会追加一个新的分类。

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

- 出口金额同比，权重 15%，阈值 +/-50%
- 出口数量同比，权重 25%，阈值 +/-35%
- 出口单价同比，权重 40%，阈值 +/-50%
- 出口单价环比，权重 20%，阈值 +/-12%

每个指标会先按阈值归一到 -1 到 +1，再加权映射为 0-100。这样可以降低“出口金额 = 单价 x 数量”带来的双重计分，同时让内存周期中最关键的单价趋势占更高权重。至少需要四项指标中的三项有效才会生成景气分，否则标记为 `insufficient_data`。

分档：

- `boom`: >= 75
- `expansion`: >= 60
- `neutral`: >= 45
- `contraction`: >= 30
- `downturn`: < 30

`charts/memory_prosperity_score.png` 会显示存储景气度评分变化。

## 内存总体繁荣指数

`memory_overall_prosperity.csv` 定义一个 0-100 的总体繁荣指标：

`overall_memory_prosperity_score = 70% * Total memory 景气分 + 30% * 分类扩散分`

其中 Total memory 景气分来自出口金额同比、出口数量同比、出口单价同比和出口单价环比；分类扩散分要求各分类的价格同比和环比同时可用，再按各分类出口额占比加权。总体分必须有 Total memory 景气分才会生成；分类数据缺失时则回退为 Total memory 景气分。这个设计让指数主要反映总量周期，同时检查景气是否从主导品类扩散到更多内存细分市场。

`charts/memory_overall_prosperity.png` 会显示总体繁荣指数、3 个月均值和分类扩散分。

## 分类价格趋势

程序会额外输出 `memory_category_price_index.csv`，默认包含：

- `dram_hbm`: DRAM/HBM 相关价格指数
- `nand`: NAND/Flash 价格指数
- `ssd`: SSD 价格指数
- `total_memory`: Total memory 综合价格指数

对应图表：

- `charts/memory_category_price_trends.png`: 四个分类的价格指数趋势对比
- `charts/memory_overall_prosperity.png`: 内存总体繁荣指数
- `charts/memory_price_trend_dram_hbm.png`
- `charts/memory_price_trend_nand.png`
- `charts/memory_price_trend_ssd.png`
- `charts/memory_price_trend_total_memory.png`

## 输出解释

`memory_unit_prices.csv`:

- `unit_usd_per_kg`: 单个 HS code 的出口 USD/kg
- `unit_usd_per_quantity`: 如果 TRASS 文件给了数量，则为 USD/quantity
- `export_value_usd`, `export_weight_kg`: 原始出口金额和重量

`memory_price_index.csv`:

- `unit_price_index`: 首个有效月份为 100、按上期出口额加权逐月链接的出口单价指数；同比和环比直接按两个比较期的共同 HS code 计算，因此改变 `--start` 只会改变指数基准水平，不会改变重叠月份的同比和环比
- `export_quantity_index`: 首个有效月份为 100、按上期出口额加权逐月链接的出口数量指数
- `unit_price_mom_1m_pct`, `unit_price_yoy_pct`: 出口单价环比和同比
- `export_quantity_yoy_pct`: 出口数量同比
- `export_value_yoy_pct`: 出口金额同比
- `index_weight_method`: 当前为 `chain_linked_prior_period_export_value`；每个月只比较相邻两期共同存在的 HS code，并以上期出口额加权，避免请求起始月份改变最新价格涨幅

`memory_category_price_index.csv`:

- `category`, `category_label`: 分类代码和显示名称
- `unit_price_index`: 分类内 HS code 按上期出口额加权后的链式价格指数
- `unit_price_mom_1m_pct`, `unit_price_yoy_pct`: 分类价格环比和同比
- `category_export_value_share_pct`: 该分类出口额占当月全部纳入内存样本出口额的比例，用来识别小样本噪声
- `category_hs_patterns`: 该分类匹配的 HS/HSK 编码规则
- `category_note`: 分类口径提示；SSD 当前是存储设备代理口径，单月跳动需谨慎解释
- `hs_codes`: 当月实际纳入计算的 HS/HSK 编码

`memory_overall_prosperity.csv`:

- `overall_memory_prosperity_score`: 0-100 的内存总体繁荣指数
- `overall_memory_prosperity_3m_avg`: 总体繁荣指数 3 个月均值
- `category_breadth_score`: 细分品类扩散分
- `category_positive_share_pct`: 价格同比和环比同时为正的分类出口额占比
- `dominant_category`, `dominant_category_share_pct`: 当月主导分类及其出口额占比

`memory_prosperity_score.csv`:

- `memory_score`, `memory_regime`: 存储景气度评分和分档
- `score_confidence`: 当月四个指标中可用指标占比，早期不足 12 个月时通常较低
- `value_score`, `volume_score`, `price_score`, `momentum_score`: 四个子评分，便于判断景气度来自价格、数量、收入还是短期动量
- `price_volume_confirmation`: 价格同比和数量同比是否相互确认，例如 `price_and_volume_up` 或 `price_up_volume_weak`
- `memory_score_3m_avg`: 3 个月平滑景气度，用来过滤单月噪声
- `score_mom_1m`, `score_mom_3m`: 景气度评分的 1 个月和 3 个月变化
- `cycle_phase`: 对当前周期状态的文字分类，例如 `broad_based_boom`、`price_led_boom`、`recovery`、`cooling`、`contraction`

注意：这个指数只是量化研究特征，不构成投资建议。
