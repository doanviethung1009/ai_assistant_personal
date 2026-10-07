# Codex Operating Guide

> Repository operating guide for OpenAI Codex CLI.
>
> This document describes how Codex should discover project context, load instructions, select skills, inspect documentation, execute commands, modify code, validate changes, and handle risky operations.
>
> `AGENTS.md` remains the primary repository instruction entry point.

---

# 1. Purpose

This repository is designed to work with OpenAI Codex CLI as an autonomous coding agent.

Codex should use the following context hierarchy:

```text
Runtime / platform instructions
        ↓
Global Codex configuration
        ↓
Global AGENTS.md
        ↓
Repository AGENTS.md
        ↓
Nested AGENTS.md / AGENTS.override.md
        ↓
Relevant repository skills
        ↓
Relevant project documentation
        ↓
Current source code and configuration
        ↓
User task
```

Use progressive context loading:

```text
Always load:
    AGENTS.md

Discover:
    Skills metadata

Load when relevant:
    SKILL.md
    references/*
    docs/*.md

Inspect when needed:
    source code
    configuration
    tests
    Git history
    logs
```

---

# 2. Repository Context Model

The project separates agent context into four categories.

## 2.1 AGENTS.md — Mandatory project rules

Purpose:

```text
WHAT MUST ALWAYS BE TRUE
```

Typical content:

- repository-wide behavior
- coding standards
- safety requirements
- documentation routing
- skill routing
- validation expectations
- destructive-operation restrictions

Keep `AGENTS.md` concise.

Do not use `AGENTS.md` as a complete project knowledge base.

---

## 2.2 Skills — Reusable workflows

Recommended location:

```text
.agents/skills/
```

Purpose:

```text
HOW TO PERFORM A SPECIFIC TYPE OF TASK
```

Example:

```text
.agents/skills/
├── postgres-cdc/
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
├── mysql-cdc/
│   └── SKILL.md
├── database-change/
│   └── SKILL.md
├── code-review/
│   └── SKILL.md
├── debugging/
│   └── SKILL.md
└── release/
    └── SKILL.md
```

Each skill should include front matter:

```yaml
---
name: skill-name
description: Clearly describe when Codex should and should not use this skill.
---
```

Example:

```yaml
---
name: postgres-cdc
description: Use for PostgreSQL logical replication, Debezium CDC, publications, replication slots, WAL configuration, CDC privileges, and replication troubleshooting.
---
```

The description is critical because Codex can use it to determine whether the skill matches the current task.

---

# 3. Skill Loading Behavior

Codex should use progressive disclosure.

At startup, Codex should primarily discover:

```text
skill name
skill description
skill path
```

It should not read every full `SKILL.md` immediately.

When the task matches a skill:

```text
Task
 ↓
Match skill description
 ↓
Read SKILL.md
 ↓
Follow skill instructions
 ↓
Read references only when required
 ↓
Run skill scripts only when required
```

Example:

```text
User:
"Add these tables to PostgreSQL Debezium CDC"

Codex:
    ↓
detect PostgreSQL + Debezium + CDC
    ↓
select postgres-cdc skill
    ↓
read .agents/skills/postgres-cdc/SKILL.md
    ↓
read relevant references
    ↓
inspect current DB/CDC configuration
    ↓
produce or execute the required change
    ↓
verify publication / privileges / slot state
```

Explicit skill invocation can also be used when supported by the installed client.

Example:

```text
$postgres-cdc
```

Do not assume every skill must be invoked explicitly.

Implicit invocation is preferred when the description clearly matches the task.

---

# 4. Project Documentation

Normal Markdown documentation is project knowledge, not automatic instructions.

Example structure:

```text
docs/
├── architecture.md
├── database.md
├── cdc.md
├── deployment.md
├── api.md
├── security.md
├── conventions.md
└── troubleshooting.md
```

Codex should read documentation only when relevant.

Recommended routing:

```text
Architecture work
    → docs/architecture.md

Database/schema work
    → docs/database.md

CDC/Debezium work
    → docs/cdc.md

Deployment / CI/CD work
    → docs/deployment.md

API integration
    → docs/api.md

Security-sensitive changes
    → docs/security.md

Project conventions
    → docs/conventions.md

Incident/debugging
    → docs/troubleshooting.md
```

Do not read all documentation at session startup unless explicitly required.

---

# 5. AGENTS.md Discovery and Precedence

Codex can receive instructions from multiple `AGENTS.md` files.

Typical hierarchy:

```text
~/.codex/AGENTS.md

repository/
├── AGENTS.md
├── apps/
│   └── web/
│       └── AGENTS.md
└── packages/
    └── database/
        └── AGENTS.md
```

