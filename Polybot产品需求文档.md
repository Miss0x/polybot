Polybot 产品需求文档（PRD）v1.0

日期：2026-04-24
状态：待确认
MVP 板块：美伊冲突
负责人：用户（产品+业务）+ Claude（技术）

---

产品概述
1.1 背景
Polymarket 弱金融事件（政治、地缘、选举）定价效率不依赖技术面，依赖信息解读深度。散户+部分机构并存，信息处理参差 → 存在概率定价偏差机会。

1.2 产品定位
针对特定垂直板块的 Polymarket 事件合约概率分析工具，通过"结构化信号 + LLM 混合推理"给出独立概率判断，输出偏离方向+幅度。

1.3 核心价值
把散落的多源信息（新闻/声明/X KOL/对照盘）结构化成概率输入
LLM 不做纯文本→概率的黑箱猜测，而是基于历史基准+情绪分+事件流做贝叶斯式权衡
一个板块验证成功 → 配置切换复制到其他板块

1.4 MVP 垂直领域
美伊冲突（2026-04 当前地缘热点，涵盖美伊直接军事行动、核协议、第三方代理冲突、关键人物事件等）

---

用户画像与场景
主用户：项目所有者本人，每日查看看板 + 被动接收 Bot 推送，不读代码但能读分析
场景 A（被动）：偏离触发 → Bot 推送 → 看板看详情 → 决策
场景 B（主动）：贴 Polymarket 链接给 Bot → 返回即时分析
场景 C（复盘）：每周看命中率 → 调权重

---

功能需求（FR）
FR-1 市场扫描
FR-1.1 定时拉取 Polymarket 活跃事件列表（默认 1h）
FR-1.2 按板块关键词白名单过滤（YAML 配置）
FR-1.3 对过滤后市场按 24h 交易量排序
FR-1.4 MVP：取 Top 10 进入监控池
FR-1.5 价格快照（默认 15min）

FR-2 新闻与舆情采集
FR-2.1 多源并发采集（RSS / API / X 数据）
FR-2.2 按板块关键词二次过滤
FR-2.3 去重：URL hash + 标题 SimHash 相似度 > 0.85
FR-2.4 存入统一 news_items 表
FR-2.5 单源失败不影响整体

FR-3 信号加工
FR-3.1 情绪打分（每篇：bearish/bullish/neutral + 强度）
FR-3.2 事件抽取 → 时间线
FR-3.3 历史基准查询（同类市场历史解决率）
FR-3.4 对照盘口价（Kalshi / Smarkets 可选）
FR-3.5 聚合为"市场状态包"（结构化 JSON）

FR-4 混合概率推理（核心）
两级漏斗：
初筛（规则+cheap LLM）：价格 1h≥3pp 或 24h≥5pp 或 高权重新闻≥2 → 触发
深度（primary LLM）：结构化 prompt → 输出 {模型概率, 偏离pp, 置信度, 理由, 证据refs}
LLM 提供商可切换（硬约束，见 §6.5）

FR-5 偏离度判断
绝对 ≥ 8pp 或 相对 ≥ 20% → 标记
同市场同向 6h 内只推一次

FR-6 Telegram Bot
独立 bot（和现有 my_perp_monitor_bot 隔离）
命令：/status /analyze <url> /subscribe /config（只读）
白名单 user_id

FR-7 Web 看板
FastAPI + Jinja2 + HTMX（不用 React，极简）
页面：监控池总览 / 事件详情（价图+分析历史+引用新闻）/ 板块配置 / 告警历史

FR-8 历史基准回填
脚本扫过去 6 个月 Polymarket 已结算市场 → LLM 打标签 → 入 historical_events 表
一次性成本约 $1

FR-9 配置管理
YAML（板块/权重/关键词/阈值/LLM选择）
热重载
多板块 profile

FR-10 下单接口预留（不实现）
TradeExecutor 抽象 + DryRunExecutor 默认（log only）
后期接 Polymarket CLOB 只需加一个实现类

---

