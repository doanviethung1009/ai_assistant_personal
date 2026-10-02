# AI Handoff & Project State

This file serves as the definitive context memory for AI assistants (Antigravity, Cursor, etc.).
Whenever you start a new session or switch computers, prompt the AI to **"Đọc file docs/AI_HANDOFF_STATE.md để lấy context"**.

## 1. Project Architecture
- **Framework**: Next.js 15 (App Router), React 19, Tailwind CSS v4.
- **Backend/Data**: Currently running in `DATA_SOURCE=file` mode (JSON local file in `data/builder-data.json`). Python/Postgres backend exists in `apps/core` but is mostly bypassed right now in favor of local file prototyping.
- **State Management**: Next.js keeps the JSON store in memory (`apps/web/lib/store/engine.ts`). **WARNING**: Directly modifying `builder-data.json` while Next.js `npm run dev` is running will result in the state being overwritten by Next.js memory cache on the next UI action. Always restart the Next.js dev server if you manually modify the JSON file!

## 2. Recent Major Features Built
- **JIRA Data Sync**: Ability to import `.xlsx` and `.csv` exports from JIRA. Maps `Issue Key`, `Assignee`, `Created Date`, `Due Date`, `Closed Date`, `Status`, and extracts `Projects` (MAG, OM, IOTEK, GIAI) and `Labels` into `task.tags`.
- **Sync Options**: Users can sync via saving URLs (`/data` page) or uploading a local file directly (`FileUploadManager`). A background API route (`/api/sync?url=...`) exists for cronjobs.
- **Team Management**: The `/team` page aggregates all tasks where `assignee` is NOT the current user ("Đoàn Việt Hưng"). It includes Pagination (50 items/page), full Tag/Title search, Status filters, and Assignee filters (with dynamic counts).
- **Personal Isolation**: The Dashboard (`Hôm nay`) and `/tasks` (`Tất cả task`) ONLY display tasks assigned to "Đoàn Việt Hưng" or unassigned (`null`).
- **Tag Management**: The `/tags` page allows globally renaming or deleting tags across all tasks and notes.

## 3. Current Data Structures (in `engine.ts`)
- `Task`: Contains `assignee` (string | null), `tags` (string[]), `project_id`, `external_id` (Jira Key), `created_at`, `due_at`, `completed_at`, etc.
- `Project`: Jira projects are automatically mapped if they exist in the DB (MAG, OM, etc.).
- `sync_urls`: Saved array of strings pointing to `.csv` or `.xlsx` files for auto-sync.

## 4. How to resume work
If the user asks to continue developing:
1. Note the separation between Personal (`/tasks`) and Team (`/team`).
2. If modifying filters, check `engine.ts` (`listTasks` filters `options.forCurrentUser`).
3. If extending JIRA importing, check `apps/web/app/actions-import.ts`.

## 5. System Tools & Integrations
- **Wipe Data (Danger Zone)**: Implemented in `/data`. Allows wiping all local JSON state (`builder-data.json`). Requires typing "DELETE".
- **Chrome History Scraper**: Implemented in `/data`. Uses Node.js `child_process` and `sqlite3` to dump the Chrome History DB into `data/chrome-history.json`. Supports MacOS, Windows, and Linux dynamically based on OS platform.
- **Chrome History Viewer**: A dedicated `/history` page that parses `chrome-history.json` and renders the last 1000 visited URLs in a clean table.
- **Auto Backup Before Wipe**: Whenever data is deleted via the Danger Zone, the system first creates a timestamped backup JSON file in `data/backups/builder-data-backup-[TIMESTAMP].json` so that the user never loses data permanently.
