const express = require('express');
const { z } = require('zod');
const { callAIService, AI_SERVICE_URL } = require('../utils/aiClient');
const prisma = require('../db');

const router = express.Router();

const ChatMessageSchema = z.object({
  role: z.string(),
  content: z.string(),
});

const CopilotChatSchema = z.object({
  message: z.string().min(1),
  building_id: z.string().default('office_tower_01'),
  history: z.array(ChatMessageSchema).default([]),
});

// POST /api/v1/copilot/chat
router.post('/chat', async (req, res, next) => {
  try {
    const body = CopilotChatSchema.parse(req.body);

    // Call AI service copilot endpoint
    const aiResponse = await callAIService('/internal/copilot/chat', {
      method: 'POST',
      body,
    });

    // Asynchronously record user and assistant messages into PostgreSQL conversations
    try {
      const sessionId = `sess_${body.building_id}_${new Date().toISOString().slice(0, 10)}`;
      await prisma.conversation.createMany({
        data: [
          {
            building_id: body.building_id,
            session_id: sessionId,
            role: 'user',
            message: body.message,
          },
          {
            building_id: body.building_id,
            session_id: sessionId,
            role: 'assistant',
            message: aiResponse.reply || '',
          },
        ],
      });
    } catch (dbErr) {
      console.warn('Could not record conversation in DB:', dbErr.message);
    }

    res.json(aiResponse);
  } catch (err) {
    next(err);
  }
});

// POST /api/v1/copilot/chat/stream
router.post('/chat/stream', async (req, res, next) => {
  let body;
  try {
    body = CopilotChatSchema.parse(req.body);
  } catch (err) {
    return next(err);
  }

  const aiUrl = `${AI_SERVICE_URL}/internal/copilot/chat/stream`;
  const internalApiKey = process.env.INTERNAL_API_KEY || '';
  const abortController = new AbortController();

  req.on('close', () => {
    abortController.abort();
  });

  let upstreamResponse;
  try {
    upstreamResponse = await fetch(aiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-Token': internalApiKey,
      },
      body: JSON.stringify(body),
      signal: abortController.signal,
    });
  } catch (err) {
    return res.status(502).json({ error: `AI service unreachable: ${err.message}` });
  }

  if (!upstreamResponse.ok) {
    return res.status(502).json({ error: `AI service responded with status ${upstreamResponse.status}` });
  }

  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'X-Accel-Buffering': 'no',
  });

  let fullReply = '';
  let buffer = '';

  try {
    const reader = upstreamResponse.body.getReader ? upstreamResponse.body.getReader() : null;
    if (reader) {
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunkText = decoder.decode(value, { stream: true });
        res.write(chunkText);
        buffer += chunkText;

        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const parsed = JSON.parse(line.slice(6));
              if (parsed.reply) {
                fullReply = parsed.reply;
              }
            } catch {}
          }
        }
      }
    } else if (upstreamResponse.body.on) {
      upstreamResponse.body.on('data', (chunk) => {
        const text = chunk.toString();
        res.write(chunk);
        buffer += text;
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const parsed = JSON.parse(line.slice(6));
              if (parsed.reply) {
                fullReply = parsed.reply;
              }
            } catch {}
          }
        }
      });
      await new Promise((resolve, reject) => {
        upstreamResponse.body.on('end', resolve);
        upstreamResponse.body.on('error', reject);
      });
    }

    if (fullReply) {
      try {
        const sessionId = `sess_${body.building_id}_${new Date().toISOString().slice(0, 10)}`;
        await prisma.conversation.createMany({
          data: [
            {
              building_id: body.building_id,
              session_id: sessionId,
              role: 'user',
              message: body.message,
            },
            {
              building_id: body.building_id,
              session_id: sessionId,
              role: 'assistant',
              message: fullReply,
            },
          ],
        });
      } catch (dbErr) {
        console.warn('Could not record conversation in DB:', dbErr.message);
      }
    }

    res.end();
  } catch (err) {
    if (err.name !== 'AbortError') {
      console.warn('[CopilotStream] Relay error:', err.message);
    }
    if (!res.writableEnded) {
      res.end();
    }
  }
});

// GET /api/v1/copilot/experiment-stats
router.get('/experiment-stats', async (req, res, next) => {
  try {
    const stats = await callAIService('/internal/copilot/experiment-stats');
    res.json(stats);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