非功能需求（NFR）
| 维度 | 要求 |
|---|---|
| 性能 | 扫描 1h / 快照 15min / 深度分析 ≤ 2min / 看板 ≤ 2s |
| 成本 | LLM ≤ $2/天（初期约 $0.35/天 Claude，国产更低）|
| 可扩展 | LLM / 板块 / 信源 三者均配置化 |
| 可靠性 | 单源失败降级；SQLite 每日备份；systemd 守护 |
| 安全 | API key 入 .env；Bot 白名单；看板 Bearer token |

---

系统架构
┌────────────── 配置层 (YAML) ──────────────┐
│ 板块Profile · 权重 · 关键词 · 阈值 · LLM   │
└───────────────────┬───────────────────────┘
                    ↓
┌──────────┬────────────┬─────────────────┐
│数据采集层 │ 信号加工层  │    推理层        │
│          │             │                  │
│Polymarket│ 情绪打分    │ 初筛规则         │
│新闻RSS   │ 事件抽取    │ 深度LLM          │
│新闻API   │ 历史基准    │ Adapter:         │
│X/KOL     │ 对照盘      │  Claude/         │
│          │             │  DeepSeek/Kimi/  │
│          │             │  Qwen/GLM/...    │
└──────────┴────────────┴─────────────────┘
                    ↓
┌───────────── 存储层 (SQLite) ──────────────┐
│ markets · snapshots · news · signals ·    │
│ analyses · alerts · historical_events     │
└───────────────────┬───────────────────────┘
                    ↓
┌──────────┬────────────┬─────────────────┐
│Telegram  │ Web看板    │ TradeExecutor    │
│ Bot      │ (FastAPI)  │ (Dry-run)        │
└──────────┴────────────┴─────────────────┘


数据流：Scheduler → 采集 → 信号加工 → 触发判断 → LLM 推理 → 偏离判断 → Bot 推送 + 看板展示

---

模块详细设计
6.1 M1 market_scanner
API：https://gamma-api.polymarket.com/events（免密钥）
CLOB：https://clob.polymarket.com/markets/{id}
关键字段：id, slug, question, outcome_prices, volume, volume_24hr, end_date, tags

class PolymarketClient:
    async def list_events(self, limit: int = 500) -> list[Event]
    async def get_market(self, market_id: str) -> Market
    async def get_price_history(self, market_id: str, interval: str) -> list[PricePoint]

class MarketScanner:
    def __init__(self, client, board_config):
        self.kw_whitelist = board_config.keywords
    async def scan(self) -> list[Market]:
        """返回过滤后 Top N 按 24h volume 排序"""
6.2 M2 news_collector
class NewsSource(ABC):
    name: str
    weight_default: float
    async def fetch(self, since: datetime) -> list[NewsItem]

class RSSSource(NewsSource): ...
class APISource(NewsSource): ...
class XKOLSource(NewsSource): ...   # 用户自行接入


去重：URL hash 完全相同 → drop；标题 SimHash > 0.85 → 保留最早

6.3 M3 weight_engine — 核心配置 YAML
config/boards/iran_conflict.yaml：
board:
  id: iran_conflict
  name: 美伊冲突
  keywords_market: [Iran, Israel, Khamenei, Netanyahu, IRGC,
                    Hormuz, nuclear deal, IAEA, Tehran]
  keywords_news:   [iran, tehran, IRGC, nuclear, hormuz, ...]

signal_weights:
  official_statement:    0.35   # 白宫/IAEA/伊朗最高领袖办/IDF
  mainstream_news:       0.25   # Reuters/AP/BBC/Axios
  kol_geopolitical:      0.15   # 地缘记者
  reference_odds:        0.15   # Kalshi/Smarkets
  historical_base_rate:  0.10
  polling:               0.0    # 地缘无意义
  on_chain_flow:         0.0

thresholds:
  trigger_price_1h:   0.03
  trigger_price_24h:  0.05
  trigger_news_count: 2
  alert_absolute:     0.08
  alert_relative:     0.20

llm:
  primary:    claude-sonnet-4-6
  cheap_tier: glm-4-flash
  fallback:   deepseek-chat


