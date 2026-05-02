const keyTable = document.getElementById('keyTable');
const keyNotice = document.getElementById('keyNotice');
const createKeyBtn = document.getElementById('createKey');
const sendPromptBtn = document.getElementById('sendPrompt');

createKeyBtn.addEventListener('click', () => {
  const name = document.getElementById('keyName').value.trim() || 'new-key';
  const row = document.createElement('tr');
  row.innerHTML = `<td>${name}</td><td>sk-****</td><td>Active</td>`;
  keyTable.appendChild(row);
  keyNotice.textContent = 'Key created successfully. Full key is shown only once in production flow.';
});

sendPromptBtn.addEventListener('click', () => {
  const prompt = document.getElementById('prompt').value.trim();
  const response = document.getElementById('responseBox');
  if (!prompt) {
    response.textContent = 'Please input prompt first.';
    return;
  }
  response.textContent = `Model: deepseek-chat\nPrompt: ${prompt}\n\nMock Response: 这是一个本地 UI 原型响应。`;
});
