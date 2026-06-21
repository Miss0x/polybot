# Polybot 新闻-市场匹配专项计划

> **版本：** v0.1  
> **创建时间：** 2026-04-27  
> **状态：** 讨论稿 / 专项研究与开发基准  
> **适用范围：** Polybot MVP 阶段，美伊冲突 / Iran 垂直板块优先

---

## 1. 为什么要设立这个专项

新闻-市场匹配是 Polybot 最核心的能力之一。

Polybot 的产品价值不是简单"收集新闻"，也不是简单"扫描 Polymarket 市场"，而是把两者连接起来：

```text
某条新闻发生了什么
→ 它影响哪个预测市场
→ 它影响的是 YES 还是 NO
→ 影响强度多大
→ 市场价格是否已经反映
→ 是否值得提醒用户
```

如果新闻-市场匹配不准，后面的状态包、概率判断、告警、Web 看板都会被污染。

因此，本专项的目标是把"新闻和预测市场如何匹配"作为核心问题，持续研究、设计、实验、迭代，直到形成一套可解释、可复盘、可扩展的方法论。

---

## 2. 当前背景与已知问题

### 2.1 当前链路已经跑通

目前系统已经具备：

```text
扫描 Polymarket 活跃市场
→ 采集新闻
→ 新闻去重
→ 构建市场模式卡 Market Profile
→ 新闻-市场规则匹配
→ 状态包 State Package
→ 概率判断 ProbabilityDraft
→ 告警草稿 AlertDraft
```

也就是说，产品实验闭环已经存在。

### 2.2 但匹配质量还不够

当前新闻-市场匹配存在明显问题：

1. C 档 alias 命中过宽；
2. 只要新闻提到 `Iran` / `Israel` 等通用实体，就容易匹配多个市场；
3. 多个市场容易得到相似的 key news；
4. 匹配解释经常停留在：

```text
alias hit: ['iran']
```

这类解释太粗，不能说明为什么这条新闻真的影响这个市场。

### 2.3 关键纠偏：不要追求新闻独占

本专项必须明确一点：

> **不同 Iran 市场共享同一组 key news 并不天然错误。**

很多预测市场其实是同一地缘事件的不同角度：

- 停火是否延长；
- 是否达成永久和平协议；
- 是否进行外交会面；
- 是否正式宣战；
- 伊朗政权是否倒台；
- 霍尔木兹海峡交通是否恢复；
- 美国是否结束军事行动。

这些市场当然可能被同一批新闻共同影响。

所以，优化目标不是：

```text
让每个市场只能拥有独享新闻
```

而是：

```text
允许新闻共享，但每条新闻在不同市场下应有不同的相关性权重、影响方向、解释角度和置信差异。
```

---

## 3. 本专项的核心目标

### 3.1 总目标

建立一套适合事件预测市场的新闻-市场匹配系统，使系统能够判断：

1. 一条新闻是否与某个市场相关；
2. 是背景相关、直接相关，还是强触发相关；
3. 它支持 YES、支持 NO，还是只是中性背景；
4. 它对不同市场的权重为什么不同；
5. 哪些新闻应该进入 key news；
6. 哪些新闻只应该作为 context news；
7. 匹配结果是否足够可靠，可以支撑告警。

### 3.2 产品层目标

最终产品输出不应只是：

```text
这条新闻匹配了这个市场
```

而应能表达：

```text
这条新闻为什么影响这个市场？
它影响的是市场条件里的哪一部分？
它是直接证据还是背景信息？
它支持 YES 还是 NO？
它的强度为什么是这个级别？
```

### 3.3 技术层目标

形成一个多层匹配架构：

```text
实体召回
→ 市场条件理解
→ 新闻事件理解
→ 角度相关性打分
→ 方向判断
→ 强度判断
→ 证据分层
→ 可解释输出
```

---

## 4. 核心概念定义

### 4.1 Market：预测市场

一个 Polymarket 市场不是普通新闻主题，而是一个可结算的问题。

例如：

```text
US x Iran permanent peace deal by April 30, 2026?
```

