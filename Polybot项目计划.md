# Polybot 项目计划

> **版本：** v3（2026-04-27）
> **状态：** Week 4 产品实验闭环已跑通；Polymarket `/iran` 活跃市场扫描已修复；新闻-市场匹配已设立专项计划。


---

## 1. 项目背景

Polybot 是一个面向 Polymarket 的垂直事件合约概率分析与偏离告警系统。MVP 阶段聚焦“美伊冲突”板块，目标是通过持续市场扫描、多源新闻采集、结构化信号加工和 LLM 混合推理，输出市场价与模型价之间的偏离，为用户提供 Bot 告警与 Web 看板支持。

本项目的核心价值不在于替代用户做最终决策，而在于把原本分散、临时、不可复盘的事件研究流程，沉淀为一个可持续运行的监控与研究基础设施。

---

## 2. 项目目标

### 2.1 MVP 目标
- 定时拉取 Polymarket 活跃市场
- 基于板块关键词构建监控池
- 采集新闻 / 声明 / 可选 X 数据
- 完成去重、情绪打分、事件抽取与状态包构建
- 基于规则/LLM 输出概率判断、偏离、置信度与证据引用
- 满足阈值时通过 Telegram Bot 告警
- 提供轻量 Web 看板

### 2.2 MVP 非目标
- 自动下单
- 多用户系统
- 秒级高频监控
- 移动端 App
- 全品类事件市场覆盖

---

## 3. 项目执行摘要

### 3.1 产品定位
Polybot 是一个针对特定事件板块的概率偏离发现与研究自动化系统，而不是通用资讯工具或自动交易系统。

### 3.2 MVP 板块
- 美伊冲突（Iran conflict）

### 3.3 核心用户
- 项目所有者本人
- 每日查看看板、接收 Bot 推送、不读代码但能读分析

### 3.4 核心使用场景
1. 被动告警：系统发现偏离并推送 Bot
2. 主动分析：用户提交市场链接获取即时分析
3. 周度复盘：回顾分析效果并调参数

### 3.5 核心产品原则
- 先结构化，再推理
- 两级漏斗：初筛 + 深度分析
- 目标是发现偏离，而不是输出孤立概率
- 方法论配置化，可复制到其他板块
- LLM 可切换是硬约束

---

## 4. 核心开发原则

> **先让产品往前跑，不为了局部完美牺牲整体进度。**

1. 必须以最终产品实验闭环为导向推进。
2. 继续专注美伊冲突垂直领域做小规模实验跑通，不要直接扩大化。
3. 产品实验未跑通前，不要在规则集优化、匹配精细化等局部细节上钻牛角尖；这类工作应作为框架搭完后的核心模块专项开发，而不是继续滞留在当前阶段。
4. 当前匹配质量问题是已知风险，先记录，后续专项处理。

---

## 5. 开发阶段总览

### Week 1：项目骨架 + 市场扫描 + 快照入库
**目标**：建立工程基础，完成 Polymarket 市场扫描与快照入库。

**输出**：
- 项目骨架
- 配置系统
- SQLite 初始化
- 市场扫描与快照落库

**完成情况（2026-04-24）**：
- 项目骨架建立完成；配置可加载；数据库可初始化；市场扫描可运行；扫描结果可入库；能输出美伊冲突监控池候选。

---

### Week 2：新闻采集 + 去重 + 状态包雏形
**目标**：打通新闻链路，形成初步市场-新闻聚合能力。

**输出**：
- RSS 采集
- 新闻过滤与去重
- news_items 入库

**完成情况（2026-04-24）**：
- 已完成：RSSSource、新闻关键词过滤、URL Hash 去重、标题 SimHash 去重、news_items 入库、`scripts/run_news_collect.py`
- 已实跑：Al Jazeera / BBC Middle East 可稳定拉取；部分官方源暂受网络或源格式限制
- 状态包雏形留待 Week 3 实现

---