6.4 M4 signal_processor
情绪打分：cheap LLM → JSON {sentiment: -1~1, impact: 0~1, tag: [...]}，URL 级缓存
事件抽取：近 72h 新闻 → 时间线：2026-04-20 14:00 UTC | Iran announces... | Reuters
历史基准库：表 historical_events(event_type, tags, resolution, duration_days)，按 tag 查同类解决率作为先验

6.5 M5 inference_engine + M11 llm_adapter（硬约束）
LLM 抽象：
```python
class LLMAdapter(ABC):
    async def complete(self, system, user, json_mode=False, model=None) -> dict

class ClaudeAdapter(LLMAdapter): ...
class OpenAICompatAdapter(LLMAdapter):
    """支持 DeepSeek/Kimi/Qwen/GLM/豆包/MiniMax"""
    def init(self, base_url, api_key, model):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)

ADAPTER_REGISTRY = {
    "claude":   ClaudeAdapter,
"deepseek": OpenAICompatAdapter,  # api.deepseek.com/v1
    "kimi":     OpenAICompatAdapter,  # api.moonshot.cn/v1
    "qwen":     OpenAICompatAdapter,  # dashscope.aliyuncs.com/compatible-mode/v1
    "glm":      OpenAICompatAdapter,  # open.bigmodel.cn/api/paas/v4
    "doubao":   OpenAICompatAdapter,  # ark.cn-beijing.volces.com/api/v3
    "minimax":  OpenAICompatAdapter,
}
**切换 LLM = 改一行 YAML**，代码零改动。

**深度分析 prompt 模板**：

你是事件概率分析师。独立评估下列市场定价：
【市场】{question}
【当前 Yes 价】{current_price}
【解决时间】{end_date}
【历史基准】同类 n 样本，解决 Yes 率 {base_rate}
【对照盘】Kalshi {k}，Smarkets {s}
【加权情绪(72h)】{weighted_sentiment}
【事件时间线】{timeline}

返回 JSON：{
  model_probability: float,
  reasoning: str,
  evidence_refs: [1,3,5],
  confidence: float
}
### 6.6 M6 storage — SQLite 表设计
sql
markets          (id, slug, question, category, end_date, created_at)
snapshots        (id, market_id, ts, yes_price, volume_24h, liquidity)
news_items       (id, url_hash, title, url, source_name, published_at, raw_text, board_tags)
signals          (id, news_id, sentiment, impact, event_tags, processed_at)
analyses         (id, market_id, ts, model_name, market_price,
                  model_probability, deviation_pp, confidence,
                  reasoning, evidence_json, status)
alerts           (id, analysis_id, ts, channel, sent_ok, message_id)
historical_events(id, event_type, tags, resolution, duration_days, snapshot)
### 6.7 M7 Bot 推送格式

🔔 偏离告警 | 美伊冲突
━━━━━━━━━━━━━━━━━━
Will Iran close Strait of Hormuz before May 1?
市场价: 32%  模型价: 18%  (偏离 -14pp / -44%)
置信度: 0.72

• 伊朗官方最新声明排除军事封锁
• IAEA 报告：核设施未入战时模式
• 历史基准：类似威胁解决率 ~15%

详情: http://polybot.local/market/xxx
**命令**：`/start` `/status` `/analyze <url>` `/subscribe <board>` `/unsubscribe` `/config`

### 6.8 M8 Web 看板
- FastAPI + Jinja2 + HTMX
- 页面：`/` 总览 / `/market/{slug}` 详情 / `/board/{id}` 配置 / `/alerts` 告警历史
- 访问控制：work 内网 + Bearer token

### 6.9 M9 TradeExecutor（预留）
python
class TradeExecutor(ABC):
async def place_order(self, market_id, side, size, limit_price) -> OrderResult
    async def get_position(self, market_id) -> Position

class DryRunExecutor(TradeExecutor):
    """MVP 默认，只 log 不发单"""
### 6.10 M10 回测
- `scripts/backfill_historical.py`：拉过去 6 月已结算市场，重跑 pipeline，产出准确率 CSV

### 6.12 M12 scheduler
- APScheduler 内嵌进程，无需 cron

---

## 7. 数据结构（关键）
python
@dataclass
class Market:
    id: str
    slug: str
    question: str
    yes_price: float
    volume_24h: float
    end_date: datetime
    tags: list[str]

@dataclass
class NewsItem:
    url_hash: str
    title: str
    url: str
    source_name: str
    published_at: datetime
    source_weight: float
    board_tags: list[str]

@dataclass
class Analysis:
    market_id: str
    model_name: str
    market_price: float
    model_probability: float
    deviation_pp: float
    confidence: float
    reasoning: str
    evidence_refs: list[int]
    ts: datetime
---

## 8. 技术栈

| 层 | 技术 | 理由 |
|---|---|---|
| 语言 | Python 3.11 | 与现有 bot 同栈 |
| Web | FastAPI + Jinja2 + HTMX | 轻量无前端框架 |
| DB | SQLite (WAL) + SQLAlchemy 2.x | MVP 够用，可平滑到 Postgres |
| 异步 | asyncio + httpx | 并发采集 |
| 调度 | APScheduler | 内嵌进程 |
| LLM | anthropic SDK + openai SDK（兼容多家）| **LLM 可切换是硬约束** |
| RSS | feedparser | 标准 |
| 去重 | simhash | 轻量 |
| Bot | python-telegram-bot 21.x | 和现有 bot 同栈 |
| 配置 | PyYAML + python-dotenv | 标准 |
| 日志 | loguru | 比 logging 好用 |
| 部署 | systemd + 独立 venv | 符合隔离原则 |

---

## 9. 部署方案（work 服务器）

### 9.1 目录结构

/root/.openclaw/workspace-youcheng/polybot/
├── .venv/                    # 独立 venv
├── .env                      # 密钥（.gitignore）
├── config/
│   ├── app.yaml
│   └── boards/
│       └── iran_conflict.yaml
├── polybot/
│   ├── collect/              # M1, M2
│   ├── processing/           # M3, M4
│   ├── inference/            # M5, M11
│   ├── storage/              # M6
│   ├── bot/                  # M7
│   ├── web/                  # M8
│   ├── executor/             # M9
│   ├── backtest/             # M10
│   └── scheduler.py          # M12
├── scripts/
│   ├── backfill_historical.py
│   └── setup_db.py
├── data/
│   ├── polybot.db
│   └── backups/
├── logs/
├── tests/
├── requirements.txt
└── README.md
### 9.2 进程管理（systemd）
- `polybot-worker.service` — 调度+采集+推理
- `polybot-bot.service` — Telegram bot
- `polybot-web.service` — uvicorn + FastAPI

### 9.3 密钥（.env）

ANTHROPIC_API_KEY=
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
KIMI_API_KEY=
QWEN_API_KEY=
GLM_API_KEY=
DOUBAO_API_KEY=
MINIMAX_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_WHITELIST=
POLYMARKET_API_KEY=          # 下单阶段才填
WEB_BEARER_TOKEN=
```

