# Korean Memory Export Unit Value Tracker

本项目从韩国海关总署 KCS / 韩国贸易统计数据自动拉取月度出口记录，计算韩国半导体存储、固态存储介质和通用存储设备的出口单位价值，并生成核心半导体存储繁荣度指数。

> 本项目计算的是出口单位价值（export unit value），不是 DRAM/NAND 合约价、现货价或厂商 ASP。产品结构、封装重量、容量和出口目的地变化都会影响 USD/kg。

## 核心口径

- 出口单位价值优先使用出口金额 USD / 出口净重 kg。
- 某条记录缺少有效净重、但有明确数量单位时，才回退为出口金额 / 出口数量。计价基准只由该条记录决定，不会随 `--start` 改变。
- 指数使用相邻比较期共同存在的 HSK 编码，并按上期出口额加权。
- 同比、环比直接用两个比较期计算，不依赖请求起始月份。
- 核心价格和繁荣度只使用 `854232` 半导体存储器集成电路。
- `852351` 固态非易失性介质与 `847170` 通用存储设备单独展示，不混入核心繁荣度。

## 数据来源

- KCS / Korea Customs Service: <https://tradedata.go.kr>
- KCS OpenAPI: `https://apis.data.go.kr/1220000/Itemtrade/getItemtradeList`
- TRASS / Korea Trade Statistics Promotion Institute: <https://www.trass.or.kr>

KCS OpenAPI 返回申报出口额 `expDlr` 和净重 `expWgt`。同一月份和HSK编码同时输入 KCS 与 TRASS 时，程序优先选择信息更完整的数据源，并去除完全重复记录。

客户端会对临时网络错误、HTTP 429 和 5xx 响应进行指数退避重试。

## 默认商品分类

三个互不混用的顶层范围：

| 分类 | HSK规则 | 用途 |
|---|---|---|
| `semiconductor_memory` | `854232` | 核心价格与繁荣度 |
| `solid_state_media` | `852351` | 固态非易失性介质观察指标，不等同于纯SSD |
| `storage_devices` | `847170` | 通用存储设备，包含HDD及其他设备，不标记为SSD；聚合单位价值易受产品结构和小额出口影响 |

核心 `854232` 内部细分：

| 分类 | HSK规则 | 说明 |
|---|---|---|
| `dram` | `8542321010` | DRAM IC；不是韩国官方ICT统计的完整DRAM总额 |
| `sram` | `8542321020` | SRAM |
| `flash_memory` | `8542321030` | Flash Memory，作为NAND代理而非纯NAND序列 |
| `multichip_memory` | `8542323000` | Multichip IC，作为HBM相关代理而非纯HBM序列 |
| `mco_memory` | `8542324000` | MCO存储集成电路 |
| `other_memory_ic` | `8542321090,8542322000` | 其他及Hybrid存储IC |

官方ICT统计对账范围另行展示，不进入核心繁荣度：

| 分类 | HSK规则 | 说明 |
|---|---|---|
| `dram_module` | `8473304060` | DRAM模组，位于HS 854232之外 |
| `ict_dram` | `8542321010,8473304060` | 韩国官方ICT统计公布的DRAM范围 |
| `ict_memory_semiconductors` | `854232,8473304060` | 韩国官方ICT内存半导体对账范围 |

