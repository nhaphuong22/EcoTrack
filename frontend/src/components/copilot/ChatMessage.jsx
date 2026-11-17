import { Wrench } from 'lucide-react';

function ToolBadge({ tool }) {
  return (
    <span className="chip chip-info num font-medium">
      <Wrench size={10} aria-hidden="true" />
      {tool}
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
          return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
        if (part.startsWith('`') && part.endsWith('`'))
          return <code key={i} className="rounded bg-sunken px-1 py-0.5 font-mono text-[12px] text-shell">{part.slice(1, -1)}</code>;
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
        <MarkdownText text={message.content} />
      </div>
    </div>
  );
}
