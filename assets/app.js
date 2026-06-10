// SPDX-FileCopyrightText: Copyright (C) ARDUINO SRL (http://www.arduino.cc)
//
// SPDX-License-Identifier: MPL-2.0

const socket = io(`http://${window.location.host}`);

let thinkingMessageElement = null;
let sendButton;
let sendButtonImg;
let quickActionButtonsContainer;
let customPlaceholder;
let lastUserPrompt = '';

// ── Provider presets ─────────────────────────────────────────────────────────

const PROVIDER_PRESETS = {
    anthropic: {
        label: 'Anthropic',
        protocol: 'anthropic-messages',
        modelPlaceholder: 'claude-sonnet-4-6',
        modelSuggestions: ['claude-sonnet-4-6', 'claude-opus-4-7', 'claude-haiku-4-5-20251001'],
        timeout: 120,
        maxTokens: 4096,
        needsApiKey: true,
        needsApiBase: false,
        apiKeyHint: 'Get a key at console.anthropic.com → API Keys',
        apiBaseHint: '',
    },
    openrouter: {
        label: 'OpenRouter',
        protocol: 'openrouter',
        modelPlaceholder: 'anthropic/claude-sonnet-4-5',
        modelSuggestions: [
            'anthropic/claude-sonnet-4-5',
            'anthropic/claude-opus-4',
            'openai/gpt-4o',
            'google/gemini-2.0-flash-001',
            'meta-llama/llama-3.3-70b-instruct',
        ],
        timeout: 120,
        maxTokens: 4096,
        needsApiKey: true,
        needsApiBase: false,
        apiKeyHint: 'Get a key at openrouter.ai/keys',
        apiBaseHint: '',
    },
    openai: {
        label: 'OpenAI',
        protocol: 'openai',
        modelPlaceholder: 'gpt-4o',
        modelSuggestions: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
        timeout: 120,
        maxTokens: 4096,
        needsApiKey: true,
        needsApiBase: false,
        apiKeyHint: 'Get a key at platform.openai.com/api-keys',
        apiBaseHint: '',
    },
    azure: {
        label: 'Azure OpenAI',
        protocol: 'azure',
        modelPlaceholder: 'gpt-4o',
        modelSuggestions: [],
        timeout: 120,
        maxTokens: 4096,
        needsApiKey: true,
        needsApiBase: true,
        apiKeyHint: 'Azure portal → your resource → Keys and Endpoints',
        apiBaseHint: 'e.g. https://YOUR-RESOURCE.openai.azure.com',
    },
    litellm: {
        label: 'LiteLLM',
        protocol: 'litellm',
        modelPlaceholder: 'claude-sonnet-4-6',
        modelSuggestions: [],
        timeout: 300,
        maxTokens: 4096,
        needsApiKey: true,
        needsApiBase: true,
        apiKeyHint: 'Key for your LiteLLM proxy',
        apiBaseHint: 'e.g. http://localhost:4000/v1',
    },
    local: {
        label: 'Local (yzma)',
        protocol: 'llama-server',
        modelPlaceholder: 'Qwen_Qwen3.5-0.8B-Q4_0.gguf',
        modelSuggestions: ['Qwen_Qwen3.5-0.8B-Q4_0.gguf', 'Qwen3.5-0.8B-UD-Q4_K_XL.gguf', 'Qwen3.5-0.8B-Q8_0.gguf'],
        timeout: 1200,
        maxTokens: 2048,
        needsApiKey: false,
        needsApiBase: false,
        apiKeyHint: '',
        apiBaseHint: '',
    },
    custom: {
        label: 'Custom',
        protocol: '',
        modelPlaceholder: 'protocol/model-id',
        modelSuggestions: [],
        timeout: 120,
        maxTokens: 4096,
        needsApiKey: true,
        needsApiBase: true,
        apiKeyHint: 'API key for this endpoint',
        apiBaseHint: 'Full base URL of the OpenAI-compatible endpoint',
    },
};

// ── State ────────────────────────────────────────────────────────────────────

let currentModels = [];
let activeModelName = 'yzma';
let selectedProvider = null;

// ── Mode pills ───────────────────────────────────────────────────────────────

