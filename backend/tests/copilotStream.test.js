import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import request from 'supertest';
import app from '../src/app';

describe('Story 3.5: Copilot SSE Streaming Relay', () => {
  const originalFetch = global.fetch;
  let mockCreateMany;

  beforeEach(() => {
    mockCreateMany = vi.fn().mockResolvedValue({ count: 2 });
    global.__mockPrisma = {
      conversation: {
        createMany: mockCreateMany,
      },
    };
  });

  afterEach(() => {
    global.fetch = originalFetch;
    delete global.__mockPrisma;
    vi.restoreAllMocks();
  });

  it('relays token, sources, and done events unbuffered with correct SSE headers', async () => {
    const sseChunks = [
      'event: token\ndata: {"token": "Xin "}\n\n',
      'event: token\ndata: {"token": "chào!"}\n\n',
      'event: sources\ndata: {"sources": [{"title": "EVN Tariff", "source": "evn.md", "snippet": "Giá cao điểm 3100đ"}], "tools_used": ["domain_knowledge"], "engine": "heuristic"}\n\n',
      'event: done\ndata: {"reply": "Xin chào!"}\n\n',
    ];

    const stream = new ReadableStream({
      start(controller) {
        for (const chunk of sseChunks) {
          controller.enqueue(new TextEncoder().encode(chunk));
        }
        controller.close();
      },
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'text/event-stream' }),
      body: stream,
    });

    const res = await request(app)
      .post('/api/v1/copilot/chat/stream')
      .send({
        message: 'Giá điện giờ cao điểm?',
        building_id: 'office_tower_01',
        history: [],
      });

    expect(res.status).toBe(200);
    expect(res.headers['content-type']).toContain('text/event-stream');
    expect(res.text).toContain('event: token\ndata: {"token": "Xin "}');
    expect(res.text).toContain('event: token\ndata: {"token": "chào!"}');
    expect(res.text).toContain('event: sources');
    expect(res.text).toContain('event: done');

    // Verify upstream request headers
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/internal/copilot/chat/stream'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'X-Internal-Token': process.env.INTERNAL_API_KEY || '',
        }),
      })
    );

    // Verify DB persistence of conversation
    expect(mockCreateMany).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.arrayContaining([
          expect.objectContaining({ role: 'user', message: 'Giá điện giờ cao điểm?' }),
          expect.objectContaining({ role: 'assistant', message: 'Xin chào!' }),
        ]),
      })
    );
  });

  it('returns 502 before sending stream headers when AI service is unreachable', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));

    const res = await request(app)
      .post('/api/v1/copilot/chat/stream')
      .send({
        message: 'Kiểm tra năng lượng',
        building_id: 'office_tower_01',
      });

    expect(res.status).toBe(502);
    expect(res.headers['content-type']).toContain('application/json');
    expect(res.body.error).toContain('AI service unreachable');
  });

  it('returns 502 when AI service responds with an error status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });

    const res = await request(app)
      .post('/api/v1/copilot/chat/stream')
      .send({
        message: 'Kiểm tra năng lượng',
      });

    expect(res.status).toBe(502);
    expect(res.body.error).toContain('AI service responded with status 500');
  });
});
