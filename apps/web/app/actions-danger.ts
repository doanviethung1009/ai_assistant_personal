"use server";

import { revalidatePath } from "next/cache";
import { wipeAllDataApi } from "@/lib/api";

export async function wipeAllDataAction(options?: { tasks?: boolean, projects?: boolean, notes?: boolean, sync_urls?: boolean, chrome_history?: boolean }) {
  await wipeAllDataApi(options);
  revalidatePath('/', 'layout');
}
