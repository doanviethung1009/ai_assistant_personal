# Claude Code Operating Guide

> Repository operating guide for Anthropic Claude Code (CLI and IDE extensions).
>
> This document describes how Claude Code should discover project context, load instructions, select skills, inspect documentation, execute commands, modify code, validate changes, and handle risky operations.
>
> `AGENTS.md` is the canonical, agent-neutral instruction file. `CLAUDE.md` is the Claude Code entry point and imports it.
>
> Counterpart of `docs/CODEX_OPERATING_GUIDE.md`. Sections marked **[shared]** describe agent-neutral policy and must stay consistent with the Codex guide.

---

# 1. Purpose

This repository is designed to work with Claude Code as an autonomous coding agent, alongside Codex CLI.

Claude Code uses the following context hierarchy:

```text
Runtime / platform instructions
        ↓
Managed (enterprise) policy CLAUDE.md + managed settings
        ↓
User memory: ~/.claude/CLAUDE.md
        ↓
Repository CLAUDE.md (+ files imported with @path, e.g. @AGENTS.md)
        ↓
CLAUDE.local.md (personal, not committed)
        ↓
.claude/rules/*.md (modular rules, optionally path-scoped)
        ↓
Nested CLAUDE.md (loaded when working inside that directory)
        ↓
Relevant skills
        ↓
Relevant project documentation
        ↓
Current source code and configuration
        ↓
User task
```

Progressive context loading:

```text
Always loaded at startup:
    ~/.claude/CLAUDE.md
    CLAUDE.md (repository root and parent directories)
    files imported with @path
    CLAUDE.local.md
    skill names + descriptions (metadata only)

Loaded when working in a subdirectory:
    <subdir>/CLAUDE.md
    path-scoped rules matching the files touched

Loaded when relevant:
    SKILL.md body
    skill references/*
    docs/*.md referenced by plain path (not @import)

Inspected when needed:
    source code, configuration, tests, Git history, logs

Provided automatically by IDE extensions:
    open file, current selection, diagnostics
```

---

# 2. Repository Context Model

## 2.1 AGENTS.md — Mandatory project rules (agent-neutral)

```text
WHAT MUST ALWAYS BE TRUE — for every agent
```

Repository-wide behavior, coding standards, safety requirements, documentation routing, skill routing, validation expectations, destructive-operation restrictions.

Keep it concise. Do not use it as a knowledge base.

## 2.2 CLAUDE.md — Claude Code entry point

Claude Code does not read `AGENTS.md` natively. Bridge it:

```markdown
@AGENTS.md

## Claude Code specifics
- Operating guide: read `docs/CLAUDE_OPERATING_GUIDE.md` when changing agent configuration, skills, hooks or permissions, or when planning a large autonomous task.
- Skills live in `.claude/skills/` (shared with Codex via symlink to `.agents/skills/`).
```

Rules:

- Put only Claude-specific content in `CLAUDE.md`. Everything agent-neutral belongs in `AGENTS.md`.
- `@path` imports are loaded **every turn**. Import only small, always-needed files.
- Reference large documents by plain path so they load on demand.

## 2.3 CLAUDE.local.md — personal notes

Machine- or person-specific notes (local DB ports, personal shortcuts). Add to `.gitignore`.

## 2.4 .claude/rules/ — modular rules

Split rules by topic when `CLAUDE.md` grows. Rules can be scoped to paths so they apply only when matching files are touched:

```markdown
---
paths:
  - "backend/migrations/**"
---
- Every migration must include a reversible down step.
- Use CREATE INDEX CONCURRENTLY on tables larger than 1M rows.
```

Check with `/memory` that the installed version loads `.claude/rules/`.

## 2.5 Skills — reusable workflows

Claude Code reads project skills from:

```text
.claude/skills/<name>/SKILL.md
```

The `SKILL.md` format (front matter `name` + `description`) is compatible with Codex skills. Keep **one** set of skills and share it:

```bash
# from the repository root
mkdir -p .claude
ln -s ../.agents/skills .claude/skills
```

(Windows without symlink support: copy via a script in CI or keep `.claude/skills` as the canonical location and symlink the other way.)

```yaml
---
name: postgres-cdc
description: Use for PostgreSQL logical replication, Debezium CDC, publications, replication slots, WAL configuration, CDC privileges and replication troubleshooting. Do not use for MySQL/MariaDB binlog CDC.
---
```

## 2.6 Subagents — isolated specialists

```text
.claude/agents/<name>.md
```