function updateModePills(mode) {
    document.querySelectorAll('.mode-pill').forEach(pill => {
        pill.classList.toggle('active', pill.dataset.mode === mode);
    });
    localStorage.setItem('qclaw-mode', mode);
}

function initModePills() {
    document.querySelectorAll('.mode-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            socket.emit('commands', { command: 'set_mode', value: pill.dataset.mode });
        });
    });
}

// ── Error banner ─────────────────────────────────────────────────────────────

function showError(message) {
    console.log(message);
    const errorBanner = document.getElementById('error-banner');
    const errorMessage = document.getElementById('error-message');
    if (errorBanner && errorMessage) {
        errorMessage.textContent = message;
        errorBanner.style.display = 'block';
    }
}

function hideError() {
    const errorBanner = document.getElementById('error-banner');
    if (errorBanner) {
        errorBanner.style.display = 'none';
    }
}

// ── v3.0.5 daemon-missing banner ─────────────────────────────────────────────
//
// Backend (python/main.py) emits {state: "missing"|"ok", command: "..."} on
// startup and on a periodic re-check. The banner shows the host-side command
// and offers a Copy button. The Retry button asks the backend to re-check.

function handleDaemonStatus(data) {
    const banner    = document.getElementById('daemon-banner');
    const cmdEl     = document.getElementById('daemon-banner-command');
    if (!banner || !cmdEl) return;
    if (!data || typeof data !== 'object') { banner.style.display = 'none'; return; }

    if (data.state === 'ok') {
        banner.style.display = 'none';
        return;
    }
    if (data.state === 'missing') {
        if (typeof data.command === 'string' && data.command.length > 0) {
            cmdEl.textContent = data.command;
        }
        banner.style.display = 'block';
    }
}

function initDaemonBanner() {
    const copyBtn  = document.getElementById('daemon-banner-copy');
    const retryBtn = document.getElementById('daemon-banner-retry');
    const cmdEl    = document.getElementById('daemon-banner-command');
    if (copyBtn && cmdEl) {
        copyBtn.addEventListener('click', async () => {
            const text = cmdEl.textContent || '';
            try {
                if (navigator.clipboard && window.isSecureContext) {
                    await navigator.clipboard.writeText(text);
                } else {
                    const tmp = document.createElement('textarea');
                    tmp.value = text;
                    tmp.setAttribute('readonly', '');
                    tmp.style.position = 'absolute';
                    tmp.style.left = '-9999px';
                    document.body.appendChild(tmp);
                    tmp.select();
                    document.execCommand('copy');
                    document.body.removeChild(tmp);
                }
                copyBtn.classList.add('copied');
                copyBtn.textContent = 'Copied';
                setTimeout(() => {
                    copyBtn.classList.remove('copied');
                    copyBtn.textContent = 'Copy';
                }, 2000);
            } catch (e) {
                console.warn('clipboard copy failed:', e);
            }
        });
    }
    if (retryBtn) {
        retryBtn.addEventListener('click', () => {
            retryBtn.disabled = true;
            retryBtn.textContent = 'Checking…';
            socket.emit('commands', { command: 'recheck_daemon' });
            setTimeout(() => {
                retryBtn.disabled = false;
                retryBtn.textContent = 'I did it — retry';
            }, 2500);
        });
    }
}

// ── Thinking / stream helpers ─────────────────────────────────────────────────

function removeThinkingMessage() {
    if (thinkingMessageElement && thinkingMessageElement.parentNode) {
        thinkingMessageElement.parentNode.removeChild(thinkingMessageElement);
        thinkingMessageElement = null;
    }
}

function handleResponse(data) {
    const ai_msg = document.getElementById('active-ai-response');
    if (thinkingMessageElement) {
        const textContent = thinkingMessageElement.querySelector('.text-content');
        if (textContent) textContent.innerHTML = '';
        thinkingMessageElement.classList.remove('thinking-message');
        thinkingMessageElement.dataset.rawText = '';
        thinkingMessageElement = null;
    }
    if (ai_msg) {
        ai_msg.dataset.rawText += data;
        const textContent = ai_msg.querySelector('.text-content');
        if (textContent) {
            textContent.innerHTML = marked.parse(ai_msg.dataset.rawText);
        }
    }
}

