<p align="center">
  <a href="README.md">English</a> · <a href="README.ko.md">한국어</a> · <b>简体中文</b> · <a href="README.ja.md">日本語</a>
</p>

<p align="center">
  <img src="assets/readme/hero-v6.svg" alt="Research Orchestrator：通过 agents.md、plan.md、discoveries.md、handoff.md 四个文件，跨会话、跨主机、跨用户地协调工作项目、研究和竞赛" width="100%">
</p>

# Research Orchestrator

一个面向 Claude Code、Codex 和 Google Antigravity 的插件，让工作项目、研究和竞赛在多个 AI 会话之间持续推进。它包含一个技能、主机钩子、`ro` 命令行工具和一个只读审核代理。四个 Markdown 文件保存设置、任务队列、可复用的发现和持久的交接记录。预设决定会话如何共享队列、由谁审核发现，以及适用哪些证据检查。

**版本 6.0.2。** 自 5.1.0 以来的变更见 [CHANGELOG.md](CHANGELOG.md)。现有项目可继续使用；更改其设置前，请先阅读下方的迁移一节。

## 为什么使用它

<p align="center">
  <img src="assets/readme/why-use.webp" alt="没有编排时，工作会丢失上下文、重复实验、依赖单一模型、当前最佳不明；使用 Research Orchestrator 后，agents.md、plan.md、discoveries.md 和 handoff.md 带来共享记忆、更少重复、交叉检查过的发现，以及清晰的当前最佳和下一步假设" width="100%">
</p>

没有共享记录时，每个新的 AI 会话都从零开始：上下文丢失，同一个想法被尝试两次，某个模型未经核实的说法左右计划，也没人说得清哪个结果是最新的。Research Orchestrator 把这些状态保存在四个纯文本文件中，任何会话、主机或用户都能读取。工作从记录的恢复点继续，新条目入队前先做重复检查，在他人依赖某项发现之前可由另一个会话或主机审核，当前最佳等项目级数值也只存放在一处。无论是持续数天的工作项目、研究还是竞赛，都是如此。

## 安装

`PATH` 中需要有 Python 3.12+（CI 验证的最低版本）。可通过 Claude Code 插件安装，或在检出目录运行 `python install.py --host claude-code`、`python install.py --host codex` 或 `--host both`。只复制技能文件夹不会安装钩子。

Windows: 还必须安装 Git Bash (`sh`)。

### Claude Code 插件（推荐）

在 Claude Code 中执行：

```text
/plugin marketplace add TaeyanG4/research-orchestrator
/plugin install research-orchestrator@research-orchestrator
```

GitHub 仓库充当市场。插件会注册钩子和 `ro-reviewer` 代理，更新跟随插件版本。安装后请开启新会话；`ro brief` 应报告 `hooks active`。

缺少 `ro` 启动器时，SessionStart 和 `ro brief` 会打印适用于已安装插件的完整 `--shim-only` 命令。该命令为对应运行时创建 `ro` 入口，不复制技能或钩子。

### Codex

在检出目录或解压后的发行包中运行：

```bash
python install.py --host codex
```

该命令会一起安装技能和钩子设置；可选的 Codex 市场插件（`codex plugin marketplace add TaeyanG4/research-orchestrator`）不会注册钩子。请通过 `/hooks` 信任已安装的钩子（部分版本需先启用 `features.hooks`）；在此之前，请依靠 `ro` 命令和 Git pre-push。参阅[主机证据与信任范围](skills/research-orchestrator/references/hooks-capabilities.md)。

### 不使用插件

```bash
git clone https://github.com/TaeyanG4/research-orchestrator.git
cd research-orchestrator
python install.py --host both
```

`--host` 可取 `claude-code`、`codex` 或 `both`（默认），默认范围为用户账户。`--project <dir>` 改为安装到项目中，并在共享分派器后注册该项目的 Git pre-push 关卡；请指定仓库根目录，因为嵌套文件夹会在写入任何内容之前被拒绝。提交项目的 `.claude/` 即可共享 Claude Code 设置；Codex 项目钩子使用绝对路径，移动检出目录后请重新安装。用户级安装需要在每个仓库另行安装关卡。

其他选项：`--dry-run` 预览变更，`--uninstall` 将安装内容移至备份，`--no-hooks` 安装技能和启动器但不安装主机或 Git 钩子，`--remove-hooks` 只移除手动主机钩子（保留技能、Git 关卡和无关钩子），`--no-shim` 跳过默认的 `ro` 启动器。安装器保留无关钩子，并备份被替换的内容；若 Claude Code 插件已启用，它会移除重复的手动注册。已有的自定义 pre-push 钩子保持不变，并附有集成 [pre-push 示例](hooks/pre-push.sample)的说明。

### 发行版本与离线使用

