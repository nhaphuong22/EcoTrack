import { useEffect, useRef, useState } from 'react';
import { X, Send, Bot, Trash2, Loader2 } from 'lucide-react';
import ChatMessage from './ChatMessage';
import QuickPrompts from './QuickPrompts';
export default function CopilotDrawer({
  isOpen,
  onClose,
  messages = [],
  isLoading = false,
  error = null,
  sendMessage,
  clearHistory,
}) {
  const [input, setInput] = useState('');
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 120);
  }, [isOpen]);

  const handleSend = () => {
    const msg = input.trim();
    if (!msg || isLoading) return;
    setInput('');
    sendMessage(msg);
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <>
      {/* Backdrop overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-[2px] transition-opacity"
          onClick={onClose}
        />
      )}

      {/* Drawer panel */}
      <aside
        className={`fixed right-0 top-0 z-40 flex h-full w-full flex-col bg-slate-900 shadow-2xl transition-transform duration-300 ease-in-out sm:w-[420px] lg:w-[480px] ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700/60 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 to-violet-600 shadow-lg shadow-sky-500/20">
              <Bot size={18} className="text-white" />
            </div>
            <div>
              <p className="text-sm font-bold text-white">EcoTrack Copilot</p>
              <p className="text-[11px] text-emerald-400">● Sẵn sàng hỗ trợ</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              id="copilot-clear-btn"
              onClick={clearHistory}
              className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
              title="Xóa lịch sử hội thoại"
            >
              <Trash2 size={15} />
            </button>
            <button
              id="copilot-close-btn"
              onClick={onClose}
              className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
              title="Đóng"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {messages.map((m, i) => <ChatMessage key={i} message={m} />)}

          {/* Typing indicator */}
          {isLoading && (
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-sky-500/20 text-sky-400">
                <Bot size={15} />
              </div>
              <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm border border-slate-700/60 bg-slate-800/80 px-4 py-2.5">
                <Loader2 size={14} className="animate-spin text-sky-400" />
                <span className="text-xs text-slate-400">Đang phân tích...</span>
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-2.5 text-xs text-rose-400">
              {error}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Quick prompts + input */}
        <div className="border-t border-slate-700/60 px-5 py-4 space-y-3 bg-slate-900/80">
          <QuickPrompts onSelect={(msg) => { setInput(''); sendMessage(msg); }} disabled={isLoading} />

          <div className="flex gap-2">
            <textarea
              ref={inputRef}
              id="copilot-input"
              rows={2}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKey}
              disabled={isLoading}
              placeholder="Nhập câu hỏi về năng lượng... (Enter để gửi)"
              className="flex-1 resize-none rounded-xl border border-slate-700 bg-slate-800/60 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 outline-none transition focus:border-emerald-500/60 focus:ring-1 focus:ring-emerald-500/30 disabled:opacity-50"
            />
            <button
              id="copilot-send-btn"
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className="flex flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 px-4 text-white shadow-lg shadow-emerald-500/20 transition hover:from-emerald-400 hover:to-teal-500 disabled:opacity-40"
              title="Gửi (Enter)"
            >
              {isLoading ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
