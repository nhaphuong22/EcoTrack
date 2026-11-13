import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, User, Wrench, BookOpen } from 'lucide-react';

function ToolBadge({ tool }) {
  const labels = {
    query_metrics: '📊 query_metrics',
    get_anomalies: '⚠️ get_anomalies',
    query_forecast_summary: '📈 query_forecast_summary',
    calculate_waste_cost: '💸 calculate_waste_cost',
    domain_knowledge: '🧠 domain_knowledge',
  };
  return (
    <span className="inline-flex items-center gap-1 rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-0.5 text-[10px] font-mono text-sky-400">
      <Wrench size={9} />
      {labels[tool] || tool}
    </span>
  );
}

function SourceCard({ source }) {
  return (
    <div className="rounded-lg border border-slate-700/80 bg-slate-800/90 p-2 text-xs">
      <div className="flex items-center justify-between text-sky-400 font-semibold mb-1">
        <span className="flex items-center gap-1">
          <BookOpen size={11} className="text-sky-400" />
          {source.title || 'Tài liệu'}
        </span>
        <span className="text-[10px] text-slate-400 font-mono">{source.source}</span>
      </div>
      <p className="text-slate-300 line-clamp-3 text-[11px] leading-snug">{source.snippet}</p>
    </div>
  );
}

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';
  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar */}
      <div
        className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl ${
          isUser ? 'bg-emerald-500/20 text-emerald-400' : 'bg-sky-500/20 text-sky-400'
        }`}
      >
        {isUser ? <User size={15} /> : <Bot size={15} />}
      </div>

      {/* Bubble */}
      <div className={`max-w-[85%] space-y-1.5 ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
        {/* Tools used badges */}
        {!isUser && message.tools_used?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {message.tools_used.map((t) => (
              <ToolBadge key={t} tool={t} />
            ))}
          </div>
        )}

        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? 'rounded-tr-sm bg-emerald-600/30 text-slate-100'
              : 'rounded-tl-sm border border-slate-700/60 bg-slate-800/80 text-slate-200'
          }`}
        >
          {isUser ? (
            <span className="whitespace-pre-wrap">{message.content}</span>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ children }) => <h1 className="text-base font-bold text-white mb-2">{children}</h1>,
                h2: ({ children }) => <h2 className="text-sm font-bold text-sky-300 mb-1.5">{children}</h2>,
                h3: ({ children }) => <h3 className="text-xs font-semibold text-emerald-300 mb-1">{children}</h3>,
                p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
                ul: ({ children }) => <ul className="list-disc list-inside space-y-1 mb-2 text-xs">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal list-inside space-y-1 mb-2 text-xs">{children}</ol>,
                li: ({ children }) => <li className="text-xs">{children}</li>,
                code: ({ node, inline, className, children, ...props }) => (
                  <code className="rounded bg-slate-700/60 px-1 py-0.5 text-[11px] text-emerald-300 font-mono" {...props}>
                    {children}
                  </code>
                ),
                table: ({ children }) => (
                  <div className="overflow-x-auto my-2">
                    <table className="min-w-full divide-y divide-slate-700 border border-slate-700 text-xs text-left">
                      {children}
                    </table>
                  </div>
                ),
                th: ({ children }) => <th className="bg-slate-800/90 px-2 py-1 font-semibold text-slate-200">{children}</th>,
                td: ({ children }) => <td className="border-t border-slate-700/50 px-2 py-1 text-slate-300">{children}</td>,
              }}
            >
              {message.content || '...'}
            </ReactMarkdown>
          )}
        </div>

        {/* Cited Sources */}
        {!isUser && message.sources?.length > 0 && (
          <div className="w-full space-y-1.5 pt-1">
            <p className="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
              <BookOpen size={12} className="text-sky-400" />
              Tài liệu trích dẫn ({message.sources.length}):
            </p>
            <div className="grid gap-1.5">
              {message.sources.map((s, idx) => (
                <SourceCard key={idx} source={s} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
