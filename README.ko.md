<p align="center">
  <a href="README.md">English</a> · <b>한국어</b> · <a href="README.zh-CN.md">简体中文</a> · <a href="README.ja.md">日本語</a>
</p>

# Research Orchestrator

Claude Code, Codex, Google Antigravity에서 쓰는 플러그인으로, 업무 프로젝트·연구·대회 작업이 여러 AI 세션에 걸쳐 끊기지 않고 이어지게 합니다. 스킬, 호스트 훅, `ro` 명령줄 도구, 읽기 전용 리뷰어 에이전트를 함께 제공합니다. 네 개의 Markdown 파일이 설정, 작업 큐, 재사용할 수 있는 발견, 지속되는 인계 기록을 담습니다. 프리셋은 세션이 큐를 나누는 방식, 발견을 검토할 주체, 적용할 근거 검사를 정합니다.

**릴리스 6.0.0 (스킬 설계 v3).** 5.1.0 이후 변경 사항은 [CHANGELOG.md](CHANGELOG.md)에 있습니다. 기존 프로젝트는 그대로 동작하며, 설정을 바꾸기 전에 아래의 마이그레이션 절을 읽으세요.

## 왜 v3인가

이전 설계로 진행한 세 프로젝트의 사후 검토에서 실행은 강했지만 전략은 약했습니다. 세 프로젝트 모두 최종 목표를 볼 수 없는 측정을 믿었고, 핵심 접근법을 시험하지 않은 채 남겼으며, 마지막 구간을 작은 변형에 썼고, 계획을 바꾸지 못한 진단만 기록했습니다. 한 프로젝트는 운영 실수 28건을 기록했고 그중 일부는 서너 번 반복되었으며, 체커 지적은 234건에서 452건으로 늘어난 끝에 더는 읽히지 않았습니다. 6.0.0은 이 교훈을 선택 가능한 워크플로, 결정의 근거가 기록되었는지 확인하는 근거 가드, 그리고 소수의 결정론적 안전 검사로 바꿉니다. 작은 작업에는 가벼운 프리셋이 있고, 자세한 규칙은 해당 작업에 필요할 때만 읽습니다. 같은 흐름으로 데이터 마이그레이션 같은 업무 프로젝트도 명확한 작업 큐와 지속적인 인계를 통해 진행할 수 있습니다.

## 설치

`PATH`에 Python 3.12+(CI로 검증한 최소 버전)가 있어야 합니다. Claude Code 플러그인으로 설치하거나, 체크아웃에서 `python install.py --host claude-code`, `python install.py --host codex`, `--host both` 중 하나를 실행하세요. 스킬 폴더만 복사하면 훅은 설치되지 않습니다.

Windows: Git Bash (`sh`)도 설치해야 합니다.

### Claude Code 플러그인 (권장)

Claude Code 안에서 실행합니다:

```text
/plugin marketplace add TaeyanG4/research-orchestrator
/plugin install research-orchestrator@research-orchestrator
```

GitHub 저장소가 마켓플레이스 역할을 합니다. 플러그인은 훅과 `ro-reviewer` 에이전트를 등록하며, 업데이트는 플러그인 버전을 따릅니다. 설치 후 새 세션을 시작하세요. `ro brief`가 `hooks active`를 보고해야 합니다.

`ro` 심이 없으면 SessionStart와 `ro brief`가 설치된 플러그인에 맞는 정확한 `--shim-only` 명령을 출력합니다. 이 명령은 스킬과 훅을 복사하지 않고 해당 런타임의 `ro` 진입점을 만듭니다.

### Codex

체크아웃 또는 압축을 푼 릴리스에서 실행합니다:

```bash
python install.py --host codex
```

이 명령은 스킬과 훅 설정을 함께 설치합니다. 선택 사항인 Codex 마켓플레이스 플러그인(`codex plugin marketplace add TaeyanG4/research-orchestrator`)은 훅을 등록하지 않습니다. 설치된 훅을 `/hooks`에서 신뢰하세요(버전에 따라 `features.hooks`를 먼저 활성화). 신뢰하기 전까지는 `ro` 명령과 Git pre-push에 의존하세요. [호스트 증거와 신뢰 범위](skills/research-orchestrator/references/hooks-capabilities.md)를 참고하세요.

