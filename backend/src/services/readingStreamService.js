const EventEmitter = require('events');

// ponytail: native EventEmitter for live stream push; no external broker needed
class ReadingStreamEmitter extends EventEmitter {}

if (!global.__readingEmitter) {
  global.__readingEmitter = new ReadingStreamEmitter();
  global.__readingEmitter.setMaxListeners(100);
}

const readingEmitter = global.__readingEmitter;

function broadcastReading(reading) {
  readingEmitter.emit('reading', reading);
}

module.exports = {
  readingEmitter,
  broadcastReading,
};