它至少包含：

- 主体：US / Iran
- 行为：permanent peace deal
- 条件：by April 30, 2026
- 方向：是否发生
- 结算标准：什么算 Yes，什么算 No

### 4.2 News：新闻

新闻不是简单文本，而是一个事件或信息增量。

它至少包含：

- 谁；
- 做了什么；
- 对谁；
- 在什么时间；
- 是否新信息；
- 是否改变市场预期。

### 4.3 Match：匹配

匹配不是简单关键词相同。

真正的匹配应表示：

```text
这条新闻包含的信息，能否解释这个市场的 YES/NO 概率变化。
```

### 4.4 Key News：关键新闻

Key News 不是"独属于某个市场的新闻"。

Key News 应定义为：

```text
对该市场的概率判断有直接解释力的新闻。
```

同一条新闻可以同时是多个市场的 key news，但在不同市场下：

- 权重可以不同；
- 方向可以不同；
- 解释可以不同；
- 置信度可以不同。

### 4.5 Context News：背景新闻

Context News 是与主题相关，但不能直接解释某个市场条件的新闻。

例如一条新闻只是泛泛提到 Iran / Israel，它可能说明板块相关，但不一定能说明：

- 停火是否会延长；
- 是否会有和平协议；
- 是否会发生外交会面；
- 是否会正式宣战。

这类新闻应该降权，并作为背景，而不是强 key news。

---

## 5. 匹配质量的判断标准

### 5.1 好匹配应该是什么样

一个好的匹配结果应满足：

1. 能指出新闻与市场的共同实体；
2. 能指出新闻命中了市场的哪个条件；
3. 能区分背景相关和直接相关；
4. 能判断方向：YES / NO / neutral；
5. 能给出合理强度；
6. 能输出可读解释；
7. 用户看到后觉得"这条新闻确实该放在这个市场下面"。

### 5.2 坏匹配是什么样

坏匹配包括：

1. 只因为出现 `Iran` 就高分匹配；
2. 只因为出现 `Israel` 就跨所有市场匹配；
3. 新闻和市场都在中东，但实际条件无关；
4. 新闻是历史背景，却被当成最新触发；
5. 新闻支持 NO，却被误判为支持 YES；
6. 多个市场解释完全一样，没有市场角度差异；
7. 输出理由只有 `alias hit`，没有条件解释。

---

## 6. 核心设计原则

### 6.1 允许共享，不追求独占

共享新闻是合理现象。

本专项不追求：

```text
每个市场都有完全独立的一组新闻
```

而追求：

```text
同一新闻在不同市场下被不同解释、不同加权。
```

### 6.2 通用实体不能给高分

例如：

- Iran
- Israel
- US
- Trump
- Tehran

这类词只能证明主题相关，不能直接证明市场条件相关。

它们适合做召回，不适合单独支撑高分。

### 6.3 市场条件词决定强相关

强相关必须来自市场条件词或其语义等价表达。

例如：

| 市场类型 | 条件词 / 语义 |
|---|---|
| 停火延长 | ceasefire extension, truce extended, halt extended |
| 永久和平协议 | permanent peace deal, treaty, formal agreement |
| 外交会面 | talks, meeting, envoys, summit, negotiation |
| 宣战 | declare war, formal war declaration |
| 政权倒台 | regime collapse, coup, revolution, Supreme Leader removed |
| 霍尔木兹交通 | Strait of Hormuz, shipping traffic, tanker, maritime route |
| 核协议 | nuclear deal, enrichment, IAEA, uranium, inspection |

### 6.4 解释优先于分数

分数只是结果，解释才是产品可信度来源。

系统应该优先能说明：

```text
为什么匹配？
匹配了哪个条件？
为什么是这个方向？
为什么强/中/弱？
```

### 6.5 先小范围跑通，再逐步增强

本专项虽然重要，但仍遵守项目总原则：

> **先让产品往前跑，不为了局部完美牺牲整体进度。**

专项优化应在美伊冲突板块内小范围验证，不直接扩展到全 Polymarket。