### 플러그인 없이 설치

```bash
git clone https://github.com/TaeyanG4/research-orchestrator.git
cd research-orchestrator
python install.py --host both
```

`--host`는 `claude-code`, `codex`, `both`(기본값)를 받으며, 기본 범위는 사용자 계정입니다. `--project <dir>`는 대신 프로젝트에 설치하고 공유 디스패처 뒤에 그 프로젝트의 Git pre-push 관문을 등록합니다. 하위 폴더를 지정하면 아무것도 쓰기 전에 거부되므로 저장소 루트를 지정하세요. 프로젝트의 `.claude/`를 커밋하면 Claude Code 설정을 공유할 수 있습니다. Codex 프로젝트 훅은 절대 경로를 쓰므로 체크아웃을 옮긴 뒤에는 다시 설치하세요. 사용자 설치는 저장소마다 관문을 따로 설치해야 합니다.

기타 옵션: `--dry-run`은 변경을 미리 보여 주고, `--uninstall`은 설치 내용을 백업으로 옮기며, `--no-hooks`는 호스트·Git 훅 없이 스킬과 심을 설치하고, `--remove-hooks`는 수동 호스트 훅만 제거하며(스킬, Git 관문, 다른 훅 유지), `--no-shim`은 기본 `ro` 심을 건너뜁니다. 설치기는 다른 훅을 보존하고 교체하는 항목을 백업합니다. Claude Code 플러그인이 활성화되어 있으면 중복된 수동 등록을 제거합니다. 기존 사용자 정의 pre-push 훅은 그대로 두고 [pre-push 예시](hooks/pre-push.sample)를 통합하는 방법을 안내합니다.

### 릴리스와 오프라인 사용

