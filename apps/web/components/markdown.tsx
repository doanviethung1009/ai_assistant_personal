import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Render markdown của repo.
 *
 * Không dùng rehype-raw, nên HTML thô trong markdown sẽ bị bỏ qua thay vì
 * chèn vào DOM. Nội dung là file của chính repo, nhưng giữ nguyên tắc không
 * cho phép HTML tuỳ ý là cách rẻ nhất để không phải lo về sau.
 *
 * Style bằng cách map từng thẻ thay vì dùng plugin typography, để khỏi thêm
 * dependency và để khối code ASCII giữ đúng khung.
 */

const components: Components = {
  h1: ({ children }) => (
    <h2 className="mt-8 border-b border-[var(--color-border)] pb-2 text-lg font-semibold tracking-tight first:mt-0">
      {children}
    </h2>
  ),
  h2: ({ children }) => (
    <h3 className="mt-7 text-base font-semibold tracking-tight">{children}</h3>
  ),
  h3: ({ children }) => (
    <h4 className="mt-5 text-sm font-semibold">{children}</h4>
  ),
  h4: ({ children }) => (
    <h5 className="mt-4 text-sm font-medium text-[var(--color-ink-muted)]">
      {children}
    </h5>
  ),

  p: ({ children }) => (
    <p className="mt-3 text-sm leading-relaxed text-[var(--color-ink)]">
      {children}
    </p>
  ),

  ul: ({ children }) => (
    <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,

  strong: ({ children }) => (
    <strong className="font-semibold text-[var(--color-ink)]">{children}</strong>
  ),
  em: ({ children }) => <em className="italic">{children}</em>,

  a: ({ href, children }) => (
    <a
      href={href}
      target={href?.startsWith("http") ? "_blank" : undefined}
      rel={href?.startsWith("http") ? "noopener noreferrer" : undefined}
      className="text-[var(--color-accent)] underline underline-offset-2"
    >
      {children}
    </a>
  ),

  // Khối code giữ nguyên khung, cho phép cuộn ngang để sơ đồ ASCII không vỡ
  pre: ({ children }) => (
    <pre className="mt-3 overflow-x-auto rounded-lg border border-[var(--color-border)] bg-black/40 p-3 text-xs leading-relaxed">
      {children}
    </pre>
  ),
  code: ({ className, children }) => {
    const text = String(children ?? "");
    // Nhiều khối trong README mở bằng ``` mà không ghi tên ngôn ngữ, nên
    // không có class "language-". Các sơ đồ ASCII đều nhiều dòng, còn inline
    // code thì không bao giờ, nên dấu xuống dòng là dấu hiệu đủ tin cậy.
    const isBlock =
      (typeof className === "string" && className.includes("language-")) ||
      text.includes("\n");

    if (isBlock) {
      return (
        <code className="font-mono text-[var(--color-ink)]">{children}</code>
      );
    }
    return (
      <code className="rounded bg-black/40 px-1 py-0.5 font-mono text-[0.85em] text-[var(--color-ink)]">
        {children}
      </code>
    );
  },

  table: ({ children }) => (
    <div className="mt-3 overflow-x-auto rounded-lg border border-[var(--color-border)]">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-white/5">{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-[var(--color-border)] last:border-0">
      {children}
    </tr>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 text-left text-xs font-semibold">{children}</th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 align-top text-[var(--color-ink-muted)]">
      {children}
    </td>
  ),

  blockquote: ({ children }) => (
    <blockquote className="mt-3 border-l-2 border-[var(--color-accent)] pl-3 text-sm text-[var(--color-ink-muted)]">
      {children}
    </blockquote>
  ),

  hr: () => <hr className="mt-6 border-[var(--color-border)]" />,

  input: ({ checked }) => (
    <input
      type="checkbox"
      checked={checked}
      readOnly
      disabled
      className="mr-1 size-3.5 accent-[var(--color-accent)]"
    />
  ),
};

export function Markdown({ children }: { children: string }) {
  return (
    <div className="max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