A subagent runs in its own context window and returns only its conclusion. Use for wide searches, reviews, and log analysis that would otherwise flood the main session.

```markdown
---
name: sql-reviewer
description: Review SQL and migrations for locking, performance, data loss and rollback safety. Use after writing or changing a migration.
tools: Read, Grep, Glob
model: sonnet
---
You are a read-only SQL reviewer. Never edit files.
Report findings as: critical / should fix / suggestion.
```

## 2.7 Custom slash commands

```text
.claude/commands/<name>.md   → invoked as /<name>
```

Use `$ARGUMENTS` for input. Prefer skills for anything multi-step; keep commands for short, frequently typed prompts.

---

# 3. Skill Loading Behavior

At startup Claude Code sees only:

```text
skill name
skill description
```

When the task matches:

```text
Task
 ↓
Match skill description
 ↓
Load SKILL.md body
 ↓
Follow skill instructions
 ↓
Read references/ only when required
 ↓
Run scripts/ only when required
```

Invocation:

- **Implicit** (preferred): the description matches the task.
- **Explicit**: type `/skill-name`, or name it in the prompt — `Use the postgres-cdc skill to …`.

Verify discovery by asking: `List the project skills you can see and their descriptions.`

---

# 4. Project Documentation **[shared]**

Markdown in `docs/` is knowledge, not automatic instructions. Read only when relevant.

```text
Architecture work        → docs/architecture.md
Database/schema work     → docs/database.md
CDC/Debezium work        → docs/cdc.md
Deployment / CI/CD       → docs/deployment.md
API integration          → docs/api.md
Security-sensitive work  → docs/security.md
Conventions              → docs/conventions.md
Incident/debugging       → docs/troubleshooting.md
Claude configuration     → docs/CLAUDE_OPERATING_GUIDE.md
Codex configuration      → docs/CODEX_OPERATING_GUIDE.md
```

Never `@import` these into `CLAUDE.md`.

---

# 5. CLAUDE.md Discovery and Precedence

```text
~/.claude/CLAUDE.md
repository/
├── CLAUDE.md            → @AGENTS.md
├── CLAUDE.local.md
├── apps/web/CLAUDE.md
└── packages/database/CLAUDE.md
```

Behavior:

- Claude Code reads `CLAUDE.md` in the **current directory and every parent** at startup.
- `CLAUDE.md` in **subdirectories** is loaded only when Claude reads or edits files there.
- More specific (closer) files refine broader ones. There is no `AGENTS.override.md` equivalent; to override, state the override explicitly in the nested file.

Launch location matters:

```bash
cd repository && claude          # recommended: full config
cd repository/apps/web && claude # parent CLAUDE.md still loads,
                                 # but .claude/ at root may NOT
```

IDE: open the **repository root** as the workspace folder. Multi-root workspaces may only pick one root.

Settings precedence (`settings.json`), highest first:

```text
managed policy
command-line flags
.claude/settings.local.json   (personal, not committed)
.claude/settings.json         (shared, committed)
~/.claude/settings.json       (user)
```

---

# 6. Alternate Instruction Files

Claude Code does not automatically read `AGENTS.md`, `.cursorrules` or `.github/copilot-instructions.md`.

Policy:

- `AGENTS.md` is canonical.
- `CLAUDE.md` imports it with `@AGENTS.md`.
- Do not maintain a second, divergent rule set in `CLAUDE.md`.

---

# 7. Recommended Repository Structure

```text
repository/
├── AGENTS.md                      # canonical rules (all agents)
├── CLAUDE.md                      # @AGENTS.md + Claude specifics
├── CLAUDE.local.md                # personal, gitignored
│
├── docs/
│   ├── CLAUDE_OPERATING_GUIDE.md
│   ├── CODEX_OPERATING_GUIDE.md
│   ├── architecture.md
│   ├── database.md
│   ├── cdc.md
│   ├── deployment.md
│   └── troubleshooting.md
│
├── .agents/skills/                # canonical skills (Codex)
│   ├── database-change/SKILL.md
│   ├── postgres-cdc/SKILL.md
│   ├── mysql-cdc/SKILL.md
│   ├── debugging/SKILL.md
│   └── code-review/SKILL.md
│
├── .claude/
│   ├── skills -> ../.agents/skills   # symlink, shared skills
│   ├── agents/                    # subagents
│   ├── commands/                  # custom slash commands
│   ├── rules/                     # modular / path-scoped rules
│   ├── settings.json              # permissions + hooks (committed)
│   └── settings.local.json        # personal (gitignored)
│
├── .codex/
│   ├── config.toml
│   └── rules/default.rules
│
└── apps/web/CLAUDE.md
```