function handleToolEvent(ev) {
    const messagesContainer = document.getElementById('messages');
    if (!messagesContainer) return;
    let row;
    if (ev.type === 'tool_start') {
        row = document.createElement('div');
        row.className = 'tool-event tool-running';
        row.dataset.iter = ev.iter;
        const args = ev.arguments ? ` ${ev.arguments.slice(0, 80)}${ev.arguments.length > 80 ? '…' : ''}` : '';
        row.innerHTML = `<span class="tool-icon">🔧</span><span class="tool-text">${ev.name || '?'}<span class="tool-args">${args}</span></span>`;
        const aiMsg = document.getElementById('active-ai-response');
        if (aiMsg) {
            messagesContainer.insertBefore(row, aiMsg);
        } else {
            messagesContainer.appendChild(row);
        }
    } else if (ev.type === 'tool_done' || ev.type === 'tool_error') {
        row = messagesContainer.querySelector(`.tool-event[data-iter="${ev.iter}"]`);
        if (!row) return;
        row.classList.remove('tool-running');
        row.classList.add(ev.type === 'tool_error' ? 'tool-error' : 'tool-done');
        const icon = row.querySelector('.tool-icon');
        if (icon) icon.textContent = ev.type === 'tool_error' ? '✗' : '✓';
        const elapsedSec = ((ev.elapsed_ms || 0) / 1000).toFixed(1);
        const elapsedSpan = document.createElement('span');
        elapsedSpan.className = 'tool-elapsed';
        elapsedSpan.textContent = ` (${elapsedSec}s)`;
        row.appendChild(elapsedSpan);
    }
}

function handleStreamEnd() {
    removeThinkingMessage();
    const ai_msg = document.getElementById('active-ai-response');
    if (ai_msg) ai_msg.id = '';
    if (sendButton) {
        sendButton.classList.remove('sending-state');
        if (sendButtonImg) sendButtonImg.src = 'img/send.svg';
    }
    updateSendButtonState();
    updateClearChatButtonState();
}

function handleCompletedCommand(data) {
    console.log(`Command completed: ${data.command}`);
    const userInput = document.getElementById('user-input');

    if (data.command === 'stop_stream') {
        handleStreamEnd();
        const disclaimer = document.createElement('div');
        disclaimer.className = 'stop-disclaimer';
        disclaimer.textContent = 'You stopped this response';
        document.getElementById('messages').appendChild(disclaimer);
        if (userInput) {
            userInput.value = lastUserPrompt;
            autoExpandInput(userInput);
            updateSendButtonState();
            updatePlaceholderVisibility();
            userInput.focus();
        }

    } else if (data.command === 'clear_chat') {
        document.getElementById('messages').innerHTML = '';
        document.getElementById('empty-chat-container').style.display = 'flex';
        const mainContent = document.querySelector('.main-content');
        if (mainContent) mainContent.classList.remove('chat-active');
        if (userInput) {
            userInput.value = '';
            userInput.style.height = '32px';
        }
        if (quickActionButtonsContainer) quickActionButtonsContainer.style.display = 'none';
        lastUserPrompt = '';
        updateSendButtonState();
        updateClearChatButtonState();
        updatePlaceholderVisibility();
        if (userInput) userInput.focus();

    } else if (data.command === 'get_models') {
        currentModels = data.models || [];
        activeModelName = data.active_model || 'yzma';
        renderModelDropdown(currentModels, activeModelName);
        renderSettingsModelList(currentModels, activeModelName);
        updateModelUI(activeModelName, currentModels);
        checkOnboarding(currentModels);

    } else if (data.command === 'set_model') {
        activeModelName = data.model_name;
        renderModelDropdown(currentModels, activeModelName);
        renderSettingsModelList(currentModels, activeModelName);
        updateModelUI(activeModelName, currentModels);

    } else if (data.command === 'add_model') {
        showFormFeedback('success', `Provider "${data.model_name}" added.`);
        // Reset form and reload models
        clearAddModelForm();
        loadModels();

    } else if (data.command === 'delete_model') {
        loadModels();
    }
}

function handleCommandError(data) {
    if (data.command === 'add_model') {
        showFormFeedback('error', data.error || 'Failed to add model.');
    } else {
        showError(`Command error: ${data.command} — ${data.error}`);
    }
}

