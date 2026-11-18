import { useEffect, useRef, useState } from 'react';
import { X, Send, Trash2, Loader2, Square, RotateCcw } from 'lucide-react';
import BrandMark from '../layout/BrandMark';
import ChatMessage from './ChatMessage';
import QuickPrompts from './QuickPrompts';
export default function CopilotDrawer({
  isOpen,
  onClose,
  messages = [],
  isLoading = false,
  error = null,
  sendMessage,
  stopStreaming,
  retry,
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
          className="fixed inset-0 z-30 bg-black/40 transition-opacity"
          onClick={onClose}
        />
      )}

      {/* Drawer panel */}
      <aside
        aria-label="EcoTrack Copilot"
        className={`fixed right-0 top-0 z-40 flex h-full w-full flex-col border-l border-line-strong bg-ground shadow-[-24px_0_48px_-24px_rgba(14,30,29,0.35)] transition-transform duration-300 ease-out sm:w-[420px] lg:w-[480px] ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between bg-shell px-5 py-3.5 text-shell-ink">
          <div className="flex items-center gap-3">
            <BrandMark size={24} />
            <div>
              <p className="text-sm font-bold text-white">EcoTrack Copilot</p>
              <p className="flex items-center gap-1.5 text-xs text-shell-muted">
                <span className="h-1.5 w-1.5 rounded-full bg-[#5fd39a]" aria-hidden="true" />
                Sẵn sàng hỗ trợ
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              id="copilot-clear-btn"
              onClick={clearHistory}
              className="btn btn-shell btn-sm px-2"
              title="Xóa lịch sử hội thoại"
              aria-label="Xóa lịch sử hội thoại"
            >
              <Trash2 size={14} aria-hidden="true" />
            </button>
            <button
              id="copilot-close-btn"
              onClick={onClose}
              className="btn btn-shell btn-sm px-2"
              title="Đóng"
              aria-label="Đóng Copilot"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          {messages.map((m, i) => <ChatMessage key={i} message={m} />)}

          {isLoading && (
            <div className="flex items-center justify-between gap-3 text-xs text-muted" role="status">
              <span className="flex items-center gap-2">
                <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                Đang trả lời...
              </span>
              {stopStreaming && (
                <button id="copilot-stop-btn" onClick={stopStreaming} className="btn btn-quiet btn-sm" title="Dừng phản hồi">
                  <Square size={11} aria-hidden="true" />
                  <span>Dừng</span>
                </button>
              )}
            </div>
          )}

          {error && (
            <div role="alert" className="flex items-center justify-between rounded-md border border-crit/30 bg-crit-bg px-4 py-2.5 text-xs text-crit">
              <span>{error}</span>
              {retry && (
                <button id="copilot-retry-btn" onClick={retry} className="ml-2 flex items-center gap-1 font-semibold underline">
                  <RotateCcw size={12} aria-hidden="true" />
                  <span>Thử lại</span>
                </button>
              )}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="space-y-3 border-t border-line-strong bg-panel px-5 py-4">
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
              aria-label="Câu hỏi cho Copilot"
              placeholder="Nhập câu hỏi về năng lượng... (Enter để gửi)"
              className="field flex-1 resize-none"
            />
            {isLoading && stopStreaming ? (
              <button
                id="copilot-stop-input-btn"
                onClick={stopStreaming}
                className="btn btn-primary px-4"
                title="Dừng tạo phản hồi"
                aria-label="Dừng"
              >
                <Square size={16} aria-hidden="true" />
              </button>
            ) : (
              <button
                id="copilot-send-btn"
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
                className="btn btn-primary px-4"
                title="Gửi (Enter)"
                aria-label="Gửi"
              >
                {isLoading ? <Loader2 size={17} className="animate-spin" aria-hidden="true" /> : <Send size={17} aria-hidden="true" />}
              </button>
            )}
          </div>
        </div>
      </aside>
    </>
  );
}