---

## 7. 建议的匹配分层架构

### 7.1 Layer 0：基础召回层

目的：不要漏掉可能相关的新闻。

召回依据：

- shared entities：Iran / US / Israel / Tehran 等；
- board keywords；
- market tags；
- market title；
- market description；
- Polymarket raw_market / raw_event 字段。

输出：候选 news-market pair。

注意：这一层宁可宽一点，但不能直接给高置信。

---

### 7.2 Layer 1：规则角度匹配层

目的：用市场条件词判断这条新闻是否真的解释某个市场。

需要把 Market Profile 拆成：

```text
core_entities       通用实体
condition_terms     市场条件词
resolution_terms    结算条件词
time_terms          截止时间 / 时间窗口
positive_triggers   支持 YES 的触发词
negative_triggers   支持 NO 的触发词
background_terms    背景词
```

例如：

```text
市场：US x Iran diplomatic meeting by April 30, 2026?

core_entities:
  - US
  - Iran

condition_terms:
  - diplomatic meeting
  - talks
  - envoys
  - negotiation
  - summit

positive_triggers:
  - agreed to meet
  - talks scheduled
  - envoys arrive

negative_triggers:
  - talks cancelled
  - meeting postponed
  - negotiations collapse
```

---

### 7.3 Layer 2：语义增强层

目的：解决关键词覆盖不到的同义表达。

可能方案：

1. LLM cheap tier 做轻量判断；
2. embedding 召回相似表达；
3. 手工同义词表；
4. 事件类型分类器。

示例：

```text
"backchannel discussions resumed"
```

可能语义上接近：

```text
US-Iran diplomatic talks
```

即使没有直接出现 `meeting`，也应被识别为外交会面相关。

---

### 7.4 Layer 3：方向与强度判断层

目的：判断新闻对 YES 概率是正向、负向还是中性。

输出字段建议：

```text
relevance: 0.0 - 1.0
direction: +1 / 0 / -1
strength: 0.0 - 2.0
evidence_type: direct / context / contradiction / stale
reasoning: 可读解释
```

---

### 7.5 Layer 4：证据分层输出层

不要把所有新闻都叫 key news。

建议输出分为：

```text
direct_key_news:
  直接解释市场条件的新闻

shared_context_news:
  对 Iran 板块有背景意义，但不是该市场直接证据

negative_or_contradictory_news:
  对 YES 方向构成反向影响的新闻

ignored_or_low_signal_news:
  相关性太弱，不进入状态包核心输出
```

---

## 8. 可能的技术路线

### 路线 A：规则增强优先

优点：

- 快；
- 可解释；
- 适合 MVP；
- 不依赖额外模型服务。

做法：

1. 重构 MarketProfile；
2. 拆分 core_entities / condition_terms；
3. 对 C 档 alias hit 降权；
4. 新增 direct/context 分类；
5. 输出更细 reasoning。

适合近期优先做。

---

### 路线 B：LLM 判别器

优点：

- 能理解复杂语义；
- 能处理同义表达；
- 能输出自然语言解释。

做法：

对候选 pair 提问：

```text
Given this prediction market and this news article,
1. Is the news relevant to the market resolution?
2. Does it support YES, NO, or neither?
3. Is it direct evidence or background context?
4. Explain briefly.
```

缺点：

- 成本更高；
- 速度较慢；
- 需要缓存；
- 需要防止幻觉。

适合进入 L2 精排，不适合第一层全量使用。

---

### 路线 C：Embedding / 向量检索

优点：

- 适合语义召回；
- 可以发现非关键词表达。

缺点：

- 解释性不足；
- 需要本地模型或外部 API；
- 仍需要规则/LLM 判断方向。

适合作为召回增强，不应单独决定告警。

---

### 路线 D：事件知识图谱 / 事件框架

优点：

- 长期最强；
- 可复用到多个地缘板块；
- 能表达实体、关系、事件状态。

缺点：

- 实现成本高；
- 当前阶段不宜过早复杂化。

