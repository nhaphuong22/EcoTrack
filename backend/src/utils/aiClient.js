const AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://localhost:8000';
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || 'ecotrack_internal_secret_2026';

class AIServiceError extends Error {
  constructor(message, status = 502, details = null) {
    super(message);
    this.name = 'AIServiceError';
    this.status = status;
    this.details = details;
  }
}

async function callAIService(path, options = {}) {
  const url = `${AI_SERVICE_URL}${path}`;
  const timeoutMs = options.timeout || 30000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const headers = {
    'Content-Type': 'application/json',
    'X-Internal-Token': INTERNAL_API_KEY,
    ...(options.headers || {}),
  };

  try {
    const response = await fetch(url, {
      method: options.method || 'GET',
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
      } catch {
        errorData = await response.text();
      }
      throw new AIServiceError(
        `AI Service responded with status ${response.status}`,
        response.status,
        errorData
      );
    }

    return await response.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      throw new AIServiceError('AI Service request timed out after 30s', 504);
    }
    if (err instanceof AIServiceError) {
      throw err;
    }
    throw new AIServiceError(`Failed to reach AI Service at ${url}: ${err.message}`, 502);
  }
}

module.exports = {
  callAIService,
  AIServiceError,
  AI_SERVICE_URL,
};
