import { TableSkeleton } from "@/components/admin/table-skeleton";

export default function Loading() {
  return (
    <div className="space-y-5">
      <div className="h-9 w-64 animate-pulse rounded-lg bg-[var(--color-surface-hover)]" />
      <TableSkeleton />
    </div>
  );
}
