import { useState, useRef, useCallback } from 'react';
import { sendCopilotMessage } from '../services/api';

export function useCopilot() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '👋 Xin chào! Tôi là **EcoTrack Copilot** — trợ lý năng lượng thông minh.\n\nTôi có thể giúp anh/chị:\n- 🔍 Chẩn đoán nguyên nhân sự cố điện bất thường\n- 📈 Phân tích dự báo phụ tải 24 giờ tới\n- 💡 Đề xuất tối ưu chi phí điện năng\n\nHãy hỏi tôi bất cứ điều gì về hệ thống năng lượng tòa nhà!',
      tools_used: [],
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError]         = useState(null);
  const historyRef = useRef([]);
  const sessionRef = useRef(null);
  const generationRef = useRef(0);
  const pendingRef = useRef(false);

  const sendMessage = useCallback(async (userMessage) => {
    if (!userMessage.trim() || pendingRef.current) return;
    pendingRef.current = true;
    const generation = generationRef.current;

    const userEntry = { role: 'user', content: userMessage, tools_used: [] };
    setMessages(prev => [...prev, userEntry]);
    setIsLoading(true);
    setError(null);

    try {
      const data = await sendCopilotMessage(
        userMessage,
        'office_tower_01',
        historyRef.current,
        sessionRef.current || undefined
      );
      if (generation !== generationRef.current) return;
      sessionRef.current = data.session_id;
      const assistantEntry = {
        role: 'assistant',
        content: data.reply,
        tools_used: data.tools_used || [],
      };
      setMessages(prev => [...prev, assistantEntry]);
      historyRef.current = [
        ...historyRef.current,
        { role: 'user', content: userMessage },
        { role: 'assistant', content: data.reply },
      ].slice(-10); // Keep last 5 turns (10 entries)
    } catch (err) {
      if (generation !== generationRef.current) return;
      setError('Không thể kết nối đến Copilot. Vui lòng thử lại.');
    } finally {
      if (generation === generationRef.current) {
        pendingRef.current = false;
        setIsLoading(false);
      }
    }
  }, []);

  const clearHistory = useCallback(() => {
    generationRef.current += 1;
    sessionRef.current = null;
    pendingRef.current = false;
    setIsLoading(false);
    setError(null);
    historyRef.current = [];
    setMessages([{
      role: 'assistant',
      content: '🔄 Đã xóa lịch sử hội thoại. Tôi sẵn sàng hỗ trợ anh/chị!',
      tools_used: [],
    }]);
  }, []);

  return { messages, isLoading, error, sendMessage, clearHistory };
}
