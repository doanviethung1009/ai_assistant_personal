# AI Handoff & Project State

This file serves as the definitive context memory for AI assistants (Antigravity, Cursor, etc.).
Whenever you start a new session or switch computers, prompt the AI to **"Đọc file docs/AI_HANDOFF_STATE.md để lấy context"**.

## 1. Project Architecture
- **Framework**: Next.js 15 (App Router), React 19, Tailwind CSS v4.
- **Backend/Data**: Currently running in `DATA_SOURCE=file` mode (JSON local file in `data/builder-data.json`). Python/Postgres backend exists in `apps/core` but is mostly bypassed right now in favor of local file prototyping.
- **State Management**: Next.js keeps the JSON store in memory (`apps/web/lib/store/engine.ts`). **WARNING**: Directly modifying `builder-data.json` while Next.js `npm run dev` is running will result in the state being overwritten by Next.js memory cache on the next UI action. Always restart the Next.js dev server if you manually modify the JSON file!
- **Server Actions Limit**: `next.config.ts` has `serverActions.bodySizeLimit: "100mb"` to allow massive JSON backup uploads.

## 2. Advanced Data Sync (Jira & Google Sheets)
- **Import/Sync**: Users can import `.xlsx`/`.csv` via file upload OR paste Google Sheets links directly (auto-converts to export format). 
- **Parsing Logic (`actions-import.ts`)**:
  - **Auto-Project Creation**: Parses the `Company` column from Excel. Automatically creates a Project and assigns a random hex color if it doesn't exist (case-insensitive deduplication).
  - **Tag Extraction**: Automatically generates tags from: `Company` column, `Projects` column, `Labels` column, AND any text enclosed in `[brackets]` within the `Summary` field. All tags are strictly lowercased and deduplicated.
  - **Task Deduplication**: Falls back to deduping by Title if JIRA `Issue Key` is missing. Otherwise uses strict `Issue Key` deduplication.

## 3. Core Entities (`engine.ts`)
- **Task**: `assignee`, `tags`, `project_id`, `external_id`, `created_at`, `due_at`, `completed_at`. Separates Team vs Personal tasks based on assignee filtering.
- **Project**: Auto-generated from Company, assigned dynamic `color`.
- **sync_urls**: Managed via `UrlSyncManager`.

## 4. How to resume work
If the user asks to continue developing:
1. Note the separation between Personal (`/tasks`) and Team (`/team`).
2. If modifying filters, check `engine.ts` (`listTasks` filters `options.forCurrentUser`).
3. If extending JIRA importing, strictly use/modify `apps/web/app/actions-import.ts`.
4. Ensure timezone formatting (UTC+7) uses `formatDateTime` from `lib/format.ts`.

## 5. System Tools & Integrations
- **Tag Management**: The `/tags` page globally renames or deletes tags across all tasks and notes.
- **Wipe Data (Danger Zone)**: Granular deletion (Tasks, Projects, Notes, Sync URLs, Chrome History, All).
- **Auto-Backup Mechanism**: Before any wipe, `engine.ts` dumps current state and `chrome-history.json` into `data/backups/`. It automatically purges older backups to retain exactly **1 latest backup**.
- **Restore JSON**: Users can upload a backup JSON file (`RestoreJsonManager`) to instantly overwrite the entire DB. 
- **Chrome History Scraper**: Uses Node.js `child_process` and `sqlite3` to dump Chrome History DB into `data/chrome-history.json` (cross-platform). Rendered via `/history` with time-based filtering (1d, 3d, 1m, etc.) and search.
