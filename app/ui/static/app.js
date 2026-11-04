/**
 * ============================================================================
 * DADUS — Holographic AI Master Controller (app.js)
 * ----------------------------------------------------------------------------
 * Connects Three.js WebGL Hologram, Web Speech Recognition, Audio FFT,
 * and Backend REST & WebSocket APIs (/api/chat, /ws/voice-state, /api/confirm, etc.)
 * ============================================================================
 */

document.addEventListener('DOMContentLoaded', () => {

  // ==========================================================================
  // 1. DOM References
  // ==========================================================================
  const navItems = document.querySelectorAll('.nav-btn, .nav-item');
  const panelViews = document.querySelectorAll('.panel-view');
  const navHome = document.getElementById('navHome');
  const currentViewTitle = document.getElementById('currentViewTitle');
  const currentViewSubtitle = document.getElementById('currentViewSubtitle');

  const heroMicBtn = document.getElementById('heroMicBtn');
  const commandForm = document.getElementById('commandForm');
  const commandInput = document.getElementById('commandInput');
  const ttsAudioPlayer = document.getElementById('ttsAudioPlayer');

  const handsFreeBtn = document.getElementById('handsFreeBtn');
  const handsFreeLabel = document.getElementById('handsFreeLabel');
  const ttsToggleBtn = document.getElementById('ttsToggleBtn');
  const ttsToggleLabel = document.getElementById('ttsToggleLabel');
  const ttsIcon = document.getElementById('ttsIcon');
  const interruptBtn = document.getElementById('interruptBtn');

  const stateDot = document.getElementById('stateDot');
  const stateLabel = document.getElementById('stateLabel');
  const statePing = document.getElementById('statePing');
  const greetingText = document.getElementById('greetingText');
  const dynamicTranscript = document.getElementById('dynamicTranscript');
  const audioWaveVisualizer = document.getElementById('audioWaveVisualizer');
  const optionsContainer = document.getElementById('optionsContainer');
  const hologramStage = document.getElementById('hologramStage');

  const dialogueStream = document.getElementById('dialogueStream');
  const clearChatBtn = document.getElementById('clearChatBtn');

  const scheduleItemsList = document.getElementById('scheduleItemsList');
  const pendingTasksList = document.getElementById('pendingTasksList');
  const activeRemindersList = document.getElementById('activeRemindersList');
  const createTaskForm = document.getElementById('createTaskForm');
  const newTaskTitle = document.getElementById('newTaskTitle');
  const refreshTasksBtn = document.getElementById('refreshTasksBtn');

  const memoryStoreForm = document.getElementById('memoryStoreForm');
  const memoryKeyInput = document.getElementById('memoryKey');
  const memoryValueInput = document.getElementById('memoryValue');
  const memoryCategorySelect = document.getElementById('memoryCategory');
  const memoryCardsList = document.getElementById('memoryCardsList');
  const searchMemoryInput = document.getElementById('searchMemoryInput');
  const refreshMemoryBtn = document.getElementById('refreshMemoryBtn');

  const auditLogsBody = document.getElementById('auditLogsBody');
  const refreshLogsBtn = document.getElementById('refreshLogsBtn');

  const toolsGrid = document.getElementById('toolsGrid');
  const toolStatsBadge = document.getElementById('toolStatsBadge');

  const confirmModal = document.getElementById('confirmModal');
  const confirmPrompt = document.getElementById('confirmPrompt');
  const modalApproveBtn = document.getElementById('modalApproveBtn');
  const modalRejectBtn = document.getElementById('modalRejectBtn');

  // ==========================================================================
  // 2. Application State
  // ==========================================================================
  let audioEnabled = true;
  let handsFreeEnabled = true;
  let activeConfirmationId = null;
  const sessionId = 'session_' + Math.random().toString(36).substring(2, 9);
  let memoryCache = [];

  // Set Dynamic Contextual Greeting
  function updateGreeting() {
    if (!greetingText) return;
    const hour = new Date().getHours();
    let timeGreeting = "Good evening";
    if (hour >= 5 && hour < 12) timeGreeting = "Good morning";
    else if (hour >= 12 && hour < 17) timeGreeting = "Good afternoon";
    greetingText.textContent = `${timeGreeting}, Boss.`;
  }
  updateGreeting();

  // ==========================================================================
  // 3. Initialize 3D Voxel Hologram Engine
  // ==========================================================================
  let dadusOrb = null;
  if (window.DadusHolographicOrb && document.getElementById('dadusOrbCanvas')) {
    dadusOrb = new DadusHolographicOrb('dadusOrbCanvas');
  }

  function setSystemState(state, customText = null) {
    if (dadusOrb) {
      dadusOrb.setState(state);
    }

    if (stateLabel && stateDot) {
      stateLabel.textContent = state.toUpperCase();

      if (state === 'listening') {
        stateDot.style.background = '#00f0ff';
        stateDot.style.boxShadow = '0 0 10px #00f0ff';
        heroMicBtn.className = 'console-mic-btn listening';
        if (audioWaveVisualizer) audioWaveVisualizer.classList.add('active');
        if (interruptBtn) interruptBtn.style.display = 'none';
      } else if (state === 'thinking') {
        stateDot.style.background = '#a855f7';
        stateDot.style.boxShadow = '0 0 10px #a855f7';
        heroMicBtn.className = 'console-mic-btn thinking';
        if (audioWaveVisualizer) audioWaveVisualizer.classList.add('active');
        if (interruptBtn) interruptBtn.style.display = 'none';
      } else if (state === 'executing') {
        stateDot.style.background = '#0077ff';
        stateDot.style.boxShadow = '0 0 10px #0077ff';
        heroMicBtn.className = 'console-mic-btn thinking';
        if (audioWaveVisualizer) audioWaveVisualizer.classList.add('active');
        if (interruptBtn) interruptBtn.style.display = 'none';
      } else if (state === 'speaking') {
        stateDot.style.background = '#ec4899';
        stateDot.style.boxShadow = '0 0 10px #ec4899';
        heroMicBtn.className = 'console-mic-btn speaking';
        if (audioWaveVisualizer) audioWaveVisualizer.classList.add('active');
        if (interruptBtn) interruptBtn.style.display = 'inline-flex';
      } else if (state === 'error') {
        stateDot.style.background = '#f43f5e';
        stateDot.style.boxShadow = '0 0 10px #f43f5e';
        heroMicBtn.className = 'console-mic-btn';
        if (audioWaveVisualizer) audioWaveVisualizer.classList.remove('active');
        if (interruptBtn) interruptBtn.style.display = 'none';
      } else if (state === 'success') {
        stateDot.style.background = '#10b981';
        stateDot.style.boxShadow = '0 0 10px #10b981';
        heroMicBtn.className = 'console-mic-btn';
        if (audioWaveVisualizer) audioWaveVisualizer.classList.remove('active');
        if (interruptBtn) interruptBtn.style.display = 'none';
      } else {
        // Idle
        stateDot.style.background = '#00f0ff';
        stateDot.style.boxShadow = '0 0 8px #00f0ff';
        heroMicBtn.className = 'console-mic-btn';
        if (audioWaveVisualizer) audioWaveVisualizer.classList.remove('active');
        if (interruptBtn) interruptBtn.style.display = 'none';
      }
    }

    if (customText && dynamicTranscript) {
      dynamicTranscript.innerHTML = customText;
    }
  }

  // ==========================================================================
  // 4. WebSocket Live Voice-State Synchronization
  // ==========================================================================
  function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/voice-state`;
    let ws = null;

    try {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (statePing) statePing.textContent = 'NEURAL LINK ACTIVE';
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'state') {
            setSystemState(data.state, data.text || null);
          }
        } catch (e) {}
      };

      ws.onclose = () => {
        if (statePing) statePing.textContent = 'STANDBY';
        setTimeout(initWebSocket, 3000);
      };

      ws.onerror = () => {
        if (ws) ws.close();
      };
    } catch (err) {
      console.warn('[DADUS] WebSocket not available, relying on REST polling.');
    }
  }
  initWebSocket();

  // ==========================================================================
  // 5. Dual Siri Chime Synthesis
  // ==========================================================================
  function playSiriChime(type = 'wake') {
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const now = audioCtx.currentTime;

      if (type === 'wake') {
        // Rising dual bell chime (880Hz -> 1320Hz)
        const osc1 = audioCtx.createOscillator();
        const osc2 = audioCtx.createOscillator();
        const gain = audioCtx.createGain();

        osc1.type = 'sine';
        osc1.frequency.setValueAtTime(880, now);
        osc1.frequency.exponentialRampToValueAtTime(1320, now + 0.14);

        osc2.type = 'triangle';
        osc2.frequency.setValueAtTime(1760, now);

        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);

        osc1.connect(gain);
        osc2.connect(gain);
        gain.connect(audioCtx.destination);

        osc1.start(now);
        osc2.start(now);
        osc1.stop(now + 0.3);
        osc2.stop(now + 0.3);
      } else {
        // Soft fallback chime (660Hz -> 440Hz)
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(660, now);
        osc.frequency.exponentialRampToValueAtTime(440, now + 0.16);

        gain.gain.setValueAtTime(0.06, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);

        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start(now);
        osc.stop(now + 0.24);
      }
    } catch (e) {}
  }

  // ==========================================================================
  // 6. Web Speech Recognition Architecture (Hands-Free "Hey Dadus")
  // ==========================================================================
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isListening = false;
  let isRecognitionRunning = false;
  let restartTimeout = null;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      isRecognitionRunning = true;
    };

    recognition.onresult = (event) => {
      let interim = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const text = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += text;
        } else {
          interim += text;
        }
      }

      const activeText = (finalTranscript || interim).trim();
      const lower = activeText.toLowerCase();

      // Wake-words
      const wakeWords = ['hey dadus', 'ok dadus', 'hi dadus', 'dadus'];
      const matched = wakeWords.find(w => lower.includes(w));

      if (matched && !isListening) {
        isListening = true;
        playSiriChime('wake');
        setSystemState('listening', `I am listening, Boss... <em>"${activeText}"</em>`);
      } else if (isListening) {
        setSystemState('listening', `Listening: <em>"${activeText}"</em>`);
      }

      if (finalTranscript && isListening) {
        let command = finalTranscript.trim();
        for (const wp of wakeWords) {
          if (command.toLowerCase().startsWith(wp)) {
            command = command.substring(wp.length).replace(/^[,\s]+/, '');
            break;
          }
        }

        if (command) {
          dispatchUserCommand(command);
        }
        isListening = false;
      }
    };

    recognition.onerror = (e) => {
      if (e.error !== 'no-speech') {
        console.warn('[Speech Recognition] Notice:', e.error);
      }
    };

    recognition.onend = () => {
      isRecognitionRunning = false;
      if (handsFreeEnabled) {
        clearTimeout(restartTimeout);
        restartTimeout = setTimeout(() => {
          try {
            if (!isRecognitionRunning && handsFreeEnabled) {
              recognition.start();
            }
          } catch (e) {}
        }, 300);
      }
    };

    try {
      recognition.start();
    } catch (e) {}
  }

  function startManualSpeech() {
    isListening = true;
    playSiriChime('wake');
    setSystemState('listening', 'Listening for your command...');

    if (recognition && !isRecognitionRunning) {
      try {
        recognition.start();
      } catch (e) {}
    } else if (!SpeechRecognition) {
      // Backend Push-to-Talk fallback
      triggerBackendListen();
    }
  }

  async function triggerBackendListen() {
    setSystemState('listening', 'Microphone active. Speak now...');
    try {
      const res = await fetch('/api/voice/listen', { method: 'POST' });
      const data = await res.json();
      if (data.success && data.transcription) {
        dispatchUserCommand(data.transcription);
      } else {
        setSystemState('idle', 'Boss, I could not detect any speech.');
      }
    } catch (e) {
      setSystemState('idle', 'Voice input standby.');
    }
  }

  // Hero Mic Button Click
  if (heroMicBtn) {
    heroMicBtn.addEventListener('click', () => {
      startManualSpeech();
    });
  }

  // Tap 3D Stage to Speak
  if (hologramStage) {
    hologramStage.addEventListener('click', (e) => {
      if (!dadusOrb || !dadusOrb.isDragging) {
        startManualSpeech();
      }
    });
  }

  // Interrupt Speech Button
  if (interruptBtn) {
    interruptBtn.addEventListener('click', () => {
      if (ttsAudioPlayer) {
        ttsAudioPlayer.pause();
        ttsAudioPlayer.currentTime = 0;
      }
      setSystemState('idle', 'Speech interrupted, Boss.');
      interruptBtn.style.display = 'none';
    });
  }

  // ==========================================================================
  // 7. Command Execution & API Gateway (/api/chat)
  // ==========================================================================
  async function dispatchUserCommand(command) {
    if (!command || !command.trim()) return;

    command = command.trim();
    appendDialogue('user', command);
    setSystemState('thinking', `Processing request: <em>"${command}"</em>`);

    // Clear previous disambiguation options
    if (optionsContainer) {
      optionsContainer.innerHTML = '';
      optionsContainer.style.display = 'none';
    }

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: command,
          session_id: sessionId,
          speak_response: audioEnabled
        })
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const data = await response.json();

      // Check if Confirmation is required for sensitive operation
      if (data.needs_confirmation) {
        activeConfirmationId = data.confirmation_id;
        showConfirmationModal(data.text);
        setSystemState('idle', data.text);
        appendDialogue('assistant', data.text, data.tool_called);
        return;
      }

      // Check if Clarification / Disambiguation Options returned
      if (data.needs_clarification && data.options && data.options.length > 0) {
        renderClarificationOptions(data.options);
      }

      // Handle assistant response
      appendDialogue('assistant', data.text, data.tool_called, data.tool_result);
      setSystemState('speaking', data.text);

      // Automatically launch web link in user browser tab (e.g. YouTube, Spotify, Web apps)
      if (data.tool_result && data.tool_result.data) {
        const resData = data.tool_result.data;
        const targetUrl = resData.url || (resData.mode === 'browser_fallback' ? resData.target : null);
        if (targetUrl && (targetUrl.startsWith('http://') || targetUrl.startsWith('https://'))) {
          try {
            window.open(targetUrl, '_blank');
          } catch (e) {
            console.warn('[DADUS] Window open blocked by browser popup manager:', e);
          }
        }
      }

      // Play synthesized audio if returned
      if (data.audio_url && audioEnabled && ttsAudioPlayer) {
        ttsAudioPlayer.src = data.audio_url;
        ttsAudioPlayer.play().catch(() => {});

        if (dadusOrb) {
          dadusOrb.attachAudioElement(ttsAudioPlayer);
        }

        ttsAudioPlayer.onended = () => {
          setSystemState('idle');
          if (interruptBtn) interruptBtn.style.display = 'none';
        };
      } else {
        const timeoutDuration = Math.min(8000, Math.max(3500, (data.text || '').length * 60));
        setTimeout(() => setSystemState('idle'), timeoutDuration);
      }

    } catch (err) {
      console.error('[DADUS] Command execution failed:', err);
      const errMsg = "Boss, I encountered a temporary connection error. Please try again.";
      appendDialogue('assistant', errMsg);
      setSystemState('error', errMsg);
      setTimeout(() => setSystemState('idle'), 4000);
    }
  }

  // Render Disambiguation / Clarification Options Chips
  function renderClarificationOptions(options) {
    if (!optionsContainer) return;
    optionsContainer.innerHTML = '';
    optionsContainer.style.display = 'flex';

    options.forEach(opt => {
      const btn = document.createElement('button');
      btn.className = 'clarification-btn';
      btn.textContent = opt;
      btn.addEventListener('click', () => {
        optionsContainer.style.display = 'none';
        dispatchUserCommand(opt);
      });
      optionsContainer.appendChild(btn);
    });
  }

  // Append Message to Dialogue View
  function appendDialogue(role, text, toolCalled = null, toolResult = null) {
    if (!dialogueStream) return;

    const card = document.createElement('div');
    card.className = `dialogue-card ${role}`;

    let toolMarkup = '';
    if (toolCalled) {
      toolMarkup = `
        <div class="tool-badge-pill">
          <span>⚡ Tool: <strong>${toolCalled}</strong></span>
        </div>
      `;
    }

    card.innerHTML = `
      <div class="card-meta">
        <span class="badge ${role}-badge">${role.toUpperCase()}</span>
        <span class="timestamp">${new Date().toLocaleTimeString()}</span>
      </div>
      <div class="card-content">${text}</div>
      ${toolMarkup}
    `;

    dialogueStream.appendChild(card);
    dialogueStream.scrollTop = dialogueStream.scrollHeight;
  }

  // Command Input Form Submit
  if (commandForm && commandInput) {
    commandForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const val = commandInput.value.trim();
      if (val) {
        commandInput.value = '';
        dispatchUserCommand(val);
      }
    });
  }

  // Suggestion Chips Click
  document.querySelectorAll('.chip-item').forEach(chip => {
    chip.addEventListener('click', () => {
      const cmd = chip.getAttribute('data-command');
      if (cmd) {
        dispatchUserCommand(cmd);
      }
    });
  });

  // Clear Chat View
  if (clearChatBtn && dialogueStream) {
    clearChatBtn.addEventListener('click', () => {
      dialogueStream.innerHTML = `
        <div class="dialogue-card system">
          <div class="card-meta">
            <span class="badge system-badge">SYSTEM</span>
            <span class="timestamp">FEED CLEARED</span>
          </div>
          <div class="card-content">Dialogue feed cleared. Background memory preserved.</div>
        </div>
      `;
    });
  }

  // ==========================================================================
  // 8. Navigation & Panel View Switching
  // ==========================================================================
  const viewTitles = {
    home: { title: 'Core Assistant', sub: 'Autonomous Executive Intelligence' },
    history: { title: 'Dialogue Feed', sub: 'Real-Time Message Trace & Execution History' },
    tasks: { title: 'Agenda & Tasks', sub: 'Scheduled Events, Productivity & Reminders' },
    memory: { title: 'Neural Memory Store', sub: 'Stored Facts, Personal Preferences & Knowledge' },
    activity: { title: 'Activity & Audit Logs', sub: 'Cryptographic Operations & Safety Logs' },
    tools: { title: 'MCP Tool Matrix', sub: 'Registered System Tools & External Integrations' },
    settings: { title: 'System Configuration', sub: 'Holographic Parameters & Security Guardrails' }
  };

  function switchPanel(panelId) {
    navItems.forEach(item => {
      item.classList.toggle('active', item.getAttribute('data-panel') === panelId);
    });

    panelViews.forEach(panel => {
      const match = panel.id.toLowerCase() === `panel${panelId.toLowerCase()}`;
      panel.classList.toggle('active', match);
    });

    if (currentViewTitle && currentViewSubtitle && viewTitles[panelId]) {
      currentViewTitle.textContent = viewTitles[panelId].title;
      currentViewSubtitle.textContent = viewTitles[panelId].sub;
    }

    // Lazy load data for selected panel
    if (panelId === 'tasks') loadAgendaData();
    if (panelId === 'memory') loadMemoryData();
    if (panelId === 'activity') loadAuditLogs();
    if (panelId === 'tools') loadToolsMatrix();
    if (panelId === 'home' && dadusOrb) {
      setTimeout(() => dadusOrb._handleResize(), 50);
    }
  }

  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const panel = item.getAttribute('data-panel');
      switchPanel(panel);
    });
  });

  if (navHome) {
    navHome.addEventListener('click', () => {
      switchPanel('home');
    });
  }

  // ==========================================================================
  // 9. Agenda, Tasks & Reminders Synchronization
  // ==========================================================================
  async function loadAgendaData() {
    try {
      const [scheduleRes, tasksRes] = await Promise.all([
        fetch('/api/schedule'),
        fetch('/api/tasks')
      ]);

      const scheduleData = await scheduleRes.json();
      const tasksData = await tasksRes.json();

      // Render Schedule Items
      if (scheduleItemsList) {
        const items = scheduleData.schedule_items || [];
        scheduleItemsList.innerHTML = items.length ? items.map(item => `
          <div class="agenda-item-card">
            <div class="agenda-item-info">
              <span class="agenda-item-title">${item.title}</span>
              <span class="agenda-item-sub">${item.start_time || 'Scheduled Today'}</span>
            </div>
          </div>
        `).join('') : '<div class="empty-state">No scheduled events for today.</div>';
      }

      // Render Reminders
      if (activeRemindersList) {
        const rems = scheduleData.reminders || [];
        activeRemindersList.innerHTML = rems.length ? rems.map(rem => `
          <div class="agenda-item-card">
            <div class="agenda-item-info">
              <span class="agenda-item-title">${rem.title}</span>
              <span class="agenda-item-sub">${rem.target_time}</span>
            </div>
          </div>
        `).join('') : '<div class="empty-state">No active reminders.</div>';
      }

      // Render Pending Tasks
      if (pendingTasksList) {
        const tasks = tasksData.tasks || [];
        pendingTasksList.innerHTML = tasks.length ? tasks.map(task => `
          <div class="agenda-item-card" data-task-id="${task.id}">
            <div class="agenda-item-info">
              <span class="agenda-item-title">${task.title}</span>
              <span class="agenda-item-sub">Priority: ${task.priority || 'Normal'}</span>
            </div>
            <div class="agenda-item-actions">
              <button class="task-complete-btn" title="Mark as Done" onclick="completeTask(${task.id})">✓</button>
              <button class="task-delete-btn" title="Delete Task" onclick="deleteTask(${task.id})">🗑</button>
            </div>
          </div>
        `).join('') : '<div class="empty-state">No pending tasks. You are all caught up, Boss!</div>';
      }

    } catch (e) {
      console.warn('[DADUS] Could not sync agenda:', e);
    }
  }

  // Complete Task Action
  window.completeTask = async function(taskId) {
    try {
      await fetch(`/api/tasks/${taskId}/complete`, { method: 'POST' });
      loadAgendaData();
    } catch (e) {}
  };

  // Delete Task Action
  window.deleteTask = async function(taskId) {
    try {
      await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
      loadAgendaData();
    } catch (e) {
      console.error('[DADUS] Failed to delete task:', e);
    }
  };

  // Add Task Form
  if (createTaskForm && newTaskTitle) {
    createTaskForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const title = newTaskTitle.value.trim();
      if (!title) return;

      try {
        await fetch('/api/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, priority: 'medium' })
        });
        newTaskTitle.value = '';
        loadAgendaData();
      } catch (e) {}
    });
  }

  if (refreshTasksBtn) refreshTasksBtn.addEventListener('click', loadAgendaData);

  // ==========================================================================
  // 10. Neural Memory Store Synchronization
  // ==========================================================================
  async function loadMemoryData() {
    try {
      const res = await fetch('/api/memory');
      const data = await res.json();
      memoryCache = data.memories || [];
      renderMemoryCards(memoryCache);
    } catch (e) {
      console.warn('[DADUS] Could not load memories:', e);
    }
  }

  function renderMemoryCards(memories) {
    if (!memoryCardsList) return;
    if (!memories.length) {
      memoryCardsList.innerHTML = '<div class="empty-state">No stored facts in neural memory yet.</div>';
      return;
    }

    memoryCardsList.innerHTML = memories.map(m => `
      <div class="memory-item-tile">
        <button class="mem-tile-delete" title="Forget Fact" onclick="forgetMemory('${m.key}')">✕</button>
        <span class="mem-tile-cat">${m.category || 'Preference'}</span>
        <span class="mem-tile-key">${m.key}</span>
        <span class="mem-tile-val">${m.value}</span>
      </div>
    `).join('');
  }

  window.forgetMemory = async function(key) {
    try {
      await fetch(`/api/memory/${encodeURIComponent(key)}`, { method: 'DELETE' });
      loadMemoryData();
    } catch (e) {}
  };

  // Add Memory Form
  if (memoryStoreForm && memoryKeyInput && memoryValueInput) {
    memoryStoreForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const key = memoryKeyInput.value.trim();
      const value = memoryValueInput.value.trim();
      const category = memoryCategorySelect ? memoryCategorySelect.value : 'preference';

      if (!key || !value) return;

      try {
        await fetch('/api/memory', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key, value, category })
        });
        memoryKeyInput.value = '';
        memoryValueInput.value = '';
        loadMemoryData();
      } catch (e) {}
    });
  }

  // Search Memory
  if (searchMemoryInput) {
    searchMemoryInput.addEventListener('input', (e) => {
      const query = e.target.value.toLowerCase();
      const filtered = memoryCache.filter(m => 
        (m.key && m.key.toLowerCase().includes(query)) ||
        (m.value && m.value.toLowerCase().includes(query)) ||
        (m.category && m.category.toLowerCase().includes(query))
      );
      renderMemoryCards(filtered);
    });
  }

  if (refreshMemoryBtn) refreshMemoryBtn.addEventListener('click', loadMemoryData);

  // ==========================================================================
  // 11. Activity & Execution Audit Logs
  // ==========================================================================
  async function loadAuditLogs() {
    try {
      const res = await fetch('/api/logs?limit=40');
      const data = await res.json();
      const logs = data.logs || [];

      if (auditLogsBody) {
        if (!logs.length) {
          auditLogsBody.innerHTML = '<tr><td colspan="4" class="table-loading">No activity logs recorded yet.</td></tr>';
          return;
        }

        auditLogsBody.innerHTML = logs.map(l => `
          <tr>
            <td>${l.timestamp ? new Date(l.timestamp).toLocaleTimeString() : 'Recent'}</td>
            <td><strong>${l.action || 'Tool Trigger'}</strong></td>
            <td><span class="status-badge-ok">${l.status || 'SUCCESS'}</span></td>
            <td>${l.details ? JSON.stringify(l.details).substring(0, 80) : 'Standard system operation'}</td>
          </tr>
        `).join('');
      }
    } catch (e) {
      console.warn('[DADUS] Could not load logs:', e);
    }
  }

  if (refreshLogsBtn) refreshLogsBtn.addEventListener('click', loadAuditLogs);

  // ==========================================================================
  // 12. MCP Tools Registry Matrix
  // ==========================================================================
  async function loadToolsMatrix() {
    try {
      const res = await fetch('/api/mcp/tools');
      const data = await res.json();
      const tools = data.tools || [];

      if (toolStatsBadge) {
        toolStatsBadge.textContent = `${tools.length} Tools Loaded`;
      }

      if (toolsGrid) {
        if (!tools.length) {
          toolsGrid.innerHTML = '<div class="empty-state">No registered MCP tools found.</div>';
          return;
        }

        toolsGrid.innerHTML = tools.map(t => `
          <div class="tool-entry-card">
            <span class="tool-entry-name">${t.name}</span>
            <span class="tool-entry-desc">${t.description || 'Native system tool integration'}</span>
          </div>
        `).join('');
      }
    } catch (e) {
      console.warn('[DADUS] Could not load MCP tools:', e);
    }
  }

  // ==========================================================================
  // 13. Confirmation Modal Dialog
  // ==========================================================================
  function showConfirmationModal(promptText) {
    if (confirmPrompt) confirmPrompt.textContent = promptText;
    if (confirmModal) confirmModal.classList.add('active');
  }

  function hideConfirmationModal() {
    if (confirmModal) confirmModal.classList.remove('active');
    activeConfirmationId = null;
  }

  if (modalApproveBtn) {
    modalApproveBtn.addEventListener('click', async () => {
      if (!activeConfirmationId) return;
      await resolveConfirmation(activeConfirmationId, true);
      hideConfirmationModal();
    });
  }

  if (modalRejectBtn) {
    modalRejectBtn.addEventListener('click', async () => {
      if (!activeConfirmationId) return;
      await resolveConfirmation(activeConfirmationId, false);
      hideConfirmationModal();
    });
  }

  async function resolveConfirmation(confId, confirmed) {
    try {
      const res = await fetch('/api/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          confirmation_id: confId,
          confirmed: confirmed,
          session_id: sessionId
        })
      });
      const data = await res.json();
      appendDialogue('assistant', data.message);
      setSystemState('idle', data.message);
    } catch (e) {}
  }

  // ==========================================================================
  // 14. Top Header Switches (Hands-Free & Audio Speech)
  // ==========================================================================
  if (handsFreeBtn && handsFreeLabel) {
    handsFreeBtn.addEventListener('click', () => {
      handsFreeEnabled = !handsFreeEnabled;
      handsFreeBtn.classList.toggle('active', handsFreeEnabled);
      handsFreeLabel.innerHTML = handsFreeEnabled ? 'Hey Dadus: <strong>ON</strong>' : 'Hey Dadus: <strong>OFF</strong>';
      setSystemState('idle');

      if (handsFreeEnabled && recognition && !isRecognitionRunning) {
        try { recognition.start(); } catch (e) {}
      } else if (!handsFreeEnabled && recognition && isRecognitionRunning) {
        try { recognition.stop(); } catch (e) {}
      }
    });
  }

  if (ttsToggleBtn && ttsToggleLabel) {
    ttsToggleBtn.addEventListener('click', () => {
      audioEnabled = !audioEnabled;
      ttsToggleBtn.classList.toggle('active', audioEnabled);
      ttsToggleLabel.textContent = audioEnabled ? 'Audio' : 'Muted';
      if (ttsIcon) ttsIcon.textContent = audioEnabled ? '🔊' : '🔇';
    });
  }

  // Initial MCP Tool Matrix inspection in background
  loadToolsMatrix();

});
