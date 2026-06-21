# Polybot 新闻-市场匹配专项评估与测试优化结论

**时间：** 2026-04-27 23:24

## 1. 结论先说

`Polybot新闻市场匹配专项计划.md` 这份专项计划，**作为“架构重构 + 评估闭环设计”的完成效果是达标的，甚至可以说主干已经跑通**。

但如果按“真实线上告警质量已经足够稳定”来衡量，**还没有完全达标**。

当前状态更准确地说是：

- **专项方案设计已经落地到代码与数据结构**；
- **离线 gold sample 回归门禁已经建立，并且当前通过**；
- **真实新闻回放里仍存在明显误匹配/误告警样本**；
- 因此项目应从“方案搭建阶段”进入 **“测试驱动的优化调整阶段”**，而不是直接宣告匹配问题已解决。

---

## 2. 对专项计划完成效果的评估

## 2.1 已完成且效果明确的部分

### A. 专项方向是对的

专项计划最重要的纠偏已经落实：

- 不再追求“不同市场必须拥有独占新闻”；
- 改为允许共享新闻，但要求：
  - 市场角度不同；
  - direction 不同；
  - strength 不同；
  - evidence_type 不同；
  - reasoning 不同。

这点非常关键，方向正确。

### B. 匹配系统已从“泛 alias 规则”切到“事件本体 + 市场条件 + 映射矩阵”

这不是小修补，而是核心架构升级。

已经落地的能力包括：

1. **事件本体层**：新闻先抽成 event_type；
2. **市场归一层**：市场先归一成 market_condition；
3. **映射层**：通过 event_type × market_condition 查 direction / strength / evidence_type；
4. **输出层**：状态包、概率判断、告警草稿都已接入 direct/context 分层。

这意味着专项计划不是纸面文档，而是已经真正进入代码主链路。

### C. 回归评估闭环已建立

本轮重新验证结果：

- `run_match_evaluation.py` 重新执行通过；
- gold sample：12/12 passed；
- matched / event / evidence / direction 四项准确率都是 100%；
- false positive = 0；
- false negative = 0。

这说明：

**专项计划中最重要的“可复盘、可回归、可量化”能力已经具备。**

这点价值很高，因为以后任何匹配规则调整，都有最基本的门禁，而不是盲改。

---

## 2.2 当前尚未完成到“可以放心上线”的部分

### A. gold sample 通过，不等于真实数据稳健

真实数据回放结果仍显示：

- 活跃市场 6 个；
- 仍有 3 个 warning；
- 其中至少 2 组 case 看起来仍有明显问题：
  - `US x Iran permanent peace deal` 市场使用了 Gaza / Lebanon 相关新闻作为 direct negative key news；
  - `Will the Iranian regime fall` 市场出现了 Lebanon 新闻被解释成 regime_change direct evidence 的情况；
  - `US x Iran diplomatic meeting` 市场仍把 `State of war in Gaza` 这类新闻放进 direct key news。

这说明：

**当前离线评估集覆盖的是“已知风险样本”，但还没有充分覆盖真实新闻流中的变体。**

### B. 当前评估脚本更像“单 case 规则验证”，还不是“真实回放评测”

`run_match_evaluation.py` 的价值很高，但它当前验证的是：

- 单条新闻；
- 单个 market_condition；
- 预期 event/evidence/direction 是否正确。

它还没有覆盖这些更真实的问题：

1. 同一新闻在多个 event_type 下的冲突；
2. 同一新闻在多个市场下的排序优先级；
3. key news 进入 top N 的竞争结果；
4. direct/context 在真实新闻分布下是否过宽；
5. 最终 alert 是否被错误触发。

### C. 数据结构还有一个核心限制没有解

`news_market_links` 仍使用 `(news_id, market_id)` 唯一键。

这导致：

- 同一新闻对同一市场若命中多个 event_type；
- 最终只保留最后一次 upsert 的结果；
- 多证据并存、分市场解释差异、排序可解释性都会受限。

这不是当前必须马上重构的阻塞项，但它已经是进入下一阶段后的主要技术债。

---

## 3. 这次测试阶段重新验证到的事实

本轮已做的测试：

1. 重新运行离线评估；
2. 重新抽取 news events；
3. 重新运行 ontology match 落库；
4. 重新运行产品实验回放。

### 3.1 离线评估结果

- baseline recheck：12/12 passed
- 结论：规则没有退化，当前 gold sample 门禁有效。

### 3.2 真实数据回放结果

- markets processed: 6
- alerts generated: 3
- low confidence: 2

### 3.3 真实数据暴露的主要问题

#### 问题 1：负样本仍可能绕过 actor/geography guard

虽然 gold sample 中 Gaza/Lebanon-only 负样本已经被挡住，但真实数据里仍然出现了：

- Gaza 战争新闻进入 peace deal / diplomatic meeting 的 direct key news；
- Lebanon 新闻进入 regime_fall 的 direct key news。

这说明 guard 机制还不够，至少存在以下可能性之一：

- event_type 抽取偏宽；
- actors 抽取不完整或被错误补齐；
- 某些 market_condition 的 actors 要求过松；
- 真实数据文本中出现了弱 Iran 提及，导致被放行；
- `state of war` / `air strike` 这类词在映射表里给 direct 过重。