If Codex is launched from:

```bash
cd repository/apps/web
codex
```

the effective instruction order is conceptually:

```text
~/.codex/AGENTS.md
        ↓
repository/AGENTS.md
        ↓
repository/apps/web/AGENTS.md
```

Instructions closer to the working directory are more specific.

Use:

```text
AGENTS.override.md
```

when a directory needs to override the normal instructions for that scope.

Do not duplicate repository-wide rules into every nested `AGENTS.md`.

---

# 6. Alternate Instruction Files

Do not assume arbitrary Markdown files automatically become Codex instructions.

If the repository already has alternative instruction filenames, configure fallback filenames only when needed.

Recommended policy:

```text
AGENTS.md
```

should remain the canonical project instruction file.

Other agent files should adapt to it instead of creating separate conflicting rule sets.

---

# 7. Recommended Repository Structure

```text
repository/
│
├── AGENTS.md
│
├── docs/
│   ├── CODEX_OPERATING_GUIDE.md
│   ├── architecture.md
│   ├── database.md
│   ├── cdc.md
│   ├── deployment.md
│   └── troubleshooting.md
│
├── .agents/
│   └── skills/
│       ├── database-change/
│       │   └── SKILL.md
│       ├── postgres-cdc/
│       │   └── SKILL.md
│       ├── mysql-cdc/
│       │   └── SKILL.md
│       ├── debugging/
│       │   └── SKILL.md
│       └── code-review/
│           └── SKILL.md
│
├── .codex/
│   ├── config.toml
│   └── rules/
│       └── default.rules
│
├── apps/
│   └── web/
│       └── AGENTS.md
│
└── packages/
```

Responsibilities:

```text
AGENTS.md
    → mandatory behavior

docs/
    → project knowledge

.agents/skills/
    → reusable workflows

.codex/config.toml
    → Codex runtime configuration

.codex/rules/
    → shell command execution policy
```

---

# 8. Codex Startup Procedure

When starting a Codex session in this repository:

```text
1. Detect repository root.
2. Load applicable AGENTS.md instructions.
3. Discover available skills.
4. Understand the user request.
5. Inspect repository structure.
6. Identify the relevant module/service.
7. Load only relevant documentation.
8. Activate relevant skills.
9. Inspect existing implementation.
10. Determine validation commands.
11. Make the smallest appropriate change.
12. Run validation.
13. Review the final diff.
14. Report:
    - what changed
    - why
    - validation performed
    - unresolved issues
```

---

# 9. Interactive Codex CLI

Start Codex:

```bash
cd <repository>
codex
```

Check available CLI commands:

```bash
codex --help
```

Inside the interactive composer, type:

```text
/
```

to inspect slash commands supported by the installed client/version.

The installed version is the runtime source of truth.

---

# 10. Common Interactive Commands

Available slash commands can change by version. Verify them at runtime by typing `/`.

Commonly useful commands include:

```text
/init
/status
/compact
/model
/reasoning
/plan
/review
/mcp
/fork
/worktree
```

## `/init`

Use for initial repository agent setup and generating an `AGENTS.md` scaffold.

Do not blindly overwrite a maintained `AGENTS.md`.

## `/status`

Inspect current session state, context usage, workspace information, or related status.

## `/compact`

Compress a long session when the objective remains the same.

Permanent project knowledge should be written into repository files rather than relying only on chat context.

## `/model`

Select a model when model selection is supported.

Use stronger reasoning for:

- architecture
- complex debugging
- large refactors
- database incident analysis
- security-sensitive changes
- cross-service changes

## `/reasoning`

Select reasoning effort where supported.

## `/plan`

Use planning mode for:

- multi-module changes
- large refactors
- schema migrations
- production-impacting work
- complex bugs
- architecture changes

A plan should identify:

```text
scope
affected files
dependencies
risks
validation
rollback strategy
```

## `/review`

Use review mode after implementation or when auditing existing changes.

Focus on:

```text
correctness
regressions
security
data integrity
concurrency
backward compatibility
error handling
tests
performance
operational risk
```

## `/mcp`

Inspect connected MCP servers and tools when supported.

Never assume an integration exists without checking.

## `/fork`

Use a separate session when a new objective diverges significantly from the current one.

## `/worktree`

Use an isolated Git worktree when supported for:

- parallel agent tasks
- experiments
- large refactors
- work that should not disturb the current working tree

---

# 11. Skill Invocation

When the installed client supports skill completion, use:

```text
$skill-name
```

Example:

```text
$postgres-cdc
```

Example prompt:

