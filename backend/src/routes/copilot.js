const express = require('express');
const { z } = require('zod');
const { callAIService } = require('../utils/aiClient');
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
      // Non-fatal if DB conversation recording fails
      console.warn('Could not record conversation in DB:', dbErr.message);
    }

    res.json(aiResponse);
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