适合作为长期研究方向。

---

## 9. 映射系统开发计划（v2 — 事件本体 + 映射矩阵架构）

> 本计划基于 2026-04-27 讨论确认的"板块事件本体 + 市场条件归一 + 映射矩阵"架构。
> 核心思路：新闻不打标签，而是抽取事件类型；市场不打标签，而是归一成可结算条件；匹配通过查映射表完成。

### Phase 0：事件本体 + 映射矩阵（数据层）

目标：为美伊冲突板块建立受控的事件类型库、市场条件库和映射矩阵。

新建文件：

```text
config/ontology/iran_conflict_events.yaml       — 事件类型本体（~15-20 个 event_type）
config/ontology/iran_conflict_market_conditions.yaml — 市场条件归一表
config/ontology/iran_conflict_mapping.yaml       — 事件×市场条件 映射矩阵
polybot/ontology/__init__.py
polybot/ontology/event_ontology.py               — EventType dataclass + 加载器
polybot/ontology/market_condition.py             — MarketCondition dataclass + 加载器
polybot/ontology/impact_mapping.py               — ImpactMapping dataclass + 加载器 + 查表 API
```

事件本体结构（每个 event_type）：

```yaml
- id: diplomatic_contact
  label: 外交接触/会面
  description: 美伊双方或通过中间人进行外交接触、会谈、峰会
  keywords: [talks, meeting, summit, envoys, negotiation, backchannel, diplomatic]
  actors: [US, Iran]
  examples:
    - "US and Iran envoys meet in Oman"
    - "Backchannel discussions resumed between Washington and Tehran"
```

市场条件结构（每个 market_condition_type）：

```yaml
- id: permanent_peace_deal
  label: 永久和平协议
  resolution_question: "US x Iran permanent peace deal by {deadline}?"
  resolution_keywords: [permanent peace deal, treaty, formal agreement, comprehensive deal]
  actors: [US, Iran]
```

映射矩阵结构：

```yaml
- event_type: diplomatic_contact
  market_condition: permanent_peace_deal
  direction: +1          # 外交接触对和平协议是正向信号
  strength: weak         # 但只是前置条件，不是直接证据
  evidence_type: context # 背景信号，不是直接证据
  note: "外交接触是和平协议的必要不充分条件"

- event_type: peace_deal_signed
  market_condition: permanent_peace_deal
  direction: +1
  strength: strong
  evidence_type: direct
  note: "直接结算事件"
```

验收：

- 3 个 YAML 文件结构完整，覆盖美伊冲突板块 6 类核心市场
- Python 加载器能正确解析 YAML → dataclass
- `ImpactMapping.lookup(event_type, market_condition)` 返回 direction/strength/evidence_type

---

### Phase 1：新闻事件抽取器

目标：将新闻从"原始文本"转化为"事件类型 + 结构化属性"。

新建文件：

```text
polybot/processing/news_event_extractor.py — 新闻事件抽取器
```

新增数据库表：

```text
news_events: id / news_id / event_type / actors / certainty / time_ref / evidence_sentence / extraction_method / created_at
```

第一版用规则抽取（关键词匹配事件本体的 keywords），后续可升级为 LLM 分类。

抽取输出：

```python
@dataclass
class NewsEvent:
    news_id: int
    event_type: str          # 从本体中选择
    actors: list[str]        # 涉及的行为体
    certainty: str           # confirmed / reported / rumored / denied
    time_ref: str | None     # 事件时间引用
    evidence_sentence: str   # 支撑句
```

验收：

- 对已有新闻能抽取出 event_type（从本体的 ~15-20 个中选）
- 抽取结果落库到 news_events 表
- 无法归类的新闻标记为 `unclassified`

---

### Phase 2：匹配引擎重构

目标：用"新闻事件类型 → 查映射表 → 得到 direction/strength/evidence_type"替代当前的关键词匹配。

新建文件：

```text
polybot/processing/ontology_match_engine.py — 基于映射表的匹配引擎
```

重构 `news_market_matcher.py` 匹配流程：

