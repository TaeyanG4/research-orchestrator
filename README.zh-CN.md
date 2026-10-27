<p align="center">
  <a href="README.md">English</a> · <a href="README.ko.md">한국어</a> · <b>简体中文</b> · <a href="README.ja.md">日本語</a>
</p>

# Research Orchestrator

一个面向 Claude Code、Codex 和 Google Antigravity 的插件，让工作项目、研究和竞赛在多个 AI 会话之间持续推进。它包含一个技能、主机钩子、`ro` 命令行工具和一个只读审核代理。四个 Markdown 文件保存设置、任务队列、可复用的发现和持久的交接记录。预设决定会话如何共享队列、由谁审核发现，以及适用哪些证据检查。

**版本 6.0.0（技能设计 v3）。** 自 5.1.0 以来的变更见 [CHANGELOG.md](CHANGELOG.md)。现有项目可继续使用；更改其设置前，请先阅读下方的迁移一节。

## 为什么是 v3

对以往设计下进行的三个项目的复盘发现：执行强，策略弱。三个项目都信任了无法反映最终目标的测量，留下了未经检验的核心方法，把最后阶段花在小变体上，并记录了从未改变计划的诊断。其中一个项目还记录了 28 次操作失误，部分重复了三四次；它的检查器发现从 234 条增长到 452 条，最终无人再看。6.0.0 将这些教训转化为可选的工作流、检查决策依据是否已记录的证据守卫，以及少量确定性的安全检查。小型工作有更轻量的预设，详细规则只在操作需要时才加载。同样的流程也能通过清晰的任务队列和持续交接推进数据迁移等工作项目。

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
3. **剩余预设问题**：从检测结果和请求推断平台、`Environment` 和 `Language`，仅在没有明确答案且检测失败或有歧义时询问；默认值通过 `Info:` 报告（`Language` 默认为 `en`）。竞赛预设还需要竞赛与阶段时钟。仅在仓库内询问 Git 同步；`quick` 只需预设和姓名，仓库内再加 Git 同步。

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

| 文件 | 内容 |
| --- | --- |
| `agents.md` | 预设摘要、设置、阅读指引，以及由用户拥有的 `## Project rules` 区域（常设规则、会过期的例外、一行教训） |
| `plan.md` | 仅含未完成的条目；完成的条目会离开队列 |
| `discoveries.md` | 附带证据和审核状态的可复用发现 |
| `handoff.md` | 共享状态、事件历史、外部操作，以及每个槽位的恢复点 |

初始化程序写入四个协调文件，并将渲染元数据存放在 `.ro/` 中。`Language` 只作用于自由文本；标题、字段名、ID、状态词、检查 ID 和设置键保持英文，以便检查器、钩子和 `ro` 正常工作。

**新会话。** 明确指定的槽位或继续/并行意图会被直接采纳；只有一个未过期的合格槽位时会自动接手。其他情况下，SessionStart 和 `ro brief` 会列出每个候选槽位的所有者、最近活动和运行中的作业，代理只问一个问题：继续某个槽位（若其会话已结束则回收）、启动并行槽位，或使用指定槽位。已占用的槽位若没有受保护的作业，且在 `Stale slot after`（默认 `2h`）内没有事件或认领，即视为过期。回收会被记录，并保留认领、可恢复状态和作业；`Autonomy: away` 不提问，直接启动新的并行槽位，并记录该选择以便稍后决定。[会话](skills/research-orchestrator/references/sessions.md)。

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

使用 Claude Code 插件时，SessionStart 会指出插件匹配器未覆盖的可选检查，并打印用于订阅它们的 `install.py --project .`；当 Git 检出缺少 pre-push 关卡时，SessionStart 和 `ro brief` 还会报告 `publish gate not installed` 及其安装命令。包装器在启动 Python 之前先查找 `agents.md`，因此项目之外的调用无需解释器。没有作业注册表时，Stop 和编辑检查跳过 Python；未变化的 PostToolUse 调用依据文件时间戳跳过它；未变化的压缩复用检查器摘要。在 Windows 上实测的每次调用 p95：项目之外以及无作业的 Stop 和编辑为 23–36 ms，普通 shell 检查和未变化的 PostToolUse 为 48–125 ms，均在 150 ms 预算之内。

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

4. 更改 `Workflow` 还需要 `--migrate`；请先释放活动槽位。工作流迁移会写入 `*.pre-migrate` 备份和恢复日志，而仅修改设置的重新配置不会。
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

轻量检查覆盖清单版本、README 结构和链接、SVG 有效性、核心与参考文档的大小预算、领域词汇、记录格式和示例项目。发布检查会扫描 `docs/`（包括证据 ZIP 内的成员），查找私有路径、账户名、原生标识符和内部会话模式。完整检查再加上确定性测试套件以及初始化和重新配置场景。计时测试带有 `latency` 标记，通过 `python -m pytest -q -m latency` 单独运行。

GitHub Actions 在 Windows、Ubuntu 和 macOS 上以 Python 3.12 和只读权限运行完整检查，随后在每个操作系统上测量已安装钩子的 p95，并将结果保存为构件。用于行为用例、触发评估和已安装主机试运行的开发工具位于 [scripts/evals](scripts/evals/README.md)、[scripts/trigger](scripts/trigger/README.md) 和 `scripts/host/`。

## 证据

行为证据是历史记录（保存的运行，而非本版本本身），Codex 钩子仅在逐次调用信任下得到验证，Windows 计时为本地结果，CI 结果在发布前仍待定；请参阅[证据与限制](docs/evals/README.md)。

## 许可证

[MIT](LICENSE).