function handleModelChanged(data) {
    activeModelName = data.model_name;
    renderModelDropdown(currentModels, activeModelName);
    renderSettingsModelList(currentModels, activeModelName);
    updateModelUI(activeModelName, currentModels);
}

function handleLLMError(data) {
    showError(`LLM error: ${data.error}`);
    removeThinkingMessage();
    if (quickActionButtonsContainer) quickActionButtonsContainer.style.display = 'none';
    handleStreamEnd();
}

// ── Model selector ────────────────────────────────────────────────────────────

function loadModels() {
    socket.emit('commands', { command: 'get_models' });
}

function isLocalModel(model) {
    const proto = model.model || '';
    return proto.startsWith('llama-server/') || proto.startsWith('llamaserver/');
}

function providerLabel(model) {
    const proto = (model.model || '').split('/')[0];
    const map = {
        'llama-server': 'LOCAL',
        'llamaserver':  'LOCAL',
        'anthropic-messages': 'ANTHROPIC',
        'openrouter':   'OPENROUTER',
        'openai':       'OPENAI',
        'azure':        'AZURE',
        'litellm':      'LITELLM',
    };
    return map[proto] || proto.toUpperCase() || 'CLOUD';
}

function renderModelDropdown(models, active) {
    const dropdown = document.getElementById('model-dropdown');
    if (!dropdown) return;
    dropdown.innerHTML = '';

    models.forEach(m => {
        const item = document.createElement('div');
        item.className = 'model-dropdown-item' + (m.model_name === active ? ' active' : '');
        const local = isLocalModel(m);
        item.innerHTML = `
            <div class="model-dropdown-dot"></div>
            <span class="model-dropdown-name">${m.model_name}</span>
            <span class="model-dropdown-badge ${local ? 'local' : 'cloud'}">${local ? 'LOCAL' : providerLabel(m)}</span>
        `;
        item.addEventListener('click', () => {
            setActiveModel(m.model_name);
            closeModelDropdown();
        });
        dropdown.appendChild(item);
    });

    // Divider + "Add model" shortcut
    const divider = document.createElement('div');
    divider.className = 'model-dropdown-divider';
    dropdown.appendChild(divider);

    const addItem = document.createElement('div');
    addItem.className = 'model-dropdown-add';
    addItem.innerHTML = '<span>+ Add provider</span>';
    addItem.addEventListener('click', () => {
        closeModelDropdown();
        openSettings(true);
    });
    dropdown.appendChild(addItem);
}

function setActiveModel(name) {
    socket.emit('commands', { command: 'set_model', model_name: name });
}

function updateModelUI(name, models) {
    // Update selector button label
    const nameEl = document.getElementById('active-model-name');
    if (nameEl) nameEl.textContent = name;

    // Update title-label and disclaimer
    const model = models.find(m => m.model_name === name);
    const local = model ? isLocalModel(model) : true;
    const titleLabel = document.getElementById('title-label');
    const disclaimer = document.getElementById('disclaimer');

    const selectorBtn = document.getElementById('model-selector-btn');
    if (selectorBtn) {
        selectorBtn.classList.toggle('active-cloud', !local);
    }

    if (titleLabel) {
        titleLabel.textContent = local ? 'on-device llm' : 'cloud llm';
    }
    if (disclaimer) {
        if (local) {
            disclaimer.textContent = 'Running locally — no cloud, no internet required.';
        } else {
            const provider = model ? providerLabel(model) : 'CLOUD';
            disclaimer.textContent = `Running via ${provider} — cloud inference.`;
        }
    }
}

function initModelSelector() {
    const btn = document.getElementById('model-selector-btn');
    const selector = document.getElementById('model-selector');
    if (!btn || !selector) return;

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        selector.classList.toggle('open');
    });

    document.addEventListener('click', (e) => {
        if (selector && !selector.contains(e.target)) {
            closeModelDropdown();
        }
    });
}

function closeModelDropdown() {
    const selector = document.getElementById('model-selector');
    if (selector) selector.classList.remove('open');
}

// ── Settings panel ────────────────────────────────────────────────────────────