#### 问题 2：映射矩阵里“军事升级类事件”对部分市场给得过强

当前 mapping 中：

- `war_declared -> permanent_peace_deal` 是 direct strong negative；
- `military_strike -> permanent_peace_deal` 也是 direct strong negative；
- `war_declared -> diplomatic_meeting` 是 direct strong negative；
- `military_strike -> diplomatic_meeting` 是 direct medium negative。

理论上这没错，但在真实数据里如果新闻并不是 **US-Iran / Israel-Iran 的直接结算级冲突**，而只是 Gaza/Lebanon 层面的区域冲突，那么这些 direct strong 映射会把噪音放大成 key news。

也就是说：

**当前不是“映射方向错了”，而是“direct 的触发前提还不够严格”。**

#### 问题 3：当前评估口径缺少“产品输出质量”指标

现在的评估更偏底层匹配正确性，但还缺少产品级指标，例如：

- false alert rate
- bad key-news rate
- irrelevant direct rate
- top-3 key news precision
- market-level reasoning diversity

这些指标才真正决定 Telegram 告警是否可用。

---

## 4. 因此，专项现在应进入什么阶段？

我建议把专项正式定义为：

## Phase 6：真实回放测试 + 精准收敛优化

目标不是再大改架构，而是：

1. **扩大测试集**；
2. **针对真实误报做小步修正**；
3. **把评估从 case-level 提升到 product-level**；
4. **形成“改一条规则，就能知道对最终告警有无帮助”的闭环。**

---

## 5. 下一阶段的优化建议（按优先级）

## P0：先补“真实误报样本集”

把本轮产品实验里暴露的误报，直接补进 gold sample 或新增 replay sample：

至少新增这三类 case：

1. Gaza `state of war` 不应成为 `US x Iran permanent peace deal` 的 direct key news；
2. Lebanon `air strike` 不应成为 `Iran regime fall` 的 direct key news；
3. 区域战争新闻若未明确指向 US-Iran 双边接触中断，不应自动成为 `diplomatic_meeting` 的高优先 direct 证据。

这个动作最值，因为它会立刻把“真实问题”转成可回归资产。

## P1：收紧 direct 触发条件，而不是简单改方向

建议优先检查并收紧这两类逻辑：

### 1) 军事升级类事件

对于 `war_declared` / `military_strike` / `ceasefire` 这类事件：

- 若 market_condition 是 `permanent_peace_deal`、`diplomatic_meeting`、`regime_fall`；
- 除了 event_type 匹配外，应再要求：
  - actors 更严格命中；或
  - evidence_sentence 明确出现 Iran/US/Israel 相关核心实体组合；或
  - 事件文本与市场 resolution actors 存在更强交集。

否则降级为 context，而不是 direct。

### 2) Iran-only 市场

如 `regime_fall`：

- 不能只要求文本提到 Iran；
- 应尽量要求出现政权、政府、最高领袖、Tehran authority、collapse/overthrow 等 regime-specific 证据。

否则普通战事新闻很容易被误转成 regime_change。

## P2：给产品实验增加“坏 key news”审计

建议新增一个轻量脚本或报告段落，输出：

- 每个市场 top 3 key news；
- 每条 key news 的 event_type / evidence_type / actors / reason；
- 人工一眼可看出是否离谱。

这是当前最直接的质量检查手段。

## P3：为多证据结构做技术预研

短期不一定马上改库，但应把它列为下一阶段设计点：

- 新增 `news_market_evidence` 明细表；或
- 将唯一键扩展为 `(news_id, market_id, event_type)`。

因为后续如果要比较“同一新闻为什么在 A 市场是 context，在 B 市场是 direct”，单条覆盖式结构会越来越难用。

---

## 6. 我对当前专项完成度的判断

如果按不同标准打分：

### 作为“专项方案是否跑通”
**8.5/10**

因为：
- 架构已落地；
- 主链路已接通；
- 回归评估已建立；
- 文档与代码基本一致。

### 作为“真实产品告警是否已经可信”
**6/10**

因为：
- 真实回放仍有明显坏 key news；
- gold sample 规模还不够；
- product-level 评估指标还缺。

### 作为“是否适合进入测试优化阶段”
**是，而且现在就该进入。**

因为现在继续讨论抽象方案的收益已经下降，下一步最值钱的工作就是：

- 用真实误报驱动扩样；
- 用小步修正规则收紧 direct；
- 用回归门禁防止修一处坏一片。

---

## 7. 建议的下一步执行顺序

### 第 1 步
把本轮产品实验暴露的 3-5 个误报样本加入评估集。

### 第 2 步
围绕 `war_declared` / `military_strike` / `regime_change` 对应市场条件，收紧 direct 判定前提。

### 第 3 步
重跑：

- `run_match_evaluation.py`
- `run_ontology_match.py`
- `run_product_experiment.py`

同时观察：

- baseline 是否退化；
- 真实 bad key news 是否减少；
- alerts 数量是否更合理。

### 第 4 步
若真实误报仍多，再决定是否进入数据结构升级（多证据明细表）。

---

## 8. 当前阶段判断

一句话总结：

**这份专项计划已经从“想法文档”变成“已落地的核心能力改造方案”，完成度是合格的；但它真正的价值现在才开始体现——接下来必须进入真实回放测试和针对性优化，而不是停留在计划完成的表面胜利。**
