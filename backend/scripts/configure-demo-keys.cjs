// Provision local demo credentials without printing them or bundling them in the UI.
const fs = require('fs');
const path = require('path');
const { randomBytes } = require('crypto');
const dotenv = require('dotenv');
const root = path.resolve(__dirname, '../..');
const files = [path.join(root, '.env'), path.join(root, 'backend/.env')];
const contents = files.map((file) => fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '');
const parsed = contents.map((content) => dotenv.parse(content));
const placeholder = (value) => !value || value === 'ecotrack_ingest_secret_2026'
  || /^(change-me|replace-with)/.test(value);

for (const name of ['INGEST_API_KEY', 'OPERATOR_API_KEY']) {
  const existing = parsed.map((env) => env[name]).find((value) => !placeholder(value));
  const generated = existing || randomBytes(32).toString('hex');
  for (let i = 0; i < files.length; i += 1) {
    if (!placeholder(parsed[i][name])) continue;
    const line = new RegExp(`^${name}=.*$`, 'm');
    contents[i] = line.test(contents[i]) ? contents[i].replace(line, `${name}=${generated}`)
      : `${contents[i].trimEnd()}\n${name}=${generated}\n`;
  }
}
files.forEach((file, index) => fs.writeFileSync(file, contents[index]));
console.log('Local demo API keys configured in .env and backend/.env; existing custom keys preserved.');