### Week 3：新闻-市场匹配主链路 + 状态包雏形

**目标**：建立“Polymarket 原始数据 → 市场模式卡 → 新闻-市场匹配 → 状态包”的主链路。重点从单纯“LLM 初筛”调整为先补齐数据底座和可解释匹配机制，LLM/Embedding 作为后续增强层逐步接入。

**最终目标**：
> 建立“Polymarket 原始数据 → 市场模式卡 → 新闻-市场匹配 → 状态包”的主链路。

**Phase 1：数据底座（已完成）**
- `MarketORM` 已补齐增强字段（condition_id、description、resolution_source、outcomes_json、clob_token_ids_json、raw_event_json、raw_market_json、updated_at）
- `NewsItemORM` 已补充 `created_at`
- `market_profiles` / `news_market_links` 已建表
- `repositories.py` 已补充 profile/link/news 查询函数，修复 `url_hash` 查询方式
- `polymarket_client.py` 已支持 event/market 双层字段解析与安全 JSON 列表解析
- `run_scan.py` 已支持增强字段与 raw JSON 落库
- `market_scanner.py` 已调整为有限多页扫描 + iran_conflict 定向排除
- 实测扫描：pages_scanned=6、events_scanned=3000、excluded_count=2145、keyword_hits=4

**Phase 2：市场模式卡（已完成）**
- `polybot/processing/market_profile_builder.py`：MarketProfile dataclass + MarketProfileBuilder 规则提取引擎（无 LLM）
- 实测：5 profiles generated, 0 errors

**Phase 3：新闻-市场匹配（已完成）**
- `match_rules.py`：MatchTier A/C/B 分档 + MatchEngine 规则匹配 + direction 计算 + 词边界匹配
- `news_market_matcher.py`：NewsMarketMatcher 批量引擎
- `run_news_market_match.py`：执行脚本，支持 --hours 参数
- 运行结果：5 markets × 31 news = 155 matches（全部 C 档），direction +1=5/-1=45/0=105

**Phase 4：状态包（已完成）**
- `state_package_builder.py`：StatePackage/MatchedNewsEntry dataclass + StatePackageBuilder 聚合引擎
- `run_state_package.py`：输出状态包（yes_price / ±strength_24h / neutral_count / matched_news + reasoning）

**Phase 5：质量复评（已完成）**
- 主链路完整、可运行、可复盘，10 项验收标准全部通过，范围未膨胀
- 当前最大遗留问题是匹配精度（C 档 over-matching、B 档未触发、方向判断偏保守、跨领域误匹配），后续应作为专项处理，不应否定 Week 3 第一轮验收

**暂不完成**：
- chromadb、本地 embedding 模型、cheap LLM 精排、复杂 NER、完整知识图谱、Telegram 告警、Web 看板、历史回测、自动交易

---

### Week 4：产品实验闭环

**目标**：不再继续围绕 Week 3 的规则细节打转，基于现有状态包，生成用户能看、能判断、能反馈的产品化输出。

**Phase 1：概率判断草稿模块（已完成）**
- `polybot/analysis/probability_judger.py`：ProbabilityDraft dataclass + ProbabilityJudger 启发式规则引擎
- 输入 StatePackage，输出方向/信心/关键新闻/风险备注

**Phase 2：告警草稿生成模块（已完成）**
- `polybot/analysis/alert_draft_builder.py`：AlertDraft dataclass + AlertDraftBuilder
- 保守策略：high confidence + higher/lower 才 warning；medium + key_news 可 watch；low confidence 不告警

**Phase 3：本地产品实验脚本（已完成）**
- `scripts/run_product_experiment.py`：串联 StatePackage → ProbabilityDraft → AlertDraft → 终端输出 + Markdown + JSON
- 实测：5 markets | 5 alerts | 0 watch | 0 low-conf，终端可读，报告可保存

