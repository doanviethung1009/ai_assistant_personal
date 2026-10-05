"use server";

import { setCurrentUsersApi } from "@/lib/api";
import { revalidatePath } from "next/cache";

export async function setCurrentUserAction(names: string[]) {
  await setCurrentUsersApi(names);
  revalidatePath("/", "layout"); // Cập nhật toàn bộ các trang (Hôm nay, Task, Team)
}
