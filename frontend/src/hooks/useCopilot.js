import { useState, useRef, useCallback } from 'react';
import { streamCopilotMessage, sendCopilotMessage } from '../services/api';

const GREETING = {
  role: 'assistant',
  content: '👋 Xin chào! Tôi là **EcoTrack Copilot** — trợ lý năng lượng thông minh.\n\nTôi có thể giúp anh/chị:\n- 🔍 Chẩn đoán nguyên nhân sự cố điện bất thường\n- 📈 Phân tích dự báo phụ tải 24 giờ tới\n- 💡 Đề xuất tối ưu chi phí điện năng\n\nHãy hỏi tôi bất cứ điều gì về hệ thống năng lượng tòa nhà!',
  tools_used: [],
  sources: [],
};

const CONNECT_ERROR = 'Không thể kết nối đến Copilot. Vui lòng thử lại.';

export function useCopilot() {
  const [messages, setMessages] = useState([GREETING]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const historyRef = useRef([]);
  const sessionRef = useRef(null);
  // Bumped on clear/stop so a late answer from an abandoned request is dropped.
  const generationRef = useRef(0);
  const pendingRef = useRef(false);
  const abortControllerRef = useRef(null);
  const lastUserMessageRef = useRef('');

  const abortCurrent = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  };

  const stopStreaming = useCallback(() => {
    abortCurrent();
    pendingRef.current = false;
    setIsLoading(false);
  }, []);

  const sendMessage = useCallback(async (userMessage) => {
    if (!userMessage || !userMessage.trim() || pendingRef.current) return;
    pendingRef.current = true;
    const generation = generationRef.current;
    const isCurrent = () => generation === generationRef.current;
    lastUserMessageRef.current = userMessage;

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: userMessage, tools_used: [] },
      { role: 'assistant', content: '', tools_used: [], sources: [] },
    ]);
    setIsLoading(true);
    setError(null);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Patch the assistant bubble that is being filled (always the last message).
    const patchLast = (patch) => {
      if (!isCurrent()) return;
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === 'assistant') next[next.length - 1] = { ...last, ...patch };
        return next;
      });
    };
    const remember = (reply) => {
      historyRef.current = [
        ...historyRef.current,
        { role: 'user', content: userMessage },
        { role: 'assistant', content: reply },
      ].slice(-10); // Keep last 5 turns (10 entries)
    };
    // Non-stream path; it is also the only one that carries the saved chat session.
    const sendWithoutStream = async () => {
      const data = await sendCopilotMessage(userMessage, 'office_tower_01', historyRef.current, sessionRef.current || undefined);
      if (!isCurrent()) return;
      sessionRef.current = data.session_id;
      patchLast({
        content: data.reply,
        tools_used: data.tools_used || [],
        sources: data.sources || [],
        engine: data.engine || 'heuristic',
      });
      remember(data.reply);
    };

    let text = '';
    let extras = { sources: [], tools_used: [], engine: 'heuristic' };

    try {
      if (typeof ReadableStream !== 'undefined' && typeof TextDecoder !== 'undefined') {
        await streamCopilotMessage({
          message: userMessage,
          buildingId: 'office_tower_01',
          history: historyRef.current,
          signal: controller.signal,
          onToken: (tok) => {
            text += tok;
            patchLast({ content: text });
          },
          onSources: (src) => {
            extras = {
              sources: src.sources || [],
              tools_used: src.tools_used || [],
              engine: src.engine || 'heuristic',
            };
            patchLast(extras);
          },
          onDone: (done) => {
            if (done.reply) text = done.reply;
            patchLast({ content: text, ...extras });
            if (isCurrent()) remember(text);
          },
          onError: (errText) => {
            if (isCurrent()) setError(errText);
          },
        });
      } else {
        await sendWithoutStream();
      }
    } catch (err) {
      if (err.name === 'AbortError' || !isCurrent()) {
        // User clicked Stop or cleared the chat: keep whatever arrived.
      } else if (!text) {
        try {
          await sendWithoutStream();
        } catch {
          if (isCurrent()) setError(CONNECT_ERROR);
        }
      } else {
        setError(CONNECT_ERROR);
      }
    } finally {
      if (isCurrent()) {
        abortControllerRef.current = null;
        pendingRef.current = false;
        setIsLoading(false);
      }
    }
  }, []);

  const retry = useCallback(() => {
    if (lastUserMessageRef.current) sendMessage(lastUserMessageRef.current);
  }, [sendMessage]);

  const clearHistory = useCallback(() => {
    generationRef.current += 1;
    abortCurrent();
    sessionRef.current = null;
    pendingRef.current = false;
    historyRef.current = [];
    setIsLoading(false);
    setError(null);
    setMessages([{ ...GREETING, content: '🔄 Đã xóa lịch sử hội thoại. Tôi sẵn sàng hỗ trợ anh/chị!' }]);
  }, []);

  return { messages, isLoading, error, sendMessage, stopStreaming, retry, clearHistory };
}