`main`은 최신 안정 버전이고 태그는 `vX.Y.Z` 형식이며, 각 GitHub Release에는 CHANGELOG 내용과 zip 첨부 파일이 있습니다. 오프라인에서는 [GitHub Releases](https://github.com/TaeyanG4/research-orchestrator/releases)의 zip을 풀고 그 폴더에서 같은 `install.py` 명령을 실행하세요. 설치 없이 플러그인을 시험하려면:

```text
claude --plugin-dir <folder>
```

### Google Antigravity

`skills/research-orchestrator/`를 `<project>/.agents/skills/research-orchestrator/` 또는 전역 `~/.gemini/config/skills/research-orchestrator/`에 복사하세요(이전 CLI 위치: `~/.gemini/antigravity-cli/skills/research-orchestrator/`). `/skills`로 인식을 확인합니다. 초기화 과정은 Antigravity 세션을 감지해 호스트로 기록합니다. 설치 대상이나 훅 어댑터는 없으므로 `ro`를 사용하고 [Git pre-push 관문](skills/research-orchestrator/references/publication-safety.md)을 수동으로 설치하세요.

## 프리셋

프리셋은 `agents.md`의 설정 블록을 채우며, 모든 값은 그곳에서 보이고 수정할 수 있습니다. *Profile*은 작업 종류, *workflow*는 세션이 큐를 나누는 방식, *verification*은 발견을 누가 검토해야 하는지입니다.

| 프리셋 | 용도 | Profile | Workflow | Item size | Guards | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| [`quick`](examples/quick-script-cleanup/README.md) | 에이전트 하나의 짧은 작업 | work | classic | short | off | self |
| [`work-project`](examples/work-project-data-migration/README.md) | 며칠에 걸친 이전·분석·구축 | work | unified | staged | light | independent-review |
| [`solo-research`](examples/solo-research-literature-replication/README.md) | 에이전트 하나의 장기 연구 (연구에 권장) | research | unified | staged | light | independent-review |
| [`team-research`](examples/team-research-cv-leakage/README.md) | 여러 세션이나 호스트의 병렬 작업 (5.1.0 방식) | research | classic | short | light | cross-host-once |
| [`competition-solo`](examples/competition-solo-tabular/README.md) | 주로 에이전트 하나가 진행하는 대회 | competition | unified | staged | light | independent-review |
| [`competition-team`](examples/competition-team-forecasting/README.md) | 병렬 세션이나 호스트가 참여하는 대회 | competition | classic | short | light | hybrid |

- **집행:** 모든 프리셋은 `Enforcement: block`과 `Block: shell.background, shell.heredoc, jobs.mutate-bound, publish.scan`을 쓰며, 대회 프리셋은 `external.gate`를 추가합니다.
- **플랫폼:** 단독 프리셋은 감지된 플랫폼 하나에서 실행되고(`Cross-check fallback: same-host`), 팀 프리셋의 기본값은 `Claude Code, Codex`입니다(`wait`).
- **영수증:** `Receipt policy`는 `competition-solo`에서 `self`, 나머지에서 `independent`이며, `independent`에서는 다른 세션이 산출물 영수증에 서명해야 합니다.
- **서브에이전트:** 계획 수집기와 리뷰어는 `off`로 시작하고, 큐 한도는 `stop at 50, resume at 5`입니다.
- **사용자 설정과 저장된 프리셋:** `custom` 또는 프리셋 생략은 새 프로젝트에 가벼운 작업 기본값과 단일 감지 호스트를 사용하며, 기존 프로젝트는 호환 설정을 유지합니다. `--save-preset <name>`으로 저장한 설정은 `--preset user:<name>`으로 재사용합니다.

각 프리셋은 예제 프로젝트로 연결됩니다. [설정, 우선순위, 사용자 프리셋](skills/research-orchestrator/references/presets.md).

## 설정

설치한 뒤 에이전트에게 Research Orchestrator 초기화를 요청하세요. 에이전트는 다음 답을 한꺼번에 모으며, 이미 말한 답은 건너뜁니다.

1. **프리셋**: 위의 여섯 가지 중 하나(`--list-presets`는 저장한 프리셋도 보여 줍니다).
2. **이름**: 이 세션의 사용자로 기록되는 한 단어, 예: `user1`.
3. **남은 프리셋 질문**: 플랫폼, `Environment`, `Language`는 감지 정보와 요청에서 추론하며, 명시된 답이 없고 감지가 실패하거나 모호할 때만 묻습니다. 기본값은 `Info:`로 알립니다(`Language` 기본값은 `en`). 대회 프리셋은 대회와 단계 시계도 필요합니다. Git 동기화는 저장소 안에서만 묻습니다. `quick`은 프리셋과 이름, 저장소 안이면 Git 동기화만 필요합니다.

그다음 에이전트가 초기화 도구를 실행합니다. 초기화 도구는 플래그만 받고 질문하지 않습니다. `<skill-root>`는 `SKILL.md`가 들어 있는 설치 디렉터리입니다. `--answers`는 같은 답을 JSON 객체나 파일로 받으며, 키는 밑줄을 쓴 설정 이름과 `name`, `user`, `agents`, `ordering`입니다. 명시적 플래그가 그 키를 덮어씁니다. 답이 빠지면 오류 메시지가 완전한 예시 명령을 출력합니다.

```text
python <skill-root>/scripts/init_research_orchestrator.py --list-presets
python <skill-root>/scripts/init_research_orchestrator.py . -n "<project>" --preset work-project --user <user> --platforms "<host>" --environment linux/bash --language en
python <skill-root>/scripts/init_research_orchestrator.py . --answers answers.json
python <skill-root>/scripts/check_project.py .
```

<p align="center">
  <img src="assets/readme/setup-flow.svg" alt="설정: 프리셋, 이름, 해결되지 않은 질문만 확인. 감지한 기본값을 보고하고 네 조정 파일과 .ro/template-render.json 생성." width="100%">
</p>

| 파일 | 담는 내용 |
| --- | --- |
| `agents.md` | 프리셋 요약, 설정, 읽기 안내, 사용자가 소유하는 `## Project rules` 영역(상시 규칙, 만료되는 예외, 한 줄 교훈) |
| `plan.md` | 끝나지 않은 항목만; 끝난 항목은 큐에서 빠집니다 |
| `discoveries.md` | 근거와 검토 상태를 갖춘 재사용 가능한 발견 |
| `handoff.md` | 공유 상태, 이벤트 기록, 외부 행동, 각 슬롯의 재개 지점 |

초기화 도구는 네 조정 파일을 쓰고 렌더링 메타데이터를 `.ro/`에 저장합니다. `Language`는 자유 텍스트에만 적용됩니다. 제목, 필드명, ID, 상태 단어, 검사 ID, 설정 키는 체커·훅·`ro`가 동작하도록 영어를 유지합니다.

**새 세션.** 명시한 슬롯이나 계속/병렬 의도는 그대로 따르고, 오래되지 않은 적격 슬롯이 하나뿐이면 자동으로 맡습니다. 그 밖의 경우 SessionStart와 `ro brief`가 후보마다 소유자, 마지막 활동, 실행 중인 작업을 보여 주고, 에이전트는 질문 하나를 묻습니다: 슬롯 계속하기(세션이 끝났으면 회수), 병렬 슬롯 시작, 지정한 슬롯 사용. 점유된 슬롯은 보호된 작업이 없고 `Stale slot after`(기본 `2h`) 안에 이벤트나 점유가 없을 때 오래된 것으로 봅니다. 회수는 기록되며 점유, 재개 상태, 작업을 유지합니다. `Autonomy: away`에서는 묻지 않고 새 병렬 슬롯을 시작하며 나중에 결정할 수 있도록 그 선택을 기록합니다. [세션](skills/research-orchestrator/references/sessions.md).

## 워크플로

슬롯(`A`, `B`, … `AA`)은 도구나 사람이 아니라 작업 줄기의 이름이므로, 어떤 호스트든 슬롯을 이어받을 수 있습니다.

<p align="center">
  <img src="assets/readme/workflows.svg" alt="Classic: 각 슬롯이 plan.md의 Agent 섹션을 소유하고 항목은 기록된 인수로만 소유자가 바뀝니다. Unified: 공유 Queue 하나에서 각 항목이 Claimed 줄을 갖고 ro claim이 잠그고 다시 읽은 뒤 점유를 기록합니다" width="100%">
</p>

### Classic

각 슬롯은 `plan.md`의 `## Agent: <slot>` 섹션 하나를 소유하고 자기 섹션의 세부 내용만 읽습니다. 중복 확인, 배분, 인수는 좁은 메타데이터만 읽습니다. 항목의 소유자는 기록된 인수로만 바뀌고, 다른 호스트가 큐에 넣은 항목은 보통 그 호스트에 남습니다. 이것이 5.1.0의 동작이며, `Workflow` 줄이 없는 프로젝트의 기본값입니다. [Classic 워크플로](skills/research-orchestrator/references/workflow-classic.md). [다른 호스트의 한 항목 인수 예외](skills/research-orchestrator/references/workflow-classic.md#cross-host-take-over-by-judgment)는 원래 호스트가 유휴 상태이고 가까운 작업을 소진했으며 문서의 적격 조건을 충족할 때 적용됩니다.

### Unified

`## Queue` 하나가 모든 항목을 담고, 각 항목은 `Claimed: none` 또는 `Claimed: <slot> since <time>`으로 시작합니다. `ro claim`은 프로젝트 잠금을 잡고 큐를 다시 읽은 뒤 점유를 기록하므로, 두 슬롯이 같은 항목을 점유할 수 없습니다. 점유되지 않은 항목은 누구나 다듬을 수 있지만, 다른 활성 슬롯이 점유한 항목은 아무도 수정하지 않습니다. [Unified 워크플로](skills/research-orchestrator/references/workflow-unified.md).

두 워크플로 모두에서 `Item size: staged`이면 긴 항목이 `Stages:`를 선언하고 단계 이벤트를 남길 수 있습니다. `Important stages:`에 지정한 단계는 정확한 `:before` 범위의 독립 영수증이 있어야만 시작되며, `Receipt policy: self`에서도 마찬가지입니다. 결정을 바꾼 단계는 `Decision: changed`를 담은 자체 날짜 이벤트와 발견을 남기고, 그 항목을 다음에 시작하기 전에 독립 `:after` 영수증을 받아야 합니다. [단계 항목](skills/research-orchestrator/references/staged-items.md).

`Workflow`를 바꾸면 항목이 이동하므로 `--reconfigure --migrate`가 필요합니다.

## 항목 수명 주기

<p align="center">
  <img src="assets/readme/lifecycle.svg" alt="항목 수명 주기: 점유하거나 소유하고, 작업하고, 발견과 이벤트를 기록하고, 후속 항목을 도출한 뒤 plan.md에서 항목을 지워 닫습니다" width="100%">
</p>

1. **점유 또는 소유**: 중복 확인(`ro dupcheck`) 후 워크플로에 따라 항목을 맡습니다.
2. **작업**: 다음에 할 만한 시험을 실행합니다. 긴 작업은 `ro launch`와 `ro monitor`로 다루며, 시작이 확인되었다고 결과가 나온 것은 아닙니다.
3. **발견**: 부정적이거나 결론이 나지 않은 결과까지 `discoveries.md`에 기록합니다. 검토는 `Verification` 설정을 따릅니다: `self`(검토 불필요), `cross-host-once`(다른 호스트가 한 번), `independent-review`(서브에이전트 같은 다른 세션), `hybrid`(둘 중 하나).
4. **이벤트**: 발견을 가리키는 이벤트를 `handoff.md`에 추가합니다.
5. **후속 항목**: 결과가 시사하는 항목을 큐에 넣거나, 아무것도 이어지지 않는 이유를 기록합니다.
6. **닫기**: 끝난 항목을 `plan.md`에서 지웁니다. 발견, 이벤트, 후속 항목, 삭제를 함께 마친 뒤 다른 일을 시작합니다.

프로젝트 종료 후 [사후 검토](skills/research-orchestrator/references/postmortem.md)로 교훈을 기록합니다. 호스트 한도나 429/503 오류에는 [새 세션 재시도 규칙](skills/research-orchestrator/references/compute.md)을 적용합니다.

`cross-host-once`에서는 다른 슬롯이 필요합니다. 같은 호스트의 검토는 single 모드, 또는 `Cross-check fallback: same-host`인 adaptive 모드에서 인정됩니다. 적격 리뷰어를 실행할 수 없으면 발견을 `PENDING`으로 두고, 폴링 없이 인계와 닫기를 완료합니다.

work 프로필(`quick`, `work-project`)은 더 가볍습니다. 점수와 Priority는 선택 사항이라 큐 순서나 `Next:` 줄이 순서를 정합니다. 발견은 재사용할 결과(확정된 결정, 막다른 길, 검증된 의존성)만 남기고, 세션 이벤트 하나가 끝난 항목을 나열합니다. research와 competition은 항목마다 전체 기록을 유지합니다. [항목 필드와 후속 항목](skills/research-orchestrator/references/plan-items.md), [기록](skills/research-orchestrator/references/records.md), [검증](skills/research-orchestrator/references/verification.md), [세션](skills/research-orchestrator/references/sessions.md).

`solo-research`는 `Ordering: queue`를 생성합니다. 다른 연구·대회 프로젝트도 이를 선택할 수 있으며, 입력한 점수는 계속 검증합니다.

## 가드

가드는 결정의 근거가 기록되었는지 확인할 뿐, 그 품질을 판단하지 않습니다. `Guards: light`는 빈틈을 경고로 알리고, `strict`는 각 가드가 지정한 검사를 오류로 바꾸며, `off`는 가드를 끕니다. 활성화에는 날짜가 붙으므로(`light since YYYY-MM-DD`) 그 이전 기록은 면제됩니다. 가드는 Shared state에서 한 번 `not applicable — <reason>`으로 선언할 수 있고, 임곗값은 설정할 수 있습니다. 선택적인 discovery `Control`은 위약·잡음 바닥 근거 파일과 선택 이득을 기록합니다. Control 누락은 예외로, `guard.control.missing`이 light 모드에서는 INFO, strict 모드에서는 WARN입니다.

| 가드 | 요구하는 것 | `Guard set: auto`가 켜는 대상 |
| --- | --- | --- |
| G1 Instrument evidence | 발견을 결정한 측정의 출처, 범위, 일치도, 분해능 | research, competition |
| G3 Family saturation | 한 계열에서 동률이 반복된 뒤 더 분해능 높은 측정이나 검토된 구조 변경 | competition |
| G5 Overrides and rejections | 각 예외의 재확인 조건과 만료일; 기각한 변경이 실제로 실행되었다는 증거 | 모든 프로필 |
| G6 Insights | 진단마다 기한, 그 뒤 계획된 항목이나 근거 있는 기각 | 모든 프로필 |
| GD Direction review | 격차와 결정의 주기적 검토(research와 competition은 더 자세히) | 모든 프로필 |
| G8 Phase clock | `Phase clock` 기간 안의 이정표 | competition |
| G11 Selection | 같은 계열을 공유하는 이유가 설명된 최종 선택 | competition |
| G12 Effort | 결과를 바꿀 수 있는 작업 대비 절차 작업의 비중 | 명시적으로 켤 때만 |
| E1 External actions | 외부 행동 전에 쓴 기대치, 산출물 해시, 표시 없는 중복 없음 | 모든 프로필 |

[연구 가드](skills/research-orchestrator/references/research-guards.md), [결정 가드](skills/research-orchestrator/references/decision-guards.md), [외부 행동](skills/research-orchestrator/references/external-actions.md), [competition 프로필](skills/research-orchestrator/references/competition.md).

## `ro` CLI

`ro`는 `python <skill-root>/scripts/ro.py`를 뜻합니다. 명령이 기준이며 모든 호스트에서 동작하고, 훅은 그 명령을 더 일찍 실행할 뿐입니다. 전역 옵션은 `--project`, `--slot`, `--session`이고, 각 명령에는 `--help`가 있습니다.

| 명령 | 용도 |
| --- | --- |
| `next-id {D,H,I,X,N}` | 다음 발견, 계획 항목, 측정 도구, 외부 행동, 메모 ID 예약 |
| `dupcheck <terms>` | 작업을 추가하기 전에 보관된 기록을 포함해 제목과 핵심 줄 검색 |
| `index [ID]` | 발견 색인, 또는 항목 하나의 전체 내용 출력 |
| `claim <item>`, `release <item>` | 프로젝트 잠금 아래 unified 큐 항목 점유, 또는 해제 |
| `launch --item … --expect … -- <command>` | 묶인 입력과 출력, 오류 패턴, 하트비트, 확인 구간, 선택적 `--require-receipt`를 갖춘 소유 작업 시작 |
| `monitor <job>`, `jobs [--prune]`, `kill <job>` | 작업을 결과까지 추적, 작업과 모니터 상태 나열, 신원을 확인한 소유 프로세스 트리 중지 |
| `receipt add`, `receipt check` | `Receipt policy`에 따라 PASS 또는 FAIL 판정을 산출물의 SHA256에 묶기, 또는 확인 |
| `external --action <X-id> -- <command>` | 기록부, 영수증, 중복, 시도 이력 검사를 통과한 경우에만 외부 명령 실행 |
| `observe <key> <value>` | 변동성 Shared state 사실 기록; `--source`는 선택 사항, `--ttl` 기본값은 `6h` |
| `brief [--max N]` | 사실만 담은 세션 요약: 설정, 훅 자체 시험, 슬롯 선택, 점유, 작업, 기한 지난 가드, 체커 건수 |
| `close` | 실행 중이거나 모니터되지 않은 작업의 점유는 유지하고 나머지는 해제한 뒤 체커 실행 및 잔여 사항 보고 |
| `hook <event>` | 호스트 훅은 표준 입력 JSON을, `pre-push`는 Git 참조 갱신 행을 받음 |
| `check <command>` | 명령 문자열에 셸 검사 실행(`--dialect bash` 또는 `powershell`) |

작업은 소유한 프로세스 그룹(Windows에서는 작업 개체)에서 실행됩니다. 작업자가 계속 도는 동안 실행기가 끝나도 바인딩과 점유는 유지되고, 실패한 실행기는 하위 프로세스가 살아 있거나 확인되지 않은 동안 슬롯을 유지합니다. `ro kill`은 슬롯 소유권, PID, 시작 시각을 확인하므로 재사용된 PID를 대상으로 삼지 않습니다. `ro external`은 실행 전에 시도를 저널에 기록하고 그 이력을 산출물 해시와 목적지로 대조하므로, 기록부 항목을 수정·철회·개명해도 이전 시도를 숨길 수 없습니다. 중단되거나 시간이 초과된 행동은 조정될 때까지 `unknown`으로 남습니다.

[운영 명령과 그 한계](skills/research-orchestrator/references/operations-safety.md), [외부 행동과 영수증](skills/research-orchestrator/references/external-actions.md).

## 호스트별 안전

Codex 훅에 의존하기 전에 `/hooks`에서 신뢰를 설정하세요. `ro` 명령과 Git pre-push가 실행 관문입니다.

<p align="center">
  <img src="assets/readme/safety-layers.svg" alt="훅, ro 명령, Git pre-push. 링크된 호스트 기능 증거를 참고하세요." width="100%">
</p>

| 호스트 | 호출별 훅 | 실행을 막는 장치 |
| --- | --- | --- |
| Claude Code | 플러그인 훅 또는 `install.py --host claude-code` | `ro`, Git pre-push |
| Codex | `install.py --host codex`; 훅 신뢰 필요 | `ro`, Git pre-push |
| Google Antigravity | 없음; 명령만 사용 | `ro` 명령과 Git pre-push 공개 검사 |

- `Enforcement: off`는 아무것도 출력하지 않고, `warn`은 막지 않으며, `block`은 `Block`에 나열된 검사만 거부합니다.
- **각 셸 호출은 해당 도구의 방언(Bash 또는 PowerShell)으로 파싱합니다.** `Environment`와 달라도 마찬가지이며, `Environment`는 경로 규칙과 대체 셸을 정합니다. 불확실한 파싱은 경고만 하고 막지 않습니다.
- 호출별 훅은 충돌, 시간 초과, 잘못된 입력, 인터프리터 부재 시 통과시키며, `ro brief`가 훅 자체 시험과 경고 건수를 보고합니다. `ro external`, `ro launch`, Git pre-push 관문은 검증이 실패하거나 실행될 수 없으면 거부하며, pre-push는 메시지와 경로를 포함해 나가는 모든 커밋을 검사합니다.
- 훅은 협조하는 세션의 사고를 막을 뿐, 적대적 공격에 대한 보안 경계가 아닙니다. 중첩된 인터프리터 본문, here-string 본문, 별칭, 동적 경로, 인코딩된 비밀은 신뢰할 수 있는 파싱 범위 밖입니다.

Claude Code 플러그인에서는 SessionStart가 플러그인 매처가 다루지 않는 선택 검사를 알려 주고 이를 구독할 `install.py --project .`를 출력합니다. Git 체크아웃에 pre-push 관문이 없으면 SessionStart와 `ro brief`가 설치 명령과 함께 `publish gate not installed`도 보고합니다. 래퍼는 Python을 시작하기 전에 `agents.md`를 찾으므로 프로젝트 밖의 호출에는 인터프리터가 필요 없습니다. 작업 레지스트리가 없으면 Stop과 편집 검사는 Python을 생략하고, 변경 없는 PostToolUse 호출은 파일 스탬프로 생략하며, 변경 없는 압축은 체커 요약을 재사용합니다. Windows에서 측정한 호출당 p95는 프로젝트 밖과 작업 없는 Stop·편집에서 23–36 ms, 일반 셸 검사와 변경 없는 PostToolUse에서 48–125 ms로 150 ms 예산 안입니다.

[훅, 기능 표, 신뢰](skills/research-orchestrator/references/hooks-capabilities.md), [공개 관문](skills/research-orchestrator/references/publication-safety.md).

## 5.1.0에서 마이그레이션

설치된 플러그인을 업데이트해도 기존 프로젝트는 다시 쓰이지 않습니다. 없는 설정은 5.1.0 동작(classic 워크플로, short 항목, cross-host-once 검증, 가드 끔)을 유지합니다. 수동 설치는 두 사본을 함께 두지 말고 이전 스킬 폴더를 `research-orchestrator`로 교체하세요. 이름 변경은 CHANGELOG를 참고하세요.

5.1.0에서 인정된 `multi`/`same-host` 리뷰는 계속 유효합니다. 재설정은 해당 리뷰의 지문을 `agents.md`에 보존하며, 새 리뷰에는 현재 검증 규칙을 적용합니다.

1. 네 파일과 `.ro/` 상태의 복구 가능한 사본을 저장하고, 체커를 실행해 구조 오류를 고치세요.
2. `agents.md`의 생성된 부분에 직접 쓴 지침을 `## Project rules`로 옮기세요. 재구성은 이 영역을 그대로 보존합니다.
3. 생성된 설정과 읽기 안내를 새로 고칩니다. 프리셋을 쓰려면 `--preset <preset>`과 그 답을 추가하세요. 두 번째 명령은 classic 프로젝트를 unified 워크플로로 바꿉니다.

```text
python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure
python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure --workflow unified --migrate --user <user>
```

4. `Workflow`를 바꾸려면 `--migrate`도 필요하며, 먼저 활성 슬롯을 해제하세요. 워크플로 마이그레이션은 `*.pre-migrate` 백업과 복구 저널을 남기지만, 설정만 바꾸는 재구성은 남기지 않습니다.
5. 결과를 확인하고 체커를 다시 실행한 뒤 변경을 인계 이벤트로 기록하세요.

워크플로를 바꾸거나 `--force`를 쓰기 전에 [마이그레이션과 롤백 절차](skills/research-orchestrator/references/migration-v2-to-v3.md)를 읽으세요.

## 검증과 CI

프로젝트에서는 세션 시작 시, 인수나 마이그레이션 뒤, 닫기 전에 `python <skill-root>/scripts/check_project.py .`를 실행하세요(`ro close`도 실행합니다). ERROR는 종료 코드 1, WARN은 `--strict`일 때만 실패, INFO는 조언이며, 종료 코드 2는 프로젝트를 읽을 수 없다는 뜻입니다. `--baseline-update`는 지적의 지문을 저장해, 이후 실행이 기존 지적을 숨기지 않고 새 지적을 추가로 표시합니다.

이 저장소에서는 pytest를 설치한 뒤 가벼운 구조 검사, 결정론적 테스트, 전체 릴리스 검사 중 필요한 것을 실행하세요.

```bash
python scripts/validate_release.py --skip-tests
python -m pytest -q -m "not latency"
python scripts/validate_release.py
```

가벼운 검사는 매니페스트 버전, README 구조와 링크, SVG 유효성, 코어와 참고 문서의 크기 예산, 분야 어휘, 기록 형식, 예제 프로젝트를 확인합니다. 릴리스 검사는 증거 ZIP 내부 항목을 포함한 `docs/`에서 비공개 경로, 계정 이름, 네이티브 식별자, 내부 세션 패턴을 검사합니다. 전체 검사는 결정론적 테스트 모음과 초기화·재구성 시나리오를 더합니다. 시간 측정 테스트에는 `latency` 표지가 붙어 있으며 `python -m pytest -q -m latency`로 따로 실행합니다.

GitHub Actions는 Windows, Ubuntu, macOS에서 Python 3.12와 읽기 전용 권한으로 전체 검사를 실행한 뒤, OS마다 설치된 훅의 p95를 측정해 아티팩트로 보관합니다. 행동 사례, 트리거 평가, 설치된 호스트 시험 실행을 위한 개발 도구는 [scripts/evals](scripts/evals/README.md), [scripts/trigger](scripts/trigger/README.md), `scripts/host/`에 있습니다.

## 근거

행동 근거는 과거 기록(이번 릴리스 그대로가 아닌 저장된 실행)이고, Codex 훅은 호출별 신뢰로만 검증되었으며, Windows 시간 측정은 로컬 결과이고, CI 결과는 공개 전까지 대기 중입니다. [근거와 한계](docs/evals/README.md)를 확인하세요.

## 라이선스

[MIT](LICENSE).
