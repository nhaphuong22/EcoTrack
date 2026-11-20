import { describe, it, expect, vi } from 'vitest';
const { waitForAI } = require('../../scripts/wait-for-ai.cjs');

describe('Development startup readiness', () => {
  it('waits for application health rather than a bound TCP port', async () => {
    const fetchImpl = vi.fn()
      .mockRejectedValueOnce(new Error('ECONNREFUSED'))
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'healthy' }) });
    let clock = 0;
    await waitForAI({ fetchImpl, now: () => clock, sleep: async (ms) => { clock += ms; } });
    expect(fetchImpl).toHaveBeenCalledTimes(3);
    expect(clock).toBe(2000);
  });

  it('fails within the deadline if the AI app never starts', async () => {
    let clock = 0;
    await expect(waitForAI({ timeoutMs: 2000, now: () => clock,
      fetchImpl: async () => { throw new Error('offline'); },
      sleep: async (ms) => { clock += ms; },
    })).rejects.toThrow('AI did not become ready');
    expect(clock).toBe(2000);
  });
});
