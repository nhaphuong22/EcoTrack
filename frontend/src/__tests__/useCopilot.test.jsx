import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCopilot } from '../hooks/useCopilot';
import { sendCopilotMessage } from '../services/api';

vi.mock('../services/api', () => ({ sendCopilotMessage: vi.fn() }));
beforeEach(() => vi.resetAllMocks());

describe('Copilot session lifecycle', () => {
  it('reuses a server session and starts a different session after clearing', async () => {
    sendCopilotMessage.mockResolvedValue({ reply: 'Hello', session_id: 'session-a' });
    const { result } = renderHook(() => useCopilot());
    await act(async () => result.current.sendMessage('First'));
    await act(async () => result.current.sendMessage('Second'));
    expect(sendCopilotMessage.mock.calls[1][3]).toBe('session-a');
    act(() => result.current.clearHistory());
    await act(async () => result.current.sendMessage('New chat'));
    expect(sendCopilotMessage.mock.calls[2][2]).toEqual([]);
    expect(sendCopilotMessage.mock.calls[2][3]).toBeUndefined();
  });

  it('does not restore a cleared chat when a previous request completes late', async () => {
    let complete;
    sendCopilotMessage.mockReturnValue(new Promise((resolve) => { complete = resolve; }));
    const { result } = renderHook(() => useCopilot());
    let pending;
    act(() => { pending = result.current.sendMessage('Old chat'); });
    act(() => result.current.clearHistory());
    await act(async () => { complete({ reply: 'Late answer', session_id: 'old' }); await pending; });
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].content).not.toBe('Late answer');
    expect(result.current.isLoading).toBe(false);
  });
});
