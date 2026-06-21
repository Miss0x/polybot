Polybot 新闻-市场匹配管线 v1.0
PRD §6.2.5 独立章节 | 日期：2026-04-24

问题定义
市场侧（静态）：Polymarket 事件合约，判定条件 = 主体 + 动作 + 对象 + 阈值 + 截止时间。数量几十-几百。
新闻侧（动态）：每天上百条涌入，可能正面命中、旁敲侧击、或假阳。
目标：为每条新闻找到它真正实质相关的市场，并判定方向（支持 YES / NO / 中性）和强度。

失败模式：
假阳性：关键词命中但无关（"Iran welcomes Hormuz shipping standard"）
假阴性：语义相关但词不同（"Tanker reroutes after IRGC patrol" ↔ 封锁市场）
方向混乱：同新闻对不同市场方向相反

纯关键词崩、纯 Embedding 方向不清、纯 LLM 太贵 → 组合管线。

---

总体架构（四层流水线）
新闻到达
    ↓
┌────────────────────────────────┐
│ L1  关键词/实体字典（粗筛）     │  ← 零成本，规则
│     命中板块关键词 + 实体命中   │
└────────────────────────────────┘
    ↓ 降噪 ≥ 90%
┌────────────────────────────────┐
│ L2  Embedding 向量召回         │  ← 本地模型或 API
│     Top-K 候选市场 (K=10)       │
└────────────────────────────────┘
    ↓ 候选 ≤ 10 市场
┌────────────────────────────────┐
│ L3  cheap LLM 精排             │  ← GLM-Flash/DeepSeek/Haiku
│     输出 relevance/direction/   │
│     strength/reasoning         │
│     依赖：L4 市场模式卡          │
└────────────────────────────────┘
    ↓ relevance ≥ 0.5
┌────────────────────────────────┐
│ 写入 news_market_links 表       │
└────────────────────────────────┘

┌────────────────────────────────┐
│ L4  市场模式卡（前置，一次性）   │  ← 每新市场加入监控池时跑
│     主体/动作/对象/阈值/信号/    │
│     边缘情况                   │
└────────────────────────────────┘


锁定参数（已确认）：
向量模型：本地部署（型号见 §5）
模式卡：前期就做（Top 10 市场）
匹配频率：15min 批量
新市场回溯窗口：72h（YAML 可改 7 天）

---

L1 — 关键词 + 实体字典（粗筛）
作用
把全量新闻过滤到板块相关
零成本，毫秒级
预期降噪 ≥ 90%

数据源：config/entity_aliases.yaml（半人工维护）
```yaml
entities:
  iran:
    aliases:
      
Iran
伊朗
Tehran
IRGC
Islamic Revolutionary Guard
Ayatollah Khamenei
Supreme Leader
Raisi
Pezeshkian
israel:
  aliases:
Israel
以色列
IDF
Netanyahu
Mossad
Knesset
hormuz:
  aliases:
Strait of Hormuz
霍尔木兹
Hormuz strait
Persian Gulf chokepoint
# ...
### 命中规则
- 新闻 title + 首段命中实体 ≥ 1 **且** 命中板块关键词 ≥ 1 → 过
- 全匹配不区分大小写，支持中/英/波斯语字符

### 维护
- 新人物/新组织出现时**半人工**添加别名
- 每周人工扫一遍漏掉的（从未匹配上任何市场但出现次数多的实体）

---

## 4. L2 — Embedding 向量召回

### 作用
- 把 L1 过滤后的候选新闻，映射到 Top-10 候选市场
- 补 L1 的假阴性（语义相关但词不同）

### 流程
python
一次性：市场入库
for market in Top10_markets:
    text = f"{market.question}. Resolution: {market.criteria}"
    emb = embed_model.encode(text)
    vector_store.upsert(market.id, emb, metadata={
        "board_id": market.board_id,
        "end_date": market.end_date
    })

每 15min 批处理新闻
new_news = db.fetch_news_since(last_run)
for news in new_news:
    text = f"{news.title}. {news.summary[:500]}"
    emb = embed_model.encode(text)
    candidates = vector_store.query(
        emb, top_k=10,
        filter={"board_id": news.board_id, "end_date > now"}
    )
    news.candidate_markets = candidates  # 进 L3
```

向量库选型
chromadb（推荐）：SQLite-like，本地文件，内嵌 Python，无需独立进程。占用几十 MB
备选：qdrant（更强但独立进程，work 内存紧）

相似度
Cosine similarity
门槛：top_k=10，相似度 ≥ 0.4 才入 L3（避免完全无关）

---

Embedding 模型选型（work 资源现实）
work 实际资源
2 核 CPU / 仅 2GB 可用 RAM / 无 GPU

