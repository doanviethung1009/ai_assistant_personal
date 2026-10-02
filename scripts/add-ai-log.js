const fs = require('fs');
const path = require('path');

const dataDir = process.env.DATA_DIR ? path.resolve(process.env.DATA_DIR) : path.resolve(__dirname, '..', 'data');
const jsonFile = path.join(dataDir, 'ai-logs.json');

const args = process.argv.slice(2);
if (args.length < 3) {
  console.error("Usage: node add-ai-log.js <category> <prompt> <action_and_response>");
  process.exit(1);
}

const [category, prompt, action] = args;

let data = { schema_version: 1, exported_at: new Date().toISOString(), ai_logs: [] };

try {
  if (fs.existsSync(jsonFile)) {
    const raw = fs.readFileSync(jsonFile, 'utf8');
    data = JSON.parse(raw);
    if (!data.ai_logs) data.ai_logs = [];
  }
} catch (err) {
  console.error("Lỗi khi đọc file JSON:", err.message);
  process.exit(1);
}

const newLog = {
  id: require('crypto').randomUUID(),
  category: category.replace(/[\[\]]/g, ''),
  prompt: prompt,
  response: action,
  created_at: new Date().toISOString()
};

data.ai_logs.push(newLog);
data.exported_at = new Date().toISOString();

try {
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  fs.writeFileSync(jsonFile, JSON.stringify(data, null, 2), 'utf8');
  console.log(`Đã ghi thành công log vào ${jsonFile}`);
} catch (err) {
  console.error("Lỗi khi ghi file JSON:", err.message);
  process.exit(1);
}