```text
旧流程：news_text → MatchEngine(profile) → keyword match → relevance/direction
新流程：news → event_type(s) → 查映射表(event_type × market_condition) → direction/strength/evidence_type
```

保留旧 `match_rules.py` 作为 fallback（当新闻无法归类为任何 event_type 时）。

`news_market_links` 表新增字段：

```text
evidence_type: direct / context / irrelevant
event_type: 命中的事件类型
```

验收：

- 同一条新闻对不同市场产生不同的 direction/strength/evidence_type
- "Iran" 泛匹配问题显著减少
- 匹配 reasoning 能说明"命中了什么事件类型，映射到什么市场条件"

保留回顾位：

- 当前 `news_market_links` 仍然是 `(news_id, market_id)` 唯一键，所以如果同一新闻有多个事件类型同时影响同一市场，目前只保留最后一次 upsert 的 `event_type/evidence_type`。
- 这对 Phase 2 跑通是够的，但如果后续要保留"同一新闻对同一市场的多条事件证据"，需要新增明细表或调整唯一键。

---

### Phase 3：状态包 + 概率判断器升级


目标：利用 evidence_type 分层，提升状态包和概率判断的质量。

升级 `state_package_builder.py`：

- 新增 `direct_news_count` / `context_news_count` 统计
- `positive_strength_24h` / `negative_strength_24h` 只从 direct evidence 计算
- context news 单独统计，不参与核心强度

升级 `probability_judger.py`：

- `key_news` 只从 direct evidence 中选取
- context news 只影响 `risk_notes`
- 无 direct evidence 时，confidence 封顶 low

验收：

- 状态包输出区分 direct / context 两层
- 概率判断不再被大量 context news 误导
- 告警质量显著提升

---

### Phase 4：评估基准 + 回归测试

目标：建立可重复的匹配质量评估体系。

新建文件：

```text
tests/gold_samples/iran_conflict_gold.yaml — 人工标注的 gold cases
scripts/run_match_evaluation.py            — 评估脚本
```

评估指标：

```text
precision@top_k          — 前 K 条匹配中正确的比例
recall on gold cases     — gold cases 中被召回的比例
direct/context 分类准确率 — evidence_type 判断是否正确
direction 准确率          — YES/NO/neutral 方向是否正确
false alert count        — 误告警数量
missed key news count    — 漏掉的关键新闻数量
```

验收：

- 每次改匹配规则后，可以跑固定评估集
- 能量化看到匹配质量的变化趋势

---

### Phase 5：匹配质量闭环优化 + 回归门禁

目标：把 Phase 4 的固定评估集接入日常开发流程，用 baseline 指标驱动事件抽取、本体关键词、映射矩阵和 direct/context 分层的持续修正。

本阶段不追求一次性完美，而是建立一个可重复的质量闭环：

```text
gold sample
→ run_match_evaluation.py
→ baseline report
→ 定位 false positive / false negative / evidence_type 错误 / direction 错误
→ 小步修改 ontology / mapping / extraction rule
→ 重新评估
→ 指标不退化才允许进入真实告警
```

新增 / 固化文件：

```text
tests/gold_samples/iran_conflict_gold.yaml       — Phase 5 baseline gold sample
scripts/run_match_evaluation.py                  — 离线匹配评估脚本
reports/phase5_match_evaluation_baseline.md      — baseline Markdown 报告
reports/phase5_match_evaluation_baseline.json    — baseline JSON 指标
```

第一版门禁建议：

```text
matched_accuracy >= 90%
event_type_accuracy >= 85%
evidence_type_accuracy >= 85%
direction_accuracy >= 90%
false_positive_count == 0   # 尤其不能把 Gaza/Lebanon-only 新闻误判为 US-Iran direct evidence
```

Phase 5 保留回顾位：