function openSettings(goToAddProvider = false) {
    const overlay = document.getElementById('settings-overlay');
    if (overlay) overlay.classList.add('open');
    loadModels();
    if (goToAddProvider) {
        setTimeout(() => {
            const addSection = document.getElementById('add-provider-section');
            if (addSection) addSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 300);
    }
}

function closeSettings() {
    const overlay = document.getElementById('settings-overlay');
    if (overlay) overlay.classList.remove('open');
    // Reset add form
    clearAddModelForm();
    selectedProvider = null;
    document.querySelectorAll('.provider-chip').forEach(c => c.classList.remove('selected'));
}

function renderSettingsModelList(models, active) {
    const list = document.getElementById('settings-model-list');
    if (!list) return;
    if (!models.length) {
        list.innerHTML = '<div class="settings-loading">No models configured.</div>';
        return;
    }
    list.innerHTML = '';
    models.forEach(m => {
        const local = isLocalModel(m);
        const isActive = m.model_name === active;
        const item = document.createElement('div');
        item.className = 'settings-model-item' + (isActive ? ' active-item' : '');

        const proto = m.model || '';
        const protoDisplay = proto.length > 40 ? proto.slice(0, 38) + '…' : proto;

        item.innerHTML = `
            <div class="settings-model-dot"></div>
            <div class="settings-model-info">
                <div class="settings-model-name">${m.model_name}</div>
                <div class="settings-model-proto">${protoDisplay}</div>
            </div>
            <div class="settings-model-actions">
                <span class="model-badge ${local ? 'local' : 'cloud'}">${local ? 'LOCAL' : providerLabel(m)}</span>
                ${isActive
                    ? '<span class="model-badge active-badge">active</span>'
                    : `<button class="btn-use" data-name="${m.model_name}">Use</button>`}
                ${!isActive
                    ? `<button class="btn-delete" data-name="${m.model_name}" title="Remove">✕</button>`
                    : ''}
            </div>
        `;

        const useBtn = item.querySelector('.btn-use');
        if (useBtn) {
            useBtn.addEventListener('click', () => setActiveModel(m.model_name));
        }
        const delBtn = item.querySelector('.btn-delete');
        if (delBtn) {
            delBtn.addEventListener('click', () => {
                if (confirm(`Remove model "${m.model_name}"?`)) {
                    socket.emit('commands', { command: 'delete_model', model_name: m.model_name });
                }
            });
        }

        list.appendChild(item);
    });
}

// ── Add model form ────────────────────────────────────────────────────────────

function initProviderChips() {
    document.querySelectorAll('.provider-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.provider-chip').forEach(c => c.classList.remove('selected'));
            chip.classList.add('selected');
            selectedProvider = chip.dataset.provider;
            renderAddModelForm(PROVIDER_PRESETS[selectedProvider]);
        });
    });
}