**Phase 4：实验复盘（已完成）**
- 已生成 `reports/week4_product_experiment.md` + `reports/week4_product_experiment.json`
- 复盘结论：产品化输出链路已跑通，但暴露出匹配精度和过期市场问题
- 明确判断：暂不建议进入真实 Telegram 告警

**Phase 5：Telegram Mock（已完成）**
- `polybot/notify/telegram_mock.py`：TelegramMockSender 模拟发送器 + JSONL 日志
- `scripts/run_telegram_mock.py`：完整链路 → Mock 发送 → 终端预览 + JSONL
- 实测：5/5 mock-sent，日志含完整 HTML 格式 Telegram 文本
- 后续替换真实 sender 只需替换 TelegramMockSender 类

**Phase 6：总体验收（已完成）**
- 10/10 验收项通过
- 产品化输出链路打通
- 人可以阅读输出并理解系统判断
- 输出暴露了真实产品问题（过期市场、over-matching、5/5 高告警）
- 能形成下一阶段优先级
- 未陷入规则集精修

**当前已知问题（匹配质量待专项处理）**：
- C 档 over-matching：5/5 全匹配，全部 C 档
- B 档未触发：歧义词没有机会进入 B 档过滤
- direction 偏保守：105/155 direction=0
- 弱相关新闻污染状态包：31 条新闻跨领域匹配到所有市场
- alias / subject 过宽导致跨领域误匹配
- 过期市场未过滤：2022 年到期市场、0% YES 价格市场进入实验输出
- 5/5 高 confidence WARNING 过于激进，不符合保守策略

**暂不完成**：
- 不优化 C 档 / B 档匹配规则
- 不重构 match_rules.py
- 不引入 chromadb / embedding
- 不做复杂 LLM 精排 / NER
- 不扩展到其他 Polymarket 板块
- 不直接搭复杂 Telegram 生产发送链路

---

### Week 5：Web 看板 + Scheduler
**目标**：完成连续运行和可视化查看。

**输出**：
- 总览页 / 详情页 / 告警历史页
- 定时任务编排

**与新闻-市场匹配专项的关系**：
- Week 5 不必被匹配专项完全阻塞，Web 看板和 Scheduler 可以继续推进。
- 但真实高置信告警依赖匹配质量，新闻-市场匹配专项需要并行推进。
- 看板应优先展示 direct key news / shared context news / reasoning 等字段，为后续专项评估提供样本和反馈入口。

---

### 新闻-市场匹配专项：核心能力专项优化
**目标**：把新闻中的事件信息映射到预测市场的可结算条件上，让同一条新闻在不同市场下具备不同的相关性权重、影响方向、证据类型和解释逻辑。

**专项文件**：`Polybot新闻市场匹配专项计划.md`

**关键原则**：
- 不追求每个 Iran 市场都有独享新闻；共享新闻是合理现象。
- 通用实体命中（如 Iran / Israel / US）只能作为召回，不应单独支撑高分。
- 强相关应来自市场条件词、触发词、结算标准和新闻事件之间的关系。
- 状态包后续应区分 direct key news、shared context news、contradictory news 和 low signal news。

**近期最小闭环**：
1. 固定 5 个典型 Iran 市场作为 gold sample：peace deal、diplomatic meeting、regime fall、Hormuz traffic、declare war / military operations。
2. 取最近 30-50 条相关新闻，导出当前 news-market 匹配结果。
3. 人工标注一批 pair：relevant、direct/context/irrelevant、YES/NO/neutral、strength、human_reason。
4. 重构 Market Profile，拆分 core_entities、condition_terms、background_terms、positive_triggers、negative_triggers。
5. 降低纯实体命中的权重，重跑 Product Experiment，验证 key news 权重和解释是否开始分化。

---


### Week 6：历史回填 + 回测 + 部署交付
**目标**：完成研究验证与可部署版本。

**输出**：
- historical_events 回填
- 回测报表
- systemd 部署方案

---

## 6. 数据库设计（当前版本）