- 如果评估发现大量错误来自同一条新闻的多事件证据被覆盖，需要回到 Phase 2 的保留问题，考虑新增 `news_market_evidence` 明细表，或把唯一键从 `(news_id, market_id)` 调整为 `(news_id, market_id, event_type)`。
- 如果误报主要来自 Gaza / Lebanon / Israel-only 新闻，需要在事件抽取层增加 actor/geography guard，避免仅凭 `state of war`、`air strike`、`talks` 等宽关键词生成 US-Iran direct evidence。

验收：

- 固定 gold sample 可一键评估
- 报告能明确列出失败 case 和错误类型
- 每轮 ontology / mapping 改动后可比较 baseline
- 未通过门禁时，不进入真实 Telegram 高置信告警

---

### Phase 6：扩样评估 + 真实回放优化

目标：避免系统只对少量人工样本“特调通过”，把评估对象从“小型 gold case”扩展到“结构化 gold sample + 真实回放样本 + 产品级输出审计”。

本阶段的核心不是继续微调规则本身，而是先解决两个风险：

1. 样本量过小，导致 baseline 很容易被人工适配；
2. case-level 指标通过，但真实市场回放里的 key news / alert 仍不可信。

Phase 6 的测试对象拆成三层：

```text
Layer A: gold sample
- 小而准的人工标注样本
- 用来做规则回归门禁

Layer B: replay sample
- 从真实运行日志 / 产品实验里回收的误报、漏报、坏 key-news case
- 用来约束系统不要只适配理想化样本

Layer C: product audit sample
- 面向市场级输出，检查 top key news、alert、reasoning 是否像人话、是否离谱
- 用来验证“最终产品是否可用”
```

建议样本扩展策略：

```text
当前 12 条 baseline gold cases
→ 先扩到 30-40 条（覆盖每个核心 market_condition 的正例 / 负例 / 边界例）
→ 再增加 20-30 条 replay cases（来自真实误报/漏报）
→ 总量至少达到 50-70 条，才适合开始更认真地看规则收敛效果
```

样本构成建议：

1. **正例**：直接结算型新闻（如签协议、正式会面、正式宣战、军事行动结束）
2. **负例**：Gaza-only / Lebanon-only / Israel-only / 宽泛中东背景新闻
3. **边界例**：
   - 提到 Iran 但不满足 market actors
   - 提到 talks 但不是 US-Iran direct contact
   - 提到 air strike / state of war，但只是区域冲突背景
   - 提到 regime / government，但并非 Iran regime collapse
4. **多市场共享例**：同一条新闻对多个市场都相关，但 direction / evidence_type / strength 应不同
5. **产品级坏例**：进入 top 3 key news 但人一眼觉得不合理的 case

新增 / 建议固化文件：

```text
tests/gold_samples/iran_conflict_gold.yaml          — 小而准的核心门禁样本
tests/gold_samples/iran_conflict_replay_cases.yaml  — 从真实运行中积累的 replay cases
reports/phase6_replay_evaluation.md                 — replay 层评估结果
reports/phase6_product_audit.md                     — 产品级输出审计报告
```

Phase 6 评估指标建议分两类：

### A. case-level 指标（底层匹配）

```text
matched_accuracy
event_type_accuracy
evidence_type_accuracy
direction_accuracy
false_positive_count
false_negative_count
```

### B. product-level 指标（最终输出）

```text
bad_key_news_rate          — top key news 中明显不合理的比例
false_alert_rate           — 市场级误告警比例
top3_key_news_precision    — top 3 key news 中人工认可的比例
market_reasoning_diversity — 不同市场是否仍然输出近乎相同的解释
direct_noise_rate          — 被标成 direct 但实际更像 context/irrelevant 的比例
```

Phase 6 工作顺序建议：

1. 把当前真实回放里已经暴露的问题样本补进 replay sample；
2. 把 baseline gold 扩到至少 30-40 条；
3. 单独生成 product audit 报告，检查每个市场 top 3 key news；
4. 只针对 replay / audit 中稳定复现的问题做小步规则修正；
5. 每次修改后同时跑 gold + replay + product audit，防止“修一个样本，坏一片数据”。

Phase 6 的通过标准建议：