Responsibilities:

```text
AGENTS.md              → mandatory behavior (all agents)
CLAUDE.md              → Claude entry point
docs/                  → project knowledge
skills                 → reusable workflows
.claude/agents/        → isolated specialist contexts
.claude/settings.json  → permissions + hooks (technical enforcement)
```

---

# 8. Claude Code Startup Procedure

```text
1. Detect repository root.
2. Load applicable CLAUDE.md (+ AGENTS.md via import).
3. Discover skill metadata.
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
14. Report: what changed, why, validation performed, unresolved issues.
```

---

# 9. Interactive Claude Code

```bash
cd <repository>
claude
```

```bash
claude --help
```

Inside the session type `/` or `/help` to list commands supported by the installed version. The installed version is the runtime source of truth.

IDE:

- Native extension panel (VS Code, Cursor, JetBrains), or
- run `claude` in the IDE terminal, then `/ide` to connect to the editor.

---

# 10. Common Interactive Commands

Verify at runtime with `/help`.

| Command | Purpose |
|---|---|
| `/init` | Generate a `CLAUDE.md` scaffold. Do not overwrite a maintained file blindly — merge into the `@AGENTS.md` layout. |
| `/memory` | Show/edit loaded memory files. Primary tool to verify instruction loading. |
| `/context` | Show context usage by source (memory, tools, messages). |
| `/status` | Session, model, account, working directory. |
| `/clear` | Start fresh context (new objective). |
| `/compact [focus]` | Summarize a long session; e.g. `/compact keep schema decisions`. |
| `/model` | Change model. |
| `/cost`, `/usage` | Token cost / plan usage. |
| `/review` | Review changes / a PR. |
| `/security-review` | Security-focused review of pending changes (if available). |
| `/permissions` | Inspect allow/deny rules. |
| `/hooks` | Inspect configured hooks. |
| `/agents` | Manage subagents. |
| `/mcp` | Inspect MCP servers/tools. Never assume an integration exists without checking. |
| `/add-dir <path>` | Add an extra working directory. |
| `/resume` | Reopen a previous session. |
| `/rewind` | Return code and conversation to an earlier checkpoint. |
| `/export` | Export the conversation. |
| `/doctor` | Diagnose installation. |

## Planning mode

Press `Shift+Tab` to cycle permission modes until **plan mode**, or start with:

```bash
claude --permission-mode plan
```

In plan mode Claude reads and plans but does not edit. Use it for multi-module changes, refactors, schema migrations, production-impacting work, complex bugs, architecture changes.

A plan should identify:

```text
scope · affected files · dependencies · risks · validation · rollback strategy
```

## Reasoning depth

Use the strongest model and extended thinking for architecture, complex debugging, large refactors, database incident analysis, security-sensitive and cross-service changes. Extended thinking can be requested in the prompt (e.g. "think hard about …") or toggled where the client supports it; verify with `/help`.

## Input shortcuts

| Input | Effect |
|---|---|
| `@path` | Attach a file/directory to the prompt |
| `!cmd` | Run a shell command; output goes into context |
| `Esc` | Interrupt |
| `Esc Esc` | Edit previous message / rewind |
| `Shift+Tab` | Cycle permission modes |

---

# 11. Skill Invocation

```text
/postgres-cdc
```

or

```text
Use the postgres-cdc skill to inspect the current publication and determine the safest SQL required to add these tables.
```

Without explicit invocation, Claude should still activate skills whose descriptions match.

Codex uses `$skill-name`; Claude Code uses `/skill-name` or natural language. The `SKILL.md` content is the same.

---

# 12. Non-Interactive Claude Code

```bash
claude -p "<task>"
```

```bash
claude -p "Analyze this repository and list architectural risks."
```

Useful flags (verify with `claude --help`):

```text
--max-turns <n>              limit agent loop length
--allowedTools "Read,Grep"   restrict tools for the run
--disallowedTools "Bash"     forbid tools
--permission-mode plan       analysis only
--model <name>               choose model
--append-system-prompt "…"   add run-specific instructions
```

---

# 13. Structured Output

```bash
claude -p --output-format json "Analyze the repository"
claude -p --output-format stream-json "…"
```

Prefer structured output when another tool consumes the result (CI, orchestration, logging).