function renderAddModelForm(preset) {
    const container = document.getElementById('add-model-form-container');
    if (!container) return;

    const suggestionsHtml = preset.modelSuggestions.length
        ? `<datalist id="model-id-suggestions">${preset.modelSuggestions.map(s => `<option value="${s}">`).join('')}</datalist>`
        : '';

    container.innerHTML = `
        <div class="add-model-form" id="add-model-form">
            ${suggestionsHtml}
            <div class="form-row">
                <label class="form-label">Display name <span class="form-required">*</span></label>
                <input class="form-input" id="form-model-name" type="text" placeholder="e.g. claude-sonnet" autocomplete="off" />
                <p class="form-hint">Unique name used in the model selector</p>
            </div>
            <div class="form-row">
                <label class="form-label">Model ID <span class="form-required">*</span></label>
                <input class="form-input" id="form-model-id" type="text"
                    placeholder="${preset.modelPlaceholder}"
                    ${preset.modelSuggestions.length ? 'list="model-id-suggestions"' : ''}
                    autocomplete="off" />
                ${selectedProvider !== 'custom' && selectedProvider !== 'local'
                    ? `<p class="form-hint">Full model string e.g. <code>${preset.modelPlaceholder}</code></p>`
                    : '<p class="form-hint">For custom: use <code>protocol/model-id</code> format</p>'}
            </div>
            ${preset.needsApiKey ? `
            <div class="form-row">
                <label class="form-label">API key <span class="form-required">*</span></label>
                <input class="form-input" id="form-api-key" type="password" placeholder="sk-..." autocomplete="off" />
                ${preset.apiKeyHint ? `<p class="form-hint">${preset.apiKeyHint}</p>` : ''}
            </div>` : ''}
            ${preset.needsApiBase ? `
            <div class="form-row">
                <label class="form-label">API base URL ${selectedProvider === 'azure' ? '<span class="form-required">*</span>' : ''}</label>
                <input class="form-input" id="form-api-base" type="text" placeholder="${preset.apiBaseHint}" autocomplete="off" />
                ${preset.apiBaseHint ? `<p class="form-hint">${preset.apiBaseHint}</p>` : ''}
            </div>` : ''}
            <div class="form-row" style="display:flex;gap:12px;">
                <div style="flex:1">
                    <label class="form-label">Timeout (s)</label>
                    <input class="form-input" id="form-timeout" type="number" value="${preset.timeout}" min="10" max="7200" />
                </div>
                <div style="flex:1">
                    <label class="form-label">Max tokens</label>
                    <input class="form-input" id="form-max-tokens" type="number" value="${preset.maxTokens}" min="256" max="65536" />
                </div>
            </div>
            <div id="form-feedback"></div>
            <div class="form-submit-row">
                <button class="btn-add-model" id="btn-submit-model">Add model</button>
            </div>
        </div>
    `;

    document.getElementById('btn-submit-model').addEventListener('click', submitAddModel);

    // Auto-populate display name when model ID changes
    const modelIdInput = document.getElementById('form-model-id');
    const modelNameInput = document.getElementById('form-model-name');
    if (modelIdInput && modelNameInput) {
        modelIdInput.addEventListener('input', () => {
            if (!modelNameInput.value) {
                // Suggest a name from the model ID last segment
                const parts = modelIdInput.value.split('/');
                modelNameInput.placeholder = parts[parts.length - 1] || '';
            }
        });
    }
}

function submitAddModel() {
    const preset = PROVIDER_PRESETS[selectedProvider] || PROVIDER_PRESETS.custom;
    const nameInput  = document.getElementById('form-model-name');
    const idInput    = document.getElementById('form-model-id');
    const keyInput   = document.getElementById('form-api-key');
    const baseInput  = document.getElementById('form-api-base');
    const timeoutInput    = document.getElementById('form-timeout');
    const maxTokensInput  = document.getElementById('form-max-tokens');

    const name    = nameInput ? nameInput.value.trim() : '';
    const modelId = idInput   ? idInput.value.trim()   : '';
    const apiKey  = keyInput  ? keyInput.value.trim()  : (preset.needsApiKey ? '' : 'local');
    const apiBase = baseInput ? baseInput.value.trim() : '';

    if (!name) { showFormFeedback('error', 'Display name is required.'); return; }
    if (!modelId) { showFormFeedback('error', 'Model ID is required.'); return; }
    if (preset.needsApiKey && !apiKey) { showFormFeedback('error', 'API key is required.'); return; }

    // Build the model protocol string
    let fullModel;
    if (selectedProvider === 'custom') {
        fullModel = modelId; // user enters full protocol/model-id
    } else if (selectedProvider === 'local') {
        fullModel = `llama-server/${modelId}`;
    } else {
        fullModel = `${preset.protocol}/${modelId}`;
    }

    const entry = {
        model_name:      name,
        model:           fullModel,
        api_key:         apiKey || 'local',
        request_timeout: parseInt(timeoutInput ? timeoutInput.value : preset.timeout, 10) || preset.timeout,
        max_tokens:      parseInt(maxTokensInput ? maxTokensInput.value : preset.maxTokens, 10) || preset.maxTokens,
    };

    if (apiBase) entry.api_base = apiBase;

    const submitBtn = document.getElementById('btn-submit-model');
    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Adding…'; }

    socket.emit('commands', { command: 'add_model', entry });
}

function clearAddModelForm() {
    const container = document.getElementById('add-model-form-container');
    if (container) container.innerHTML = '';
    document.querySelectorAll('.provider-chip').forEach(c => c.classList.remove('selected'));
    selectedProvider = null;
}

