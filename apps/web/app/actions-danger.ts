"use server";

import { revalidatePath } from "next/cache";
import { wipeAllDataApi } from "@/lib/api";
import { deleteVaultAction } from "./vault-actions";

export async function wipeAllDataAction(options?: { tasks?: boolean, tasks_personal?: boolean, tasks_team?: boolean, projects?: boolean, notes?: boolean, vault?: boolean, sync_urls?: boolean, chrome_history?: boolean }) {
  await wipeAllDataApi(options);
  if (!options || options.vault) {
    await deleteVaultAction();
  }
  revalidatePath('/', 'layout');
}
