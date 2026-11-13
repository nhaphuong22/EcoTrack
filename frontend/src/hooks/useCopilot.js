import { useState, useRef, useCallback } from 'react';
import { streamCopilotMessage, sendCopilotMessage } from '../services/api';

export function useCopilot() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '👋 Xin chào! Tôi là **EcoTrack Copilot** — trợ lý năng lượng thông minh.\n\nTôi có thể giúp anh/chị:\n- 🔍 Chẩn đoán nguyên nhân sự cố điện bất thường\n- 📈 Phân tích dự báo phụ tải 24 giờ tới\n- 💡 Đề xuất tối ưu chi phí điện năng\n\nHãy hỏi tôi bất cứ điều gì về hệ thống năng lượng tòa nhà!',
      tools_used: [],
      sources: [],
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const historyRef = useRef([]);
  const abortControllerRef = useRef(null);
  const lastUserMessageRef = useRef('');

  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
  }, []);

  const sendMessage = useCallback(async (userMessage) => {
    if (!userMessage || !userMessage.trim()) return;

    lastUserMessageRef.current = userMessage;
    const userEntry = { role: 'user', content: userMessage, tools_used: [] };
    const initialAssistantEntry = {
      role: 'assistant',
      content: '',
      tools_used: [],
      sources: [],
    };

    setMessages((prev) => [...prev, userEntry, initialAssistantEntry]);
    setIsLoading(true);
    setError(null);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    let accumulatedText = '';
    let sourcesData = [];
    let toolsUsed = [];
    let engineUsed = 'heuristic';

    try {
      if (typeof ReadableStream !== 'undefined' && typeof TextDecoder !== 'undefined') {
        await streamCopilotMessage({
          message: userMessage,
          buildingId: 'office_tower_01',
          history: historyRef.current,
          signal: controller.signal,
          onToken: (tok) => {
            accumulatedText += tok;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === 'assistant') {
                next[next.length - 1] = {
                  ...last,
                  content: accumulatedText,
                };
              }
              return next;
            });
          },
          onSources: (src) => {
            sourcesData = src.sources || [];
            toolsUsed = src.tools_used || [];
            engineUsed = src.engine || 'heuristic';
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === 'assistant') {
                next[next.length - 1] = {
                  ...last,
                  sources: sourcesData,
                  tools_used: toolsUsed,
                  engine: engineUsed,
                };
              }
              return next;
            });
          },
          onDone: (done) => {
            if (done.reply) accumulatedText = done.reply;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === 'assistant') {
                next[next.length - 1] = {
                  ...last,
                  content: accumulatedText,
                  sources: sourcesData,
                  tools_used: toolsUsed,
                  engine: engineUsed,
                };
              }
              return next;
            });
            historyRef.current = [
              ...historyRef.current,
              { role: 'user', content: userMessage },
              { role: 'assistant', content: accumulatedText },
            ].slice(-10);
          },
          onError: (errText) => {
            setError(errText);
          },
        });
      } else {
        // Fallback for non-stream environments
        const data = await sendCopilotMessage(
          userMessage,
          'office_tower_01',
          historyRef.current
        );
        accumulatedText = data.reply;
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            role: 'assistant',
            content: data.reply,
            tools_used: data.tools_used || [],
            sources: data.sources || [],
            engine: data.engine || 'heuristic',
          };
          return next;
        });
        historyRef.current = [
          ...historyRef.current,
          { role: 'user', content: userMessage },
          { role: 'assistant', content: data.reply },
        ].slice(-10);
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        // User clicked Stop ("Dừng") -> retain partial answer
      } else {
        if (!accumulatedText) {
          try {
            const data = await sendCopilotMessage(
              userMessage,
              'office_tower_01',
              historyRef.current
            );
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = {
                role: 'assistant',
                content: data.reply,
                tools_used: data.tools_used || [],
                sources: data.sources || [],
                engine: data.engine || 'heuristic',
              };
              return next;
            });
            historyRef.current = [
              ...historyRef.current,
              { role: 'user', content: userMessage },
              { role: 'assistant', content: data.reply },
            ].slice(-10);
            return;
          } catch {
            setError('Không thể kết nối đến Copilot. Vui lòng thử lại.');
          }
        } else {
          setError('Không thể kết nối đến Copilot. Vui lòng thử lại.');
        }
      }
    } finally {
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  }, []);

  const retry = useCallback(() => {
    if (lastUserMessageRef.current) {
      sendMessage(lastUserMessageRef.current);
    }
  }, [sendMessage]);

  const clearHistory = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    historyRef.current = [];
    setMessages([
      {
        role: 'assistant',
        content: '🔄 Đã xóa lịch sử hội thoại. Tôi sẵn sàng hỗ trợ anh/chị!',
        tools_used: [],
        sources: [],
      },
    ]);
  }, []);

  return { messages, isLoading, error, sendMessage, stopStreaming, retry, clearHistory };
}
