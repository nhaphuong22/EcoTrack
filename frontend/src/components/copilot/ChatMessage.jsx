import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Wrench, BookOpen } from 'lucide-react';

function ToolBadge({ tool }) {
  return (
    <span className="chip chip-info num font-medium">
      <Wrench size={10} aria-hidden="true" />
      {tool}
    </span>
  );
}

function SourceCard({ source }) {
  return (
    <div className="rounded-md border border-line bg-panel p-2 text-xs">
      <div className="mb-1 flex items-center justify-between font-semibold text-shell">
        <span className="flex items-center gap-1">
          <BookOpen size={11} aria-hidden="true" />
          {source.title || 'Tài liệu'}
        </span>
        <span className="font-mono text-[10px] text-muted">{source.source}</span>
      </div>
      <p className="line-clamp-3 text-[11px] leading-snug text-ink">{source.snippet}</p>
    </div>
  );
}

const markdownComponents = {
  h1: ({ children }) => <h1 className="mb-2 text-base font-bold text-ink">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-1.5 text-sm font-bold text-ink">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1 text-xs font-semibold text-ink">{children}</h3>,
  p: ({ children }) => <p className="mb-2 leading-relaxed last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-inside list-disc space-y-1 text-xs">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-inside list-decimal space-y-1 text-xs">{children}</ol>,
  li: ({ children }) => <li className="text-xs">{children}</li>,
  code: ({ children }) => (
    <code className="rounded bg-sunken px-1 py-0.5 font-mono text-[12px] text-shell">{children}</code>
  ),
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="min-w-full divide-y divide-line border border-line text-left text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="bg-sunken px-2 py-1 font-semibold text-ink">{children}</th>,
  td: ({ children }) => <td className="border-t border-line px-2 py-1 text-ink">{children}</td>,
};

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';
  return (
    <div className={`flex flex-col gap-1.5 ${isUser ? 'items-end' : 'items-start'}`}>
      <span className="text-[11px] font-semibold text-muted">{isUser ? 'Bạn' : 'Copilot'}</span>

      {!isUser && message.tools_used?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {message.tools_used.map(t => <ToolBadge key={t} tool={t} />)}
        </div>
      )}

      <div
        className={`max-w-[88%] rounded-md px-3.5 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'bg-shell text-white'
            : 'border border-line bg-panel text-ink'
        }`}
      >
        {isUser ? (
          <span className="whitespace-pre-wrap">{message.content}</span>
        ) : (
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {message.content || '...'}
          </ReactMarkdown>
        )}
      </div>

      {!isUser && message.sources?.length > 0 && (
        <div className="w-full max-w-[88%] space-y-1.5 pt-1">
          <p className="flex items-center gap-1 text-[11px] font-semibold text-muted">
            <BookOpen size={12} aria-hidden="true" />
            Tài liệu trích dẫn ({message.sources.length}):
          </p>
          <div className="grid gap-1.5">
            {message.sources.map((s, idx) => <SourceCard key={idx} source={s} />)}
          </div>
        </div>
      )}
    </div>
  );
}
