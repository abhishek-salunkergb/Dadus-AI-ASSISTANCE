/* ========================================================
   DADUS - Personal AI Operating Assistant Frontend Logic
   ======================================================== */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const messagesContainer = document.getElementById('messagesContainer');
  const chatForm = document.getElementById('chatForm');
  const userInput = document.getElementById('userInput');
  const micBtn = document.getElementById('micBtn');
  const voiceWave = document.getElementById('voiceWave');
  const audioPlayer = document.getElementById('audioPlayer');
  const liveStatusBadge = document.getElementById('liveStatusBadge');
  const ttsToggleBtn = document.getElementById('ttsToggleBtn');
  const confirmationBanner = document.getElementById('confirmationBanner');
  const confirmationMessage = document.getElementById('confirmationMessage');
  const confirmYesBtn = document.getElementById('confirmYesBtn');
  const confirmNoBtn = document.getElementById('confirmNoBtn');
  const clarificationBanner = document.getElementById('clarificationBanner');
  const clarificationPrompt = document.getElementById('clarificationPrompt');
  const clarificationOptions = document.getElementById('clarificationOptions');

  let audioEnabled = true;
  let activeConfirmationId = null;

  // Tab Navigation
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const tabId = `tab-${btn.dataset.tab}`;
      const pane = document.getElementById(tabId);
      if (pane) pane.classList.add('active');

      if (btn.dataset.tab === 'schedule') loadSchedule();
      if (btn.dataset.tab === 'memory') loadMemories();
      if (btn.dataset.tab === 'audit') loadAuditLogs();
    });
  });

  // Toggle Audio
  ttsToggleBtn.addEventListener('click', () => {
    audioEnabled = !audioEnabled;
    ttsToggleBtn.classList.toggle('active', audioEnabled);
    ttsToggleBtn.querySelector('.btn-label').textContent = audioEnabled ? 'Audio On' : 'Audio Off';
  });

  // Quick Command Chips
  document.querySelectorAll('.command-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      userInput.value = chip.dataset.cmd;
      chatForm.dispatchEvent(new Event('submit'));
    });
  });

  // Update Status Badge
  function setStatus(statusText, className) {
    liveStatusBadge.className = `status-badge ${className}`;
    liveStatusBadge.querySelector('.badge-label').textContent = statusText;
  }

  // Append Message to UI
  function appendMessage(text, role, toolData = null) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}-message`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'user' ? 'U' : 'D';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    
    const p = document.createElement('p');
    p.textContent = text;
    bubble.appendChild(p);

    if (toolData && toolData.tool_called) {
      const tbadge = document.createElement('div');
      tbadge.className = 'tool-badge';
      tbadge.innerHTML = `<span>⚡ Tool: <strong>${escapeHtml(toolData.tool_called)}</strong></span>`;
      bubble.appendChild(tbadge);
    }

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(bubble);
    messagesContainer.appendChild(msgDiv);

    // Scroll to bottom
    const viewport = document.querySelector('.chat-viewport');
    viewport.scrollTop = viewport.scrollHeight;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Send Chat Message
  async function sendMessage(text) {
    if (!text.trim()) return;

    appendMessage(text, 'user');
    userInput.value = '';
    setStatus('Understanding...', 'status-understanding');

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: 'desktop_ui',
          speak_response: audioEnabled
        })
      });

      const data = await resp.json();

      // Check if confirmation is required
      if (data.needs_confirmation) {
        setStatus('Waiting for confirmation...', 'status-confirmation');
        activeConfirmationId = data.confirmation_id;
        confirmationMessage.textContent = data.text;
        confirmationBanner.classList.remove('hidden');
      } else {
        confirmationBanner.classList.add('hidden');
      }

      // Check if clarification is needed (e.g. music apps)
      if (data.needs_clarification && data.options) {
        setStatus('Waiting for choice...', 'status-understanding');
        clarificationPrompt.textContent = data.text;
        clarificationOptions.innerHTML = '';
        data.options.forEach(opt => {
          const optBtn = document.createElement('button');
          optBtn.className = 'option-btn';
          optBtn.textContent = opt;
          optBtn.addEventListener('click', () => {
            clarificationBanner.classList.add('hidden');
            sendMessage(opt);
          });
          clarificationOptions.appendChild(optBtn);
        });
        clarificationBanner.classList.remove('hidden');
      } else {
        clarificationBanner.classList.add('hidden');
      }

      // Display response
      appendMessage(data.text, 'assistant', { tool_called: data.tool_called });

      // Play audio if available and audio enabled
      if (audioEnabled && data.audio_url) {
        audioPlayer.src = data.audio_url;
        audioPlayer.play().catch(e => console.log('Audio autoplay prevented:', e));
      }

      if (!data.needs_confirmation && !data.needs_clarification) {
        setStatus('Ready', 'status-ready');
      }

    } catch (err) {
      console.error('API error:', err);
      appendMessage('Boss, I had trouble connecting to the backend service.', 'assistant');
      setStatus('Error', 'status-confirmation');
    }
  }

  // Handle Form Submit
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    sendMessage(userInput.value);
  });

  // Handle Confirmation Buttons
  confirmYesBtn.addEventListener('click', async () => {
    if (!activeConfirmationId) return;
    confirmationBanner.classList.add('hidden');
    setStatus('Executing...', 'status-executing');

    try {
      const resp = await fetch('/api/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation_id: activeConfirmationId, confirmed: true })
      });
      const data = await resp.json();
      appendMessage(data.message, 'assistant');
      setStatus('Ready', 'status-ready');
    } catch (err) {
      setStatus('Error', 'status-confirmation');
    }
  });

  confirmNoBtn.addEventListener('click', async () => {
    if (!activeConfirmationId) return;
    confirmationBanner.classList.add('hidden');
    try {
      const resp = await fetch('/api/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation_id: activeConfirmationId, confirmed: false })
      });
      const data = await resp.json();
      appendMessage(data.message, 'assistant');
      setStatus('Ready', 'status-ready');
    } catch (err) {
      setStatus('Ready', 'status-ready');
    }
  });

  // Push to Talk / Mic Button
  micBtn.addEventListener('click', async () => {
    micBtn.classList.add('recording');
    voiceWave.classList.remove('hidden');
    setStatus('Listening...', 'status-listening');

    try {
      const resp = await fetch('/api/voice/listen', { method: 'POST' });
      const data = await resp.json();

      micBtn.classList.remove('recording');
      voiceWave.classList.add('hidden');

      if (data.success && data.transcription) {
        appendMessage(data.transcription, 'user');
        if (data.response) {
          appendMessage(data.response.text, 'assistant', { tool_called: data.response.tool_called });
        }
        setStatus('Ready', 'status-ready');
      } else {
        setStatus('Ready', 'status-ready');
      }
    } catch (err) {
      micBtn.classList.remove('recording');
      voiceWave.classList.add('hidden');
      setStatus('Ready', 'status-ready');
    }
  });

  // Load Schedule & Reminders
  async function loadSchedule() {
    const remList = document.getElementById('remindersList');
    const evtList = document.getElementById('eventsList');
    remList.innerHTML = '<li class="loading-item">Fetching reminders...</li>';
    evtList.innerHTML = '<li class="loading-item">Fetching schedule...</li>';

    try {
      const resp = await fetch('/api/schedule');
      const data = await resp.json();

      if (data.reminders.length === 0) {
        remList.innerHTML = '<li class="loading-item">No active reminders.</li>';
      } else {
        remList.innerHTML = data.reminders.map(r => `
          <li class="schedule-item-row">
            <div class="item-title">${escapeHtml(r.title)}</div>
            <div class="item-time">⏰ ${new Date(r.target_time).toLocaleString()} (${r.status})</div>
          </li>
        `).join('');
      }

      if (data.schedule_items.length === 0) {
        evtList.innerHTML = '<li class="loading-item">No schedule items today.</li>';
      } else {
        evtList.innerHTML = data.schedule_items.map(s => `
          <li class="schedule-item-row">
            <div class="item-title">${escapeHtml(s.title)}</div>
            <div class="item-time">📅 ${new Date(s.start_time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
          </li>
        `).join('');
      }
    } catch (e) {
      remList.innerHTML = '<li class="loading-item">Failed to load schedule.</li>';
    }
  }

  // Load Memories
  async function loadMemories() {
    const memList = document.getElementById('memoryList');
    memList.innerHTML = '<div class="loading-item">Fetching memories...</div>';

    try {
      const resp = await fetch('/api/memory');
      const data = await resp.json();

      if (data.memories.length === 0) {
        memList.innerHTML = '<div class="loading-item">No stored memories yet. Tell DADUS "Remember that I prefer Spotify"</div>';
      } else {
        memList.innerHTML = data.memories.map(m => `
          <div class="memory-row">
            <div>
              <div class="memory-key">${escapeHtml(m.key)}</div>
              <div class="memory-val">${escapeHtml(m.value)}</div>
            </div>
            <button class="memory-del-btn" data-key="${escapeHtml(m.key)}">✕</button>
          </div>
        `).join('');

        document.querySelectorAll('.memory-del-btn').forEach(btn => {
          btn.addEventListener('click', async () => {
            await fetch(`/api/memory/${encodeURIComponent(btn.dataset.key)}`, { method: 'DELETE' });
            loadMemories();
          });
        });
      }
    } catch (e) {
      memList.innerHTML = '<div class="loading-item">Failed to load memories.</div>';
    }
  }

  // Load Audit Logs
  async function loadAuditLogs() {
    const tbody = document.getElementById('auditTableBody');
    tbody.innerHTML = '<tr><td colspan="6" class="loading-item">Fetching audit history...</td></tr>';

    try {
      const resp = await fetch('/api/logs?limit=25');
      const data = await resp.json();

      if (data.logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="loading-item">No tool activity logged yet.</td></tr>';
      } else {
        tbody.innerHTML = data.logs.map(l => {
          let tagClass = 'tag-success';
          if (l.status === 'BLOCKED' || l.status === 'FAILED') tagClass = 'tag-blocked';
          if (l.status === 'CONFIRMATION_REQUIRED') tagClass = 'tag-pending';

          return `
            <tr>
              <td>${new Date(l.timestamp).toLocaleTimeString()}</td>
              <td>${escapeHtml(l.user_input)}</td>
              <td><code>${escapeHtml(l.tool_name || 'None')}</code></td>
              <td>${escapeHtml(l.permission_level)}</td>
              <td><span class="status-tag ${tagClass}">${escapeHtml(l.status)}</span></td>
              <td>${escapeHtml(l.result_summary || '')}</td>
            </tr>
          `;
        }).join('');
      }
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="6" class="loading-item">Failed to load logs.</td></tr>';
    }
  }

  // Refresh buttons
  document.getElementById('refreshScheduleBtn')?.addEventListener('click', loadSchedule);
  document.getElementById('refreshMemoryBtn')?.addEventListener('click', loadMemories);
  document.getElementById('refreshAuditBtn')?.addEventListener('click', loadAuditLogs);
  document.getElementById('systemStatusBtn')?.addEventListener('click', () => {
    sendMessage('system status');
  });
});