---

# 14. Ephemeral Runs

`claude -p` runs are one-shot. For throwaway analysis, combine with read-only tools and plan mode:

```bash
claude -p --permission-mode plan --allowedTools "Read,Grep,Glob" "<task>"
```

---

# 15. Permission Modes and Isolation

Least privilege:

```text
read-only analysis        → plan mode / restricted --allowedTools
repository modifications  → default mode (ask) or acceptEdits
unattended broad access   → bypassPermissions (--dangerously-skip-permissions)
                            ONLY in an isolated container / ephemeral CI / dedicated VM
```

Never make bypass mode the project default.

Technical enforcement lives in `.claude/settings.json` (Section 18), not in prose.

Isolation for parallel or experimental work:

```bash
git worktree add ../repo-exp -b exp/feature
cd ../repo-exp && claude
```

Subagents may also run in an isolated worktree where supported.

---

# 16. Resume a Session

```bash
claude -c              # continue the most recent session
claude -r              # pick a session to resume
claude -p -r <id> "…"  # resume in non-interactive mode
```

Resume only when the new task genuinely depends on prior context. Otherwise start fresh (`/clear` or a new session).

---

# 17. Pipe Logs or Diffs Into Claude

```bash
npm test 2>&1 | claude -p "Analyze these failing tests and identify the likely root cause."
tail -n 500 app.log | claude -p "Analyze this log and rank the likely root causes."
git diff | claude -p "Review this diff for correctness and regressions."
cat postgres.log | claude -p "Analyze PostgreSQL errors and rank likely root causes."
```

Trim input first (`tail`, `grep`) — piped content counts toward tokens.

---

# 18. Execution Policy: settings.json and Hooks

Do not confuse:

```text
CLAUDE.md / AGENTS.md      → behavior, conventions, workflow (advisory)
.claude/settings.json      → permissions + hooks (enforced)
```

Equivalent of `.codex/rules`:

```json
{
  "permissions": {
    "allow": [
      "Bash(git status)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(make test:*)",
      "Bash(pytest:*)"
    ],
    "ask": [
      "Bash(git push:*)",
      "Bash(kubectl:*)",
      "Bash(terraform:*)"
    ],
    "deny": [
      "Read(./.env*)",
      "Read(./**/*.pem)",
      "Read(./dumps/**)",
      "Read(./**/*.sql.gz)",
      "Read(./node_modules/**)",
      "Bash(rm -rf:*)",
      "Bash(git reset --hard:*)",
      "Bash(git clean:*)",
      "Bash(terraform destroy:*)",
      "Bash(kubectl delete:*)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": ".claude/hooks/block-destructive-sql.sh" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "make fmt >/dev/null 2>&1 || true" }]
      }
    ]
  }
}
```

Example `PreToolUse` guard (exit code `2` blocks the call and returns stderr to Claude):

```bash
#!/usr/bin/env bash
# .claude/hooks/block-destructive-sql.sh
input="$(cat)"
if echo "$input" | grep -Eiq 'DROP (DATABASE|TABLE)|TRUNCATE|pg_drop_replication_slot'; then
  echo "Blocked: destructive SQL requires explicit human execution." >&2
  exit 2
fi
exit 0
```

Pattern matching on Bash is a safety net, not a guarantee. Production credentials must not be reachable from the agent environment at all.

---

# 19. Safety Policy **[shared]**

Distinguish:

```text
analysis · local development change · external side effect · production operation · destructive operation
```

Lower risk: `ls`, `rg`, `cat`, `git status`, `git diff`, `git log`, `SELECT`, `EXPLAIN`, `SHOW`, `DESCRIBE`.

Higher risk: push, merge, deploy, cloud changes, production DB changes, service restarts, infrastructure deletion, credential rotation, IAM changes.

For destructive or production-impacting changes:

```text
1. Inspect first.
2. Explain the impact.
3. Show the proposed command or change.
4. Provide rollback / recovery strategy.
5. Require explicit authorization.
6. Verify the result after execution.
```

---

# 20. Database Safety **[shared]**

Before modifying a database:

```text
engine · version · environment · database/schema · current state
locks · replication/CDC impact · rollback
```

DDL:

```text
table size · locking behavior · online/in-place support
expected duration · replica impact · application compatibility
```

CDC:

```text
WAL/binlog prerequisites · publication · replication slot · privileges
replica identity / primary key · connector configuration · retention risk
```

Never drop or recreate a replication slot without evaluating retained WAL/binlog and consumer position.