```text
Use $postgres-cdc to inspect the current publication and determine the safest SQL required to add these tables.
```

When no explicit skill is provided, Codex should still activate matching skills based on their descriptions.

---

# 12. Non-Interactive Codex

For scripts, CI, automation, or one-shot analysis:

```bash
codex exec "<task>"
```

Example:

```bash
codex exec "Analyze this repository and list architectural risks."
```

Use non-interactive execution for deterministic automation workflows.

---

# 13. Structured and Machine-Readable Output

When supported by the installed version:

```bash
codex exec --json "Analyze the repository"
```

Useful for:

```text
CI
automation
logging
agent orchestration
post-processing
```

Structured output should be preferred when another tool consumes Codex results.

---

# 14. Ephemeral Runs

When supported:

```bash
codex exec --ephemeral "<task>"
```

Use ephemeral runs for temporary analysis jobs that should not persist session state.

---

# 15. Sandbox Modes

Follow least privilege.

Conceptually:

```text
read-only analysis
    → read-only/default sandbox

repository modifications
    → workspace-write

broad machine access
    → danger-full-access only in controlled environments
```

Example controlled environments:

```text
isolated container
ephemeral CI runner
dedicated development VM
```

Never make broad unrestricted access the normal project default.

Verify the exact sandbox flags with:

```bash
codex --help
codex exec --help
```

---

# 16. Resume a Session

When supported by the installed version, resume only when the new task genuinely depends on previous context.

For unrelated work, start a new execution or session.

Verify exact syntax with:

```bash
codex exec --help
```

---

# 17. Pipe Logs or Diffs Into Codex

Examples:

```bash
npm test 2>&1 | codex exec "Analyze these failing tests and identify the likely root cause."
```

```bash
tail -n 500 app.log | codex exec "Analyze this log and rank the likely root causes."
```

```bash
git diff | codex exec "Review this diff for correctness and regressions."
```

DBA example:

```bash
cat postgres.log | codex exec "Analyze PostgreSQL errors and rank likely root causes."
```

---

# 18. Codex Rules vs AGENTS.md

Do not confuse:

```text
AGENTS.md
```

with:

```text
.codex/rules/*.rules
```

They solve different problems.

`AGENTS.md` controls:

```text
agent behavior
coding conventions
workflow
project expectations
validation requirements
documentation routing
skill routing
```

`.codex/rules` controls shell execution policy where supported.

Examples of actions that should usually require approval or explicit policy:

```text
git push
git reset --hard
git clean -fd
rm -rf
DROP DATABASE
DROP TABLE
TRUNCATE
kubectl delete
terraform destroy
production deployment
credential changes
```

Use runtime sandboxing and execution policy as technical enforcement.

---

# 19. Safety Policy

Codex should distinguish between:

```text
analysis
local development change
external side effect
production operation
destructive operation
```

Read-only inspection is normally lower risk:

```text
ls
find
rg
cat
git status
git diff
git log
SELECT
EXPLAIN
SHOW
DESCRIBE
```

Higher-risk examples:

```text
push repository
merge PR
deploy application
change cloud resources
modify production databases
restart production services
delete infrastructure
rotate credentials
change IAM permissions
```

For destructive or production-impacting changes:

```text
1. Inspect first.
2. Explain the impact.
3. Show the proposed command or change.
4. Provide rollback or recovery strategy where possible.
5. Require explicit authorization when appropriate.
6. Verify the result after execution.
```

---

# 20. Database Safety

Before modifying a database:

```text
identify engine
identify version
identify environment
identify database/schema
inspect current state
evaluate locks
evaluate replication/CDC impact
evaluate rollback
```

For DDL:

```text
check table size
check locking behavior
check online/in-place support
check expected duration
check replica impact
check application compatibility
```

For CDC:

```text
verify WAL/binlog prerequisites
verify publication
verify replication slot
verify privileges
verify table identity / primary key
verify connector configuration
verify retention risk
```

Never drop or recreate a replication slot without evaluating retained WAL/binlog and consumer position.

Never perform destructive production SQL merely because the generated SQL is syntactically valid.

---

# 21. Code Modification Workflow

Default workflow:

```text
UNDERSTAND
    ↓
INSPECT
    ↓
PLAN
    ↓
IMPLEMENT
    ↓
VERIFY
    ↓
REVIEW
    ↓
REPORT
```

Detailed behavior:

