# Changelog

Sinh tự động bằng `bash scripts/changelog.sh --write` từ `git log`,
gom theo type của [Conventional Commits](.agents/skills/git-commit/SKILL.md).
Đừng sửa tay — chạy lại script sau khi có commit mới.

## [Chưa phát hành] — cập nhật lần cuối 2026-10-03

### Thêm mới

- implement AI trace logging rule and initialize ai_logs.md (`618c701`)
- add interactive API Tester popup modal in API Docs page (`e527ef7`)
- add dedicated API tab to navigation (`65701a2`)
- group docs by category in web UI and polish styles (`1d85977`)
- add pagination to history page (50/page), add pagination rule to steering docs (`f8a2926`)
- add Chrome profile selector dropdown with email detection for history extraction (`4d83661`)
- add date filter, sort toggle on history page, custom path input for Chrome history, ensure temp file cleanup (`d7ef870`)
- add project edit/delete and Jira ticket link badge (`a41d59d`)
- them rate limit theo cua so co dinh qua Redis (`712b8bb`)
- sinh migration Alembic khoi tao schema (`d155709`)
- Phase 1 builder AI assistant - task management, flow diagrams, docs (`a3fa0c0`)

### Sửa lỗi

- update docker volumes and deploy runbook to use .agents instead of .kiro (`bc1ad67`)
- restore deleted skills folder from git and move to .agents/skills (`e42b1ae`)
- update import actions and patch scripts (`c058584`)
- support macOS BSD sed for bootstrap and make commands (`1f6452a`)
- sua .gitignore khop nham apps/web/app/data (`c3ec891`)
- sua loi parse cors_origins tu .env (`b6de8ab`)

### Tài liệu

- append latest git changelog tracking process to AI trace log (`018e2ab`)
- add guide on AI data storage architecture (markdown vs database) (`5d09c46`)
- add multi-agent workflow demo and scenario (`b6e35b0`)
- add guide on how to create AI customizations (skills, rules, hooks) and register it in UI (`bc2773a`)
- add agent prompt examples and register in docs tab (`4681201`)
- expand fileMatchPattern globally to automatically scale for any future backend or frontend apps (`40ee91a`)
- register AGENTS.md in web docs tab (`2042274`)
- add global AGENTS.md system prompt to optimize agent behavior and context loading (`b1d8efb`)
- improve project structure tree visualization (`6d680e4`)
- add API_REFERENCE.md and register it to web docs tab (`6786847`)
- add deep review and AI auto-commenting role (`01131ef`)
- them runbook deploy cho tung tinh huong thuc te (`4437d2a`)
- bo sung quy uoc comment va quy trinh commit (`b3ff039`)

### CI/CD

- them hook kiem tra commit message va script sinh changelog (`47c98e2`)

### Dọn dẹp

- fix macOS bash compatibility in changelog script and generate latest changelog (`9672eb0`)
- migrate to .agents architecture, cleanup root patches, and update docs registry (`656d634`)
- update project files, tasks, history and patch scripts (`ba6315f`)
- tach steering always-include thanh fileMatch va skill (`fe825b9`)
- mo hinh git main-uat-prod, script thang cap chi fast-forward (`d0cbccc`)

### Khác

- style: fix misalignment in docs menu by using flex-col and h-full (`79c0997`)
- update non AI 2 (`2a222bf`)
- update non AI (`3d31b41`)
-  lastest update (`796b261`)