Never run destructive production SQL merely because it is syntactically valid.

---

# 21. Code Modification Workflow **[shared]**

```text
UNDERSTAND → INSPECT → PLAN → IMPLEMENT → VERIFY → REVIEW → REPORT
```

- **Understand**: intent, success criteria.
- **Inspect**: relevant files, adjacent code, tests, configuration.
- **Plan**: minimal change, risks, validation (plan mode for large work).
- **Implement**: preserve architecture, no unrelated cleanup.
- **Verify**: lint, typecheck, unit/integration tests, build, targeted checks.
- **Review**: `git diff`, accidental changes, regressions.
- **Report**: changes, validation results, unresolved risks.

---

# 22. Minimal Diff Principle **[shared]**

Smallest correct change. Do not unnecessarily rewrite unrelated modules, rename symbols, upgrade dependencies, reformat whole files, refactor opportunistically, or change public APIs.

---

# 23. Inspect Before Changing **[shared]**

Inspect implementation, callers, tests, configuration and relevant Git history before assuming code is wrong. Follow established patterns unless there is a concrete reason to change them.

---

# 24. Validation Discovery **[shared]**

Discover commands from `package.json`, `Makefile`, `justfile`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `docker-compose.yml`, `.github/workflows/*`.

Prefer repository-defined commands. Do not invent validation commands. Run the narrowest relevant test first, full suite only when needed.

---

# 25. Final Diff Review **[shared]**

```bash
git status
git diff
```

Check for unexpected files, debug output, temporary files, secrets, formatting noise, unrelated edits, missed tests, accidental config changes.

`/review` or the `sql-reviewer` / `code-review` subagent can provide an independent pass.

---

# 26. Secrets and Credentials **[shared]**

Never write secrets into source, `AGENTS.md`, `CLAUDE.md`, `SKILL.md`, docs, logs, Git history or example config.

Use environment variables, secret managers, CI secrets. Deny agent read access to secret files (Section 18).

---

# 27. Context Management

```text
same objective + large context      → /compact [focus]
different objective                 → /clear or new session
wide search / heavy reading         → subagent (keeps main context small)
knowledge needed repeatedly         → docs/*.md
repeatable workflow                 → skill
mandatory behavior (all agents)     → AGENTS.md
mandatory behavior (Claude only)    → CLAUDE.md / .claude/rules/
must happen every time, guaranteed  → hook
```

Check `/context` when sessions feel slow or expensive. Do not rely on chat history as permanent documentation.

---

# 28. Context Routing Decision

```text
Always applicable, all agents?          → AGENTS.md
Always applicable, Claude only?         → CLAUDE.md
Applies to a path / file type?          → nested CLAUDE.md or .claude/rules/ (paths:)
Repeatable multi-step workflow?         → skill (SKILL.md)
Project knowledge?                      → docs/*.md
Deterministic executable logic?         → skill scripts/
Isolated analysis returning a verdict?  → .claude/agents/
Short reusable prompt?                  → .claude/commands/
Allow / deny tool or command?           → .claude/settings.json permissions
Must always run, not optional?          → .claude/settings.json hooks
Personal / machine-specific?            → CLAUDE.local.md / settings.local.json
```

---

# 29. When to Create a Skill **[shared]**

When a workflow repeats, has ordered steps, domain-specific validation, known failure modes, needs references or reusable scripts.

Good candidates: PostgreSQL CDC, MySQL/MariaDB CDC, migrations, incident analysis, log analysis, API integration, release verification, code review, security review, deployment.

Not for one-line preferences — those go in `AGENTS.md`.

---

# 30. Skill Quality Requirements **[shared]**

Each skill defines: when it applies, when it does not, required inputs, inspection steps, implementation steps, validation, failure handling, output expectations, risk boundaries.

Weak: `Helps with databases.`

Strong: `Use for PostgreSQL schema changes, indexes, migrations, locking analysis, query-plan validation and rollback planning. Do not use for MongoDB or application-only changes.`

---

# 31. Agent Configuration Audit

Inspect:

```text
AGENTS.md · CLAUDE.md · CLAUDE.local.md · nested CLAUDE.md
.claude/rules/* · .claude/skills/* (and .agents/skills/*)
.claude/agents/* · .claude/commands/*
.claude/settings.json · .claude/hooks/*
docs/* · build files · CI configuration
```

Identify:

