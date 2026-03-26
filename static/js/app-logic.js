function mainApp() {
    return {
        // UI state
        activePanel: 'chat',
        sidebarOpen: false,
        vrmSystemEnabled: localStorage.getItem('vrmSystemEnabled') === 'true', // 默认 false (关闭VRM系统)
        showVrm: localStorage.getItem('showVrm') === 'true',                   // 默认 false (折叠VRM面板)

        // Agent status
        agentOnline: false,
        statusText: '连接中...',
        eventSource: null,

        // Chat
        messages: [{ id: 'sys-0', role: 'assistant', content: '主人，我回来啦~！' }],
        inputText: '',
        isReceiving: false,
        currentController: null,

        // Image paste / drop / staged files
        stagedFiles: [],       // Array of File objects
        isDragOver: false,

        // Slash commands
        showCommandMenu: false,
        commandSelectedIndex: 0,
        availableCommands: [
            // ── 会话管理 ──
            { command: '/clear', desc: '清空当前页面对话历史', action: 'clear_chat', icon: '✗' },
            { command: '/new', desc: '新建会话并保存当前历史', action: 'new_session', icon: '+' },
            // ── 模型管理 ──
            { command: '/upload', desc: '上传本地文件（图片/文本）发给 AI 分析', action: 'upload_file', icon: '↑' },
            { command: '/save', desc: '保存当前模型视角与位置配置', action: 'save_vrm', icon: '▣' },
            // ── AI 快捷任务 ──
            { command: '/recall ', desc: '搜索长期记忆，如: /recall 南京', action: 'send_recall', icon: '◐' },
            { command: '/plan', desc: '查看当前活跃任务计划状态', action: 'send_plan', icon: '▤' },
            { command: '/weather ', desc: '查询天气，如: /weather 上海', action: 'send_weather', icon: '◑' },
            { command: '/remind ', desc: '设置提醒，如: /remind 10分钟后喝水', action: 'send_remind', icon: '◔' },
            { command: '/screenshot', desc: '截取屏幕并让 AI 分析当前画面', action: 'send_screenshot', icon: '▨' },
            // ── 系统维护 ──
            { command: '/poke', desc: '强制触发一次视觉感知', action: 'poke_ai', icon: '→' },
            { command: '/sandbox clear', desc: '清理所有后台沙箱实例', action: 'clear_sandbox', icon: '⊘' },
        ],
        filteredCommands: [],

        // Debug log
        debugLogs: [],
        contextStatus: '',
        expandedContext: false,

        // Context tracking
        lastBackendTokens: 0,
        lastMaxTokens: 182200,

        get contextTokens() {
            // Context used = last backend total_tokens + offline estimation of current input
            let tokens = this.lastBackendTokens || 0;
            const text = this.inputText || '';
            tokens += Math.ceil(text.length * 0.8);

            if (this.stagedFiles && this.stagedFiles.length > 0) {
                // Approximate 500-1000 tokens per file depending on type, just a very rough indicator
                tokens += this.stagedFiles.length * 800;
            }
            return tokens;
        },
        get maxTokensDisplay() {
            return this.lastMaxTokens;
        },
        get contextDisplay() {
            const current = this.contextTokens;
            const max = this.maxTokensDisplay;
            const percentage = ((current / max) * 100).toFixed(1);
            const formatK = (num) => num >= 1000 ? (num / 1000).toFixed(1) + 'K' : num.toString();
            return `${percentage}% • ${formatK(current)} / ${formatK(max)} context used`;
        },

        // Data
        sessions: [],
        currentSessionId: null,
        diaryDates: [],
        selectedDiaryContent: null,
        memoryItems: [],
        memoryFilteredItems: [],
        memorySearch: '',
        memoryTypeFilter: 'all',
        mcpServers: [],
        mcpLoading: false,
        mcpSaving: false,
        personas: {},
        config: {
            browser_choice: 'edge',
            proactive: { interval_minutes: null, cooldown_minutes: null, verbose: true, mode: 'silent' },
            journal: { enable_diary: false },
            channels: {
                telegram: { bot_token: '', proxy: '' },
                feishu: { app_id: '', app_secret: '' },
                dingtalk: { client_id: '', client_secret: '' }
            }
        },
        channelTestResults: {},
        proactiveDefaults: {
            silent: { interval_minutes: null, cooldown_minutes: null },
            normal: { interval_minutes: 5, cooldown_minutes: 15 },
            lively: { interval_minutes: 5, cooldown_minutes: 1 }
        },
        imChannels: [],
        imSessions: [],

        // Scheduler
        schedulerTasks: [],
        schedulerExecutions: [],
        schedulerViewTab: 'tasks',
        showSchedulerForm: false,
        schedulerFormData: {
            id: null,
            name: '',
            description: '',
            delivery_workspace_enabled: true,
            delivery_desktop_enabled: false,
            delivery_im_enabled: false,
            delivery_targets: [],
            target_kind: 'workspace_inbox',
            target_workspace_id: '',
            target_session_id: '',
            target_desktop_session_id: '',
            target_im_session_id: '',
            target_channel: '',
            target_chat_id: '',
            task_type: 'task',
            prompt: '',
            reminder_message: '',
            trigger_type: 'once',
            enabled: true,
            trigger_config_onceTime: '',
            trigger_config_intervalMinutes: 0,
            trigger_config_intervalHours: 0,
            trigger_config_cron: '0 9 * * *',
            trigger_preset_time: '09:00',
            trigger_preset_weekday: '1',
            trigger_preset_day: '1'
        },

        // Model Config Data
        vrmModels: [],
        vrmAnimations: [],
        uploadingModel: false,
        uploadStatus: '',
        saveVrmStatus: '',

        // Store state
        storeLoading: false,
        storeItems: { models: [], animations: [] },
        downloadingItems: [],
        selectedCategory: 'All',
        categories: ['All', 'Vroid', 'Official', 'Basic'],

        // Skills state
        skills: [],
        skillSearchQuery: '',
        skillCategoryFilter: 'all',
        skillStatusFilter: 'all',
        skillMarketplace: [],
        skillMarketLoading: false,
        skillMarketSearch: '',
        skillInstallingId: null,
        skillInstallMsg: null,
        skillTab: 'installed',
        skillUrlInput: '',
        expandedSkills: [], // track expanded skill tool lists in marketplace

        // System state
        requiresRestart: false,

        // Model endpoint config state
        configTab: 'models',
        modelConfig: {},           // loaded from /api/config/model
        modelDrafts: {},           // edit drafts per role
        modelShowKey: {},          // show/hide API key per role
        modelExpandedRole: 'api',  // which accordion card is open
        modelSaving: {},           // saving spinner
        modelTesting: {},          // testing spinner
        modelTestResult: {},       // test result per role
        modelProviders: [],        // from /api/config/model/providers
        modelRoles: [],            // from /api/config/model/providers
        modelDraftProvider: {},    // currently selected provider slug per role

        // Chat Endpoints list state
        chatEndpoints: [],         // list of {id,name,provider,base_url,api_key,model,...}
        activeEndpointId: null,    // ID of the currently active endpoint
        endpointSwitching: false,  // spinner when switching active endpoint
        epEditIdx: null,           // which endpoint card is expanded for editing
        epShowKey: {},             // show/hide api_key per endpoint index
        epSaving: false,           // endpoint list save spinner
        epTesting: {},             // testing per endpoint index
        epTestResult: {},          // test result per endpoint index
        epFetchedModels: {},       // fetched model list per endpoint index {idx: [modelId,...]}
        epModelFetching: {},       // fetching spinner per endpoint index
        epModelFetchError: {},     // fetch error message per endpoint index

        // Role Endpoints (extra endpoints per functional role: vision/image_analyzer/embedding/autogui)
        roleEndpoints: {},         // {role_key: [{name,provider,base_url,api_key,model,...}]}
        roleEpTesting: {},         // {'vision-0': true/false}
        roleEpTestResult: {},      // {'vision-0': {status,model,error}}
        roleEpSaving: {},          // {role_key: true/false}
        roleEpFetchedModels: {},   // {'vision-0': [modelId,...]}
        roleEpModelFetching: {},   // {'vision-0': true/false}
        roleEpModelFetchError: {}, // {'vision-0': 'error message'}

        // Token stats
        tokenStats: {
            total_prompt_tokens: 0,
            total_completion_tokens: 0,
            total_tokens: 0,
            request_count: 0,
            by_model: {},
            timeline: [],
        },
        tokenPeriod: '1d',

        // Chat model/agent selector
        chatModel: '',          // '' means use default
        chatAgent: null,        // null means use default
        chatModelList: [],      // [{id, name}]
        chatAgentList: [],      // [{id, name, icon, ...}]
        showModelPicker: false,
        showAgentPicker: false,

        async init() {
            await this.checkStatus();
            setInterval(() => this.checkStatus(), 15000);
            this.loadSessions();
            this.loadDiaryDates();
            this.subscribeEvents();
            this.loadModels();
            this.loadAnimations();
            this.loadCurrentSession();
            this.loadGlobalConfig();
            this.refreshSchedulerData();
            this.loadModelConfig();
            this.loadChatEndpoints();
            this.loadRoleEndpoints();
            this.loadMemories();
            this.loadMcpServers();
            this.loadTokenStats(this.tokenPeriod);
            this.loadChatModels();
            this.loadChatAgents();
        },

        // ── loadRoleEndpoints ──────────────────────────────────────────────
        // Merges the primary config.json role sections (vision/image_analyzer/embedding/autogui)
        // with any extra endpoints stored under role_extra_endpoints.
        async loadRoleEndpoints() {
            const ROLE_KEYS = ['vision', 'image_analyzer', 'embedding', 'autogui'];
            try {
                // 1) Fetch primary role configs from /api/config/model
                let primary = {};
                const mr = await fetch('/api/config/model');
                if (mr.ok) {
                    const md = await mr.json();
                    const cfg = md.config || {};
                    for (const key of ROLE_KEYS) {
                        if (cfg[key] && cfg[key].configured !== false) {
                            primary[key] = {
                                name: key === 'vision' ? '视觉模型（主）' :
                                    key === 'image_analyzer' ? '图像解析（主）' :
                                        key === 'embedding' ? '嵌入模型（主）' : 'GUI操作（主）',
                                provider: '',
                                base_url: cfg[key].base_url || '',
                                api_key: cfg[key].api_key || '',
                                model: cfg[key].model || '',
                                _primary: true,  // marks this as the top-level config.json entry
                            };
                        }
                    }
                }

                // 2) Fetch extra endpoints from /api/config/role-endpoints
                let extra = {};
                const er = await fetch('/api/config/role-endpoints');
                if (er.ok) {
                    const ed = await er.json();
                    extra = ed.role_extra_endpoints || {};
                }

                // 3) Ensure modelProviders is loaded (may not be ready on first call)
                let providers = this.modelProviders || [];
                if (providers.length === 0) {
                    try {
                        const pr = await fetch('/api/config/model/providers');
                        if (pr.ok) {
                            const pd = await pr.json();
                            providers = pd.providers || [];
                            if (!this.modelProviders || this.modelProviders.length === 0) {
                                this.modelProviders = providers;
                            }
                        }
                    } catch (_) { /* ignore, provider matching is best-effort */ }
                }

                // 4) Merge: primary first, then extra endpoints
                const merged = {};
                for (const key of ROLE_KEYS) {
                    const arr = [];
                    if (primary[key]) arr.push(primary[key]);
                    if (extra[key] && Array.isArray(extra[key])) {
                        extra[key].forEach(ep => {
                            if (!ep._primary) arr.push(ep);
                        });
                    }

                    // Auto-match provider for role endpoints
                    if (providers.length > 0) {
                        arr.forEach(ep => {
                            if (!ep.provider || ep.provider === 'custom') {
                                const matched = providers.find(pv =>
                                    (pv.base_url && ep.base_url) &&
                                    (pv.base_url.replace(/\/$/, '') === ep.base_url.replace(/\/$/, ''))
                                );
                                if (matched) ep.provider = matched.slug;
                            }
                        });
                    }

                    merged[key] = arr;
                }
                this.roleEndpoints = merged;
            } catch (e) { console.error('Failed to load role endpoints:', e); }
        },

        async loadMemories() {
            try {
                const r = await fetch('/api/memory');
                if (r.ok) {
                    const data = await r.json();
                    this.memoryItems = (data.memories || []).map(m => ({
                        ...m,
                        _selected: false,
                        _editing: false,
                        _editBuffer: '',
                        _confirmDelete: false
                    }));
                    this.refreshFilteredMemories();
                }
            } catch (e) { console.error('Failed to load memories:', e); }
        },

        refreshFilteredMemories() {
            const search = (this.memorySearch || '').trim().toLowerCase();
            const type = this.memoryTypeFilter || 'all';
            this.memoryFilteredItems = this.memoryItems.filter((item) => {
                const matchesType = type === 'all' || (item.type || 'general') === type;
                if (!matchesType) return false;
                if (!search) return true;
                const haystack = [
                    item.content || '',
                    item.type || '',
                    ...(Array.isArray(item.tags) ? item.tags : [])
                ].join(' ').toLowerCase();
                return haystack.includes(search);
            });
        },

        get selectedMemoryCount() {
            return this.memoryItems.filter(m => m._selected).length;
        },

        get allMemoriesSelected() {
            return this.memoryItems.length > 0 && this.selectedMemoryCount === this.memoryItems.length;
        },

        toggleMemorySelectAll() {
            const select = !this.allMemoriesSelected;
            this.memoryItems.forEach(m => m._selected = select);
        },

        async batchDeleteMemories() {
            const ids = this.memoryItems.filter(m => m._selected).map(m => m.id);
            if (ids.length === 0) return;

            try {
                const r = await fetch('/api/memory/batch_delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids })
                });
                if (r.ok) {
                    this.pushLog('status', `已删除 ${ids.length} 条记忆`);
                    await this.loadMemories();
                } else {
                    this.pushLog('error', '批量删除记忆失败');
                }
            } catch (e) { console.error(e); }
        },

        async deleteMemory(id) {
            if (!id) return;
            try {
                const r = await fetch(`/api/memory/${id}`, { method: 'DELETE' });
                if (r.ok) {
                    this.pushLog('status', '记忆已成功删除');
                    await this.loadMemories();
                } else {
                    this.pushLog('error', '删除记忆失败 (API 错误)');
                }
            } catch (e) {
                console.error(e);
                this.pushLog('error', '网络异常');
            }
        },

        startEditMemory(item) {
            item._editBuffer = item.content;
            item._editing = true;
        },

        cancelEditMemory(item) {
            item._editing = false;
        },

        async saveMemoryEdit(item) {
            try {
                const r = await fetch(`/api/memory/${item.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: item._editBuffer })
                });
                if (r.ok) {
                    this.pushLog('status', '记忆已更新');
                    item.content = item._editBuffer;
                    item._editing = false;
                    this.refreshFilteredMemories();
                    // re-fetch to ensure sync (optional)
                    // await this.loadMemories();
                } else {
                    this.pushLog('error', '更新记忆失败');
                }
            } catch (e) { console.error(e); }
        },

        async loadMcpServers() {
            this.mcpLoading = true;
            try {
                const r = await fetch('/api/mcp/servers');
                if (r.ok) {
                    const data = await r.json();
                    const servers = data.mcpServers || {};
                    this.mcpServers = Object.entries(servers).map(([name, cfg]) => ({
                        name,
                        command: cfg.command || '',
                        argsText: Array.isArray(cfg.args) ? cfg.args.join('\n') : '',
                        envText: cfg.env ? Object.entries(cfg.env).map(([k, v]) => `${k}=${v}`).join('\n') : '',
                        disabled: !!cfg.disabled
                    }));
                }
            } catch (e) {
                console.error('Failed to load MCP servers:', e);
                this.pushLog('error', '加载 MCP 工具配置失败');
            } finally {
                this.mcpLoading = false;
            }
        },

        addMcpServer() {
            this.mcpServers.push({
                name: '',
                command: '',
                argsText: '',
                envText: '',
                disabled: false
            });
        },

        removeMcpServer(idx) {
            this.mcpServers.splice(idx, 1);
        },

        async saveMcpServers() {
            this.mcpSaving = true;
            try {
                const payload = { mcpServers: {} };
                this.mcpServers.forEach((server) => {
                    const name = (server.name || '').trim();
                    if (!name) return;
                    const args = (server.argsText || '')
                        .split(/\r?\n/)
                        .map(s => s.trim())
                        .filter(Boolean);
                    const env = {};
                    (server.envText || '')
                        .split(/\r?\n/)
                        .map(s => s.trim())
                        .filter(Boolean)
                        .forEach((line) => {
                            const idx = line.indexOf('=');
                            if (idx <= 0) return;
                            const key = line.slice(0, idx).trim();
                            const value = line.slice(idx + 1).trim();
                            if (key) env[key] = value;
                        });

                    payload.mcpServers[name] = {
                        command: (server.command || '').trim(),
                        args,
                        ...(Object.keys(env).length ? { env } : {}),
                        ...(server.disabled ? { disabled: true } : {})
                    };
                });

                const r = await fetch('/api/mcp/servers', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (r.ok) {
                    this.pushLog('status', 'MCP 工具配置已保存');
                    await this.loadMcpServers();
                } else {
                    const data = await r.json().catch(() => ({}));
                    this.pushLog('error', `MCP 配置保存失败：${data.detail || '未知错误'}`);
                }
            } catch (e) {
                console.error(e);
                this.pushLog('error', 'MCP 配置保存异常');
            } finally {
                this.mcpSaving = false;
            }
        },


        // ── Chat Endpoints Methods ────────────────────────────────────────────

        async loadChatEndpoints() {
            try {
                const r = await fetch('/api/endpoints');
                if (r.ok) {
                    const data = await r.json();
                    let endpoints = data.endpoints || [];

                    // Auto-match provider by base_url if not explicitly set
                    if (this.modelProviders && this.modelProviders.length > 0) {
                        endpoints.forEach(ep => {
                            if (!ep.provider || ep.provider === 'custom') {
                                const matched = this.modelProviders.find(pv =>
                                    (pv.base_url && ep.base_url) &&
                                    (pv.base_url.replace(/\/$/, '') === ep.base_url.replace(/\/$/, ''))
                                );
                                if (matched) ep.provider = matched.slug;
                            }
                        });
                    }

                    this.chatEndpoints = endpoints;
                    this.activeEndpointId = data.active_id || null;
                }
            } catch (e) { console.error('Failed to load chat endpoints:', e); }
        },

        addChatEndpoint() {
            this.chatEndpoints.push({
                id: null, name: '', provider: 'custom',
                base_url: '', api_key: '', model: '',
                max_tokens: 8000, temperature: 0.7,
                _new: true,
            });
            // Directly set epExpandedIdx to open the new card
            this.epExpandedIdx = this.chatEndpoints.length - 1;
        },

        deleteChatEndpoint(idx) {
            this.chatEndpoints.splice(idx, 1);
            if (this.epEditIdx === idx) this.epEditIdx = null;
            else if (this.epEditIdx > idx) this.epEditIdx--;
        },

        applyEpPreset(epIdx, provider) {
            const ep = this.chatEndpoints[epIdx];
            if (!ep) return;
            ep.provider = provider.slug;
            ep.base_url = provider.base_url || '';
            if (!ep.name) ep.name = provider.name;
            if (provider.models && provider.models.length > 0 && !ep.model) {
                ep.model = provider.models[0];
            }
            // Trigger reactivity
            this.chatEndpoints = [...this.chatEndpoints];
        },

        async saveChatEndpoints() {
            this.epSaving = true;
            try {
                const r = await fetch('/api/endpoints', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.chatEndpoints),
                });
                const data = await r.json();
                if (r.ok && data.status === 'ok') {
                    if (data.requires_restart) this.requiresRestart = true;
                    await this.loadChatEndpoints(); // reload with assigned IDs
                    this.epEditIdx = null;
                    this.pushLog('status', `✓ 已保存 ${data.count} 个端点配置`);
                } else {
                    this.pushLog('error', `端点保存失败：${data.detail || JSON.stringify(data)}`);
                }
            } catch (e) {
                this.pushLog('error', `端点保存异常：${e.message}`);
            } finally {
                this.epSaving = false;
            }
        },

        async testChatEndpoint(epIdx) {
            const ep = this.chatEndpoints[epIdx];
            if (!ep?.model) return;
            this.epTesting = { ...this.epTesting, [epIdx]: true };
            this.epTestResult = { ...this.epTestResult, [epIdx]: null };
            try {
                const r = await fetch('/api/config/model/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        role: 'api',
                        base_url: ep.base_url || '',
                        api_key: ep.api_key || '',
                        model: ep.model || '',
                    }),
                });
                const data = await r.json();
                this.epTestResult = { ...this.epTestResult, [epIdx]: data };
                if (data.status === 'ok') {
                    setTimeout(() => { this.epTestResult = { ...this.epTestResult, [epIdx]: null }; }, 5000);
                }
            } catch (e) {
                this.epTestResult = { ...this.epTestResult, [epIdx]: { status: 'error', error: e.message } };
            } finally {
                this.epTesting = { ...this.epTesting, [epIdx]: false };
            }
        },

        async fetchEndpointModels(epIdx) {
            const ep = this.chatEndpoints[epIdx];
            if (!ep?.base_url) return;
            this.epModelFetching = { ...this.epModelFetching, [epIdx]: true };
            this.epModelFetchError = { ...this.epModelFetchError, [epIdx]: null };
            try {
                const r = await fetch('/api/endpoints/fetch-models', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ base_url: ep.base_url, api_key: ep.api_key || '' }),
                });
                const data = await r.json();
                if (data.status === 'ok') {
                    this.epFetchedModels = { ...this.epFetchedModels, [epIdx]: data.models };
                } else {
                    this.epModelFetchError = { ...this.epModelFetchError, [epIdx]: data.error || '获取失败' };
                }
            } catch (e) {
                this.epModelFetchError = { ...this.epModelFetchError, [epIdx]: e.message };
            } finally {
                this.epModelFetching = { ...this.epModelFetching, [epIdx]: false };
            }
        },

        async switchChatEndpoint(id) {
            if (id === this.activeEndpointId || this.endpointSwitching) return;
            this.endpointSwitching = true;
            try {
                const r = await fetch('/api/endpoints/active', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id }),
                });
                const data = await r.json();
                if (r.ok && data.status === 'ok') {
                    if (data.requires_restart) this.requiresRestart = true;
                    this.activeEndpointId = data.active_id;
                    this.pushLog('status', `✓ 已切换模型 → ${data.name} (${data.model})`);
                } else {
                    this.pushLog('error', `切换失败：${data.detail || JSON.stringify(data)}`);
                }
            } catch (e) {
                this.pushLog('error', `切换异常：${e.message}`);
            } finally {
                this.endpointSwitching = false;
            }
        },
        // ── Role Endpoint Methods (vision / image_analyzer / embedding / autogui) ──────────

        addRoleEndpoint(roleKey) {
            if (!this.roleEndpoints[roleKey]) this.roleEndpoints[roleKey] = [];
            this.roleEndpoints[roleKey].push({
                name: '', provider: 'custom',
                base_url: '', api_key: '', model: '',
                _new: true,   // triggers auto-open in x-data
            });
            // Trigger Alpine reactivity
            this.roleEndpoints = { ...this.roleEndpoints };
        },

        deleteRoleEndpoint(roleKey, idx) {
            if (!this.roleEndpoints[roleKey]) return;
            this.roleEndpoints[roleKey].splice(idx, 1);
            this.roleEndpoints = { ...this.roleEndpoints };
        },

        applyRoleEpPreset(roleKey, idx, provider) {
            if (!this.roleEndpoints[roleKey]?.[idx]) return;
            const rep = this.roleEndpoints[roleKey][idx];
            rep.provider = provider.slug;
            rep.base_url = provider.base_url || '';
            if (!rep.name) rep.name = provider.name;
            if (provider.models?.length && !rep.model) rep.model = provider.models[0];
            this.roleEndpoints = { ...this.roleEndpoints };
        },

        async testRoleEndpoint(roleKey, idx) {
            const rep = this.roleEndpoints[roleKey]?.[idx];
            if (!rep?.model) return;
            const key = `${roleKey}-${idx}`;
            this.roleEpTesting = { ...this.roleEpTesting, [key]: true };
            this.roleEpTestResult = { ...this.roleEpTestResult, [key]: null };
            try {
                const r = await fetch('/api/config/model/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        role: roleKey, base_url: rep.base_url || '',
                        api_key: rep.api_key || '', model: rep.model || '',
                    }),
                });
                const data = await r.json();
                this.roleEpTestResult = { ...this.roleEpTestResult, [key]: data };
                if (data.status === 'ok') {
                    setTimeout(() => { this.roleEpTestResult = { ...this.roleEpTestResult, [key]: null }; }, 5000);
                }
            } catch (e) {
                this.roleEpTestResult = { ...this.roleEpTestResult, [key]: { status: 'error', error: e.message } };
            } finally {
                this.roleEpTesting = { ...this.roleEpTesting, [key]: false };
            }
        },

        async fetchRoleEndpointModels(roleKey, rIdx) {
            const rep = this.roleEndpoints[roleKey]?.[rIdx];
            if (!rep?.base_url) return;
            const key = `${roleKey}-${rIdx}`;
            this.roleEpModelFetching = { ...this.roleEpModelFetching, [key]: true };
            this.roleEpModelFetchError = { ...this.roleEpModelFetchError, [key]: null };
            try {
                const r = await fetch('/api/endpoints/fetch-models', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ base_url: rep.base_url, api_key: rep.api_key || '' }),
                });
                const data = await r.json();
                if (data.status === 'ok') {
                    this.roleEpFetchedModels = { ...this.roleEpFetchedModels, [key]: data.models };
                } else {
                    this.roleEpModelFetchError = { ...this.roleEpModelFetchError, [key]: data.error || '获取失败' };
                }
            } catch (e) {
                this.roleEpModelFetchError = { ...this.roleEpModelFetchError, [key]: e.message };
            } finally {
                this.roleEpModelFetching = { ...this.roleEpModelFetching, [key]: false };
            }
        },

        async saveRoleEndpoints(roleKey) {
            // Splits endpoints into primary (top-level config.json key) and extra (role_extra_endpoints).
            this.roleEpSaving[roleKey] = true;
            try {
                const allEps = this.roleEndpoints[roleKey] || [];
                const primaryEp = allEps.find(ep => ep._primary);
                const extraEps = allEps.filter(ep => !ep._primary);

                // Save primary endpoint via /api/config/model (writes top-level role key)
                if (primaryEp) {
                    const pr = await fetch('/api/config/model', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            role: roleKey,
                            base_url: primaryEp.base_url || '',
                            api_key: primaryEp.api_key || '',
                            model: primaryEp.model || '',
                        }),
                    });
                    const pd = await pr.json();
                    if (!pr.ok || pd.status !== 'ok') {
                        this.pushLog('error', `主端点保存失败：${pd.detail || JSON.stringify(pd)}`);
                        return;
                    }
                    if (pd.requires_restart) this.requiresRestart = true;
                }

                // Save extra endpoints via /api/config/role-endpoints
                const er = await fetch('/api/config/role-endpoints', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ role: roleKey, endpoints: extraEps }),
                });
                const ed = await er.json();
                if (er.ok && ed.status === 'ok') {
                    if (ed.requires_restart) this.requiresRestart = true;
                    // Clean _new flags
                    allEps.forEach(ep => delete ep._new);
                    this.roleEndpoints = { ...this.roleEndpoints };
                    this.pushLog('status', `✓ ${roleKey} 角色端点已保存`);
                } else {
                    this.pushLog('error', `额外端点保存失败：${ed.detail || JSON.stringify(ed)}`);
                }
            } catch (e) {
                this.pushLog('error', `保存异常：${e.message}`);
            } finally {
                this.roleEpSaving[roleKey] = false;
            }
        },
        // ── End Role Endpoint Methods ─────────────────────────────────────────────

        // ── End Chat Endpoints Methods ────────────────────────────────────────

        // ── Model Config Methods ─────────────────────────────────────────
        async loadModelConfig() {

            try {
                // Load providers/roles
                const pr = await fetch('/api/config/model/providers');
                if (pr.ok) {
                    const pd = await pr.json();
                    this.modelProviders = pd.providers || [];
                    this.modelRoles = pd.roles || [];
                }
                // Load current config
                const r = await fetch('/api/config/model');
                if (r.ok) {
                    const data = await r.json();
                    this.modelConfig = data.config || {};
                    // Initialize drafts from current config
                    for (const [key, val] of Object.entries(this.modelConfig)) {
                        if (!this.modelDrafts[key]) {
                            this.modelDrafts[key] = {
                                base_url: val.base_url || '',
                                api_key: val.api_key || '',
                                model: val.model || '',
                                max_tokens: val.max_tokens || 8192,
                                temperature: val.temperature || 0.7,
                            };
                        }
                    }
                }
            } catch (e) { console.error('Failed to load model config:', e); }
        },

        toggleModelRole(key) {
            this.modelExpandedRole = this.modelExpandedRole === key ? null : key;
            // Clear old test result when switching
            this.modelTestResult[key] = null;
        },

        setModelDraft(role, field, value) {
            if (!this.modelDrafts[role]) this.modelDrafts[role] = {};
            this.modelDrafts[role][field] = value;
        },

        applyProviderPreset(provider, currentRole) {
            const role = currentRole || this.modelExpandedRole;
            if (!role) return;
            if (!this.modelDrafts[role]) this.modelDrafts[role] = {};
            this.modelDrafts[role].base_url = provider.base_url || '';
            if (provider.models && provider.models.length > 0) {
                this.modelDrafts[role].model = provider.models[0];
            }
            this.modelDraftProvider[role] = provider.slug;
            // Expand the card for this role
            if (role) this.modelExpandedRole = role;
        },

        async saveModelEndpoint(role) {
            const draft = this.modelDrafts[role];
            if (!draft?.model) return;
            this.modelSaving[role] = true;
            this.modelTestResult[role] = null;
            try {
                const r = await fetch('/api/config/model', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        role,
                        base_url: draft.base_url || '',
                        api_key: draft.api_key || '',
                        model: draft.model || '',
                        max_tokens: draft.max_tokens || null,
                        temperature: draft.temperature || null,
                    })
                });
                const data = await r.json();
                if (r.ok && data.status === 'ok') {
                    if (data.requires_restart) this.requiresRestart = true;
                    // Refresh config from server
                    await this.loadModelConfig();
                    this.pushLog('status', `✓ ${role} 端点已保存：${draft.model}`);
                } else {
                    this.pushLog('error', `保存失败：${data.detail || JSON.stringify(data)}`);
                }
            } catch (e) {
                this.pushLog('error', `保存异常：${e.message}`);
            } finally {
                this.modelSaving[role] = false;
            }
        },

        async testModelEndpoint(role) {
            const draft = this.modelDrafts[role];
            if (!draft?.model) return;
            this.modelTesting = { ...this.modelTesting, [role]: true };
            this.modelTestResult = { ...this.modelTestResult, [role]: null };
            try {
                const r = await fetch('/api/config/model/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        role,
                        base_url: draft.base_url || '',
                        api_key: draft.api_key || '',
                        model: draft.model || '',
                    })
                });
                const data = await r.json();
                this.modelTestResult = { ...this.modelTestResult, [role]: data };
                // Auto-clear success result after 5s
                if (data.status === 'ok') {
                    setTimeout(() => { this.modelTestResult = { ...this.modelTestResult, [role]: null }; }, 5000);
                }
            } catch (e) {
                this.modelTestResult = { ...this.modelTestResult, [role]: { status: 'error', error: e.message } };
            } finally {
                this.modelTesting = { ...this.modelTesting, [role]: false };
            }
        },

        async applyAndRestart() {
            this.pushLog('system', "正在重启后端服务...");
            const modal = document.getElementById('restart-modal');
            if (modal) modal.style.display = 'flex';
            this.closeEventStream();
            const controller = new AbortController();
            const restartTimeout = setTimeout(() => controller.abort(), 2500);
            try {
                const resp = await fetch('/api/system/restart', {
                    method: 'POST',
                    signal: controller.signal,
                });
                if (!resp.ok) {
                    let detail = `HTTP ${resp.status}`;
                    try {
                        const payload = await resp.json();
                        if (payload && payload.detail) detail = payload.detail;
                    } catch (_) { /* ignore parse failure */ }
                    throw new Error(detail);
                }
            } catch (e) {
                const isTolerableDisconnect =
                    e?.name === 'AbortError' ||
                    e instanceof TypeError;
                if (!isTolerableDisconnect) {
                    console.warn("Restart request failed:", e);
                    this.pushLog('error', `❌ 无法自动重启: ${e.message}`);
                    alert(`无法自动重启: ${e.message}`);
                    if (modal) modal.style.display = 'none';
                    return;
                }
                console.warn("Restart request interrupted after trigger, continue polling:", e);
                this.pushLog('system', '重启请求连接已中断，继续等待服务恢复...');
            } finally {
                clearTimeout(restartTimeout);
            }

            // 先短暂等待，确保旧进程已经退出，避免轮询到旧进程
            await new Promise(r => setTimeout(r, 300));

            // Start polling health — 每 200ms 一次，比原来的 1s 快 5 倍
            let attempts = 0;
            const maxAttempts = 150; // 150 × 200ms = 30s 超时，与原逻辑等价
            const poll = setInterval(async () => {
                attempts++;
                try {
                    const r = await fetch('/api/health', { cache: 'no-store' });
                    if (r.ok) {
                        clearInterval(poll);
                        this.requiresRestart = false;
                        this.subscribeEvents();
                        const statusDiv = modal?.querySelector?.('div[style*="font-size:11px"]');
                        if (statusDiv) statusDiv.textContent = '服务就绪，由于不需要刷新页面所以不需要跳转';
                        setTimeout(() => {
                            if (modal) modal.style.display = 'none';
                        }, 1000);
                    }
                } catch (e) {
                    // still dead, keep waiting
                }
                if (attempts >= maxAttempts) {
                    clearInterval(poll);
                    alert("重启超时，请手动检查服务状态并刷新页面。");
                    if (modal) modal.style.display = 'none';
                }
            }, 200);
        },
        // ── End Model Config Methods ─────────────────────────────────────


        async loadGlobalConfig() {
            try {
                const r = await fetch('/api/config');
                if (r.ok) {
                    const data = await r.json();
                    // BUG#8 fix: defensive merge so missing keys don't break UI
                    this._fullConfig = data;
                    this.config.proactive = { ...this.config.proactive, ...(data.proactive || {}) };
                    this.config.journal = { ...this.config.journal, ...(data.journal || {}) };
                    this.config.channels = { ...this.config.channels, ...(data.channels || {}) };
                    // BUG#2 fix: restore vrm toggle from backend config (fallback to localStorage)
                    if (data.journal && typeof data.journal.vrm_enabled === 'boolean') {
                        this.vrmSystemEnabled = data.journal.vrm_enabled;
                        localStorage.setItem('vrmSystemEnabled', this.vrmSystemEnabled);
                    }
                }
            } catch (e) { console.error('Failed to load global config:', e); }
        },

        async setProactiveMode(m) {
            const def = this.proactiveDefaults[m];
            this.config.proactive = {
                ...this.config.proactive,
                mode: m,
                interval_minutes: def ? def.interval_minutes : this.config.proactive.interval_minutes,
                cooldown_minutes: def ? def.cooldown_minutes : this.config.proactive.cooldown_minutes
            };
            await this.saveGlobalConfig();
        },

        async saveGlobalConfig() {
            try {
                if (!this._fullConfig) {
                    this.pushLog('error', '⚠ 配置尚未加载完成，无法保存');
                    return;
                }
                this._fullConfig.proactive = this.config.proactive;
                this._fullConfig.journal = this.config.journal;
                this._fullConfig.channels = this.config.channels;
                const r = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this._fullConfig)
                });
                if (r.ok) {
                    this.pushLog('status', '⚙ 系统配置已实时更新');
                } else {
                    const err = await r.json().catch(() => ({}));
                    this.pushLog('error', `⚠ 保存配置失败: ${err.detail || r.status}`);
                }
            } catch (e) {
                this.pushLog('error', '⚠ 保存配置失败: ' + e.message);
            }
        },

        async testChannelConnection(channel) {
            try {
                this.channelTestResults[channel] = null;
                const r = await fetch('/api/config/channels/health', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        channel: channel,
                        // Send the current UI config so they don't have to save first
                        config: this.config.channels
                    })
                });

                if (r.ok) {
                    const data = await r.json();
                    if (data.results && data.results.length > 0) {
                        this.channelTestResults[channel] = data.results[0];
                    }
                } else {
                    const err = await r.json().catch(() => ({}));
                    this.channelTestResults[channel] = {
                        status: 'unhealthy',
                        error: err.detail || r.statusText
                    };
                }
            } catch (e) {
                this.channelTestResults[channel] = {
                    status: 'unhealthy',
                    error: e.message
                };
            }
        },

        async pokeAI() {
            try {
                const r = await fetch('/api/context/poke', { method: 'POST' });
                if (r.ok) {
                    this.pushLog('status', '⚡ 已强制触发视觉感知，AI 正在赶来...');
                }
            } catch (e) {
                this.pushLog('error', '❌ 触发失败: ' + e.message);
            }
        },

        async loadCurrentSession() {
            try {
                const r = await fetch('/api/sessions/current/info');
                if (r.ok) {
                    const { session_id } = await r.json();
                    if (session_id) {
                        this.currentSessionId = session_id;
                        await this.loadSession(session_id, true);
                    }
                }
            } catch { /* silently ignore startup failures */ }

            try {
                const pref = await (await fetch('/api/config/preferences')).json();
                if (pref && pref.browser_choice) {
                    this.config.browser_choice = pref.browser_choice;
                }
            } catch { /* silently ignore */ }
        },

        closeEventStream() {
            if (this.eventSource) {
                this.eventSource.close();
                this.eventSource = null;
            }
        },

        subscribeEvents() {
            this.closeEventStream();
            const es = new EventSource('/api/events');
            this.eventSource = es;
            es.onmessage = (e) => {
                try {
                    const ev = JSON.parse(e.data);
                    if (ev.type === 'context') {
                        const icon = { working: '💻', idle: '😴', error: '🔴', entertainment: '🎮' }[ev.status] || '❓';
                        this.pushLog('context', `${icon} ${ev.status} — ${ev.summary}`);
                        this.contextStatus = `${icon} ${ev.summary}`;
                    } else if (ev.type === 'system') {
                        this.pushLog('system', ev.text || '');
                    } else if (ev.type === 'proactive' && ev.message) {
                        this.pushLog('system', `👀 视觉系统观察到屏幕新动态 (已禁用自动搭话)`);
                    } else if (ev.type === 'chat_event') {
                        // Real-time chat update from scheduler or other background tasks.
                        // When the shell is using workspace-scoped threads, refresh the
                        // active workspace thread instead of the legacy global session.
                        const eventSessionId = ev.session_id || null;
                        const eventSessionIds = Array.isArray(ev.session_ids)
                            ? ev.session_ids.filter(id => typeof id === 'string' && id)
                            : (eventSessionId ? [eventSessionId] : []);
                        const workspaceIds = Array.isArray(ev.workspace_ids) ? ev.workspace_ids : [];
                        const activeWorkspaceId = this.activeWorkspaceId || null;
                        const currentThreadId = this.currentThreadId || null;
                        const matchesWorkspaceThread =
                            !!activeWorkspaceId &&
                            !!currentThreadId &&
                            eventSessionIds.includes(currentThreadId) &&
                            (workspaceIds.length === 0 || workspaceIds.includes(activeWorkspaceId));

                        if (activeWorkspaceId && typeof this.loadWorkspaceThreads === 'function') {
                            if (workspaceIds.length === 0 || workspaceIds.includes(activeWorkspaceId)) {
                                this.loadWorkspaceThreads(activeWorkspaceId, true);
                            }
                        }

                        if (matchesWorkspaceThread && typeof this.loadThread === 'function') {
                            this.loadThread(activeWorkspaceId, currentThreadId).then(() => {
                                this.$nextTick(() => this.scrollToBottom());
                            });
                        } else if (this.currentSessionId && eventSessionIds.includes(this.currentSessionId) && typeof this.loadSession === 'function') {
                            this.loadSession(this.currentSessionId, true).then(() => {
                                this.$nextTick(() => this.scrollToBottom());
                            });
                        } else {
                            this.loadCurrentSession().then(() => {
                                this.$nextTick(() => this.scrollToBottom());
                            });
                        }
                        // Do NOT force switch panel to 'chat' to avoid annoying UI jumps during automated tasks
                    } else if (ev.type === 'scheduler_updated') {
                        this.refreshSchedulerData();
                    } else if (ev.type === 'skills_version') {
                        this.loadSkills();
                        if (ev.message) {
                            this.pushLog('system', ev.message);
                        }
                    }
                } catch { }
            };
            es.onerror = () => {
                this.agentOnline = false;
                this.statusText = '连接中断，重连中...';
                if (this.eventSource === es && es.readyState === EventSource.CLOSED) {
                    this.eventSource = null;
                }
            };
            es.onopen = () => {
                this.checkStatus();
            };
        },

        async checkStatus() {
            try {
                const r = await fetch('/api/status');
                const data = await r.json();
                this.agentOnline = data.status === 'online';
                const persona = data.active_persona || 'unknown';
                this.statusText = this.agentOnline ? `在线 · ${persona}` : '离线';
                if (data.last_context_summary && !this.contextStatus) {
                    const icon = { working: '💻', idle: '😴', error: '🔴', entertainment: '🎮' }[data.last_context_status] || '❓';
                    this.contextStatus = `${icon} ${data.last_context_summary}`;
                }
            } catch {
                this.agentOnline = false;
                this.statusText = '连接失败';
            }
        },

        toggleVrmSystem(nextValue) {
            this.vrmSystemEnabled = typeof nextValue === 'boolean' ? nextValue : !this.vrmSystemEnabled;
            localStorage.setItem('vrmSystemEnabled', this.vrmSystemEnabled);
            if (!this.vrmSystemEnabled && this.showVrm) {
                this.showVrm = false;
                localStorage.setItem('showVrm', 'false');
            }
            // BUG#2 fix: persist vrm toggle to backend config
            if (this._fullConfig) {
                if (!this._fullConfig.journal) this._fullConfig.journal = {};
                this._fullConfig.journal.vrm_enabled = this.vrmSystemEnabled;
                this.saveGlobalConfig();
            }
            if (!this.vrmSystemEnabled && (this.activePanel === 'persona' || this.activePanel === 'store')) {
                this.switchPanel('chat');
            }
            if (typeof this.notifyShellStateChanged === 'function') {
                this.notifyShellStateChanged();
            }
            // 稍后触发 resize 防止页面布局更新时 3D 画布渲染错乱
            setTimeout(() => { window.dispatchEvent(new Event('resize')); }, 520);
        },

        toggleVrm() {
            this.showVrm = !this.showVrm;
            localStorage.setItem('showVrm', this.showVrm);
            if (typeof this.notifyShellStateChanged === 'function') {
                this.notifyShellStateChanged();
            }
            if (this.showVrm) {
                // 等待 CSS transition (500ms) 完成后再让 Three.js resize
                setTimeout(() => {
                    window.dispatchEvent(new Event('resize'));
                }, 520);
            } else {
                // 隐藏时立即通知布局变化
                this.$nextTick(() => {
                    window.dispatchEvent(new Event('resize'));
                });
            }
        },

        async switchPanel(panel) {
            this.activePanel = panel;
            if (panel === 'history' && this.sessions.length === 0) this.loadSessions();
            if (panel === 'im') this.fetchIMData();
            if (panel === 'diary' && this.diaryDates.length === 0) this.loadDiaryDates();
            if (panel === 'persona' && Object.keys(this.personas).length === 0) this.loadPersona();
            if (panel === 'skills' && this.skills.length === 0) this.loadSkills();
            if (panel === 'config' && this.vrmModels.length === 0) this.loadModels();
            if (panel === 'tokens') this.loadTokenStats(this.tokenPeriod);
            if (panel === 'debug') {
                this.$nextTick(() => {
                    const d = document.getElementById('debug-container');
                    if (d) d.scrollTop = d.scrollHeight;
                });
            }
        },

        async loadSessions() {
            try {
                this.sessions = await (await fetch('/api/sessions')).json();
            } catch { this.sessions = []; }
        },

        async fetchIMData() {
            try {
                const resC = await fetch('/api/im/channels');
                if (resC.ok) {
                    const data = await resC.json();
                    this.imChannels = data.channels || [];
                }
                const resS = await fetch('/api/im/sessions');
                if (resS.ok) {
                    const data = await resS.json();
                    this.imSessions = data.sessions || [];
                }
            } catch (err) {
                console.error('Failed to fetch IM data:', err);
                this.imChannels = [];
                this.imSessions = [];
            }
        },

        async loadSession(sessionId, keepPanel = false) {
            try {
                const data = await (await fetch(`/api/sessions/${sessionId}`)).json();
                this.debugLogs = [];
                const validMessages = [];
                let lastAssistantMsg = null;

                data.messages.forEach((m, i) => {
                    if (m.role === 'debug_log') {
                        try {
                            const ev = JSON.parse(m.content);
                            let text = '';
                            if (ev.type === 'tool_call') {
                                text = `${ev.name}(${JSON.stringify(ev.params || {}).slice(0, 50)}...)`;
                            } else if (ev.type === 'tool_result') {
                                text = `${ev.name} → ${ev.result}`;
                            } else if (ev.type === 'message') {
                                text = (ev.content || '响应已完成').replace(/\s+/g, ' ').slice(0, 80);
                                if ((ev.content || '').length > 80) text += '...';
                            } else {
                                text = ev.content || '';
                            }
                            this.debugLogs.push({ type: ev.type, text: text, ts: ev.ts || m.timestamp.split(' ')[1] });
                        } catch { }
                        return;
                    }

                    if (m.role === 'user') {
                        lastAssistantMsg = null;
                        let displayText = '';
                        if (Array.isArray(m.content)) {
                            // Reconstruct a clean display label from multimodal content:
                            // - image_url blocks → show as "[图片]" placeholder
                            // - text blocks that look like file content (【文件内容：...】) → show filename only
                            // - the final plain prompt text → show as-is
                            const fileParts = [];
                            let promptText = '';
                            for (const c of m.content) {
                                if (c.type === 'image_url') {
                                    fileParts.push('[图片]');
                                } else if (c.type === 'text') {
                                    // File content blocks start with 【文件内容：filename】
                                    const fileMatch = c.text.match(/^【文件内容：(.+?)】/);
                                    if (fileMatch) {
                                        fileParts.push(`[文件: ${fileMatch[1]}]`);
                                    } else {
                                        // This is the user's actual prompt (last text block)
                                        promptText = c.text.trim();
                                    }
                                }
                            }
                            const parts = [];
                            if (fileParts.length > 0) parts.push(fileParts.join(' '));
                            if (promptText) parts.push(promptText);
                            displayText = parts.join('\n\n') || '(附件)';
                        } else {
                            displayText = m.content || '';
                        }
                        validMessages.push({ id: `h-${i}`, role: m.role, content: displayText });
                    } else if (m.role === 'assistant') {
                        if (!lastAssistantMsg) {
                            lastAssistantMsg = {
                                id: `h-${i}`,
                                role: 'assistant',
                                content: '',
                                thinkingHtml: '',
                                _thinkingRaw: '',
                                blocks: [],
                                _thinkCollapsed: true
                            };
                            validMessages.push(lastAssistantMsg);
                        }
                        if (m.thinking) {
                            lastAssistantMsg._thinkingRaw += (lastAssistantMsg._thinkingRaw ? '\n\n' : '') + m.thinking;
                            lastAssistantMsg.thinkingHtml = this.mdRender(lastAssistantMsg._thinkingRaw);
                        }
                        if (m.content) {
                            lastAssistantMsg.blocks.push({ type: 'text', content: m.content, html: this.mdRender(m.content) });
                        }
                        if (m.tool_calls) {
                            (m.tool_calls || []).forEach(tc => {
                                lastAssistantMsg.blocks.push({
                                    type: 'tool',
                                    id: tc.id || tc.function?.name,
                                    name: tc.function?.name || 'unknown',
                                    paramsStr: tc.function?.arguments || '{}',
                                    status: 'done',
                                    _collapsed: true,
                                    resultStr: null
                                });
                            });
                        }
                    } else if (m.role === 'tool') {
                        if (lastAssistantMsg) {
                            const block = lastAssistantMsg.blocks.find(b => b.id === m.tool_call_id || b.name === m.name);
                            if (block) block.resultStr = m.content;
                        }
                    } else if (m.role === 'visual_log') {
                        lastAssistantMsg = null;
                        validMessages.push({ id: `h-${i}`, role: 'visual_log', content: m.content, html: this.mdRender(m.content) });
                    }
                });

                this.messages = validMessages;
                this.currentSessionId = sessionId;
                if (!keepPanel) this.activePanel = 'chat';

                // 使用后端精确估算的 token 数，避免刷新后 context bar 清零
                if (data.estimated_tokens > 0) this.lastBackendTokens = data.estimated_tokens;

                this.$nextTick(() => this.scrollToBottom());
            } catch { alert('加载对话失败。'); }
        },

        async deleteSession(sessionId) {
            if (!confirm('确定永久删除该节点吗？此操作无法撤销。')) return;
            try {
                const r = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
                if (r.ok) {
                    this.sessions = this.sessions.filter(s => s.id !== sessionId);
                    if (this.currentSessionId === sessionId) {
                        this.messages = [];
                        this.currentSessionId = null;
                    }
                    this.pushLog('status', `已销毁节点: ${sessionId}`);
                } else {
                    const err = await r.json().catch(() => ({}));
                    alert(`删除失败: ${err.detail || r.status}`);
                }
            } catch (e) {
                alert(`删除出错: ${e.message}`);
            }
        },

        async loadDiaryDates() {
            try {
                this.diaryDates = await (await fetch('/api/diary')).json();
            } catch { this.diaryDates = []; }
        },

        async loadDiary(date) {
            try {
                const data = await (await fetch(`/api/diary/${date}`)).json();
                this.selectedDiaryContent = data.content;
            } catch { alert('加载日记失败。'); }
        },

        async loadPersona() {
            try {
                this.personas = await (await fetch('/api/persona')).json();
            } catch { this.personas = {}; }
        },

        async loadChatModels() {
            try {
                const r = await fetch('/api/models/list');
                const data = await r.json();
                this.chatModelList = data.models || [];
            } catch { this.chatModelList = []; }
        },

        async loadChatAgents() {
            try {
                const r = await fetch('/api/agents');
                const data = await r.json();
                this.chatAgentList = data.agents || [];
            } catch { this.chatAgentList = []; }
        },

        async loadModels() {
            try {
                const r = await fetch('/api/vrm/models');
                const data = await r.json();
                this.vrmModels = data.models || [];
                this.uploadStatus = '';
            } catch (e) {
                this.vrmModels = [];
                this.uploadStatus = '加载模型列表失败: ' + e.message;
            }
        },

        async loadAnimations() {
            try {
                const r = await fetch('/api/vrm/animations');
                const data = await r.json();
                this.vrmAnimations = data.animations || [];
            } catch (e) {
                this.vrmAnimations = [];
            }
        },

        async uploadModel(e) {
            const file = e.target.files[0];
            if (!file) return;
            if (!file.name.toLowerCase().endsWith('.vrm')) {
                this.uploadStatus = '❌ 请上传 .vrm 格式文件';
                return;
            }
            this.uploadingModel = true;
            this.uploadStatus = '上传中...';
            const formData = new FormData();
            formData.append('file', file);
            try {
                const r = await fetch('/api/vrm/upload', { method: 'POST', body: formData });
                const data = await r.json();
                if (r.ok) {
                    this.uploadStatus = '✓ 上传成功';
                    this.loadModels();
                    this.switchVrmModel(data.path);
                } else {
                    this.uploadStatus = `❌ 上传失败: ${data.detail || '未知原因'}`;
                }
            } catch (err) {
                this.uploadStatus = `❌ 上传出错: ${err.message}`;
            } finally {
                this.uploadingModel = false;
                e.target.value = '';
                setTimeout(() => this.uploadStatus = '', 3000);
            }
        },

        switchVrmModel(modelPath) {
            const vm = window.appInstance?.vrmManager;
            if (!vm) return;
            let snapshot = null;
            try {
                const cam = vm.camera;
                const scene = vm.currentModel?.scene;
                if (cam && scene) {
                    snapshot = {
                        posX: scene.position.x, posY: scene.position.y, posZ: scene.position.z,
                        scaleX: scene.scale.x, scaleY: scene.scale.y, scaleZ: scene.scale.z,
                        camX: cam.position.x, camY: cam.position.y, camZ: cam.position.z,
                        qx: cam.quaternion.x, qy: cam.quaternion.y,
                        qz: cam.quaternion.z, qw: cam.quaternion.w,
                        tgtX: vm._cameraTarget?.x ?? 0,
                        tgtY: vm._cameraTarget?.y ?? 1,
                        tgtZ: vm._cameraTarget?.z ?? 0,
                    };
                }
            } catch (_) { }

            this.pushLog('status', `正在热切换模型: ${modelPath}`);
            const savedActionUrl = vm.animation?._lastVrmaUrl;

            vm.loadModel(modelPath, { autoPlay: false }).then(() => {
                const applySnapshot = () => {
                    if (snapshot) {
                        try {
                            const newScene = vm.currentModel?.scene;
                            const cam = vm.camera;
                            if (newScene) {
                                newScene.position.set(snapshot.posX, snapshot.posY, snapshot.posZ);
                                newScene.scale.set(snapshot.scaleX, snapshot.scaleY, snapshot.scaleZ);
                                newScene.rotation.set(0, 0, 0);
                            }
                            if (cam) {
                                cam.position.set(snapshot.camX, snapshot.camY, snapshot.camZ);
                                cam.quaternion.set(snapshot.qx, snapshot.qy, snapshot.qz, snapshot.qw);
                            }
                            if (window.THREE) {
                                vm._cameraTarget = new THREE.Vector3(snapshot.tgtX, snapshot.tgtY, snapshot.tgtZ);
                            }
                        } catch (_) { }
                    }
                    const lastUrl = savedActionUrl || '/static/vrm/animation/wait03.vrma';
                    if (vm.animation) {
                        vm.animation.playVRMAAnimation(lastUrl, { loop: true, immediate: true }).catch(() => { });
                    }
                    this.pushLog('status', `模型切换成功! 已继承当前视角并恢复动作`);
                };
                requestAnimationFrame(() => requestAnimationFrame(applySnapshot));
            }).catch(e => {
                this.pushLog('error', `模型切换失败: ${e.message}`);
            });
        },

        triggerExpression(mood) {
            if (window.appInstance?.vrmManager?.expression) {
                window.appInstance.vrmManager.expression.setMood(mood);
                this.pushLog('status', `触发表情: ${mood}`);
            }
        },

        triggerAction(url) {
            if (window.appInstance?.vrmManager) {
                window.appInstance.vrmManager.playVRMAAnimation(url, { loop: true });
                this.pushLog('status', `播放动作: ${url.split('/').pop()}`);
            }
        },

        async deleteModel(filename) {
            if (!confirm(`确定要删除模型 ${filename} 吗？`)) return;
            try {
                const r = await fetch(`/api/vrm/models/${encodeURIComponent(filename)}`, { method: 'DELETE' });
                const data = await r.json();
                if (r.ok) {
                    this.pushLog('status', `模型已删除: ${filename}`);
                    await this.loadModels();
                } else {
                    this.pushLog('error', `删除失败: ${data.detail || '未知原因'}`);
                }
            } catch (err) {
                this.pushLog('error', `删除出错: ${err.message}`);
            }
        },

        async saveVrmConfig() {
            const vm = window.appInstance?.vrmManager;
            if (!vm) {
                this.saveVrmStatus = 'error';
                setTimeout(() => this.saveVrmStatus = '', 3000);
                return;
            }
            this.saveVrmStatus = 'saving';
            try {
                const model = vm.currentModel;
                if (!model || !model.url || !model.scene) throw new Error('模型尚未加载');
                const scene = model.scene;
                const cam = vm.camera;
                const position = { x: scene.position.x, y: scene.position.y, z: scene.position.z };
                const scale = { x: scene.scale.x, y: scene.scale.y, z: scene.scale.z };
                const rotation = { x: scene.rotation.x, y: scene.rotation.y, z: scene.rotation.z };
                let cameraPosition = null;
                if (cam) {
                    const tgt = vm._cameraTarget || { x: 0, y: 0, z: 0 };
                    cameraPosition = {
                        x: cam.position.x, y: cam.position.y, z: cam.position.z,
                        qx: cam.quaternion.x, qy: cam.quaternion.y,
                        qz: cam.quaternion.z, qw: cam.quaternion.w,
                        targetX: tgt.x, targetY: tgt.y, targetZ: tgt.z
                    };
                }
                const payload = {
                    model_path: model.url, position, scale, rotation,
                    viewport: { width: window.screen.width, height: window.screen.height },
                    camera_position: cameraPosition
                };
                const r = await fetch('/api/config/preferences', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                this.saveVrmStatus = 'ok';
                this.pushLog('status', '视角配置已保存，刷新后将自动恢复');
                this.pushLog('status', `模型位置: x=${position.x.toFixed(3)}, y=${position.y.toFixed(3)}, z=${position.z.toFixed(3)}`);
                this.pushLog('status', `模型缩放: x=${scale.x.toFixed(3)}, y=${scale.y.toFixed(3)}, z=${scale.z.toFixed(3)}`);
                if (cameraPosition) {
                    this.pushLog('status', `镜头位置: x=${cameraPosition.x.toFixed(3)}, y=${cameraPosition.y.toFixed(3)}, z=${cameraPosition.z.toFixed(3)}`);
                }
            } catch (e) {
                this.saveVrmStatus = 'error';
                this.pushLog('error', `保存视角失败: ${e.message}`);
            }
            setTimeout(() => this.saveVrmStatus = '', 3000);
        },

        async updateBrowserSetting(choice) {
            this.config.browser_choice = choice;
            try {
                const r = await fetch('/api/config/preferences', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ browser_choice: choice })
                });
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                this.pushLog('status', `默认浏览器已切换为: ${choice === 'edge' ? 'Microsoft Edge' : 'Google Chrome'}`);
            } catch (e) {
                this.pushLog('error', `保存浏览器设置失败: ${e.message}`);
            }
        },

        async loadStoreItems() {
            this.storeLoading = true;
            try {
                const r = await fetch('/api/store/list');
                this.storeItems = await r.json();
            } catch (e) {
                this.pushLog('error', `获取商店列表失败: ${e.message}`);
            } finally {
                this.storeLoading = false;
            }
        },

        async downloadStoreItem(item, type) {
            if (this.downloadingItems.includes(item.id)) return;
            this.downloadingItems.push(item.id);
            this.pushLog('status', `开始下载资源: ${item.name}`);
            try {
                const r = await fetch('/api/store/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: item.url, type: type, name: item.name })
                });
                const data = await r.json();
                if (!r.ok) throw new Error(data.detail || '下载请求失败');
                this.pushLog('status', `${item.name} 正在后台下载，等待完成...`);
                const expectedExt = type === 'model' ? '.vrm' : '.vrma';
                const expectedName = item.name + expectedExt;
                const deadline = Date.now() + 120_000;
                const poll = async () => {
                    if (type === 'model') await this.loadModels();
                    else await this.loadAnimations();
                    const found = type === 'model'
                        ? this.vrmModels.some(m => m.name === expectedName)
                        : this.vrmAnimations.some(a => a.name === item.name || a.name === expectedName);
                    if (found || Date.now() > deadline) {
                        this.downloadingItems = this.downloadingItems.filter(id => id !== item.id);
                        this.pushLog('status', found ? `资源 ${item.name} 下载完成` : `⚠ ${item.name} 下载超时，请手动刷新`);
                    } else {
                        setTimeout(poll, 3000);
                    }
                };
                setTimeout(poll, 3000);
            } catch (err) {
                this.pushLog('error', `下载 ${item.name} 失败: ${err.message}`);
                this.downloadingItems = this.downloadingItems.filter(id => id !== item.id);
            }
        },

        get filteredModels() {
            if (this.selectedCategory === 'All') return this.storeItems.models || [];
            return (this.storeItems.models || []).filter(item => item.category === this.selectedCategory);
        },

        isDownloaded(item) {
            if (!this.vrmModels) return false;
            const expectedName = item.name.endsWith('.vrm') ? item.name : item.name + '.vrm';
            return this.vrmModels.some(m => m.name === expectedName);
        },

        isAnimationDownloaded(item) {
            if (!this.vrmAnimations) return false;
            const expectedName = item.name.endsWith('.vrma') ? item.name : item.name + '.vrma';
            return this.vrmAnimations.some(a => a.name === item.name || a.name === expectedName);
        },

        get filteredAnimations() {
            if (this.selectedCategory === 'All') return this.storeItems.animations || [];
            return (this.storeItems.animations || []).filter(item => item.category === this.selectedCategory);
        },

        async newSession() {
            try {
                const r = await fetch('/api/sessions/new', { method: 'POST' });
                if (!r.ok) throw new Error('server error');
                this.messages = [{ id: 'sys-new', role: 'assistant', content: '开始新对话啊！有什么想聊的吗~' }];
                this.activePanel = 'chat';
                await this.loadSessions();
            } catch (e) { console.error('新建对话失败:', e); }
        },

        abortReceiving() {
            if (this.currentController) {
                this.currentController.abort();
                this.currentController = null;
                this.isReceiving = false;
            }
        },

        handleInput(e) {
            const text = this.inputText;
            if (text.startsWith('/')) {
                const search = text.toLowerCase();
                this.filteredCommands = this.availableCommands.filter(c => c.command.toLowerCase().startsWith(search));
                this.showCommandMenu = this.filteredCommands.length > 0;
                this.commandSelectedIndex = 0;
            } else {
                this.showCommandMenu = false;
            }
        },

        navigateCommand(dir, e) {
            if (this.showCommandMenu && this.filteredCommands.length > 0) {
                this.commandSelectedIndex += dir;
                if (this.commandSelectedIndex < 0) this.commandSelectedIndex = this.filteredCommands.length - 1;
                if (this.commandSelectedIndex >= this.filteredCommands.length) this.commandSelectedIndex = 0;
            }
        },

        handleEnter(e) {
            if (this.showCommandMenu && this.filteredCommands.length > 0) {
                this.selectCommand(this.filteredCommands[this.commandSelectedIndex]);
            } else if (e.shiftKey) {
                this.inputText += '\n';
                this.autoResize(e.target);
            } else {
                if (this.isReceiving) {
                    this.abortReceiving();
                } else {
                    this.sendMessage();
                }
            }
        },

        // ── Image paste / drop helpers ────────────────────────────────────────

        handlePaste(e) {
            const items = e.clipboardData && e.clipboardData.items;
            if (!items) return;
            for (const item of items) {
                if (item.type.startsWith('image/')) {
                    e.preventDefault();
                    const file = item.getAsFile();
                    if (file) this._addStagedFile(file);
                    return;
                }
            }
            // Non-image paste: let the browser handle it normally (text into textarea)
        },

        async handleDrop(e) {
            e.preventDefault();
            this.isDragOver = false;

            const dropItems = e.dataTransfer && e.dataTransfer.items;
            if (!dropItems) return;

            for (const item of dropItems) {
                if (item.kind === 'file') {
                    const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
                    if (entry) {
                        await this._processEntry(entry);
                    } else {
                        const file = item.getAsFile();
                        if (file) this._addStagedFile(file);
                    }
                }
            }

            this.$nextTick(() => {
                const ta = document.querySelector('textarea');
                if (ta) ta.focus();
            });
        },

        // 递归处理文件夹条目
        async _processEntry(entry) {
            if (entry.isFile) {
                return new Promise((resolve) => {
                    entry.file((file) => {
                        this._addStagedFile(file);
                        resolve();
                    });
                });
            } else if (entry.isDirectory) {
                const dirReader = entry.createReader();
                return new Promise((resolve) => {
                    dirReader.readEntries(async (entries) => {
                        for (let i = 0; i < entries.length; i++) {
                            await this._processEntry(entries[i]);
                        }
                        resolve(); // 全部读完才 resolve
                    });
                });
            }
        },

        _addStagedFile(file) {
            // Guard: Optional size limits (e.g. 50MB per file)
            if (file.size > 50 * 1024 * 1024) {
                this.pushLog('error', `文件 ${file.name} 超过 50MB 限制。`);
                return;
            }
            // Add file to staging list
            this.stagedFiles.push(file);
        },

        removeStagedFile(index) {
            if (index >= 0 && index < this.stagedFiles.length) {
                this.stagedFiles.splice(index, 1);
            }
        },

        handleFileSelect(e) {
            const files = e.target.files;
            if (files) {
                for (let i = 0; i < files.length; i++) {
                    this._addStagedFile(files[i]);
                }
            }
            e.target.value = ''; // Reset input so same file can be selected again
        },

        // ── Arg / dispatch helpers ─────────────────────────────────────────────

        // Extract the argument portion after a command prefix from the current inputText.
        // e.g. inputText="/recall 南京", cmdPrefix="/recall " → "南京"
        _extractArg(cmdPrefix, rawInput) {
            const src = rawInput || '';
            const prefix = cmdPrefix.trimEnd();
            if (src.toLowerCase().startsWith(prefix.toLowerCase())) {
                return src.slice(prefix.length).trim();
            }
            return src.trim();
        },

        // Set inputText and dispatch to AI on next tick.
        _dispatchToAI(message) {
            this.inputText = message;
            this.$nextTick(() => this.sendMessage());
        },

        // Restore inputText with a placeholder hint and focus the textarea.
        _focusInput(hint) {
            this.inputText = hint;
            this.$nextTick(() => {
                const ta = document.querySelector('textarea');
                if (ta) { ta.select(); ta.focus(); }
            });
        },

        selectCommand(cmd) {
            const rawInput = this.inputText; // capture before clearing
            this.showCommandMenu = false;

            // Define which actions are "immediate" (execute without arguments)
            const immediateActions = ['clear_chat', 'new_session', 'upload_file', 'save_vrm', 'poke_ai', 'clear_sandbox'];

            if (!immediateActions.includes(cmd.action)) {
                // Interactive shortcuts: just populate input and focus
                this.inputText = cmd.command.trim() + ' ';
                this.$nextTick(() => {
                    const ta = document.querySelector('textarea');
                    if (ta) {
                        ta.style.height = 'auto'; // Reset height
                        ta.focus();
                        // Move cursor to end
                        ta.setSelectionRange(this.inputText.length, this.inputText.length);
                    }
                });
                return;
            }

            // Immediate actions: clear input first
            this.inputText = '';
            this.$nextTick(() => {
                const ta = document.querySelector('textarea');
                if (ta) { ta.style.height = 'auto'; ta.focus(); }
            });

            const actions = {
                // ── 会话管理 ──
                clear_chat: () => {
                    this.messages = [{ id: 'sys-0', role: 'assistant', content: '对话已在前端清空。' }];
                    this.pushLog('system', '前端对话历史已清空。');
                },
                new_session: () => this.newSession(),

                // ── 模型管理 ──
                upload_file: () => {
                    // Trigger a hidden file input; result handled by _onUploadFileSelected
                    let input = document.getElementById('_slash-upload-input');
                    if (!input) {
                        input = document.createElement('input');
                        input.type = 'file';
                        input.id = '_slash-upload-input';
                        input.accept = 'image/*,text/plain,text/markdown,.txt,.md,.csv,.log';
                        input.style.display = 'none';
                        document.body.appendChild(input);
                        input.addEventListener('change', (e) => this._onUploadFileSelected(e));
                    }
                    input.value = '';
                    input.click();
                },
                save_vrm: () => this.saveVrmConfig(),

                // ── 系统维护 ──
                poke_ai: () => {
                    fetch('/api/context/poke', { method: 'POST' })
                        .then(r => r.json())
                        .then(() => this.pushLog('status', '⚡ 已强制触发视觉感知。'))
                        .catch(e => this.pushLog('error', '触发失败: ' + e.message));
                },
                clear_sandbox: () => {
                    fetch('/api/sandbox/clear', { method: 'POST' })
                        .then(r => r.json())
                        .then(data => {
                            this.messages.push({ id: 'sys-' + Date.now(), role: 'assistant', content: '✓ ' + data.message });
                            this.scrollToBottom();
                        })
                        .catch(() => { });
                },
            };

            if (actions[cmd.action]) {
                actions[cmd.action]();
            }
        },

        async _onUploadFileSelected(e) {
            this.handleFileSelect(e);
        },

        async sendFiles(files, prompt = '') {
            if (this.isReceiving) return;
            if (!files || files.length === 0) return;

            const fileNames = files.map(f => f.name).join(', ');
            let label = `[附件 ${files.length} 个] ${fileNames}`;
            if (prompt) label += `\n\n${prompt}`;

            this.messages.push({ id: 'u-' + Date.now(), role: 'user', content: label });
            this.scrollToBottom();

            const aiId = 'a-' + Date.now();
            this.messages.push({ id: aiId, role: 'assistant', content: '<span class="text-gray-400 text-xs italic animate-pulse">分析中...</span>', thinkingHtml: '', _thinkingRaw: '', _thinkCollapsed: true, blocks: [] });
            this.scrollToBottom();
            this.isReceiving = true;

            try {
                const formData = new FormData();
                for (let i = 0; i < files.length; i++) {
                    formData.append('files', files[i]);
                }
                if (prompt) formData.append('prompt', prompt);

                this.currentController = new AbortController();
                const response = await fetch('/api/chat/upload', {
                    method: 'POST',
                    body: formData,
                    signal: this.currentController.signal,
                });
                // Reuse the same SSE reader logic as sendMessage
                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();
                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        const dataStr = line.slice(6).trim();
                        if (dataStr === '[DONE]') continue;
                        try {
                            const ev = JSON.parse(dataStr);
                            const idx = this.messages.findIndex(m => m.id === aiId);
                            if (ev.type === 'status') {
                                this.pushLog('status', ev.content || '');
                            } else if (ev.type === 'tool_call') {
                                const paramStr = ev.params ? JSON.stringify(ev.params, null, 2) : '';
                                this.pushLog('tool_call', `${ev.name}(${paramStr})`);
                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    if (!m._streaming) { m._streaming = true; m.content = ''; m.blocks = []; }
                                    if (!m.blocks) m.blocks = [];
                                    m._isThinking = true;
                                    m.blocks.push({ type: 'tool', id: ev.id, name: ev.name, paramsStr: paramStr, status: 'running', _collapsed: false });
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'ask_user_interrupt') {
                                this.pushLog('tool_call', `ask_user: ${ev.question}`);
                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    if (!m._streaming) { m._streaming = true; m.content = ''; m.blocks = []; }
                                    if (!m.blocks) m.blocks = [];
                                    m._isThinking = false;
                                    const options = (ev.options || []).map((opt, i) => ({
                                        id: typeof opt === 'object' ? (opt.id || String(i)) : String(i),
                                        label: typeof opt === 'object' ? (opt.label || opt.text || String(opt)) : String(opt)
                                    }));
                                    m.blocks.push({ type: 'ask_user', question: ev.question || '请选择：', options, answered: false });
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'tool_result') {
                                this.pushLog('tool_result', `${ev.name} → ${ev.result || ''}`);
                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    if (m.blocks) {
                                        const tc = m.blocks.find(t => t.type === 'tool' && t.id === ev.id);
                                        if (tc) { tc.status = 'done'; tc.resultStr = ev.result || ''; tc._collapsed = true; }
                                        m._isThinking = m.blocks.some(b => b.type === 'tool' && b.status === 'running');
                                    }
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'message_chunk') {
                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    if (!m._streaming) { m._streaming = true; m.content = ''; m.blocks = []; }
                                    const lastBlock = m.blocks && m.blocks[m.blocks.length - 1];
                                    if (lastBlock && lastBlock.type === 'text') {
                                        lastBlock.content += ev.content;
                                        lastBlock.html = this.mdRender(lastBlock.content);
                                    } else {
                                        if (!m.blocks) m.blocks = [];
                                        m.blocks.push({ type: 'text', content: ev.content, html: this.mdRender(ev.content) });
                                    }
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'message') {
                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    m._isThinking = false;
                                    delete m._streaming;
                                    if (!m.blocks) m.blocks = [];
                                    const hasText = m.blocks.some(b => b.type === 'text' && b.content?.trim());
                                    const hasTool = m.blocks.some(b => b.type === 'tool');
                                    if (!hasText && hasTool) m.blocks.push({ type: 'status_done' });
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'usage') {
                                if (ev.content && typeof ev.content === 'object') {
                                    this.lastBackendTokens = ev.content.total_tokens || this.lastBackendTokens;
                                    this.lastMaxTokens = ev.content.max_tokens || this.lastMaxTokens;
                                }
                            } else if (ev.type === 'error') {
                                this.pushLog('error', ev.content || '');
                                if (idx !== -1) this.messages[idx].content = `<span class="text-red-400 text-xs">⚠ ${ev.content}</span>`;
                            }
                        } catch { /* ignore parse errors */ }
                    }
                }
            } catch (err) {
                if (err.name !== 'AbortError') {
                    const idx = this.messages.findIndex(m => m.id === aiId);
                    if (idx !== -1) this.messages[idx].content = '<span class="text-red-400 text-xs">⚠ 上传失败，请稍后再试。</span>';
                }
            } finally {
                this.isReceiving = false;
                this.currentController = null;
                this.scrollToBottom();
            }
        },

        async sendMessage(isProactive = false) {
            // Check if there are staged files to send
            if (this.stagedFiles.length > 0 && !isProactive) {
                const filesToSend = [...this.stagedFiles];
                const prompt = this.inputText.trim();

                // Clear inputs immediately
                this.stagedFiles = [];
                this.inputText = '';

                await this.sendFiles(filesToSend, prompt);
                return;
            }

            const text = this.inputText.trim();
            if (!text || this.isReceiving) return;
            if (!isProactive) {
                this.messages.push({ id: 'u-' + Date.now(), role: 'user', content: text });
            }
            this.inputText = '';
            this.$nextTick(() => {
                const ta = document.querySelector('textarea');
                if (ta) { ta.style.height = 'auto'; }
            });
            this.scrollToBottom();
            const aiId = 'a-' + Date.now();
            this.messages.push({ id: aiId, role: 'assistant', content: '<span class="text-gray-400 text-xs italic animate-pulse">思考中...</span>', thinkingHtml: '', _thinkingRaw: '', _thinkCollapsed: true, blocks: [] });
            this.scrollToBottom();
            this.isReceiving = true;
            try {
                this.currentController = new AbortController();
                const response = await fetch('/api/chat/stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: text,
                        ...(this.chatModel ? { model: this.chatModel } : {}),
                        ...(this.chatAgent ? { agent_id: this.chatAgent.id } : {}),
                    }),
                    signal: this.currentController.signal
                });
                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let buffer = '';
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop();
                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        const dataStr = line.slice(6).trim();
                        if (dataStr === '[DONE]') continue;
                        try {
                            const ev = JSON.parse(dataStr);
                            const idx = this.messages.findIndex(m => m.id === aiId);
                            if (ev.type === 'status') {
                                this.pushLog('status', ev.content || '');
                                if (idx !== -1) {
                                    const cur = this.messages[idx].content;
                                    if (cur.includes('animate-pulse') || cur.includes('thinking')) {
                                        this.messages[idx].content = `<span class="text-gray-500 text-xs italic">${ev.content}</span>`;
                                    }
                                }
                            } else if (ev.type === 'tool_call') {
                                const paramStr = ev.params ? JSON.stringify(ev.params, null, 2) : '';
                                this.pushLog('tool_call', `${ev.name}(${paramStr})`);
                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    if (!m._streaming) { m._streaming = true; m._rawContent = ''; m.content = ''; }
                                    if (!m.blocks) m.blocks = [];
                                    m._isThinking = true;
                                    m.blocks.push({ type: 'tool', id: ev.id, name: ev.name, paramsStr: paramStr, status: 'running', _collapsed: false });
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'ask_user_interrupt') {
                                // 后端专用事件：ask_user 工具触发，渲染交互式选项块
                                this.pushLog('tool_call', `ask_user: ${ev.question}`);
                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    if (!m._streaming) { m._streaming = true; m._rawContent = ''; m.content = ''; }
                                    if (!m.blocks) m.blocks = [];
                                    m._isThinking = false;
                                    const options = (ev.options || []).map((opt, i) => ({
                                        id: typeof opt === 'object' ? (opt.id || String(i)) : String(i),
                                        label: typeof opt === 'object' ? (opt.label || opt.text || String(opt)) : String(opt)
                                    }));
                                    m.blocks.push({ type: 'ask_user', question: ev.question || '请选择：', options, answered: false });
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'tool_result') {
                                this.pushLog('tool_result', `${ev.name} → ${ev.result || ''}`);
                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    if (m.blocks) {
                                        const tc = m.blocks.find(t => t.type === 'tool' && t.id === ev.id);
                                        if (tc) { tc.status = 'done'; tc.resultStr = ev.result || ''; tc._collapsed = true; }
                                        // Still thinking if any tool is still running
                                        m._isThinking = m.blocks.some(b => b.type === 'tool' && b.status === 'running');
                                    }
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'thinking_chunk') {
                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    if (!m._streaming) { m._streaming = true; m._rawContent = ''; m.content = ''; }
                                    m._thinkingRaw = (m._thinkingRaw || '') + (ev.content || '');
                                    m.thinkingHtml = this.mdRender(m._thinkingRaw);
                                    m._thinkCollapsed = false;
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'message_chunk') {
                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    if (!m._streaming) { m._streaming = true; m._rawContent = ''; m.content = ''; }
                                    // Collapse thinking block only after a short delay so users can see it
                                    if (m._thinkCollapsed === false && !m._thinkCollapseScheduled) {
                                        m._thinkCollapseScheduled = true;
                                        setTimeout(() => {
                                            m._thinkCollapsed = true;
                                            m._thinkCollapseScheduled = false;
                                        }, 1200);
                                    }
                                    if (ev.content) {
                                        if (!m.blocks) m.blocks = [];
                                        const lastBlock = m.blocks[m.blocks.length - 1];
                                        if (lastBlock && lastBlock.type === 'text') {
                                            lastBlock.content += ev.content;
                                            lastBlock.html = this.mdRender(lastBlock.content);
                                        } else {
                                            m.blocks.push({ type: 'text', content: ev.content, html: this.mdRender(ev.content) });
                                        }
                                    }
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'message') {
                                let logContent = (ev.content || '').trim();
                                if (!logContent && idx !== -1) {
                                    const m = this.messages[idx];
                                    if (m.blocks) {
                                        logContent = m.blocks.filter(b => b.type === 'text').map(b => b.content).join('').trim();
                                    }
                                }
                                if (!logContent) logContent = '响应已完成';
                                this.pushLog('message', logContent.replace(/\s+/g, ' ').slice(0, 80) + (logContent.length > 80 ? '...' : ''));

                                if (idx !== -1) {
                                    const m = this.messages[idx];
                                    m._isThinking = false;
                                    delete m._streaming;
                                    delete m._rawContent;
                                    // If agent only called tools without any text output, show a done status block
                                    if (!m.blocks) m.blocks = [];
                                    const hasText = m.blocks.some(b => b.type === 'text' && b.content && b.content.trim());
                                    const hasTool = m.blocks.some(b => b.type === 'tool');
                                    if (!hasText && hasTool) {
                                        m.blocks.push({ type: 'status_done' });
                                    } else if (!hasText && !hasTool) {
                                        // pure empty response fallback
                                        m.blocks.push({ type: 'status_done' });
                                    }
                                    this.scrollToBottom();
                                }
                            } else if (ev.type === 'system') {
                                this.pushLog('system', ev.text || '');
                            } else if (ev.type === 'usage') {
                                if (ev.content && typeof ev.content === 'object') {
                                    this.lastBackendTokens = ev.content.total_tokens || this.lastBackendTokens;
                                    this.lastMaxTokens = ev.content.max_tokens || this.lastMaxTokens;
                                }
                            } else if (ev.type === 'error') {
                                this.pushLog('error', ev.content || '');
                                if (idx !== -1) {
                                    this.messages[idx].content = `<span class="text-red-400 text-xs">❌ ${ev.content}</span>`;
                                }
                            }
                        } catch { /* ignore parse errors */ }
                    }
                }
            } catch (err) {
                if (err.name !== 'AbortError') {
                    const idx = this.messages.findIndex(m => m.id === aiId);
                    if (idx !== -1) this.messages[idx].content = '<span class="text-red-400 text-xs">❌ 网络异常，请稍后再试。</span>';
                }
            } finally {
                this.isReceiving = false;
                this.currentController = null;
                this.scrollToBottom();
                this.loadTokenStats(this.tokenPeriod);
            }
        },

        autoResize(el) {
            el.style.height = 'auto';
            el.style.height = Math.min(el.scrollHeight, 120) + 'px';
        },

        pushLog(type, text) {
            const ts = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            this.debugLogs.push({ type, text, ts });
            if (this.debugLogs.length > 500) this.debugLogs.shift();
            if (this.activePanel === 'debug') {
                this.$nextTick(() => {
                    const d = document.getElementById('debug-container');
                    if (d) d.scrollTop = d.scrollHeight;
                });
            }
        },

        mdRender(text) {
            if (!text || typeof text !== 'string') return text || '';
            if (text.startsWith('<span')) return text;
            try {
                // 优化：处理 Markdown 中的本地路径图片，转换成前端可访问的静态路由
                let processedText = text;
                if (processedText.includes('![')) {
                    processedText = processedText.replace(/!\[(.*?)\]\(([^)]+)\)/g, (match, alt, path) => {
                        let cleanPath = path.trim().replace(/\\/g, '/');
                        // 将 data/screenshots/ 映射到 /screenshots/ (向后兼容旧格式)
                        if (cleanPath.startsWith('data/screenshots/')) {
                            cleanPath = cleanPath.replace('data/screenshots/', '/screenshots/');
                        }
                        // /screenshots/ 开头的路径直接使用，是服务器已挂载的静态路由
                        return `![${alt}](${cleanPath})`;
                    });
                }

                return typeof marked !== 'undefined'
                    ? marked.parse(processedText, { breaks: true, gfm: true })
                    : processedText;
            } catch { return text; }
        },

        scrollToBottom() {
            this.$nextTick(() => {
                const c = document.getElementById('chat-container');
                if (c) c.scrollTop = c.scrollHeight;
            });
        },

        // 处理 ask_user 选项点击：标记已回答，并将选择作为用户消息发送给 AI
        async submitAskUserChoice(msg, block, opt) {
            const targetMsg = this.messages.find(m => m.id === msg.id) || msg;
            const targetBlock = targetMsg && Array.isArray(targetMsg.blocks)
                ? targetMsg.blocks.find(b => (block.id && b.id === block.id) || b === block)
                : block;

            if (!targetBlock || targetBlock.answered) return;
            targetBlock.answered = true;
            targetBlock.resultStr = opt.label;
            if (typeof this.notifyChatStateChanged === 'function') {
                this.notifyChatStateChanged();
            }

            // 将用户选择作为新消息发送
            this.inputText = opt.label;
            await this.sendMessage();
        },

        // ═══════════════ Scheduler Management ═══════════════
        notifySchedulerChanged() {
            window.dispatchEvent(new CustomEvent('openguiclaw:scheduler-updated', {
                detail: {
                    schedulerTasks: this.schedulerTasks,
                    schedulerExecutions: this.schedulerExecutions,
                    schedulerViewTab: this.schedulerViewTab
                }
            }));
        },

        async loadSchedulerTasks() {
            try {
                const res = await fetch('/api/scheduler/tasks');
                if (res.ok) {
                    const data = await res.json();
                    this.schedulerTasks = data.tasks || [];
                    this.notifySchedulerChanged();
                }
            } catch (e) {
                console.error('Failed to load scheduler tasks', e);
            }
        },

        async loadSchedulerExecutions() {
            try {
                const res = await fetch('/api/scheduler/executions?limit=100');
                if (res.ok) {
                    const data = await res.json();
                    this.schedulerExecutions = data.executions || [];
                    this.notifySchedulerChanged();
                }
            } catch (e) {
                console.error('Failed to load scheduler executions', e);
            }
        },

        async refreshSchedulerData() {
            await Promise.all([
                this.loadSchedulerTasks(),
                this.loadSchedulerExecutions(),
            ]);
        },

        getSchedulerExecutionStatusLabel(status) {
            return {
                running: '执行中',
                success: '成功',
                failed: '失败',
            }[status] || status || '未知';
        },

        getSchedulerExecutionStatusClass(status) {
            return {
                running: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
                success: 'bg-[var(--stem-green-500)]/10 text-[var(--stem-green-500)] border-[var(--stem-green-500)]/20',
                failed: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
            }[status] || 'bg-[var(--noble-black-800)] text-[var(--noble-black-400)] border-white/5';
        },

        getSchedulerExecutionTargetSummary(execution) {
            if (!execution) return '';
            const targets = Array.isArray(execution.delivery_targets) ? execution.delivery_targets : [];
            if (targets.length > 0) {
                return targets.map((target) => {
                    if (target.kind === 'desktop_session' && target.session_id) {
                        return `桌面对话 · ${target.session_id}`;
                    }
                    if (target.kind === 'im_session') {
                        const channel = target.channel || ((target.session_id || '').split('_')[0] || 'im');
                        const chatId = target.chat_id || ((target.session_id || '').split('_').slice(1).join('_'));
                        return `IM 会话 · ${channel}/${chatId}`;
                    }
                    const workspace = (this.workspaces || []).find(item => item && item.id === target.workspace_id);
                    return `工作区收件箱 · ${(workspace && workspace.name) || '默认工作区'}`;
                }).join(' / ');
            }
            if (execution.target_kind === 'desktop_session' && execution.target_session_id) {
                return `桌面对话 · ${execution.target_session_id}`;
            }
            if (execution.target_kind === 'im_session') {
                const channel = execution.target_channel || 'im';
                const chatId = execution.target_chat_id || execution.target_session_id || 'unknown';
                return `IM 会话 · ${channel}/${chatId}`;
            }
            const workspace = (this.workspaces || []).find(item => item && item.id === execution.target_workspace_id);
            return `工作区收件箱 · ${(workspace && workspace.name) || '默认工作区'}`;
        },

        getSchedulerDefaultWorkspaceId() {
            if (this.activeWorkspaceId) return this.activeWorkspaceId;
            if (Array.isArray(this.workspaces) && this.workspaces.length > 0) {
                const defaultWorkspace = this.workspaces.find(workspace => workspace && workspace.is_default);
                if (defaultWorkspace && defaultWorkspace.id) return defaultWorkspace.id;
                if (this.workspaces[0] && this.workspaces[0].id) return this.workspaces[0].id;
            }
            return '';
        },

        isImSessionId(sessionId) {
            return ['dingtalk_', 'feishu_', 'telegram_'].some(prefix => (sessionId || '').startsWith(prefix));
        },

        getSchedulerCurrentDesktopSessionId() {
            if (this.currentThreadId && !this.isImSessionId(this.currentThreadId)) {
                return this.currentThreadId;
            }
            return '';
        },

        hasSchedulerDesktopTargetAvailable() {
            return !!(
                this.getSchedulerCurrentDesktopSessionId()
                || (this.schedulerFormData && this.schedulerFormData.target_desktop_session_id)
            );
        },

        getSchedulerDesktopSessionLabel(sessionId) {
            const resolvedSessionId = sessionId || this.getSchedulerCurrentDesktopSessionId();
            if (!resolvedSessionId) return '当前没有可绑定的桌面对话';
            const currentSessionId = this.getSchedulerCurrentDesktopSessionId();
            const workspaceName = (this.activeWorkspace && this.activeWorkspace.name) || '当前工作区';
            if (currentSessionId && resolvedSessionId === currentSessionId) {
                return `${workspaceName} / ${resolvedSessionId}`;
            }
            return `已绑定桌面对话 / ${resolvedSessionId}`;
        },

        findImSession(sessionId) {
            return (this.imSessions || []).find(session => session && session.id === sessionId) || null;
        },

        getSchedulerImSessionLabel(sessionId) {
            const session = this.findImSession(sessionId);
            if (!session) return sessionId || '未选择 IM 会话';
            const preview = session.last_message ? ` · ${session.last_message}` : '';
            return `${session.channel}/${session.chat_id}${preview}`;
        },

        getSchedulerTargetSummary(task) {
            if (!task) return '';
            const targets = Array.isArray(task.delivery_targets) ? task.delivery_targets : [];
            if (targets.length > 0) {
                return targets.map((target) => {
                    if (target.kind === 'desktop_session' && target.session_id) {
                        return `桌面对话 · ${target.session_id}`;
                    }
                    if (target.kind === 'im_session') {
                        const channel = target.channel || ((target.session_id || '').split('_')[0] || 'im');
                        const chatId = target.chat_id || ((target.session_id || '').split('_').slice(1).join('_'));
                        return `IM 会话 · ${channel}/${chatId}`;
                    }
                    const workspace = (this.workspaces || []).find(item => item && item.id === target.workspace_id);
                    return `工作区收件箱 · ${(workspace && workspace.name) || '默认工作区'}`;
                }).join(' / ');
            }
            if (task.target_kind === 'desktop_session' && task.target_session_id) {
                return `当前桌面对话 · ${task.target_session_id}`;
            }
            if (task.target_kind === 'im_session' && (task.target_channel || task.target_session_id)) {
                const channel = task.target_channel || ((task.target_session_id || '').split('_')[0] || 'im');
                const chatId = task.target_chat_id || ((task.target_session_id || '').split('_').slice(1).join('_'));
                return `IM 会话 · ${channel}/${chatId}`;
            }
            const workspace = (this.workspaces || []).find(item => item && item.id === task.target_workspace_id);
            return `工作区收件箱 · ${(workspace && workspace.name) || '默认工作区'}`;
        },

        normalizeSchedulerTargetForm() {
            const formData = this.schedulerFormData;
            const deliveryTargets = [];

            if (formData.delivery_workspace_enabled) {
                formData.target_workspace_id = formData.target_workspace_id || this.getSchedulerDefaultWorkspaceId();
                deliveryTargets.push({
                    kind: 'workspace_inbox',
                    workspace_id: formData.target_workspace_id || null,
                });
            }

            if (formData.delivery_desktop_enabled) {
                const currentDesktopSessionId = this.getSchedulerCurrentDesktopSessionId();
                formData.target_desktop_session_id = formData.target_desktop_session_id || currentDesktopSessionId || '';
                if (!formData.target_desktop_session_id) {
                    this.pushLog('error', '当前没有可绑定的桌面对话');
                    return false;
                }
                deliveryTargets.push({
                    kind: 'desktop_session',
                    session_id: formData.target_desktop_session_id,
                });
            }

            if (formData.delivery_im_enabled) {
                const session = this.findImSession(formData.target_im_session_id);
                if (!session) {
                    this.pushLog('error', '请选择一个 IM 会话作为投递目标');
                    return false;
                }
                formData.target_im_session_id = session.id;
                formData.target_channel = session.channel || '';
                formData.target_chat_id = session.chat_id || '';
                deliveryTargets.push({
                    kind: 'im_session',
                    session_id: formData.target_im_session_id,
                    channel: formData.target_channel,
                    chat_id: formData.target_chat_id,
                });
            }

            if (deliveryTargets.length === 0) {
                this.pushLog('error', '请至少选择一个投递目标');
                return false;
            }

            formData.delivery_targets = deliveryTargets;
            const primary = deliveryTargets[0];
            formData.target_kind = primary.kind;
            formData.target_workspace_id = primary.workspace_id || formData.target_workspace_id || '';
            formData.target_session_id = primary.session_id || formData.target_session_id || '';
            formData.target_desktop_session_id = formData.target_desktop_session_id || '';
            formData.target_im_session_id = formData.target_im_session_id || '';
            formData.target_channel = primary.channel || '';
            formData.target_chat_id = primary.chat_id || '';
            return true;
        },

        async openSchedulerForm() {
            await this.fetchIMData();
            this.schedulerFormData = {
                id: null,
                name: '',
                description: '',
                delivery_workspace_enabled: true,
                delivery_desktop_enabled: false,
                delivery_im_enabled: false,
                delivery_targets: [],
                target_kind: 'workspace_inbox',
                target_workspace_id: this.getSchedulerDefaultWorkspaceId(),
                target_session_id: '',
                target_desktop_session_id: this.getSchedulerCurrentDesktopSessionId() || '',
                target_im_session_id: '',
                target_channel: '',
                target_chat_id: '',
                task_type: 'task',
                prompt: '',
                reminder_message: '',
                trigger_type: 'once',
                enabled: true,
                trigger_config_onceTime: '',
                trigger_config_intervalMinutes: 0,
                trigger_config_intervalHours: 0,
                trigger_config_cron: '0 9 * * *',
                trigger_preset_time: '09:00',
                trigger_preset_weekday: '1',
                trigger_preset_day: '1'
            };

            // Generate current time + 5 mins for onceTime default
            const now = new Date();
            now.setMinutes(now.getMinutes() + 5);
            // Format to YYYY-MM-DDThh:mm string
            const tzoffset = now.getTimezoneOffset() * 60000;
            const localISOTime = (new Date(now - tzoffset)).toISOString().slice(0, 16);
            this.schedulerFormData.trigger_config_onceTime = localISOTime;

            this.showSchedulerForm = true;
        },

        closeSchedulerForm() {
            this.showSchedulerForm = false;
        },

        async editSchedulerTask(task) {
            await this.fetchIMData();
            // copy task data to form
            this.schedulerFormData = {
                id: task.id,
                name: task.name,
                description: task.description || '',
                delivery_workspace_enabled: false,
                delivery_desktop_enabled: false,
                delivery_im_enabled: false,
                delivery_targets: Array.isArray(task.delivery_targets) ? task.delivery_targets : [],
                target_kind: task.target_kind || (task.target_session_id ? (this.isImSessionId(task.target_session_id) ? 'im_session' : 'desktop_session') : 'workspace_inbox'),
                target_workspace_id: task.target_workspace_id || this.getSchedulerDefaultWorkspaceId(),
                target_session_id: task.target_session_id || '',
                target_desktop_session_id: '',
                target_im_session_id: '',
                target_channel: task.target_channel || '',
                target_chat_id: task.target_chat_id || '',
                task_type: task.task_type || 'task',
                prompt: task.prompt || '',
                reminder_message: task.reminder_message || '',
                trigger_type: task.trigger_type,
                enabled: task.enabled,
                trigger_config_onceTime: '',
                trigger_config_intervalMinutes: 0,
                trigger_config_intervalHours: 0,
                trigger_config_cron: '',
                trigger_preset_time: '09:00',
                trigger_preset_weekday: '1',
                trigger_preset_day: '1'
            };

            const deliveryTargets = Array.isArray(task.delivery_targets) && task.delivery_targets.length > 0
                ? task.delivery_targets
                : [{
                    kind: this.schedulerFormData.target_kind,
                    workspace_id: task.target_workspace_id || null,
                    session_id: task.target_session_id || null,
                    channel: task.target_channel || null,
                    chat_id: task.target_chat_id || null,
                }];
            this.schedulerFormData.delivery_workspace_enabled = deliveryTargets.some(target => target.kind === 'workspace_inbox');
            this.schedulerFormData.delivery_desktop_enabled = deliveryTargets.some(target => target.kind === 'desktop_session');
            this.schedulerFormData.delivery_im_enabled = deliveryTargets.some(target => target.kind === 'im_session');
            const desktopTarget = deliveryTargets.find(target => target.kind === 'desktop_session');
            if (desktopTarget && desktopTarget.session_id) {
                this.schedulerFormData.target_desktop_session_id = desktopTarget.session_id;
            } else {
                this.schedulerFormData.target_desktop_session_id = this.getSchedulerCurrentDesktopSessionId() || '';
            }
            const imTarget = deliveryTargets.find(target => target.kind === 'im_session');
            if (imTarget && imTarget.session_id) {
                this.schedulerFormData.target_im_session_id = imTarget.session_id;
                this.schedulerFormData.target_channel = imTarget.channel || '';
                this.schedulerFormData.target_chat_id = imTarget.chat_id || '';
            } else {
                this.schedulerFormData.target_im_session_id = '';
            }

            if (task.trigger_type === 'once') {
                if (task.trigger_config && (task.trigger_config.run_at || task.trigger_config.run_date)) {
                    try {
                        const d = new Date(task.trigger_config.run_at || task.trigger_config.run_date);
                        // Convert UTC string to local ISOTime string
                        const tzoffset = d.getTimezoneOffset() * 60000;
                        this.schedulerFormData.trigger_config_onceTime = (new Date(d.getTime() - tzoffset)).toISOString().slice(0, 16);
                    } catch (e) { }
                }
            } else if (task.trigger_type === 'interval') {
                if (task.trigger_config) {
                    const seconds = task.trigger_config.interval_seconds || task.trigger_config.seconds || 0;
                    this.schedulerFormData.trigger_config_intervalHours = Math.floor(seconds / 3600);
                    this.schedulerFormData.trigger_config_intervalMinutes = Math.floor((seconds % 3600) / 60);
                }
            } else if (task.trigger_type === 'cron') {
                const cronExp = task.trigger_config ? (task.trigger_config.cron || task.trigger_config.expression) : '';
                this.schedulerFormData.trigger_config_cron = cronExp;

                // Try to detect presets from Cron
                const parts = cronExp.split(/\s+/);
                if (parts.length === 5) {
                    const [m, h, d, mon, dow] = parts;
                    const timeStr = `${h.padStart(2, '0')}:${m.padStart(2, '0')}`;

                    if (d === '*' && mon === '*' && dow === '*') {
                        this.schedulerFormData.trigger_type = 'daily';
                        this.schedulerFormData.trigger_preset_time = timeStr;
                    } else if (d === '*' && mon === '*' && dow !== '*') {
                        this.schedulerFormData.trigger_type = 'weekly';
                        this.schedulerFormData.trigger_preset_time = timeStr;
                        this.schedulerFormData.trigger_preset_weekday = dow;
                    } else if (d !== '*' && mon === '*' && dow === '*') {
                        this.schedulerFormData.trigger_type = 'monthly';
                        this.schedulerFormData.trigger_preset_time = timeStr;
                        this.schedulerFormData.trigger_preset_day = d;
                    }
                }
            }

            this.showSchedulerForm = true;
        },

        async saveSchedulerTask() {
            const formData = this.schedulerFormData;

            // Validation
            if (!formData.name.trim()) {
                this.pushLog('error', '任务名称不能为空');
                return;
            }

            if (formData.task_type === 'task' && !formData.prompt.trim()) {
                this.pushLog('error', '给助手的 Prompt 指令不能为空');
                return;
            }
            if (formData.task_type === 'reminder' && !formData.reminder_message.trim()) {
                this.pushLog('error', '提醒文本内容不能为空');
                return;
            }
            if (!this.normalizeSchedulerTargetForm()) return;

            let triggerConfig = {};
            let finalTriggerType = formData.trigger_type;

            if (formData.trigger_type === 'once') {
                if (!formData.trigger_config_onceTime) {
                    this.pushLog('error', '执行时间不能为空');
                    return;
                }
                const d = new Date(formData.trigger_config_onceTime);
                triggerConfig = { run_at: d.toISOString() };
            } else if (formData.trigger_type === 'interval') {
                const totalSeconds = (formData.trigger_config_intervalHours * 3600) + (formData.trigger_config_intervalMinutes * 60);
                if (totalSeconds <= 0) {
                    this.pushLog('error', '时间间隔必须大于 0');
                    return;
                }
                triggerConfig = { interval_seconds: totalSeconds };
            } else if (['daily', 'weekly', 'monthly', 'cron'].includes(formData.trigger_type)) {
                finalTriggerType = 'cron';
                let cronStr = '';

                if (formData.trigger_type === 'cron') {
                    if (!formData.trigger_config_cron.trim()) {
                        this.pushLog('error', 'Cron 规则不能为空');
                        return;
                    }
                    cronStr = formData.trigger_config_cron.trim();
                } else {
                    // Presets
                    const [h, m] = formData.trigger_preset_time.split(':').map(x => parseInt(x).toString());
                    if (formData.trigger_type === 'daily') {
                        cronStr = `${m} ${h} * * *`;
                    } else if (formData.trigger_type === 'weekly') {
                        cronStr = `${m} ${h} * * ${formData.trigger_preset_weekday}`;
                    } else if (formData.trigger_type === 'monthly') {
                        cronStr = `${m} ${h} ${formData.trigger_preset_day} * *`;
                    }
                }
                triggerConfig = { cron: cronStr };
            }

            const payload = {
                name: formData.name,
                description: formData.description,
                delivery_targets: formData.delivery_targets || [],
                target_kind: formData.target_kind,
                target_workspace_id: formData.target_workspace_id || null,
                target_session_id: formData.target_session_id || null,
                target_channel: formData.target_channel || null,
                target_chat_id: formData.target_chat_id || null,
                trigger_type: finalTriggerType,
                trigger_config: triggerConfig,
                task_type: formData.task_type,
                prompt: formData.task_type === 'task' ? formData.prompt : '',
                reminder_message: formData.task_type === 'reminder' ? formData.reminder_message : '',
                enabled: formData.enabled
            };

            try {
                let url = '/api/scheduler/tasks';
                let method = 'POST';
                if (formData.id) {
                    url += `/${formData.id}`;
                    method = 'PUT';
                }

                const res = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (res.ok) {
                    this.pushLog('system', formData.id ? '成功更新计划任务' : '成功创建计划任务');
                    this.closeSchedulerForm();
                    await this.refreshSchedulerData();
                } else {
                    const err = await res.json();
                    this.pushLog('error', `保存计划任务失败: ${err.detail}`);
                }
            } catch (e) {
                console.error(e);
                this.pushLog('error', '网络错误，请查看控制台');
            }
        },

        async deleteSchedulerTask(taskId) {
            if (!confirm("确定要删除此计划任务吗？")) return;
            try {
                const res = await fetch(`/api/scheduler/tasks/${taskId}`, { method: 'DELETE' });
                if (res.ok) {
                    this.pushLog('system', '计划任务已删除');
                    await this.refreshSchedulerData();
                } else {
                    const err = await res.json();
                    this.pushLog('error', `删除失败: ${err.detail}`);
                }
            } catch (e) { console.error(e); }
        },

        async toggleSchedulerTask(taskId, enabled) {
            try {
                const res = await fetch(`/api/scheduler/tasks/${taskId}/toggle`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: enabled })
                });
                if (res.ok) {
                    this.pushLog('system', enabled ? '已启用任务' : '已停用任务');
                    await this.refreshSchedulerData();
                } else {
                    this.pushLog('error', '切换状态失败');
                }
            } catch (e) { console.error(e); }
        },

        async triggerSchedulerTask(taskId) {
            try {
                const res = await fetch(`/api/scheduler/tasks/${taskId}/trigger`, { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    const executionId = data.execution && data.execution.id ? ` (${data.execution.id})` : '';
                    this.pushLog('system', `任务执行指令已发送${executionId}`);
                    this.schedulerViewTab = 'executions';
                    await this.refreshSchedulerData();
                } else {
                    this.pushLog('error', '触发任务失败');
                }
            } catch (e) { console.error(e); }
        },

        // ═══════════════ Skills Management ═══════════════
        notifySkillsChanged() {
            window.dispatchEvent(new CustomEvent('openguiclaw:skills-updated', {
                detail: { skills: this.skills }
            }));
        },

        async loadSkills() {
            try {
                console.log('[Skills] Loading skills...');
                const response = await fetch('/api/skills/list');
                console.log('[Skills] Response status:', response.status);
                if (response.ok) {
                    const data = await response.json();
                    console.log('[Skills] Loaded skills:', data.skills);
                    this.skills = (data.skills || []).map(skill => {
                        return {
                            ...skill,
                            _showConfig: false,
                            _saving: false,
                            config_values: skill.config_values || {}
                        };
                    });
                    console.log('[Skills] Skills array length:', this.skills.length);
                    this.notifySkillsChanged();
                } else {
                    console.error('[Skills] Failed to load skills:', response.statusText);
                }
            } catch (error) {
                console.error('[Skills] Error loading skills:', error);
            }
        },

        async toggleSkill(name, enabled) {
            try {
                // find the skill to get its tools list and registry_category
                const skill = this.skills.find(s => s.name === name);
                if (skill?.locked) {
                    this.pushLog('status', `系统能力 ${name} 不可关闭`);
                    return;
                }
                const payload = {
                    name: skill?.registry_category || name,
                    enabled,
                    tools: skill?.tools || []
                };
                const response = await fetch('/api/skills/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    const skillObj = this.skills.find(s => s.name === name);
                    if (skillObj) {
                        skillObj.enabled = enabled;
                    }
                    this.notifySkillsChanged();
                    this.pushLog('success', `技能 ${name} 已${enabled ? '启用' : '禁用'}`);
                } else {
                    const data = await response.json().catch(() => ({}));
                    this.pushLog('error', data.detail || '切换技能状态失败');
                    await this.loadSkills();
                }
            } catch (error) {
                console.error('Failed to toggle skill:', error);
                this.pushLog('error', `切换技能状态失败: ${error.message}`);
            }
        },

        async saveSkillConfig(skill) {
            skill._saving = true;
            try {
                const response = await fetch('/api/skills/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: skill.name, config: skill.config_values })
                });
                const data = await response.json();
                if (response.ok) {
                    this.pushLog('success', `技能配置 ${skill.name} 保存成功`);
                    skill.config_values = data.config_values || skill.config_values;
                    this.notifySkillsChanged();
                } else {
                    this.pushLog('error', `技能配置保存失败: ${data.detail || '未知错误'}`);
                }
            } catch (error) {
                console.error('Failed to save skill config:', error);
                this.pushLog('error', `配置保存异常: ${error.message}`);
            } finally {
                skill._saving = false;
            }
        },

        async reloadSkills() {
            try {
                this.pushLog('status', '正在重新加载技能...');
                const response = await fetch('/api/skills/reload', {
                    method: 'POST'
                });

                if (response.ok) {
                    await this.loadSkills();
                    this.pushLog('success', '技能已重新加载');
                } else {
                    this.pushLog('error', '重新加载技能失败');
                }
            } catch (error) {
                console.error('Failed to reload skills:', error);
                this.pushLog('error', `重新加载技能失败: ${error.message}`);
            }
        },

        // ═══════════════ Token Stats ═══════════════
        async loadTokenStats(period) {
            try {
                const p = period || '1d';
                const res = await fetch(`/api/token-stats?period=${p}`);
                if (res.ok) this.tokenStats = await res.json();
            } catch (e) { console.error('Failed to load token stats:', e); }
        },

        async resetTokenStats() {
            if (!confirm('确定要重置 Token 统计数据吗？')) return;
            try {
                await fetch('/api/token-stats/reset', { method: 'POST' });
                await this.loadTokenStats(this.tokenPeriod);
            } catch (e) { console.error('Failed to reset token stats:', e); }
        },

        async searchSkillMarketplace(q) {
            this.skillMarketLoading = true;
            this.skillInstallMsg = null;
            try {
                const res = await fetch('/api/skills/marketplace?q=' + encodeURIComponent(q || 'agent'));
                const data = await res.json();
                if (data.error) {
                    this.skillInstallMsg = { type: 'error', text: '同步失败: ' + data.error };
                    this.skillMarketplace = [];
                } else {
                    this.skillMarketplace = data.skills || [];
                }
            } catch (e) {
                this.skillInstallMsg = { type: 'error', text: '网络请求异常: ' + e.message };
                this.skillMarketplace = [];
            } finally {
                this.skillMarketLoading = false;
            }
        },

        async installSkillFromUrl(url, skillId = null) {
            if (!url.trim()) return;
            this.skillInstallMsg = null;
            if (skillId) this.skillInstallingId = skillId;
            try {
                const res = await fetch('/api/skills/install', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });
                const data = await res.json();
                if (!res.ok || data.error) throw new Error(data.error || data.detail || '安装失败');
                this.skillInstallMsg = { type: 'success', text: data.applied_immediately ? '✓ 技能安装成功，已立即生效' : '✓ 技能安装成功' };
                await this.loadSkills();
            } catch (e) {
                this.skillInstallMsg = { type: 'error', text: e.message };
            } finally {
                this.skillInstallingId = null;
            }
        },

        async uninstallSkill(name) {
            if (!confirm('确认卸载技能「' + name + '」？这将从注册表中移除该技能。')) return;
            this.skillInstallMsg = null;
            try {
                const res = await fetch('/api/skills/uninstall', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name })
                });
                const data = await res.json();
                if (!res.ok || data.error) throw new Error(data.error || data.detail || '卸载失败');
                this.skillInstallMsg = { type: 'success', text: '已卸载技能「' + name + '」' };
                await this.loadSkills();
            } catch (e) {
                this.skillInstallMsg = { type: 'error', text: e.message };
            }
        },

        formatNum(n) {
            if (n == null) return '—';
            if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
            if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
            return String(n);
        },

        get filteredSkills() {
            let filtered = this.skills;

            if (this.skillSearchQuery.trim()) {
                const query = this.skillSearchQuery.toLowerCase();
                filtered = filtered.filter(skill =>
                    skill.name.toLowerCase().includes(query) ||
                    skill.description.toLowerCase().includes(query)
                );
            }

            if (this.skillCategoryFilter !== 'all') {
                filtered = filtered.filter(skill =>
                    skill.category === this.skillCategoryFilter
                );
            }

            if (this.skillStatusFilter === 'enabled') {
                filtered = filtered.filter(skill => skill.enabled);
            } else if (this.skillStatusFilter === 'disabled') {
                filtered = filtered.filter(skill => !skill.enabled);
            }

            return filtered;
        },

        get groupedSkills() {
            const groups = {};
            for (const skill of this.filteredSkills) {
                const cat = skill.category || 'general';
                if (!groups[cat]) groups[cat] = [];
                groups[cat].push(skill);
            }
            return Object.entries(groups).sort((a, b) => a[0].localeCompare(b[0]));
        },

        isSkillExpanded(name) {
            return this.expandedSkills.includes(name);
        },

        toggleSkillExpand(name) {
            if (this.isSkillExpanded(name)) {
                this.expandedSkills = this.expandedSkills.filter(n => n !== name);
            } else {
                this.expandedSkills.push(name);
            }
        }
    };
}