```text
UNDERSTAND
- determine user intent
- determine success criteria

INSPECT
- inspect relevant files
- inspect adjacent implementation
- inspect tests
- inspect configuration

PLAN
- identify minimal changes
- identify risk
- identify validation

IMPLEMENT
- preserve existing architecture
- avoid unrelated cleanup
- make focused changes

VERIFY
- lint
- typecheck
- unit tests
- integration tests
- build
- targeted runtime checks

REVIEW
- inspect git diff
- look for accidental changes
- check regressions

REPORT
- summarize changes
- state validation results
- mention unresolved risks
```

---

# 22. Minimal Diff Principle

Prefer the smallest change that correctly solves the task.

Do not unnecessarily:

```text
rewrite unrelated modules
rename unrelated symbols
upgrade dependencies
reformat entire files
perform opportunistic refactors
change public APIs
```

Focused diffs are easier to review, test, rollback, debug, and merge.

---

# 23. Inspect Before Changing

Before assuming code is wrong:

```text
inspect implementation
inspect caller
inspect tests
inspect configuration
inspect recent Git history if relevant
```

Do not replace existing patterns merely because another approach appears cleaner.

Follow established repository architecture unless there is a concrete reason to change it.

---

# 24. Validation Discovery

Discover repository-native validation commands from files such as:

```text
package.json
Makefile
justfile
pyproject.toml
Cargo.toml
go.mod
pom.xml
build.gradle
docker-compose.yml
.github/workflows/*
```

Prefer repository-defined commands.

Examples:

```bash
npm run lint
npm run typecheck
npm test
npm run build
pnpm lint
pnpm test
pytest
go test ./...
cargo test
```

Do not invent validation commands without checking the repository.

---

# 25. Final Diff Review

After code modification:

```bash
git status
git diff
```

Check for:

```text
unexpected files
debug output
temporary files
generated secrets
formatting-only noise
unrelated modifications
missed tests
accidental configuration changes
```

Codex should review its own changes before declaring completion.

---

# 26. Secrets and Credentials

Never write secrets into:

```text
source code
AGENTS.md
SKILL.md
documentation
logs
Git history
example configuration
```

Sensitive values include:

```text
API keys
database passwords
private keys
access tokens
AWS credentials
cloud credentials
session tokens
production connection strings
```

Prefer:

```text
environment variables
secret managers
secure CI secrets
credential stores
```

---

# 27. Context Management

Recommended behavior:

```text
same objective + large context
    → compact

different objective
    → new session / fork

project knowledge needed repeatedly
    → document it

repeatable workflow
    → create a skill

mandatory behavior
    → put it in AGENTS.md
```

Do not rely on chat history as permanent project documentation.

---

# 28. Context Routing Decision

```text
Is this rule always applicable?
    YES → AGENTS.md

Is this a repeatable workflow?
    YES → SKILL.md

Is this project knowledge?
    YES → docs/*.md

Is this deterministic executable logic?
    YES → skill scripts/

Is this shell execution permission?
    YES → .codex/rules/

Is this Codex runtime configuration?
    YES → .codex/config.toml
```

---

# 29. When to Create a Skill

Create a skill when a workflow:

```text
happens repeatedly
requires multiple ordered steps
has domain-specific validation
has known failure modes
requires specific references
benefits from reusable scripts
```

Good candidates:

```text
PostgreSQL CDC management
MySQL/MariaDB CDC management
database migrations
incident analysis
log analysis
API integration
release verification
code review
security review
deployment
```

Do not create a skill for a simple one-line coding preference.

---

# 30. Skill Quality Requirements

Each skill should define:

```text
when it applies
when it does not apply
required inputs
inspection steps
implementation steps
validation
failure handling
output expectations
risk boundaries
```

Avoid weak descriptions such as:

```text
Helps with databases.
```

Prefer:

```text
Use for PostgreSQL schema changes, indexes, migrations,
locking analysis, query-plan validation and rollback planning.
Do not use for MongoDB or application-only changes.
```

---

# 31. Agent Configuration Audit

When asked to improve Codex configuration, inspect:

```text
AGENTS.md
nested AGENTS.md
AGENTS.override.md
.agents/skills/*
docs/*
.codex/config.toml
.codex/rules/*
package/build files
CI configuration
repository structure
```

Identify:

```text
missing instructions
duplicate instructions
conflicting instructions
oversized AGENTS.md files
missing skill routing
poor skill descriptions
missing validation rules
missing safety restrictions
stale documentation
unnecessary context loading
```

Do not modify application code during an agent-configuration audit unless explicitly requested.

---

# 32. Recommended Agent Audit Prompt

