import { Bot, User, Wrench } from 'lucide-react';

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

function MarkdownText({ text }) {
  // Minimal inline markdown: **bold**, `code`, newlines → <br>
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\n)/g);
  return (
    <span>
      {parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**'))
          return <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>;
        if (part.startsWith('`') && part.endsWith('`'))
          return <code key={i} className="rounded bg-slate-700/60 px-1 py-0.5 text-[11px] text-emerald-300 font-mono">{part.slice(1, -1)}</code>;
        if (part === '\n')
          return <br key={i} />;
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}

export default function ChatMessage({ message }) {
  const isUser = message.role === 'user';
  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar */}
      <div className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl ${isUser ? 'bg-emerald-500/20 text-emerald-400' : 'bg-sky-500/20 text-sky-400'}`}>
        {isUser ? <User size={15} /> : <Bot size={15} />}
      </div>

      {/* Bubble */}
      <div className={`max-w-[82%] space-y-1.5 ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
        {/* Tools used badges */}
        {!isUser && message.tools_used?.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {message.tools_used.map(t => <ToolBadge key={t} tool={t} />)}
          </div>
        )}

        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? 'rounded-tr-sm bg-emerald-600/30 text-slate-100'
              : 'rounded-tl-sm border border-slate-700/60 bg-slate-800/80 text-slate-200'
          }`}
        >
          <MarkdownText text={message.content} />
        </div>
      </div>
    </div>
  );
}