`main` 为最新稳定版，标签采用 `vX.Y.Z` 格式，每个 GitHub Release 都提供 CHANGELOG 说明和 zip 附件。离线时，解压 [GitHub Releases](https://github.com/TaeyanG4/research-orchestrator/releases) 中的 zip，并在该目录运行相同的 `install.py` 命令。无需安装即可试用插件：

```text
claude --plugin-dir <folder>
```

### Google Antigravity

将 `skills/research-orchestrator/` 复制到 `<project>/.agents/skills/research-orchestrator/`，或全局目录 `~/.gemini/config/skills/research-orchestrator/`（旧 CLI 位置：`~/.gemini/antigravity-cli/skills/research-orchestrator/`）；可用 `/skills` 确认发现。初始化会检测 Antigravity 会话并将其记录为主机。没有安装目标或钩子适配器：请使用 `ro`，并手动安装 [Git pre-push 关卡](skills/research-orchestrator/references/publication-safety.md)。

## 快速开始

安装后，在项目文件夹中让代理初始化 Research Orchestrator，或自己执行相同的步骤。`<skill-root>` 是包含 `SKILL.md` 的安装目录，`ro` 指 `python <skill-root>/scripts/ro.py`：

```text
python <skill-root>/scripts/init_research_orchestrator.py . --preset work-project --user user1
python <skill-root>/scripts/check_project.py .
ro --session <host-session> --slot A brief
ro --session <host-session> --slot A next-id H
ro --session <host-session> --slot A claim <item>
ro --session <host-session> --slot A close
```

`<host-session>` 是 SessionStart 在 `Host session:` 之后输出的 ID；省略时使用 `RO_SESSION` 或 Codex 线程 ID。初始化程序会写入下一节介绍的四个文件（`--list-presets` 可查看其他预设）。`ro brief` 恢复设置、钩子状态、槽位选择、认领、作业和检查器计数。`ro next-id H` 为 `plan.md` 中的新条目预留 ID；`ro claim` 为你的槽位锁定该条目（仅 unified 工作流）；`ro close` 释放空闲认领，运行检查器并报告剩余事项。代理在每个会话中重复这一循环，并按下文的条目生命周期记录每个完成的条目。

## 四个文件

每个项目都把协调状态保存在项目根目录下四个小写的 Markdown 文件中。`.ro/` 保存工具状态（作业、回执、预留、锁和检查器基线），而不是协调信息。

| 文件 | 内容 | 由谁编辑 |
| --- | --- | --- |
| `agents.md` | 预设摘要、设置、阅读指引，以及由用户拥有的 `## Project rules` 区域（常设规则、会过期的例外、一行教训） | 初始化程序写入设置和指引，`--reconfigure` 应用你手动修改的值；从 `## Project rules` 起的内容归用户所有，不会被重新生成 |
| `plan.md` | 仅含未完成的条目；完成的条目会离开队列 | classic：每个槽位编辑自己的 `## Agent:` 段落，以及有记录的接管；unified：任何槽位，但不包括其他活动槽位已认领的条目 |
| `discoveries.md` | 附带证据和审核状态的可复用发现 | 来源槽位撰写并修订条目；合格的审核者添加审核行并设置 `Cross-check` |
| `handoff.md` | 共享状态、事件历史、外部操作，以及每个槽位的恢复点 | 每个槽位只编辑自己的 `### Agent:` 段落；每个会话都追加事件并更新 Shared state 的值 |

编辑共享文件前请重新读取，只修改相关段落或追加条目，以免过时的副本覆盖其他会话的工作。每个事实只存一次，其他地方指向它。[记录与共享文件编辑](skills/research-orchestrator/references/records.md)。

## 预设

预设会填写 `agents.md` 中的设置块；每个值都在那里可见、可编辑。*Profile* 是工作类型，*workflow* 是会话共享队列的方式，*verification* 是谁必须审核发现。

| 预设 | 适用场景 | Profile | Workflow | Item size | Guards | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| [`quick`](examples/quick-script-cleanup/README.md) | 单个代理的短期工作 | work | classic | short | off | self |
| [`work-project`](examples/work-project-data-migration/README.md) | 持续数天的迁移、分析或构建 | work | unified | staged | light | independent-review |
| [`solo-research`](examples/solo-research-literature-replication/README.md) | 单个代理的长期研究（研究推荐） | research | unified | staged | light | independent-review |
| [`team-research`](examples/team-research-cv-leakage/README.md) | 多个会话或主机并行（5.1.0 的方式） | research | classic | short | light | cross-host-once |
| [`competition-solo`](examples/competition-solo-tabular/README.md) | 主要由一个代理进行的竞赛 | competition | unified | staged | light | independent-review |
| [`competition-team`](examples/competition-team-forecasting/README.md) | 由并行会话或主机参与的竞赛 | competition | classic | short | light | hybrid |

- **执行：** 所有预设都使用 `Enforcement: block` 和 `Block: shell.background, shell.heredoc, jobs.mutate-bound, publish.scan`；竞赛预设额外加入 `external.gate`。
- **平台：** 单人预设在一个检测到的平台上运行（`Cross-check fallback: same-host`）；团队预设默认为 `Claude Code, Codex`（`wait`）。
- **回执：** `Receipt policy` 在 `competition-solo` 中为 `self`，其余为 `independent`；在 `independent` 下，必须由另一个会话签署产物回执。
- **子代理：** 计划收集器和审核者初始为 `off`；队列上限为 `stop at 50, resume at 5`。
- **自定义和已保存的预设：** `custom` 或省略预设会为新项目使用轻量工作默认值及唯一检测到的主机；现有项目保留兼容设置。用 `--save-preset <name>` 保存，再以 `--preset user:<name>` 使用。

每个预设都链接到一个示例项目。[设置、优先级与用户预设](skills/research-orchestrator/references/presets.md)。

## 设置

安装后，请让代理初始化 Research Orchestrator。它会一次性收集以下回答，并跳过你已经提供的内容：

1. **预设**：上述六种之一（`--list-presets` 也会列出你保存的预设）。
2. **你的名字**：作为本会话用户记录的一个词，例如 `user1`。
3. **剩余预设问题**：从检测结果和请求推断平台、`Environment` 和 `Language`，仅在没有明确答案且检测失败或有歧义时询问；默认值通过 `Info:` 报告（`Language` 默认为 `en`）。竞赛预设还需要竞赛与阶段时钟。`--competition "kaggle/<slug> deadline=YYYY-MM-DD"` 提供适配器的外部操作模式和阶段时钟截止日期；显式 `--phase-clock` 优先。仅在仓库内询问 Git 同步；`quick` 只需预设和姓名，仓库内再加 Git 同步。

随后代理会运行初始化程序；它只接受参数，从不提问。`<skill-root>` 是包含 `SKILL.md` 的安装目录。`--answers` 以 JSON 对象或文件接收同样的回答，键为带下划线的设置名以及 `name`、`user`、`agents` 和 `ordering`；显式参数会覆盖这些键。缺少回答时，错误信息会打印一条完整的示例命令。

```text
python <skill-root>/scripts/init_research_orchestrator.py --list-presets
python <skill-root>/scripts/init_research_orchestrator.py . -n "<project>" --preset work-project --user <user> --platforms "<host>" --environment linux/bash --language en
python <skill-root>/scripts/init_research_orchestrator.py . --answers answers.json
python <skill-root>/scripts/check_project.py .
```

<p align="center">
  <img src="assets/readme/setup-flow.svg" alt="设置：预设、姓名、仅询问未解决问题。报告检测默认值，生成四个协调文件及 .ro/template-render.json。" width="100%">
</p>

初始化程序写入四个协调文件，并将渲染元数据存放在 `.ro/` 中。`Language` 只作用于自由文本；标题、字段名、ID、状态词、检查 ID 和设置键保持英文，以便检查器、钩子和 `ro` 正常工作。

## 工作流

槽位（`A`、`B`、… `AA`）命名的是工作线，而不是工具或人，因此任何主机都可以接续一个槽位。

<p align="center">
  <img src="assets/readme/workflows.svg" alt="Classic：每个槽位拥有 plan.md 中的一个 Agent 段落，条目只能通过有记录的接管更换所有者。Unified：一个共享 Queue，每个条目带有 Claimed 行，ro claim 先加锁、重新读取，再写入认领" width="100%">
</p>

### Classic

每个槽位拥有 `plan.md` 中的一个 `## Agent: <slot>` 段落，只阅读自己段落的详细内容；重复检查、分派和接管只读取有限的元数据。条目只能通过有记录的接管更换所有者，其他主机放入队列的条目通常仍归该主机。这是 5.1.0 的行为，也是没有 `Workflow` 行的项目的默认值。[Classic 工作流](skills/research-orchestrator/references/workflow-classic.md)。[跨主机接管一个条目的例外](skills/research-orchestrator/references/workflow-classic.md#cross-host-take-over-by-judgment)要求来源主机空闲、较近工作已用尽，并符合所列资格条件。

### Unified

一个 `## Queue` 保存所有条目，每个条目以 `Claimed: none` 或 `Claimed: <slot> since <time>` 开头。`ro claim` 会获取项目锁、重新读取队列，然后写入认领，因此两个槽位无法认领同一条目。任何人都可以完善未被认领的条目；没有人会编辑其他活动槽位已认领的条目。[Unified 工作流](skills/research-orchestrator/references/workflow-unified.md)。

在两种工作流中，`Item size: staged` 都允许较长的条目声明 `Stages:` 并记录阶段事件。列在 `Important stages:` 中的阶段，只有在具备与其 `:before` 范围完全匹配的独立回执时才能启动，即使在 `Receipt policy: self` 下也是如此。结果改变决策的阶段会留下自己的带日期事件（含 `Decision: changed`）和一条发现，并且在该条目下次启动前需要独立的 `:after` 回执。[分阶段条目](skills/research-orchestrator/references/staged-items.md)。

更改 `Workflow` 会移动条目，因此需要 `--reconfigure --migrate`。

## 槽位与会话

槽位依次命名为 `A` 到 `Z`，然后是 `AA` 到 `ZZ`；单个代理的工作使用 `A`，创建新槽位前会先复用已释放的槽位。每个槽位在 `handoff.md` 中有一个 `### Agent: <slot>` 段落，包含 `Current host`（平台，如 Claude Code 或 Codex，而不是模型）、`Current user`（运行该会话的人）、`Current thread`、`Resumable state`、`Blocker` 和 `Next action`。只有当 `Current host` 为 `unassigned` 或 `released` 时槽位才空闲；其他任何值都表示已被占用，即使会话看起来不活跃。

**新会话。** 明确指定的槽位或继续/并行意图会被直接采纳；只有一个未过期的合格槽位时会自动接手。其他情况下，SessionStart 和 `ro brief` 会列出每个候选槽位的所有者、最近活动和运行中的作业，代理只问一个问题：继续某个槽位（若其会话已结束则回收）、启动并行槽位，或使用指定槽位。已占用的槽位若没有受保护的作业，且在 `Stale slot after`（默认 `2h`）内没有事件或认领，即视为过期。回收会被记录，并保留认领、可恢复状态和作业；`Autonomy: away` 不提问，直接启动新的并行槽位，并记录该选择以便稍后决定。[会话](skills/research-orchestrator/references/sessions.md)。

**阅读规则（classic）。** 会话完整阅读自己的计划段落和交接段落。对于其他活动槽位，只读取用于分派或接管的条目元数据、用于重复检查的标题和 `Hypothesis`/`Goal` 行，以及 `Current host`、`Current user` 和 `Current thread` 行；不读取其可恢复状态和详细证据，使每条推理线保持独立。新条目和后续条目放进自己的段落，使用自己的 ID。

**接管（classic）。** 自己的队列用完后，先重新读取自己的段落，承接一项合格的审核，再接管同主机槽位中排队的条目：其 `Current host` 是你的主机且由你本人运行的槽位，或最近一次事件来自你的主机（或尚无事件）的 released 或 unassigned 槽位。绝不接手所有者的 `Current thread`、处于 `Active compute` 认领下的条目，或另一位用户正在运行的槽位中的任何条目。用你的下一个 ID 把条目移入自己的段落，并在标题中注明旧 ID（`H-A-05 — Retry policy for the nightly import (from H-C-03)`），废弃旧 ID，重新审视并重新打分，再把接管记录为交接事件。跨主机的条目只能在较近的工作用尽后，凭判断从空闲槽位接管一个。

<p align="center">
  <img src="assets/readme/take-over-v6.svg" alt="Classic 工作流：Claude Code 上的 A 槽位队列已空，于是把最近一次事件来自 Claude Code 的已释放槽位 C 中的 H-C-02 接管为 H-A-04，并废弃旧 ID；B 槽位由另一位活跃用户在 Codex 上运行，因此其条目留在 B" width="100%">
</p>

**跨主机审核。** 在 `cross-host-once` 下，每条发现都记录其 `Host`，并由另一台主机上的会话审核一次，因为同一主机上的会话有相同的盲点。审核者先认领审核（`Cross-check: REVIEWING <host> (<slot>)`），以免其他会话接手，然后添加带日期的审核行并设置状态。来源槽位从不审核自己的发现；同主机审核只在 single 模式或 adaptive 的 `Cross-check fallback: same-host` 下有效，并以 `same host —` 开头。

<p align="center">
  <img src="assets/readme/cross-host-check-v6.svg" alt="在 cross-host-once 下，Claude Code 上的 A 槽位审核来自 Codex 的 D-B-003 并标记为 VERIFIED；Codex 上的 B 槽位已认领来自 Claude Code 的 D-A-002 的审核；已释放的 C 槽位会被优先复用" width="100%">
</p>

[Classic 工作流](skills/research-orchestrator/references/workflow-classic.md)、[审核](skills/research-orchestrator/references/verification.md)。

## 记录格式

字段名、ID 和状态词保持英文；自由文本遵循 `Language`。用 `ro next-id` 预留 ID：条目为 `H-<slot>-<NN>`，发现为 `D-<slot>-<NNN>`，由创建它的槽位编号，且从不复用。

**计划条目，简洁形式**（work 配置，或任何使用 `Ordering: queue` 的计划）。`Claimed` 只出现在 unified 工作流中：

```markdown
### H-A-02 — Retry policy for the nightly import
- Claimed: A since 2026-10-27 09:10
- Goal: make the nightly import retry transient failures
- Evidence: two of the last ten runs failed on a network timeout
- Next test: add bounded retries and replay one failed day
```

**计划条目，打分形式**（按优先级排序的研究和竞赛）。每个因子是 0 到 3 的整数，`Priority = 2*Impact + 2*Information + Confidence + Unblock + Diversity + (3-Cost)`（0–24）。分数最高者优先；并列时先看 `Cost` 较低者，再看 `Information` 较高者。省略的路由字段表示 `CPU`、`NO` 和 `NONE`：

```markdown
### H-A-04 — Repeat the speed-up with a cold cache
- Sources: D-A-003
- Hypothesis: the new parser keeps its lead when the cache is cleared before each run
- Evidence: D-A-003 (VERIFIED) measured a 30% shorter median run time, but every run reused a warm cache
- Improvement: clears the cache before each of 20 runs, which D-A-003 did not
- Impact: 2
- Information: 3
- Confidence: 2
- Unblock: 1
- Diversity: 1
- Cost: 1
- Priority: 16
- Resource: CPU
- Parallel: NO
- Other: NONE
- Next test: 20 cold-cache runs of each parser on one machine; compare the medians
```

**发现。** `Session:` 记录来源会话，`independent-review` 和 `hybrid` 需要它。每条审核行写明审核者的主机和槽位、结论以及审核时间：

```markdown
## D-A-003 — The new parser shortens warm runs by 30%
- Source: A
- Host: Claude Code
- User: user1
- Date: 2026-10-27
- Session: claude-code:A@2026-10-27T09:10
- Cross-check: VERIFIED
- Finding: the new parser cuts the median run time from 12.0 s to 8.4 s over 20 warm-cache runs each
- Evidence: runs/parser-bench/summary.csv; reproduce with scripts/bench.py --runs 20
- Implication: adopt the new parser for warm runs; cold-cache behaviour is still untested
- Reviews:
  - Claude Code (A): CLOSED — reviewer subagent:ro-reviewer@2026-10-27T10:02 — reviewed 2026-10-27T10:15 — reran the benchmark: 8.5 s median
```

**交接事件。** 研究和竞赛为每个完成的条目追加一条，标题以条目 ID 结尾：

```markdown
### 2026-10-27 10:20 — A — H-A-03
- Host: Claude Code
- User: user1
- Action: benchmarked the new parser against the old one (20 warm-cache runs each)
- Result: 30% shorter median run time; see D-A-003
- Artifacts: runs/parser-bench/summary.csv
- Discovery updates: D-A-003
- Review verdict: D-A-003 CLOSED
- Resource: CPU
- Other executor: none
- New plan items: H-A-04
```

work 配置则只保留一条会话摘要，随条目完成而更新：

```markdown
### 2026-10-27 17:40 — A — session
- Host: Claude Code
- User: user1
- Action: added bounded retries to the nightly import and replayed one failed day
- Result: the replayed day completed; the export schema check remains queued
- Completed: H-A-02
```

**添加条目之前**，运行 `ro dupcheck <terms>` 并阅读发现索引（`ro index`）。若已有相同主张的 `VERIFIED` 结果，只能添加带 `Improvement` 的实质不同的后续条目；`CHALLENGED` 的结果要等质疑解决后再说；`PENDING` 的结果与其重复，不如去审核。还要浏览已排队条目的标题和 `Hypothesis`/`Goal` 行，并在写入前重新读取 `plan.md`；若期间出现了相同条目，保留较早的那条。

[条目字段、优先级与后续条目](skills/research-orchestrator/references/plan-items.md)、[记录](skills/research-orchestrator/references/records.md)。

## 条目生命周期

<p align="center">
  <img src="assets/readme/lifecycle.svg" alt="条目生命周期：认领或拥有，开展工作，记录发现和事件，推导后续条目，最后从 plan.md 中删除该条目以结束" width="100%">
</p>

1. **认领或拥有**：先做重复检查（`ro dupcheck`），再按工作流接手条目。
2. **工作**：运行下一项有用的测试。长时间作业通过 `ro launch` 和 `ro monitor` 处理；确认启动并不等于得到结果。
3. **发现**：把结果记录到 `discoveries.md`，包括否定和不确定的结果。审核遵循 `Verification` 设置：`self`（无需审核）、`cross-host-once`（由另一台主机审核一次）、`independent-review`（由另一个会话，例如子代理）或 `hybrid`（两种形式皆可）。
4. **事件**：在 `handoff.md` 中追加一条指向该发现的事件。
5. **后续条目**：把结果所指向的工作放入队列，或记录为何没有后续。
6. **结束**：从 `plan.md` 中删除已完成的条目。先一并完成发现、事件、后续条目和删除，再开始其他工作。

项目结束后，使用[事后复盘](skills/research-orchestrator/references/postmortem.md)记录教训。遇到主机限额或 429/503 错误，遵循[新会话重试规则](skills/research-orchestrator/references/compute.md)。

`cross-host-once` 要求另一个槽位；同主机审核在 single 模式，或采用 `Cross-check fallback: same-host` 的 adaptive 模式中有效。无法启动合格审核者时，让发现保持 `PENDING`，无需轮询等待，完成交接和结束流程。

work 配置（`quick`、`work-project`）更轻量。分数和 Priority 是可选的，由队列顺序或 `Next:` 行决定先后；只为可复用的结果（已确定的决策、死胡同、已验证的依赖）保留发现；一条会话事件列出已完成的条目。research 和 competition 为每个条目保留完整记录。[条目字段与后续条目](skills/research-orchestrator/references/plan-items.md)、[记录](skills/research-orchestrator/references/records.md)、[审核](skills/research-orchestrator/references/verification.md)、[会话](skills/research-orchestrator/references/sessions.md)。

`solo-research` 会生成 `Ordering: queue`；其他研究及竞赛项目也可选择它，已填写的分数仍会验证。

<p align="center">
  <img src="assets/readme/hypothesis-relay.webp" alt="从证据到假设 H1，分支为子假设 H1a 和 H1b 分别测试；交叉检查降低幻觉风险，结果合并为有依据的洞见，随后产生新假设 H2 和 H3" width="100%">
</p>

在研究中，这一循环不断积累：证据提出假设，子假设作为独立条目分别运行，审核检验每条发现，有依据的结果再通过后续条目引出下一批假设。

## 守卫

守卫只检查决策背后的证据是否已记录，不评判其质量。`Guards: light` 以警告报告缺口，`strict` 将各守卫列出的检查升级为错误，`off` 则关闭守卫。启用时会记录日期（`light since YYYY-MM-DD`），因此更早的记录不受约束。可在 Shared state 中一次性声明某个守卫 `not applicable — <reason>`，阈值也可以配置。可选的 discovery `Control` 记录安慰剂或噪声底线证据文件与选择收益。Control 缺失是例外：`guard.control.missing` 在 light 模式为 INFO，在 strict 模式为 WARN。

| 守卫 | 要求记录的内容 | `Guard set: auto` 为哪些配置启用 |
| --- | --- | --- |
| G1 Instrument evidence | 决定一条发现的测量的来源、覆盖范围、一致性和分辨率 | research、competition |
| G3 Family saturation | 同一系列中反复出现持平结果后，需要分辨率更高的测量或经过审核的结构性改变 | competition |
| G5 Overrides and rejections | 每个例外的复查条件和到期日；被否决的改动确实执行过的证据 | 所有配置 |
| G6 Insights | 每个诊断的截止时间，之后是计划条目或有证据的否决 | 所有配置 |
| GD Direction review | 定期回顾差距和决策（research 和 competition 更详细） | 所有配置 |
| G8 Phase clock | `Phase clock` 时间窗内的里程碑 | competition |
| G11 Selection | 说明了为何共享同一系列的最终选择 | competition |
| G12 Effort | 流程性工作相对于可能改变结果的工作所占的比例 | 仅在显式启用时 |
| E1 External actions | 外部操作前写下的预期、产物哈希，以及没有未标记的重复 | 所有配置 |

[研究守卫](skills/research-orchestrator/references/research-guards.md)、[决策守卫](skills/research-orchestrator/references/decision-guards.md)、[外部操作](skills/research-orchestrator/references/external-actions.md)、[competition 配置](skills/research-orchestrator/references/competition.md)。

## 计算资源与长时间作业

队列顺序或 Priority 决定下一步运行什么，路由决定在哪里运行。`Resource: CPU | GPU | EITHER` 是本地计算类别，`Parallel: YES | NO` 表示条目能否共享该资源，`Other: NONE | <name>` 指明独占的非计算资源或外部执行器，例如共享数据库、许可席位或云端批处理执行器。有帮助时先从两个并行槽位开始，只有在仍有独立的高价值条目且资源有余量时才继续增加。

使用独占资源之前，重新读取 `handoff.md` 并检查机器的实际占用，在 Shared state 的 `Active compute` 行中添加认领，然后通过 `ro launch` 启动；它还会在项目锁下预留该条目的本地资源：

```markdown
- Active compute: CPU — A (H-A-04, since 2026-10-27 14:05)
```

```text
ro --slot A launch --item H-A-04 --expect 2h --run-dir runs/h-a-04 --error "Traceback" -- python scripts/bench.py --runs 20 --cold
ro monitor <job>
ro jobs
ro kill <job>
```

立即启动打印出的监控命令：确认启动只能证明作业已经开始。`ro monitor` 会跟踪作业，直到它完成、匹配到错误模式、超过所设心跳上限仍无输出，或运行时间超过预期的两倍；`ro jobs` 列出作业和监控状态，`ro kill` 停止你的槽位所拥有、且经身份核验的进程树。把打印出的 Job 行追加到 `handoff.md`，检查产物，并且只在作业确实结束后才移除认领。所需资源繁忙时，去做独立的工作或合格的审核，或记录 `Blocker:`。只有当两个条目都是 `Parallel: YES` 且实测容量足够时，才共享同一资源；`ro launch` 只预留本地 CPU 和 GPU，因此 `Other` 资源需要自己的锁或调度器预留。

[工作进程与独占资源](skills/research-orchestrator/references/compute.md)、[启动、监控与停止](skills/research-orchestrator/references/operations-safety.md#lookup-launch-monitor-and-stop)。

## `ro` CLI

`ro` 指 `python <skill-root>/scripts/ro.py`。命令具有权威性，可在所有主机上使用；钩子只是让它们更早运行。全局选项为 `--project`、`--slot` 和 `--session`；每个命令都有 `--help`。

| 命令 | 用途 |
| --- | --- |
| `next-id {D,H,I,X,N}` | 预留下一个发现、计划条目、测量工具、外部操作或笔记的 ID |
| `dupcheck <terms>` | 添加工作前搜索标题和关键行，包括已归档的记录 |
| `index [ID]` | 打印发现索引，或某一条的完整内容 |
| `claim <item>`、`release <item>` | 在项目锁下认领 unified 队列中的条目，或释放它 |
| `launch --item … --expect … -- <command>` | 启动一个自有作业，带有绑定的输入和输出、错误模式、心跳、确认窗口和可选的 `--require-receipt` |
| `monitor <job>`、`jobs [--prune]`、`kill <job>` | 跟踪作业直至得到结果，列出作业和监控状态，停止经身份核验的自有进程树 |
| `receipt add`、`receipt check` | 按 `Receipt policy` 将 PASS 或 FAIL 结论绑定到产物的 SHA256，或进行验证 |
| `external --action <X-id> -- <command>` | 仅在台账、回执、重复和尝试历史检查通过后运行对外命令 |
| `observe <key> <value>` | 记录易变的 Shared state 事实；`--source` 可选，`--ttl` 默认为 `6h` |
| `brief [--max N]` | 只含事实的会话简报：设置、钩子自检、槽位选择、认领、作业、逾期守卫、检查器计数 |
| `close` | 保留运行中或未被监控的作业认领，释放其余认领，运行检查器并报告剩余事项 |
| `hook <event>` | 主机钩子接收标准输入 JSON，`pre-push` 接收 Git 引用更新行 |
| `check <command>` | 对命令字符串运行 shell 检查（`--dialect bash` 或 `powershell`） |

作业在自有的进程组（Windows 上为作业对象）中运行。启动器退出而工作进程仍在运行时，绑定和认领会保留；失败的运行器在后代进程存活或无法确认期间保留其槽位。`ro kill` 会核验槽位所有权、PID 和启动时间，因此不会把被复用的 PID 当作目标。`ro external` 在运行前把每次尝试写入日志，并按产物哈希和目标核对这段历史，因此编辑、撤回或重命名台账条目都无法隐藏先前的尝试；被中断或超时的操作在核对前保持 `unknown`。

[操作命令及其限制](skills/research-orchestrator/references/operations-safety.md)、[外部操作与回执](skills/research-orchestrator/references/external-actions.md)。

## 各主机的安全机制

依赖 Codex 钩子前，请通过 `/hooks` 建立信任；`ro` 命令和 Git pre-push 是执行关卡。

<p align="center">
  <img src="assets/readme/safety-layers.svg" alt="钩子、ro 命令和 Git pre-push；参阅链接的主机能力证据。" width="100%">
</p>

| 主机 | 逐次调用的钩子 | 保护执行的机制 |
| --- | --- | --- |
| Claude Code | 插件钩子或 `install.py --host claude-code` | `ro`, Git pre-push |
| Codex | `install.py --host codex`；需要钩子信任 | `ro`, Git pre-push |
| Google Antigravity | 无；仅命令 | `ro` 命令和 Git pre-push 发布扫描 |

- `Enforcement: off` 不输出任何内容，`warn` 从不拦截，`block` 只拒绝列在 `Block` 中的检查。
- **每次 shell 调用都按其工具自身的方言（Bash 或 PowerShell）解析，** 即使与 `Environment` 不同也是如此；`Environment` 仍决定路径规则和备用 shell。不确定的解析只警告，从不拦截。
- 逐次调用的钩子在崩溃、超时、输入格式错误或缺少解释器时放行；`ro brief` 会报告钩子自检和警告计数。当验证失败或无法运行时，`ro external`、`ro launch` 和 Git pre-push 关卡会拒绝执行；pre-push 会扫描每个待推送的提交，包括提交信息和路径。
- 钩子用于防止协作会话中的意外，并不是针对恶意行为的安全边界。嵌套的解释器代码体、here-string 内容、别名、动态路径和编码过的密钥都超出了可靠解析的范围。

Claude Code 插件订阅 `AskUserQuestion` 和 `Agent`；`Autonomy: away` 与 `Brief requirements` 未启用时，相应包装器不启动 Python。Read-bound 订阅仍需通过安装程序选择。SessionStart 和 `ro brief` 仅在 Git 检出目录缺少已注册的 pre-push 关卡时输出 `publish gate not installed` 和 `install.py --project <检出根目录>`；已有注册关卡负责发布扫描，避免每次调用重复扫描；逐次调用的预检读取推送所在的检出目录。包装器分别解析项目提示和命令工作目录，项目外不需要解释器。没有作业注册表时，Stop 和编辑检查也跳过 Python。PostToolUse 只复用稳定超过两秒的文件戳；审核回执或产物变化时，简报使缓存检查失效；简报最多对 64 MiB 审核证据计算哈希，其余标为未验证，由 `check_project.py` 完整验证。保存的 Windows 测量显示，项目外及无作业 Stop/编辑调用的 p95 为 23–36 ms，普通 shell 检查和未变化的 PostToolUse 为 48–125 ms；这些数据不代表新的受监督子进程测量。

[钩子、能力矩阵与信任](skills/research-orchestrator/references/hooks-capabilities.md)、[发布关卡](skills/research-orchestrator/references/publication-safety.md)。

## 从 5.1.0 迁移

更新已安装的插件不会改写现有项目：缺失的设置保持 5.1.0 的行为（classic 工作流、short 条目、cross-host-once 审核、守卫关闭）。手动安装时请将旧技能文件夹替换为 `research-orchestrator`，不要保留两份；更名说明见 CHANGELOG。

5.1.0 中已认可的 `multi`/`same-host` 审核仍然有效。重新配置会将其指纹保存在 `agents.md` 中；新审核遵循当前验证规则。

1. 保存四个文件和 `.ro/` 状态的可恢复副本，运行检查器并修复结构性错误。
2. 将手写在 `agents.md` 生成部分中的指示移到 `## Project rules`；重新配置会原样保留该区域。
3. 刷新生成的设置和阅读指引。如要采用某个预设，请加上 `--preset <preset>` 及其回答；第二条命令会把 classic 项目切换为 unified 工作流：

```text
python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure
python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure --workflow unified --migrate --user <user>
```

4. 更改 `Workflow` 还需要 `--migrate`；请先释放活动槽位。每次设置转换都会在写入前验证拟议记录，规范化兼容的目标和审核字段，同时保留证据和实际队列顺序。协调文件发生变化时，即使工作流不变，也会使用 `*.pre-migrate` 备份和恢复日志。
5. 检查结果，重新运行检查器，并将此次变更记录为交接事件。

在更改工作流或使用 `--force` 之前，请阅读[迁移与回滚流程](skills/research-orchestrator/references/migration-v2-to-v3.md)。

## 校验与 CI

在项目中，请在会话开始时、接管或迁移之后以及结束之前运行 `python <skill-root>/scripts/check_project.py .`（`ro close` 也会运行它）。ERROR 以退出码 1 失败，WARN 仅在 `--strict` 下失败，INFO 为建议，退出码 2 表示无法读取项目。`--baseline-update` 会保存发现的指纹，使之后的运行标出新问题而不隐藏旧问题。

在本仓库中，安装 pytest 后，按需运行轻量结构检查、确定性测试或完整发布检查：

```bash
python scripts/validate_release.py --skip-tests
python -m pytest -q -m "not latency"
python scripts/validate_release.py
```

轻量检查覆盖清单版本、README 结构和链接、SVG 有效性、核心与参考文档的大小预算、领域词汇、记录格式和示例项目。发布检查会扫描 `docs/`（包括证据 ZIP 内的成员），查找私有路径、账户名、原生标识符和内部会话模式。完整检查再加上确定性测试套件以及初始化和重新配置场景。计时测试带有 `latency` 标记，通过 `python -m pytest -q -m latency tests/test_ro_cli.py tests/test_ro_hooks.py` 单独运行。

GitHub Actions 在 Windows、Ubuntu 和 macOS 上以 Python 3.12 和只读权限运行完整检查，随后在每个操作系统上测量已安装钩子的 p95，并将结果保存为构件。用于行为用例、触发评估和已安装主机试运行的开发工具位于 [scripts/evals](scripts/evals/README.md)、[scripts/trigger](scripts/trigger/README.md) 和 `scripts/host/`。

## 证据

行为证据是历史记录（保存的运行，而非本版本本身），Codex 钩子仅在逐次调用信任下得到验证，Windows 计时为本地结果，6.0.1 版本的 CI 运行已在 Windows、Ubuntu 和 macOS 上通过，已安装钩子的 p95 约为 45–60 ms；请参阅[证据与限制](docs/evals/README.md)。

## 仓库结构

```text
.claude-plugin/  .codex-plugin/  .agents/   plugin and marketplace manifests
agents/ro-reviewer.md          read-only reviewer agent for Claude Code
assets/readme/                 README images
docs/                          plans, evaluation evidence, and host dry runs
examples/                      one worked project per preset
hooks/                         host hook wrappers and the Git pre-push gate
scripts/                       release validation, evaluation and trigger tooling, host dry runs
skills/research-orchestrator/
  SKILL.md                     the core instructions (12 KB budget)
  references/                  one file per operation, read when that operation runs
  templates/                   the four project files, plus earlier versions for migration
  presets/                     the six built-in presets
  scripts/                     initializer, checker, ro CLI, and hook runner
  agents/openai.yaml           Codex interface metadata
  evals/                       behaviour cases (not installed)
tests/                         deterministic test suite
install.py                     installer for Claude Code, Codex, or both
plugin.json                    plugin manifest
```

## 设计原则

- **通用优先。** 一个技能同等地服务日常工作项目、研究和竞赛。随附的指令使用中性词汇；竞赛专用内容只放在其参考文档和平台适配器中，并由发布检查强制执行词汇规则。
- **精简核心。** `SKILL.md` 保持在 12 KB 以内。每条详细规则只存在于一个参考文档中，在执行对应操作时才读取；生成的 `agents.md` 只保存设置、指引和项目规则，而不复制技能正文。
- **只做确定性检查。** 先是指引，再是与主机无关的检查器，然后是建议性钩子。拦截只用于 `Block` 中列出的、确定性的、代价高且反复出现的错误。
- **钩子失败时放行，关卡失败时拒绝。** 逐次调用的钩子在崩溃、超时或缺少解释器时放行调用；`ro launch`、`ro external` 和 Git pre-push 关卡在验证失败或无法运行时拒绝执行。
- **每个事实只有一个归处。** 主张和数据放在发现中，谁、何时、何地放在事件中，拟议的工作放在 `plan.md` 中，项目级数值放在 Shared state 中；其他地方只指向它们。
- **证据重于意图。** 守卫检查决策背后的证据是否已记录，确认启动不等于得到结果，发现只有经过合格审核才算已验证。
- **防止规则膨胀。** 常设规则有字节预算，例外会过期，每条教训只占一行，并写明强制执行它的检查。

## 许可证

[MIT](LICENSE).