---

成本估算（按天）
| 项 | 估算 |
|---|---|
| 情绪打分（cheap LLM）| Haiku/GLM-Flash ≈ $0.08 |
| 深度分析（primary）| Sonnet 30次 × 3k tok ≈ $0.27 |
| 合计 | ~$0.35/天 (Claude)，DeepSeek 约 1/10 |
| 新闻 API | $0（见附录 A）|

---

里程碑（6 周 MVP）
| 周 | 产出 |
|---|---|
| W1 | M1+M2+M6：Polymarket 连续拉价 + 新闻入库 |
| W2 | M3+M4+M10 回填：板块配置生效 + 历史基准库 |
| W3 | M5+M11：多 LLM 适配跑通，输出分析 |
| W4 | M7+M8：Bot 推送 + 看板闭环 |
| W5 | 小样本回测 + 权重微调 |
| W6 | systemd 守护 + 文档 + 下一板块规划 |

---

风险与边界
| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| LLM 幻觉产生错误概率 | 高 | 高 | 结构化 prompt + 证据 refs + 置信度阈值 |
| 新闻源降级/失效 | 中 | 中 | 多源冗余 + 健康检查 |
| Polymarket API 限流 | 低 | 中 | 本地缓存 + 指数退避 |
| 板块冷却期无事件 | 中 | 低 | 快速切板块（配置化）|
| X/Twitter 数据断供 | 中 | 中 | 用户自己维护通道 |