function showFormFeedback(type, message) {
    const fb = document.getElementById('form-feedback');
    if (!fb) return;
    fb.innerHTML = `<div class="form-${type}">${message}</div>`;
    const submitBtn = document.getElementById('btn-submit-model');
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Add model'; }
}

// ── Onboarding ────────────────────────────────────────────────────────────────

function checkOnboarding(models) {
    const hasCloud = models.some(m => !isLocalModel(m));
    const prompt = document.getElementById('onboarding-cloud-prompt');
    if (prompt) {
        prompt.style.display = hasCloud ? 'none' : 'flex';
    }
}

// ── Socket.IO ─────────────────────────────────────────────────────────────────

function initSocketIO() {
    socket.on('response',       handleResponse);
    socket.on('stream_end',     handleStreamEnd);
    socket.on('llm_error',      handleLLMError);
    socket.on('command_ok',     handleCompletedCommand);
    socket.on('command_error',  handleCommandError);
    socket.on('mode_changed',   (data) => updateModePills(data.mode));
    socket.on('model_changed',  handleModelChanged);
    socket.on('tool_event',     handleToolEvent);
    socket.on('daemon_status',  handleDaemonStatus);

    socket.on('connect', () => {
        console.log('Connected to backend');
        const savedMode = localStorage.getItem('qclaw-mode') || 'low';
        updateModePills(savedMode);
        socket.emit('commands', { command: 'set_mode', value: savedMode });
        loadModels();
        // v3.0.6.1: ask backend for current daemon state on every (re)connect.
        // Closes the v3.0.5 race where the initial _emit_daemon_status() fires
        // before the browser is connected; without this, late-connecting
        // browsers never see the daemon-missing banner.
        socket.emit('commands', { command: 'recheck_daemon' });
    });

    socket.on('disconnect', () => {
        showError('Connection to backend lost. Please refresh the page or check the backend server.');
    });
}

// ── Input helpers ─────────────────────────────────────────────────────────────

function autoExpandInput(field) {
    field.style.height = 'auto';
    field.style.height = field.scrollHeight + 'px';
}

function updateSendButtonState() {
    const userInput = document.getElementById('user-input');
    if (userInput && sendButton) {
        if (sendButton.classList.contains('sending-state')) {
            sendButton.classList.remove('disabled');
            sendButton.removeAttribute('disabled');
            return;
        }
        if (userInput.value.trim() === '') {
            sendButton.classList.add('disabled');
            sendButton.setAttribute('disabled', 'disabled');
        } else {
            sendButton.classList.remove('disabled');
            sendButton.removeAttribute('disabled');
        }
    }
}

function updateClearChatButtonState() {
    const messagesContainer = document.getElementById('messages');
    const clearChatButton   = document.getElementById('clear-chat-button-header');
    if (messagesContainer && clearChatButton) {
        if (messagesContainer.children.length === 0) {
            clearChatButton.classList.add('disabled');
            clearChatButton.setAttribute('disabled', 'disabled');
        } else {
            clearChatButton.classList.remove('disabled');
            clearChatButton.removeAttribute('disabled');
        }
    }
}

function sendClearChatCommand() {
    socket.emit('commands', { command: 'clear_chat' });
}

function sendMessage(text) {
    hideError();
    document.getElementById('empty-chat-container').style.display = 'none';
    const mainContent = document.querySelector('.main-content');
    if (mainContent) mainContent.classList.add('chat-active');
    const userInput = document.getElementById('user-input');
    if (!text) text = userInput.value;
    lastUserPrompt = text;

    if (sendButton) {
        sendButton.classList.add('sending-state');
        if (sendButtonImg) sendButtonImg.src = 'img/stop.svg';
    }

    userInput.value = '';
    userInput.style.height = '32px';
    updateSendButtonState();
    updatePlaceholderVisibility();

    if (quickActionButtonsContainer) quickActionButtonsContainer.style.display = 'flex';

    const userMessageDiv = document.createElement('div');
    userMessageDiv.className = 'user-message';
    userMessageDiv.textContent = text;
    document.getElementById('messages').appendChild(userMessageDiv);

    thinkingMessageElement = document.createElement('div');
    thinkingMessageElement.className = 'ai-response thinking-message';
    thinkingMessageElement.id = 'active-ai-response';

    const icon = document.createElement('img');
    icon.src = 'img/sparkle.svg';
    icon.className = 'ai-icon';
    thinkingMessageElement.appendChild(icon);

    const textContent = document.createElement('div');
    textContent.className = 'text-content';
    textContent.innerHTML = '<span class="circular-loader"></span>Thinking<span class="dot-1">.</span><span class="dot-2">.</span><span class="dot-3">.</span>';
    thinkingMessageElement.appendChild(textContent);

    document.getElementById('messages').appendChild(thinkingMessageElement);

    socket.emit('prompt', { prompt: text });
    updateClearChatButtonState();
    document.getElementById('user-input').focus();
}