```text
Analyze this repository's Codex agent configuration.

Read:
- AGENTS.md
- nested AGENTS.md / AGENTS.override.md
- docs/CODEX_OPERATING_GUIDE.md
- .agents/skills/*
- .codex/config.toml
- .codex/rules/*
- relevant project documentation

Then:

1. Map the current instruction hierarchy.
2. Identify duplicated or conflicting rules.
3. Identify missing skills.
4. Identify skills with weak descriptions.
5. Identify documentation that should be routed from AGENTS.md.
6. Identify instructions that should move from AGENTS.md into skills.
7. Identify project knowledge that should move into docs.
8. Identify risky shell commands that should be governed by execution policy.
9. Identify missing test/build/validation instructions.
10. Propose the improved repository structure.

Do not modify application source code.

Implement only agent-configuration improvements.
```

---

# 33. Recommended AGENTS.md Hook

Add this to repository root `AGENTS.md`:

```md
## Codex operating model

For Codex CLI operating conventions, context loading, skills,
documentation routing, validation workflow, command execution,
and repository-agent maintenance, read:

`docs/CODEX_OPERATING_GUIDE.md`

Read this guide when:
- modifying Codex/agent configuration;
- creating or modifying skills;
- changing AGENTS.md;
- changing .codex configuration or execution rules;
- planning a large autonomous task.

Do not load the entire guide for trivial code edits unless relevant.
```

---

# 34. Recommended Documentation Routing

Add to `AGENTS.md`:

```md
## Context routing

Load project documentation only when relevant:

- architecture changes → `docs/architecture.md`
- database/schema work → `docs/database.md`
- CDC/Debezium work → `docs/cdc.md`
- deployment/CI work → `docs/deployment.md`
- incident/debugging work → `docs/troubleshooting.md`
- Codex agent configuration → `docs/CODEX_OPERATING_GUIDE.md`
```

---

# 35. Recommended Skill Routing

Add to `AGENTS.md`:

```md
## Skill routing

Use repository skills when applicable:

- PostgreSQL CDC → `$postgres-cdc`
- MySQL/MariaDB CDC → `$mysql-cdc`
- database/schema/index changes → `$database-change`
- debugging/incident analysis → `$debugging`
- final code inspection → `$code-review`

A matching skill may be invoked implicitly.
Do not load unrelated skills.
```

---

# 36. Verify Instruction Loading

Use Codex itself to inspect what it currently sees.

Example:

```text
Summarize the active repository instructions and identify their source files.
```

For a specific directory:

```bash
cd apps/web
codex
```

then ask:

```text
List the active instruction files in precedence order and summarize the rules that apply here.
```

This is useful after adding nested `AGENTS.md` or `AGENTS.override.md`.

---

# 37. Diagnose Instruction Problems

If Codex appears to ignore project rules, check:

```text
current working directory
repository root
AGENTS.override.md
nested AGENTS.md
CODEX_HOME
config.toml
instruction size
skill discovery
```

After major instruction/configuration changes, start a fresh Codex session if needed.

Do not assume an existing long-running session perfectly represents newly changed repository context.

---

# 38. Instruction Size

Keep mandatory instructions concise.

Do not place large manuals directly in `AGENTS.md`.

Prefer:

```text
AGENTS.md
    ↓
routing rule
    ↓
relevant doc / skill
```

instead of:

```text
AGENTS.md
    ↓
all architecture knowledge
all DB knowledge
all deployment knowledge
all incident procedures
all API docs
```

---

# 39. Recommended Normal Workflow

```bash
cd repository
codex
```

Then use available interactive commands as appropriate:

```text
/status
/plan
/review
/compact
```

For repeatable domain workflows:

```text
$skill-name
```

Always verify available slash commands by typing:

```text
/
```

---

# 40. Version Awareness

Codex evolves quickly.

Commands, models, approval modes, skill behavior, and client capabilities may change.

Treat the installed CLI as the runtime source of truth:

```bash
codex --help
codex exec --help
```

Inside interactive Codex:

```text
/
```

When a documented command is unavailable:

```text
1. Check `codex --help`.
2. Check `codex exec --help`.
3. Check the interactive slash command palette.
4. Inspect the installed Codex version.
5. Use the current equivalent.
6. Update this guide if necessary.
```

Do not silently invent unsupported commands.

---

# 41. Core Principle

Optimize Codex for:

```text
minimum required context
+
maximum relevant context
+
explicit safety boundaries
+
reusable workflows
+
project-native validation
+
small reviewable changes
```

Desired flow:

```text
AGENTS.md
     ↓
route task
     ↓
select skill
     ↓
load relevant documentation
     ↓
inspect actual repository
     ↓
implement minimally
     ↓
validate
     ↓
review diff
     ↓
report result
```

This is the default operating model for Codex within this repository.