明确不做（MVP）：
自动下单（只留接口）
非地缘板块（后期复制）
秒级时效
多用户系统
移动端 App

---

附录 A：免费新闻源清单
A.1 免费 RSS（无需注册）
| 源 | URL | 权重（美伊）|
|---|---|---|
| BBC World | feeds.bbci.co.uk/news/world/rss.xml | 0.8 |
| Al Jazeera | aljazeera.com/xml/rss/all.xml | 0.9 |
| Axios World | axios.com/rss.xml | 0.8 |
| AP Top News | ap.org/rss | 0.8 |
| Times of Israel | timesofisrael.com/feed | 0.85 |
| Tehran Times | tehrantimes.com/rss | 0.85 |
| 白宫声明 | whitehouse.gov/briefing-room/feed | 1.0 |
| US State Dept | state.gov/rss-feed | 1.0 |
| IAEA | iaea.org/news/feed | 1.0 |
| Defense.gov | defense.gov RSS | 0.95 |
| IDF Spokesperson | idf.il/en/rss | 0.95 |

A.2 注册有免费额度的 API
| 源 | 免费额度 | 推荐度 |
|---|---|---|
| GDELT Project | 完全免费无限 | 全球事件库，2.5min 更新 |
| NewsAPI.org | 100 req/day | 非商用 |
| GNews API | 100 req/day | 多语言 |
| NewsData.io | 200 req/day | 含历史 |
| Currents API | 600 req/day | 主题分类好 |
| The Guardian | 500 req/day | 深度报道 |
| NYT Article API | 500 req/day | 权威 |
| Mediastack | 100 req/月 | 备胎 |

推荐组合：GDELT（主力事件流）+ 8-10 个免费 RSS + 1-2 个注册 API 做补充

A.3 X/Twitter
用户自行接入（已承诺）

---

附录 B：LLM 提供商清单（多 LLM 支持）
| 提供商 | 模型 | API 格式 | Base URL |
|---|---|---|---|
| Anthropic | opus-4-7 / sonnet-4-6 / haiku-4-5 | native | api.anthropic.com |
| DeepSeek | deepseek-chat / deepseek-reasoner | OpenAI 兼容 | api.deepseek.com/v1 |
| Moonshot Kimi | moonshot-v1-8k/32k/128k | OpenAI 兼容 | api.moonshot.cn/v1 |
| 通义千问 | qwen-plus / qwen-max | OpenAI 兼容 | dashscope.aliyuncs.com/compatible-mode/v1 |
| 智谱 GLM | glm-4-plus / glm-4-flash | OpenAI 兼容 | open.bigmodel.cn/api/paas/v4 |
| 字节豆包 | doubao-pro-32k | OpenAI 兼容 | ark.cn-beijing.volces.com/api/v3 |
| MiniMax | abab 系列 | OpenAI 兼容 | api.minimax.chat/v1 |

默认组合：cheap_tier=GLM-Flash 或 DeepSeek；primary=Sonnet 或 DeepSeek-Reasoner；切换=改 YAML 一行

---

待确认问题（5 个）
看板访问方式：work 在日本，你人在哪？公网 + Bearer token 还是 SSH 隧道？
Telegram Bot：@BotFather 新注册还是你注册后给 token？bot 名字？
国产 LLM 优先级：现有 MiniMax key 直接当 cheap_tier？还是先用免费 GLM-Flash，MiniMax 留备用？
历史基准打标签：一次性 ~$1 LLM 成本给过去 6 月已结算市场打标签，同意吗？
看板必要视图：除了总览/详情/配置/告警，还要啥？（如"LLM 对比视图"—同市场不同模型概率对比）