- gold sample 不退化；
- replay sample 中已知误报显著下降；
- peace deal / diplomatic meeting / regime fall 等核心市场，不再频繁出现 Gaza/Lebanon-only 新闻进入 direct key news；
- product audit 中 top key news 的人工可接受度明显提升。

Phase 6 保留回顾位：

- 如果扩样后仍反复出现“同一新闻多事件证据覆盖”的问题，应优先考虑升级 `news_market_links` 的存储结构；
- 如果 direct/context 的边界仍然只能靠硬规则维持，后续可考虑增加一层轻量 LLM 或 reranker 作为精排，而不是继续无限堆规则。

验收：

- 评估集不再停留在十几个 handcrafted baseline cases
- 真实运行误报可以稳定转化为 replay 资产
- 规则修改必须同时在 gold / replay / product audit 三层通过
- 产出结果能证明“系统在扩样后仍成立”，而不是只适配少数样本

---

## 10. 近期最小可执行方案

当前优先执行已从 Phase 0 转移到 **Phase 6 的扩样与真实回放闭环**，因为基础 ontology/mapping 架构已经完成，当前瓶颈不再是“没有方案”，而是“样本太少，无法证明方案稳健”。

### Step 1：建立事件本体

为美伊冲突板块定义 ~15-20 个受控事件类型，每个包含 id / label / keywords / actors / examples。

### Step 2：建立市场条件归一表

为当前 6 类核心市场定义 market_condition_type，每个包含 id / label / resolution_question / resolution_keywords / actors。

### Step 3：建立映射矩阵

填写 event_type × market_condition 的完整映射，每条包含 direction / strength / evidence_type / note。

### Step 4：Python 加载模块

创建 `polybot/ontology/` 模块，实现 YAML → dataclass 的加载器和查表 API。

### Step 5：验证

编写加载测试脚本，确认：
- YAML 解析正确
- `lookup(event_type, market_condition)` 返回预期结果
- 映射矩阵覆盖所有 event_type × market_condition 组合

---

## 11. 研究问题清单

后续我们可以围绕这些问题持续讨论：

1. 什么样的新闻才算 prediction market 的 evidence？
2. 新闻标题足够吗，还是必须看正文？
3. 如何定义"市场条件词"？
4. 是否需要给每类市场建立模板？
5. 是否需要区分事件发生、谈判、声明、传闻、分析评论？
6. 新闻源可信度是否影响强度？
7. 旧新闻是否应衰减？
8. 同一新闻多次转载如何处理？
9. 如何判断新闻已经被市场价格反映？
10. 如何评估一次匹配规则改动是变好还是变坏？

---

## 12. 与 Week 5 的关系

本专项不必阻塞 Week 5 的全部工作。

更合理的关系是：

```text
Week 5 Web 看板 / Scheduler 可以继续推进
但新闻-市场匹配专项作为核心能力并行打磨
```

原因：

- Web 看板需要展示匹配结果；
- Scheduler 需要持续产生样本；
- 匹配专项需要真实运行数据；
- 两者可以互相促进。

但如果要进入真实告警或更高置信判断，本专项必须逐步解决。

---

## 13. 当前结论

新闻-市场匹配是 Polybot 的核心能力，不是一个小规则问题。

它的本质是：

```text
把新闻中的事件信息，映射到预测市场的可结算条件上。
```

本专项的正确方向不是追求新闻独占，而是：

```text
共享新闻可以存在；
但每个市场必须有自己的相关性权重、影响方向、证据类型和解释逻辑。
```

近期最优先做的是：

1. 建立可复盘样本；
2. 重构 Market Profile；
3. 区分 core entity 与 condition terms；
4. 降低纯实体命中的权重；
5. 把 key news / context news 分层输出。

---

## 14. 下一次讨论建议

下一次讨论可以从这三个问题开始：

1. 对 Iran 市场，我们先选哪 5 个典型市场作为 gold sample？
2. Direct evidence / context news / irrelevant 的边界怎么定义？
3. 第一版 Market Profile 应该由规则生成，还是允许 LLM 参与生成？