### 6.1 markets
```text
id
slug
question
category
subcategory
condition_id
description
resolution_source
outcomes_json
clob_token_ids_json
raw_event_json
raw_market_json
end_date
updated_at
created_at
```

### 6.2 news_items
```text
id
url_hash
title_simhash
title
url
source_name
published_at
raw_text
board_tags
created_at
```

### 6.3 snapshots
```text
id
market_id
ts
yes_price
volume_24h
liquidity
```

### 6.4 market_profiles
```text
market_id (PK)
subjects_json
actions_json
objects_json
aliases_json
positive_signals_json
negative_signals_json
context_terms_json
ambiguous_terms_json
edge_cases_json
deadline_utc
generated_method
generated_at
raw_profile_json
```

### 6.5 news_market_links
```text
id (AI PK)
news_id
market_id
relevance
direction
strength
reasoning
layer
llm_model
created_at
UNIQUE(news_id, market_id)
```

---

## 7. 核心模块目录

```text
polybot/
  collect/
    polymarket_client.py
    market_scanner.py
  processing/
    market_profile_builder.py
    match_rules.py
    news_market_matcher.py
    state_package_builder.py
  analysis/
    probability_judger.py
    alert_draft_builder.py
  notify/
    telegram_mock.py
  storage/
    db.py
    models.py
    repositories.py

scripts/
  run_scan.py
  run_build_market_profiles.py
  run_news_market_match.py
  run_state_package.py
  run_product_experiment.py
  run_telegram_mock.py

reports/
  week4_product_experiment.md
  week4_product_experiment.json
```

---

## 8. 后续优先事项（按产品闭环需要）

| 优先级 | 事项 | 说明 |
|---|---|---|
| P0 | 活跃市场扫描与过滤（已完成第一轮） | 已通过 `tag_slug=iran` 修复 `/iran` 主题活跃市场扫描，并在扫描和产品实验阶段过滤 closed / archived / inactive / expired / 已解析市场 |
| P1 | 降低告警激进程度（已完成第一轮） | 无当前价格不告警；弱信号、无 key_news、neutral 占比过高时降低 confidence；medium/high 需要至少 2 条 key_news |
| P2 | 新闻-市场匹配专项 Phase 0 | 建立 5 个典型 Iran 市场 + 30-50 条新闻的 gold sample，导出当前匹配结果并人工标注 |
| P3 | Market Profile 重构 | 拆分 core_entities / condition_terms / background_terms / positive_triggers / negative_triggers，降低纯实体命中的权重 |
| P4 | Web 看板 + Scheduler | 可与匹配专项并行推进，优先展示 direct/context/reasoning 以支持评估 |
| P5 | Telegram Mock → 真实发送 | 等匹配质量和告警置信度更稳定后接入真实发送 |


---

## 9. 核心结论

1. **Week 1-2 已完成**：市场扫描 + 新闻采集 + 去重 + 入库。
2. **Week 3 第一轮达标**：数据底座 → 市场模式卡 → 新闻-市场匹配 → 状态包的主链路已打通。
3. **Week 4 第一轮达标**：状态包 → 概率判断 → 告警草稿 → 产品报告 → Telegram Mock 的实验闭环已打通。
4. **Polymarket `/iran` 扫描问题已修复**：已确认 `iran` 是 tag slug，`/tags/slug/iran -> tag_id=78`，并通过 `events?tag_slug=iran&closed=false` 获取真实活跃 Iran 市场。
5. **P0/P1 已完成第一轮最小校正**：过期/非目标/已解析市场过滤与告警保守化已落地。
6. **当前最大瓶颈是新闻-市场匹配质量**：不是链路缺失，而是同一新闻在不同市场下缺乏权重、方向、证据类型和解释差异。
7. **下一步**：以 `Polybot新闻市场匹配专项计划.md` 为基准，先做 Phase 0 样本集建设，再推进 Market Profile 重构和规则匹配重构；Week 5 Web 看板 / Scheduler 可以并行推进。