选项对比（关键决策）
| 模型 | 参数 | 磁盘 | 运行 RAM | CPU 单条速度 | 多语言 | 建议 |
|---|---|---|---|---|---|---|
| bge-m3（fp32）| 568M | 2.3GB | 2.3GB | ~300ms | 100+ 语 | ❌ 内存不够 |
| bge-m3（int8 量化）| 568M | 800MB | ~900MB | ~150ms | 100+ 语 | 边缘可行，要额外量化步骤 |
| multilingual-e5-small ⭐ | 118M | 470MB | ~550MB | ~80ms | 100+ 语 | ✅ 首选，稳 |
| bge-small-en-v1.5 | 33M | 130MB | ~200MB | ~40ms | 英文为主 | ✅ 若只做英文 |
| paraphrase-multilingual-MiniLM-L12 | 118M | 470MB | ~500MB | ~70ms | 50+ 语 | 备选 |

推荐：multilingual-e5-small
理由：
RAM 占用 ~550MB，work 够用且留出余量给 FastAPI/bot/DB
支持中/英/波斯语（未来扩板块无需换）
质量在 MTEB 检索任务上排前 20%
单条 ~80ms，批量 32 条 ~1s，15min 批处理 200 条新闻 ~15s，远够用
性能预估（work 真机）：
模型加载：冷启动 ~5s，之后常驻
批处理一轮 15min 新闻（~50 条）：5-15s
不会挤占其他服务

备选：API embedding（零本地资源）
如果你觉得本地跑不放心，也可以走 API：
OpenAI text-embedding-3-small：$0.02 / 1M tokens（约 $0.3/月，极便宜）
智谱 embedding-3：¥0.5 / 1M tokens
阿里 text-embedding-v3：¥0.7 / 1M tokens

推荐组合：
主：multilingual-e5-small 本地
fallback：智谱/阿里 API（本地挂了自动降级）
走 adapter 模式，一行配置切换

技术栈
# requirements.txt
sentence-transformers==3.x
chromadb==0.5.x
# 或 API 版
openai>=1.x  # 同时支持多家 OpenAI 兼容 API


---

L3 — cheap LLM 精排
作用
对 L2 召回的 Top-10 候选，逐一判断：真的相关吗？方向？强度？
依赖 L4 模式卡提供判定条件

Prompt 模板（batch 版，一次问 10 个）
你是事件-新闻相关性判定器。

【新闻】
标题：{news.title}
发布：{news.published_at}
来源：{news.source_name}
摘要：{news.summary[:800]}

【候选市场（10 个）】
1. [市场 ID] 问题 | 判定条件 | 正面信号 | 负面信号 | 边缘情况
2. ...

【任务】
对每个市场判定：
- relevance: 0-1（0=无关，1=直接实质相关）
- direction: +1 支持 YES / -1 支持 NO / 0 中性或方向不明
- strength: 0-1（这条新闻对该市场解决的推动力）
- reasoning: 一句话理由（≤30 字）

【返回 JSON】
{
  "judgments": [
    {"market_id": "xxx", "relevance": 0.85, "direction": -1, 
     "strength": 0.7, "reasoning": "伊朗官方排除封锁，反向信号强"},
    ...
  ]
}


模型选择
首选：glm-4-flash（免费额度高）或 deepseek-chat（便宜）
质量备选：claude-haiku-4-5
YAML llm.cheap_tier 控制

阈值
relevance ≥ 0.5 → 写入 news_market_links
relevance < 0.5 → 丢弃但记录日志（调试用）

缓存
同一 (news_id, market_id) 对已判过不重判
Redis？先用 SQLite 表自己当缓存

成本（估算）
每 15min 跑一次，每天 96 轮
每轮平均 20 条新闻入 L3（L1/L2 过滤后）
每条 × 10 候选市场 = 一次 LLM 调用（batch）
Prompt ~2000 tok、Output ~800 tok
DeepSeek-Chat：$0.27/M input + $1.10/M output ≈ $0.05-0.10/天

---

L4 — 市场模式卡（前置，一次性）
作用
为每个监控池中的市场，前置生成结构化判定卡
L3 精排时作为 context 提高准确率
前期就做（锁定）

生成触发
市场首次进入监控池 → 触发生成
市场 question 或 resolution criteria 变更 → 重新生成（少见）