```text
content duplicated between CLAUDE.md and AGENTS.md
large @imports that load every turn
missing / broken skill symlink
weak skill or subagent descriptions
rules that should be hooks (must-always-happen)
missing deny rules for secrets and large files
missing validation instructions
stale documentation
unnecessary context loading
```

Do not modify application code during an agent-configuration audit unless explicitly requested.

---

# 32. Recommended Agent Audit Prompt

Run in plan mode:

```text
Analyze this repository's Claude Code agent configuration.

Read:
- CLAUDE.md, CLAUDE.local.md, nested CLAUDE.md
- AGENTS.md
- docs/CLAUDE_OPERATING_GUIDE.md
- .claude/rules/*, .claude/skills/*, .claude/agents/*, .claude/commands/*
- .claude/settings.json and .claude/hooks/*

Then:
1. Map the effective instruction hierarchy and what loads every turn.
2. Identify duplicated or conflicting rules (CLAUDE.md vs AGENTS.md vs rules).
3. Identify @imports that should become plain path references.
4. Identify missing skills and weak skill/subagent descriptions.
5. Identify advisory rules that should be enforced by hooks or permissions.
6. Identify missing deny rules (secrets, dumps, large generated files).
7. Identify missing validation instructions.
8. Propose the improved structure.

Do not modify application source code.
Implement only agent-configuration improvements, after I approve the plan.
```

---

# 33. Recommended CLAUDE.md Hook

```md
@AGENTS.md

## Claude Code operating model
Read `docs/CLAUDE_OPERATING_GUIDE.md` when:
- modifying Claude/agent configuration, skills, subagents, hooks or permissions;
- changing CLAUDE.md or AGENTS.md;
- planning a large autonomous task.
Do not load it for trivial code edits.
```

---

# 34. Recommended Documentation Routing

Lives in `AGENTS.md` (shared by both agents) — see Section 4.

---

# 35. Recommended Skill Routing

Add to `AGENTS.md` in agent-neutral wording:

```md
## Skill routing
Use repository skills when applicable:
- PostgreSQL CDC → postgres-cdc
- MySQL/MariaDB CDC → mysql-cdc
- database/schema/index changes → database-change
- debugging/incident analysis → debugging
- final code inspection → code-review

Codex: `$name`. Claude Code: `/name` or by description.
Do not load unrelated skills.
```

---

# 36. Verify Instruction Loading

```text
/memory     → which CLAUDE.md / rule files are loaded
/context    → token usage per source
```

Then ask:

```text
List the active instruction files in precedence order, the skills you can see, and summarize the rules that apply in this directory.
```

Repeat after adding nested `CLAUDE.md`, rules, or skills.

---

# 37. Diagnose Instruction Problems

If Claude seems to ignore project rules, check:

```text
working directory / IDE workspace root
/memory output (is AGENTS.md actually imported?)
@import path typos
.claude/skills symlink resolves
skill description clarity
settings precedence (local vs shared vs user vs managed)
CLAUDE.md size (too long → rules get diluted)
stale session (start a new one after config changes)
```

Rules that must never be skipped belong in hooks or permissions, not prose.

---

# 38. Instruction Size

`CLAUDE.md` + everything it imports is sent every turn. Keep it short.

```text
CLAUDE.md → @AGENTS.md → routing rule → relevant doc / skill (on demand)
```

not

```text
CLAUDE.md → @all docs
```

---

# 39. Recommended Normal Workflow

```bash
cd repository
claude
```

```text
/clear              new task
Shift+Tab → plan    large / risky work
@file               point to exact files
/skill-name         repeatable domain workflow
/review             after implementation
/compact            long session, same objective
/context, /cost     check spend
Esc, /rewind        wrong direction
```

---

# 40. Version Awareness

Claude Code evolves quickly. Commands, flags, models, permission modes, rules and skill behavior may change.

Runtime source of truth:

```bash
claude --help
```

```text
/help
```

When a documented command is unavailable:

```text
1. Check claude --help.
2. Check /help.
3. Check the installed version (claude --version).
4. Use the current equivalent.
5. Update this guide.
```

Do not silently invent unsupported commands.

---

# 41. Core Principle **[shared]**

```text
minimum required context
+ maximum relevant context
+ explicit, enforced safety boundaries
+ reusable workflows
+ project-native validation
+ small reviewable changes
```

```text
CLAUDE.md → @AGENTS.md → route task → select skill → load relevant docs
→ inspect repository → implement minimally → validate → review diff → report
```

This is the default operating model for Claude Code within this repository.