function updatePlaceholderVisibility() {
    const userInput = document.getElementById('user-input');
    if (customPlaceholder) {
        customPlaceholder.style.display = userInput.value.trim() === '' ? 'flex' : 'none';
    }
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initSocketIO();
    initModePills();
    initModelSelector();
    initProviderChips();
    initDaemonBanner();

    const userInput     = document.getElementById('user-input');
    sendButton          = document.getElementById('send-button');
    sendButtonImg       = sendButton ? sendButton.querySelector('img') : null;
    quickActionButtonsContainer = document.getElementById('quick-action-buttons');
    customPlaceholder   = document.querySelector('.custom-placeholder');
    const clearChatButton     = document.getElementById('clear-chat-button-header');
    const settingsButton      = document.getElementById('settings-button');
    const settingsClose       = document.getElementById('settings-close');
    const settingsOverlay     = document.getElementById('settings-overlay');
    const onboardingSetupBtn  = document.getElementById('onboarding-setup-btn');

    updateSendButtonState();
    updateClearChatButtonState();
    updatePlaceholderVisibility();
    userInput.focus();

    // Input events
    userInput.addEventListener('input', () => {
        autoExpandInput(userInput);
        updateSendButtonState();
        updatePlaceholderVisibility();
    });

    userInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            if (!sendButton.classList.contains('disabled')) sendMessage();
        }
    });

    if (sendButton) {
        sendButton.addEventListener('click', (event) => {
            event.preventDefault();
            if (sendButton.classList.contains('disabled')) return;
            if (sendButton.classList.contains('sending-state')) {
                socket.emit('commands', { command: 'stop_stream' });
            } else {
                sendMessage();
            }
        });
    }

    clearChatButton.addEventListener('click', (event) => {
        if (clearChatButton.classList.contains('disabled')) {
            event.preventDefault();
        } else {
            sendClearChatCommand();
        }
    });

    // Settings panel
    if (settingsButton)  settingsButton.addEventListener('click', () => openSettings());
    if (settingsClose)   settingsClose.addEventListener('click', closeSettings);
    if (settingsOverlay) {
        settingsOverlay.addEventListener('click', (e) => {
            if (e.target === settingsOverlay) closeSettings();
        });
    }

    // Onboarding shortcut
    if (onboardingSetupBtn) {
        onboardingSetupBtn.addEventListener('click', () => openSettings(true));
    }

    // Quick action buttons
    if (quickActionButtonsContainer) {
        const quickButtons = quickActionButtonsContainer.querySelectorAll('.quick-action-button');
        quickButtons.forEach(button => {
            button.addEventListener('click', () => {
                if (userInput.value.length > 0 && userInput.value.slice(-1) !== ' ') {
                    userInput.value += ' ';
                }
                userInput.value += button.textContent;
                autoExpandInput(userInput);
                updateSendButtonState();
                updatePlaceholderVisibility();
                userInput.focus();
            });
        });
    }

    // Suggestion cards
    document.getElementById('card-1').addEventListener('click', () => sendMessage(document.getElementById('card-1').querySelector('p').textContent));
    document.getElementById('card-2').addEventListener('click', () => sendMessage(document.getElementById('card-2').querySelector('p').textContent));
    document.getElementById('card-3').addEventListener('click', () => sendMessage(document.getElementById('card-3').querySelector('p').textContent));
    document.getElementById('card-4').addEventListener('click', () => sendMessage(document.getElementById('card-4').querySelector('p').textContent));
});