[KOSIS官方答复](https://kosis.kr/civilComplaint/qnaDetail.do?boardIdx=21313)明确说明，ICT出口统计的DRAM由 `8542321010` 和 `8473304060` 两个HSK编码合计。项目因此默认拉取 `854232`、`8473304060`、`852351` 和 `847170`，但核心指数仍只使用物理口径更一致的 `854232` 存储IC。`--end latest` 只使用核心 `854232` 判断最新可用月份，避免外围小分类提前出现数据时误判整月已经就绪。

HSK十位编码可能随海关年度税则变化。长期研究中，核心指数使用稳定的六位 `854232` 范围；细分类需要结合当年税则和TRASS说明复核。

## 安装和运行

```bash
python3 -m pip install -r requirements.txt
export DATA_GO_KR_SERVICE_KEY="你的 service key"
```

一条命令完成查询、计算、回测和图表：

```bash
python3 -m korean_memory_price run \
  --start 202301 \
  --end latest \
  --outdir output/memory
```

只拉取原始KCS记录：

```bash
python3 -m korean_memory_price kcs-fetch \
  --start 202301 \
  --end latest \
  --out data/kcs_memory_trade.csv
```

从既有文件重新计算：

```bash
python3 -m korean_memory_price price \
  --input data/kcs_memory_trade.csv \
  --out data/memory_unit_prices.csv \
  --index-out data/memory_price_index.csv \
  --category-index-out data/memory_category_price_index.csv \
  --score-out data/memory_prosperity_score.csv \
  --overall-out data/memory_overall_prosperity.csv \
  --backtest-out data/memory_prosperity_backtest.csv
```

导入TRASS文件：

```bash
python3 -m korean_memory_price trass-import \
  --file downloads/trass_export.xlsx \
  --out data/trass_memory_trade.csv
```

自定义或覆盖分类：

```bash
python3 -m korean_memory_price run \
  --start 202301 \
  --end latest \
  --category flash_memory=8542321030 \
  --outdir output/memory
```

覆盖默认核心分类时会保留它的核心角色；新增分类默认仅作观察，不会自动进入繁荣度扩散分。

## 繁荣度模型 v5.1

核心评分只使用三个有权重的指标：

- 单位价值同比：48.75%
- 单位价值环比：16.25%
- 出口量同比：35%

等价于：

```text
核心繁荣度 = 65% × 出口单位价值周期（75%同比 + 25%环比）
           + 35% × 出口量周期
```

出口金额近似等于价格乘以数量，因此出口金额同比权重为0，只保留为收入方向一致性诊断，避免同一信息重复计分。

每个指标使用平滑半饱和函数：

```text
signal = value / (abs(value) + scale)
```

尺度分别为价格同比40个百分点、价格环比8个百分点、出口量同比30个百分点。与旧模型的硬截断相比，极端变化不会刚越过阈值就全部变成同一个满分。

三个核心指标必须全部有效才生成评分。分档：

- `boom`: >= 75
- `expansion`: >= 60
- `neutral`: >= 45
- `contraction`: >= 30
- `downturn`: < 30

只有核心 `854232` 内部的DRAM IC、SRAM、Flash、Multichip、MCO和其他存储IC参与分类扩散分。DRAM模组、官方对账范围、固态介质和通用存储设备都不会影响核心繁荣度。

```text
overall_memory_prosperity_score
  = 80% × core_memory_score
  + 20% × category_breadth_score
```

## 历史回测

每次 `run` 都会生成 `memory_prosperity_backtest.csv`，把月度评分与未来1、3、6、12个月核心出口单位价值指数变化配对，输出：

- Pearson相关系数；
- 扩张/收缩信号的方向命中率；
- 扩张月份与收缩月份的未来平均变化；
- 两组之间的收益差；
- `supportive_internal`、`mixed_internal` 或 `insufficient_sample` 内部诊断状态。

2015-01至2026-07的固定样本回测和限制见 [docs/historical_backtest.md](docs/historical_backtest.md)。这是全历史回顾性的前瞻关联诊断，不是独立留出样本或交易策略回测；重叠期收益、海关修订和产品结构变化都会影响结果。

## 外部数据核验

仓库内的 `benchmarks/motie_2025.csv` 保存韩国产业通商资源部月报公布的2025年官方出口额及DRAM/NAND固定价格。连接KCS重跑后，可直接复核：

```bash
python3 -m korean_memory_price run \
  --start 201501 \
  --end latest \
  --external-benchmark benchmarks/motie_2025.csv \
  --outdir output/memory
```

也可以对既有分类指数单独验证：

```bash
python3 -m korean_memory_price validate \
  --category-index output/memory/memory_category_price_index.csv \
  --benchmark benchmarks/motie_2025.csv \
  --out output/memory/memory_external_validation.csv
```

出口额比较用于检验商品分类和API汇总；市场固定价比较只用于评估出口单位价值的代理质量，两者不会混为同一种验证。2026-08-15的完整结果和解释见 [docs/external_validation.md](docs/external_validation.md)。

## 输出文件

- `memory_trade.csv`: KCS/TRASS原始标准化记录。
- `memory_unit_prices.csv`: 每月每个HSK编码的USD/kg或USD/数量。
- `memory_price_index.csv`: 仅 `854232` 核心半导体存储指数。
- `memory_category_price_index.csv`: 顶层范围和核心内部细分类指数。
- `memory_prosperity_score.csv`: 核心繁荣度、周期阶段和诊断项。
- `memory_overall_prosperity.csv`: 核心评分与分类扩散合成结果。
- `memory_prosperity_backtest.csv`: 历史前瞻验证结果。
- `memory_external_validation.csv`: 选择外部基准时生成的分类对账和市场价格代理检验。
- `charts/`: 指标、评分、扩散度及各分类图表。

分类总览图只比较核心存储IC与固态介质。`847170` 通用存储设备的USD/kg指数会被设备重量和产品结构剧烈影响，因此保留独立明细和单独图表，但不放入总览或繁荣度。

`memory_category_price_index.csv` 同时提供：

- `category_export_value_share_pct`: 占全部跟踪范围的份额；
- `category_scope_export_value_share_pct`: 核心子分类占 `854232` 的份额；
- `category_role`: `core`、`component`、`official_component`、`official_scope`、`context` 或 `aggregate`；
- `prosperity_eligible`: 是否进入核心分类扩散分。

## 定时查询

示例见 [examples/crontab.txt](examples/crontab.txt)。正式部署时应固定Python解释器和项目路径，并增加进程锁、日志、失败告警及输出原子替换。不要仅凭某个外围HSK编码有记录就认定完整月份已经发布。

## 解释限制

- KCS只有金额和重量时，“出口量”实际是净重kg代理，不是芯片颗数或bit shipment。
- Flash、Multichip和固态介质都是代理范围，不应直接写成纯NAND、纯HBM或纯SSD价格。
- 外部验证表明，出口单位价值与市场固定价的相关性有限；指数适合跟踪韩国出口产品结构和景气周期，不替代行业报价机构数据。
- 本项目为量化研究工具，不构成投资建议。
