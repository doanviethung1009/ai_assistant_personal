import { notFound } from "next/navigation";
import { Markdown } from "@/components/markdown";
import { DOCS, readDoc, stripFrontMatter } from "@/lib/docs";

export const dynamic = "force-dynamic";

export default async function AiDocPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const entry = DOCS.find((d) => d.slug === slug);
  
  if (!entry) {
    notFound();
  }

  const content = await readDoc(entry);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{entry.title}</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          {entry.description}
        </p>
      </div>

      <article className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 sm:p-6">
        {content.markdown === null ? (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 p-3"
          >
            <p className="text-sm font-medium text-[var(--color-danger)]">
              Không đọc được {entry.title}
            </p>
            <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
              {content.error}
            </p>
          </div>
        ) : (
          <Markdown>{stripFrontMatter(content.markdown)}</Markdown>
        )}
      </article>
    </div>
  );
}