Prompt（用 primary LLM，一次性投入）
```
分析下面 Polymarket 事件合约，生成结构化判定卡。

【市场】
Question: {question}
Resolution Criteria: {criteria}
End Date: {end_date}
Category: {category}

【任务】
抽取以下字段，保守判定：
subjects: 核心主体（人/组织/国家）
actions: 触发解决的动作动词
objects: 动作作用的对象
deadline_utc: 截止时间 ISO 格式
positive_signals: 支持 YES 解决的典型信号（3-5 条）
negative_signals: 支持 NO 解决的典型信号（3-5 条）
edge_cases: 判定边界（如"部分骚扰不算封锁"）

返回 JSON
### 数据表
sql
market_profiles (
  market_id       TEXT PRIMARY KEY,
  subjects_json   TEXT,
  actions_json    TEXT,
  objects_json    TEXT,
  deadline_utc    TIMESTAMP,
  positive_signals_json  TEXT,
  negative_signals_json  TEXT,
  edge_cases_json        TEXT,
  generated_at    TIMESTAMP,
  generated_by_llm TEXT,
  raw_response    TEXT    -- debug 用
);
### 样例（Hormuz 封锁市场）
json
{
  "market_id": "hormuz-closure-may1",
  "subjects": ["Iran", "IRGC", "Iranian Navy"],
  "actions": ["close", "blockade", "mine", "militarily restrict"],
  "objects": ["Strait of Hormuz"],
  "deadline_utc": "2026-05-01T00:00:00Z",
  "positive_signals": [
    "Iranian official declares formal closure",
    "IRGC mines strait or deploys blockade fleet",
    "Mass tanker rerouting via Cape",
    "Multi-day shipping halt confirmed"
  ],
  "negative_signals": [
    "Iran officials publicly deny closure intent",
    "US-Iran de-escalation talks",
    "IRGC scales back naval patrols",
    "Shipping traffic returns to normal"
  ],
  "edge_cases": [
    "Single tanker harassment ≠ closure",
    "IRGC verbal threats without action = weak signal",
    "Brief hours-level disruption ≠ meets criteria"
  ]
}
### 成本
- 每张卡 ~$0.01（Sonnet）
- Top 10 市场 ≈ **$0.1 一次性**
- 每次新市场加入 += $0.01

---

## 8. 数据表设计（新增）

### `market_profiles`（见 §7）

### `news_market_links`（核心关联表）
sql
news_market_links (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  news_id         INTEGER NOT NULL REFERENCES news_items(id),
  market_id       TEXT NOT NULL REFERENCES markets(id),
  relevance       REAL NOT NULL,           -- 0-1
  direction       INTEGER NOT NULL,         -- -1 / 0 / +1
  strength        REAL NOT NULL,           -- 0-1（已乘信源权重）
  reasoning       TEXT,
layer           TEXT,                     -- 'L3_llm' 等，debug
  llm_model       TEXT,
  created_at      TIMESTAMP NOT NULL,
  UNIQUE(news_id, market_id)
);
CREATE INDEX idx_nml_market_ts ON news_market_links(market_id, created_at DESC);
CREATE INDEX idx_nml_news ON news_market_links(news_id);
**最终的 72h 情绪/事件加权汇总**（M4 信号加工）直接 JOIN 这张表。

---

## 9. 增量流程

### 新市场加入监控池（事件驱动）

Market Scanner 发现新市场进入 Top 10
    ↓
生成 market_profile（LLM，~$0.01）
Embed 市场文本 → 入 chromadb
回溯 past 72h（YAML 可改 7d）的新闻
→ 跑 L1 → L2 → L3 → 回填 news_market_links
 ↓
完成，进入日常匹配循环
### 日常 15min 批量匹配

Scheduler 每 15min 触发 matcher.run()
    ↓
拉 news_items where created_at > last_matched_ts
L1 板块关键词 + 实体字典过滤
L2 批量 embed + 向量查询（Top-10 候选市场）
L3 batch prompt 精排
relevance ≥ 0.5 → 插 news_market_links
更新 last_matched_ts
### 市场 end_date 过期
- 从向量库移除（或标记 archived）
- `news_market_links` 保留（回测用）

---

## 10. 成本汇总

| 项 | 频率 | 日成本 |
|---|---|---|
| L1 关键词 | 实时 | $0 |
| L2 向量召回 | 15min | $0（本地）或 <$0.01（API）|
| L3 cheap LLM 精排 | 15min | $0.05-0.15 |
| L4 模式卡生成 | 按需（新市场）| 均摊 <$0.01 |
| **合计** | — | **~$0.1/天** |

**年化 ~$36**，完全可接受。

---

## 11. 坑与注意（重点）

1. **时间相容**：新闻 `published_at` 必须在 `market.created_at` 到 `market.end_date` 之间。**回测尤其关键**——防"未来新闻泄露"
2. **信源权重**：L3 输出的 `strength` 要乘板块配置的信源权重（官方 0.35、主流 0.25 等）再写入
3. **方向冲突**：同一事件对不同市场方向可能相反。模式卡的 `edge_cases` 要把这类边界说清楚
4. **边缘情况**：模式卡必写 `edge_cases`，避免"单次袭击 ≠ 封锁"被误判
5. **多语言**：multilingual-e5-small 支持中/英/波斯语直接跨语言匹配，未来扩板块无需换
6. **词典衰减**：`entity_aliases.yaml` 每周半人工维护，否则新人物漏匹
7. **向量库膨胀**：一个市场一条 vector，Top 10 × 多板块只会有百级规模，chromadb 无压力
8. **缓存一致性**：市场的 `question` 或 `criteria` 变了，要重新生成模式卡 + 重 embed
9. **OOM 防御**：embed 模型加载失败或 OOM 时，自动降级到 API embedding

---

## 12. 实现依赖清单

新增依赖
sentence-transformers==3.x
chromadb==0.5.x
已有的 openai SDK 用于 API embedding fallback 和 cheap LLM
```

---

待你最后拍板 2 件事
向量模型：multilingual-e5-small 本地（~550MB RAM，够稳），同意吗？还是你希望直接上 API embedding 零本地负担？
向量库：chromadb（SQLite-like 内嵌），同意？还是要独立 qdrant？