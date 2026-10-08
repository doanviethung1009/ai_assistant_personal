"use server";

import { revalidatePath } from "next/cache";
import { wipeAllDataApi } from "@/lib/api";
import type { WipeOptions } from "@/lib/store/types";
import { deleteVaultAction } from "./vault-actions";

export async function wipeAllDataAction(options?: WipeOptions & { vault?: boolean }) {
  await wipeAllDataApi(options);
  if (!options || options.vault) {
    await deleteVaultAction();
  }
  revalidatePath('/', 'layout');
}
