const express = require('express');
const { z } = require('zod');
const { callAIService } = require('../utils/aiClient');
const prisma = require('../db');
const { randomUUID } = require('crypto');

const router = express.Router();

const ChatMessageSchema = z.object({
  role: z.enum(['user', 'assistant']),
  content: z.string().max(20000),
});

const CopilotChatSchema = z.object({
  message: z.string().min(1).max(20000),
  building_id: z.string().min(1).max(50).default('office_tower_01'),
  session_id: z.string().uuid().optional(),
  history: z.array(ChatMessageSchema).max(50).default([]),
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

    const sessionId = body.session_id || randomUUID();
    let conversationSaved = false;
    // Recording is best-effort; expose its result instead of silently losing history.
    try {
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
      conversationSaved = true;
    } catch (dbErr) {
      // Non-fatal if DB conversation recording fails
      console.warn('Could not record conversation in DB:', dbErr.message);
    }

    res.json({ ...aiResponse, session_id: sessionId, conversation_saved: conversationSaved });
  } catch (err) {
    next(err);
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
