/**
 * workspace-logic.js
 * 在 app-logic.js 的 mainApp() 基础上，注入 Codex Shell 所需的工作区状态与方法。
 * 通过替换 window.mainApp，在原始对象上直接追加属性，避免 this 绑定问题。
 */
(function () {
    'use strict';

    // 等待 DOM 解析完成后再包装（此时 app-logic.js 已执行）
    var _wrap = function () {
        if (typeof window.mainApp !== 'function') {
            console.error('[workspace-logic] mainApp not found');
            return;
        }

        var _base = window.mainApp;

        window.mainApp = function () {
            var obj = _base();

            // ── Shell 新增状态 ────────────────────────────────────────────
            obj.currentView = 'home';
            obj.sidebarCollapsed = false;

            obj.workspaces = [];
            obj.activeWorkspaceId = null;
            obj.activeWorkspace = null;
            obj.workspaceThreads = [];
            obj.workspaceThreadMap = {};
            obj.expandedWorkspaceIds = {};
            obj.workspaceLoading = false;

            obj.currentThreadId = null;
            obj.threadLoading = false;

            obj.showSettings = false;
            obj.settingsTab = 'models';
            obj.previousViewBeforeSettings = 'home';
            obj.settingsTabs = [
                { id: 'models', cfgTab: 'models', title: '模型', description: '管理聊天、嵌入和工具调用的主模型端点' },
                { id: 'agent', cfgTab: 'agent_sys', title: 'Agent', description: '调整代理行为、系统提示与运行偏好' },
                { id: 'diary', cfgTab: null, panel: 'diary', title: '日记', description: '查看认知日志回溯与每日思维整理记录' },
                { id: 'persona', cfgTab: null, panel: 'persona', title: 'VRM 模型', description: '管理角色资料、VRM 形象、表情与动作资源' },
                { id: 'mcp', cfgTab: 'mcp', title: 'MCP 工具', description: '配置 Model Context Protocol 外部工具服务器' },
                { id: 'memory', cfgTab: 'memory', title: '记忆管理', description: '查看、编辑和清理 AI 长期记忆条目' },
                { id: 'tokens', cfgTab: 'tokens', title: 'Token 统计', description: '查看 Token 用量、请求次数与模型分布趋势' },
                { id: 'integrations', cfgTab: 'channels', title: '集成', description: '配置 IM 通道、服务连接与外部桥接' },
                { id: 'identity', cfgTab: 'identity', title: '身份', description: '维护角色设定、记忆摘要与个性化配置' },
                { id: 'diagnostics', cfgTab: 'system', title: '诊断', description: '查看环境信息、运行状态与问题排查项' },
                { id: 'archived', cfgTab: null, title: '归档', description: '整理已归档的工作区与线程' }
            ];

            obj.showNewWorkspaceModal = false;
            obj.showWorkspaceSwitcher = false;
            obj.newWorkspaceName = '';
            obj.newWorkspacePath = '';
            obj.newWorkspaceError = '';
            obj.chatScrollbarHidden = false;
            obj.composerHovering = false;
            obj.notifyShellStateChanged = function () {
                window.dispatchEvent(new CustomEvent('openguiclaw:shell-updated', {
                    detail: {
                        currentView: this.currentView,
                        sidebarCollapsed: !!this.sidebarCollapsed,
                        activeWorkspaceId: this.activeWorkspaceId,
                        currentThreadId: this.currentThreadId,
                        workspaces: this.workspaces,
                        homeData: this.homeData,
                        workspaceThreads: this.workspaceThreads,
                        workspaceThreadMap: this.workspaceThreadMap,
                        expandedWorkspaceIds: this.expandedWorkspaceIds,
                        workspaceLoading: !!this.workspaceLoading,
                        showNewWorkspaceModal: !!this.showNewWorkspaceModal,
                        showWorkspaceSwitcher: !!this.showWorkspaceSwitcher,
                        showSettings: !!this.showSettings,
                        settingsTab: this.settingsTab || 'models',
                        previousViewBeforeSettings: this.previousViewBeforeSettings || 'home',
                        newWorkspaceName: this.newWorkspaceName,
                        newWorkspacePath: this.newWorkspacePath,
                        newWorkspaceError: this.newWorkspaceError,
                        vrmSystemEnabled: !!this.vrmSystemEnabled,
                        showVrm: !!this.showVrm,
                        isReceiving: !!this.isReceiving
                    }
                }));
            };
            obj.notifyWorkspaceModalStateChanged = function () {
                window.dispatchEvent(new CustomEvent('openguiclaw:shell-updated', {
                    detail: {
                        showNewWorkspaceModal: !!this.showNewWorkspaceModal,
                        showWorkspaceSwitcher: !!this.showWorkspaceSwitcher,
                        newWorkspaceName: this.newWorkspaceName,
                        newWorkspacePath: this.newWorkspacePath,
                        newWorkspaceError: this.newWorkspaceError
                    }
                }));
            };
            obj.notifyChatStateChanged = function () {
                window.dispatchEvent(new CustomEvent('openguiclaw:chat-updated', {
                    detail: {
                        currentThreadId: this.currentThreadId,
                        threadLoading: !!this.threadLoading,
                        messages: this.messages
                    }
                }));
            };

            obj.homeData = null;

            obj.findNearestScrollable = function (startNode, boundaryNode) {
                var node = startNode instanceof Element ? startNode : null;
                while (node && node !== boundaryNode) {
                    var style = window.getComputedStyle(node);
                    var overflowY = style.overflowY;
                    var overflowX = style.overflowX;
                    var canScrollY = (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay')
                        && node.scrollHeight > node.clientHeight + 1;
                    var canScrollX = (overflowX === 'auto' || overflowX === 'scroll' || overflowX === 'overlay')
                        && node.scrollWidth > node.clientWidth + 1;
                    if (canScrollY || canScrollX) return node;
                    node = node.parentElement;
                }
                return null;
            };

            obj.getActiveSettingsScrollContainer = function (overlayEl) {
                if (!(overlayEl instanceof Element)) return null;
                var candidates = overlayEl.querySelectorAll('.settings-main-body .overflow-y-auto, .settings-archived-pane');

                for (var i = 0; i < candidates.length; i++) {
                    var el = candidates[i];
                    if (el.offsetParent === null) continue;
                    if (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1) return el;
                }

                for (var j = 0; j < candidates.length; j++) {
                    if (candidates[j].offsetParent !== null) return candidates[j];
                }

                return null;
            };

            obj.handleSettingsWheel = function (event) {
                if (!this.showSettings) return;

                var overlayEl = event.currentTarget instanceof Element ? event.currentTarget : null;
                if (!overlayEl) return;

                var scrollTarget = this.findNearestScrollable(event.target, overlayEl)
                    || this.getActiveSettingsScrollContainer(overlayEl);

                event.preventDefault();
                event.stopPropagation();

                if (!scrollTarget) return;

                if (typeof event.deltaX === 'number' && event.deltaX !== 0) {
                    scrollTarget.scrollLeft += event.deltaX;
                }
                if (typeof event.deltaY === 'number' && event.deltaY !== 0) {
                    scrollTarget.scrollTop += event.deltaY;
                }
                this.notifyChatStateChanged();
            };

            obj.openSettingsView = function (tabId) {
                if (this.currentView !== 'settings') {
                    this.previousViewBeforeSettings = this.currentView || 'home';
                }
                this.showSettings = true;
                this.currentView = 'settings';
                if (tabId) {
                    this.settingsTab = tabId;
                    var tabMeta = Array.isArray(this.settingsTabs)
                        ? this.settingsTabs.find(function (tab) { return tab.id === tabId; })
                        : null;
                    if (tabMeta && tabMeta.cfgTab) {
                        this.activePanel = 'config';
                        this.configTab = tabMeta.cfgTab;
                    } else if (tabMeta && tabMeta.panel) {
                        this.activePanel = tabMeta.panel;
                        if (typeof this.switchPanel === 'function') {
                            this.switchPanel(tabMeta.panel);
                        }
                    }
                }
                this.notifyShellStateChanged();
            };

            obj.closeSettingsView = function () {
                this.showSettings = false;
                this.currentView = this.previousViewBeforeSettings || 'home';
                this.notifyShellStateChanged();
            };

            // ── 保存原始 init，扩展后调用 ────────────────────────────────
            var _baseInit = obj.init.bind(obj);
            var _baseAbortReceiving = typeof obj.abortReceiving === 'function'
                ? obj.abortReceiving.bind(obj)
                : null;

            obj.init = async function () {
                window.__openGuiclawApp = this;
                await _baseInit();
                var savedWsId = localStorage.getItem('activeWorkspaceId');
                await this.loadWorkspaces();
                await this.loadHome();
                if (savedWsId && this.workspaces.find(function (w) { return w.id === savedWsId; })) {
                    await this.switchWorkspace(savedWsId, true);
                } else if (this.workspaces.length > 0) {
                    this.expandedWorkspaceIds[this.workspaces[0].id] = true;
                }
                this.currentView = 'home';
                window.__openGuiclawApp = this;
                window.dispatchEvent(new CustomEvent('openguiclaw:app-ready'));
                this.notifyShellStateChanged();
                this.notifyChatStateChanged();
            };

            obj.resetDraftState = function () {
                this.currentThreadId = null;
                this.messages = [];
                this.inputText = '';
                this.chatScrollbarHidden = false;
                this.composerHovering = false;
                if (Array.isArray(this.stagedFiles)) this.stagedFiles = [];
                this.showCommandMenu = false;
                this.commandSelectedIndex = 0;
                this.isDragOver = false;
                this.$nextTick(function () {
                    var ta = document.querySelector('.composer-textarea');
                    if (ta) ta.style.height = 'auto';
                });
                this.notifyShellStateChanged();
                this.notifyChatStateChanged();
            };

            obj.setNewWorkspaceName = function (value) {
                this.newWorkspaceName = typeof value === 'string' ? value : '';
                this.notifyWorkspaceModalStateChanged();
            };

            obj.setNewWorkspacePath = function (value) {
                this.newWorkspacePath = typeof value === 'string' ? value : '';
                this.notifyWorkspaceModalStateChanged();
            };

            obj.closeNewWorkspaceModal = function () {
                this.showNewWorkspaceModal = false;
                this.notifyWorkspaceModalStateChanged();
            };

            obj.getCurrentThread = function () {
                return this.workspaceThreads.find(function (thread) {
                    return thread.session_id === this.currentThreadId;
                }.bind(this)) || null;
            };

            obj.hideChatScrollbar = function () {
                this.chatScrollbarHidden = true;
            };

            obj.showChatScrollbar = function () {
                this.chatScrollbarHidden = false;
            };

            obj.handleComposerMouseEnter = function () {
                this.composerHovering = true;
            };

            obj.handleComposerMouseLeave = function () {
                this.composerHovering = false;
                this.showChatScrollbar();
            };

            obj.handleComposerFocusIn = function () {
                this.hideChatScrollbar();
            };

            obj.handleComposerFocusOut = function () {
                if (!this.composerHovering) {
                    this.showChatScrollbar();
                }
            };

            obj.getSidebarRecentSessions = function (wsId) {
                return this.getSidebarWorkspaceThreads(wsId).slice(0, 3);
            };

            obj.getSidebarWorkspaceThreads = function (wsId) {
                return Array.isArray(this.workspaceThreadMap[wsId]) ? this.workspaceThreadMap[wsId] : [];
            };

            obj.isWorkspaceExpanded = function (wsId) {
                return !!this.expandedWorkspaceIds[wsId];
            };

            obj.toggleWorkspaceGroup = async function (wsId) {
                if (!wsId) return;
                var willExpand = !this.expandedWorkspaceIds[wsId];
                this.expandedWorkspaceIds[wsId] = willExpand;
                this.notifyShellStateChanged();
                if (willExpand) {
                    await this.switchWorkspace(wsId, true);
                    await this.loadWorkspaceThreads(wsId, true);
                    this.currentView = this.currentThreadId ? 'chat' : 'home';
                    this.notifyShellStateChanged();
                }
            };

            obj.openSidebarThread = async function (wsId, sessionId) {
                this.expandedWorkspaceIds[wsId] = true;
                this.notifyShellStateChanged();
                await this.switchWorkspace(wsId, true);
                await this.loadThread(wsId, sessionId);
            };

            obj.formatSidebarSessionTime = function (value) {
                if (!value) return '';
                var date = new Date(String(value).replace(' ', 'T'));
                if (isNaN(date.getTime())) return '';

                var diffMs = Date.now() - date.getTime();
                var dayMs = 24 * 60 * 60 * 1000;
                var hourMs = 60 * 60 * 1000;
                if (diffMs < hourMs) {
                    var mins = Math.max(1, Math.round(diffMs / (60 * 1000)));
                    return mins + ' 分钟前';
                }
                if (diffMs < dayMs) {
                    return Math.round(diffMs / hourMs) + ' 小时前';
                }
                return Math.round(diffMs / dayMs) + ' 天前';
            };

            obj.getTopbarTitle = function () {
                if (this.currentView === 'home') {
                    return this.activeWorkspace ? this.activeWorkspace.name : '选择一个工作区';
                }
                if (!this.activeWorkspace) return '选择工作区';

                var title = this.activeWorkspace.name;
                if (!this.currentThreadId) return title + ' / 新对话';

                var thread = this.getCurrentThread();
                var threadTitle = thread && thread.title
                    ? thread.title
                    : this.currentThreadId.slice(0, 12) + '...';
                return title + ' / ' + threadTitle;
            };

            // ── Home ──────────────────────────────────────────────────────
            obj.getTopbarTitle = function () {
                if (this.currentView === 'home') {
                    return this.activeWorkspace ? this.activeWorkspace.name : 'Select a workspace';
                }
                if (this.currentView === 'skills') {
                    return '技能管理';
                }
                if (this.currentView === 'scheduler') {
                    return '自动化';
                }
                if (!this.activeWorkspace) return 'Select a workspace';

                var title = this.activeWorkspace.name;
                if (!this.currentThreadId) return title + ' / 新对话';

                var thread = this.getCurrentThread();
                var threadTitle = thread && thread.title
                    ? thread.title
                    : this.currentThreadId.slice(0, 12) + '...';
                return title + ' / ' + threadTitle;
            };

            obj.getTopbarKicker = function () {
                if (this.currentView === 'home') return 'New Thread';
                if (this.currentView === 'skills') return 'Skill Library';
                if (this.currentView === 'scheduler') return 'Automation';
                if (this.currentView === 'settings') return 'Settings';
                return 'Active Workspace';
            };

            obj.openSidebarPanel = async function (view) {
                this.showSettings = false;
                if (view === 'skills') {
                    this.currentView = 'skills';
                    this.activePanel = 'skills';
                    this.notifyShellStateChanged();
                    if (typeof this.loadSkills === 'function' && this.skills.length === 0) {
                        await this.loadSkills();
                    }
                    return;
                }

                if (view === 'scheduler') {
                    this.currentView = 'scheduler';
                    this.activePanel = 'scheduler';
                    if (typeof this.showSchedulerForm !== 'undefined') {
                        this.showSchedulerForm = false;
                    }
                    this.notifyShellStateChanged();
                    if (typeof this.loadSchedulerTasks === 'function') {
                        await this.loadSchedulerTasks();
                    }
                    return;
                }

                if (view === 'home') {
                    this.currentView = 'home';
                    this.notifyShellStateChanged();
                    return;
                }

                if (view === 'chat') {
                    this.currentView = 'chat';
                    this.activePanel = 'chat';
                    this.notifyShellStateChanged();
                }
            };

            obj.loadHome = async function () {
                try {
                    var r = await fetch('/api/home');
                    if (r.ok) this.homeData = await r.json();
                } catch (e) { console.warn('[Shell] loadHome:', e); }
                this.notifyShellStateChanged();
            };

            // ── Workspaces ────────────────────────────────────────────────
            obj.loadWorkspaces = async function () {
                this.workspaceLoading = true;
                this.notifyShellStateChanged();
                try {
                    var r = await fetch('/api/workspaces');
                    if (r.ok) {
                        var data = await r.json();
                        this.workspaces = Array.isArray(data) ? data : (data.workspaces || []);
                    }
                } catch (e) {
                    console.warn('[Shell] loadWorkspaces:', e);
                    this.workspaces = [];
                } finally {
                    this.workspaceLoading = false;
                    this.notifyShellStateChanged();
                }
            };

            obj.switchWorkspace = async function (wsId, silent) {
                if (this.activeWorkspaceId === wsId && !silent) return;
                if (this.isReceiving && this.currentController) this.abortReceiving();

                this.activeWorkspaceId = wsId;
                this.activeWorkspace = this.workspaces.find(function (w) { return w.id === wsId; }) || null;
                this.expandedWorkspaceIds[wsId] = true;
                this.resetDraftState();
                localStorage.setItem('activeWorkspaceId', wsId);
                this.notifyShellStateChanged();

                await this.loadWorkspaceThreads(wsId);
            };

            obj.focusWorkspaceHome = async function (wsId) {
                if (!wsId) return;
                await this.switchWorkspace(wsId, true);
                this.currentView = 'home';
                this.showWorkspaceSwitcher = false;
                this.notifyShellStateChanged();
            };

            obj.openNewWorkspaceModal = function () {
                this.showNewWorkspaceModal = true;
                this.showWorkspaceSwitcher = false;
                this.newWorkspaceError = '';
                this.notifyWorkspaceModalStateChanged();
            };

            obj.pickWorkspacePath = async function () {
                if (this.newWorkspaceError) {
                    this.newWorkspaceError = '';
                    this.notifyWorkspaceModalStateChanged();
                }
                try {
                    var selected = null;

                    if (window.pywebview && window.pywebview.api && window.pywebview.api.select_workspace_folder) {
                        selected = await window.pywebview.api.select_workspace_folder();
                    } else {
                        var response = await fetch('/api/workspaces/pick-folder', { method: 'POST' });
                        var payload = await response.json();
                        if (!response.ok) {
                            throw new Error((payload && payload.detail) || '当前环境无法打开目录选择器');
                        }
                        selected = payload && payload.path;
                    }

                    if (!selected) return;

                    this.newWorkspacePath = selected;
                    if (!this.newWorkspaceName) {
                        var normalized = selected.replace(/[\\/]+$/, '');
                        var parts = normalized.split(/[\\/]/);
                        this.newWorkspaceName = parts[parts.length - 1] || '';
                    }
                    this.notifyWorkspaceModalStateChanged();
                } catch (e) {
                    this.newWorkspaceError = '打开目录选择器失败：' + e.message;
                    this.notifyWorkspaceModalStateChanged();
                }
            };

            obj.loadWorkspaceThreads = async function (wsId, force) {
                if (!wsId) return;
                if (!force && Array.isArray(this.workspaceThreadMap[wsId]) && this.workspaceThreadMap[wsId].length > 0) {
                    if (this.activeWorkspaceId === wsId) {
                        this.workspaceThreads = this.workspaceThreadMap[wsId];
                    }
                    this.notifyShellStateChanged();
                    return;
                }
                try {
                    var r = await fetch('/api/workspaces/' + wsId + '/sessions');
                    if (r.ok) {
                        var data = await r.json();
                        var sessions = Array.isArray(data) ? data : (data.sessions || []);
                        this.workspaceThreadMap[wsId] = sessions;
                        if (this.activeWorkspaceId === wsId) {
                            this.workspaceThreads = sessions;
                        }
                    }
                } catch (e) {
                    console.warn('[Shell] loadWorkspaceThreads:', e);
                    this.workspaceThreadMap[wsId] = [];
                    if (this.activeWorkspaceId === wsId) {
                        this.workspaceThreads = [];
                    }
                }
                this.notifyShellStateChanged();
            };

            obj.createWorkspace = async function (name, path) {
                var workspaceName = typeof name === 'string' ? name : this.newWorkspaceName;
                var workspacePath = typeof path === 'string' ? path : this.newWorkspacePath;
                workspaceName = (workspaceName || '').trim();
                workspacePath = (workspacePath || '').trim();

                this.newWorkspaceError = '';
                if (!workspaceName) {
                    this.newWorkspaceError = '请输入工作区名称';
                    return;
                }
                if (!workspacePath) {
                    this.newWorkspaceError = '请选择项目目录';
                    return;
                }

                try {
                    var r = await fetch('/api/workspaces', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: workspaceName, workspace_path: workspacePath })
                    });
                    var data = await r.json();
                    if (r.ok) {
                        this.showNewWorkspaceModal = false;
                        this.newWorkspaceName = '';
                        this.newWorkspacePath = '';
                        this.notifyShellStateChanged();
                        await this.loadWorkspaces();
                        await this.loadHome();
                        await this.focusWorkspaceHome(data.id || data.workspace_id);
                    } else {
                        this.newWorkspaceError = data.detail || '创建失败';
                    }
                } catch (e) {
                    this.newWorkspaceError = '网络错误：' + e.message;
                }
            };

            // ── Threads ───────────────────────────────────────────────────
            obj.createThread = async function (wsId) {
                if (!wsId) return;
                try {
                    var r = await fetch('/api/workspaces/' + wsId + '/sessions/new', { method: 'POST' });
                    if (r.ok) {
                        var data = await r.json();
                        var sessionId = data.session_id || data.id;
                        await this.loadWorkspaceThreads(wsId, true);
                        await this.loadHome();
                        await this.loadThread(wsId, sessionId);
                    }
                } catch (e) { console.error('[Shell] createThread:', e); }
            };

            obj.loadThread = async function (wsId, sessionId) {
                if (!wsId || !sessionId) return;
                this.threadLoading = true;
                this.currentThreadId = sessionId;
                this.currentView = 'chat';
                this.messages = [];
                this.notifyChatStateChanged();

                try {
                    var r = await fetch('/api/workspaces/' + wsId + '/sessions/' + sessionId + '/messages');
                    if (r.ok) {
                        var data = await r.json();
                        this._parseWorkspaceMessages(data);
                    } else {
                        throw new Error('加载线程失败');
                    }
                } catch (e) {
                    console.warn('[Shell] loadThread:', e);
                    this.messages = [{
                        id: 'ws-load-error-' + Date.now(),
                        role: 'assistant',
                        content: '⚠ 无法加载当前对话，请稍后重试。'
                    }];
                    this.pushLog('error', '加载工作区对话失败');
                } finally {
                    this.threadLoading = false;
                    this.notifyChatStateChanged();
                    this.$nextTick(function () { this.scrollToBottom(); }.bind(this));
                }
            };

            obj._parseWorkspaceMessages = function (data) {
                var self = this;
                var validMessages = [];
                var lastAssistantMsg = null;
                // tool_call_id → block index in lastAssistantMsg.blocks
                var toolCallBlockMap = {};

                (data.messages || []).forEach(function (m, i) {
                    if (m.role === 'debug_log') return;

                    if (m.role === 'user') {
                        lastAssistantMsg = null;
                        toolCallBlockMap = {};
                        var displayText = '';
                        if (Array.isArray(m.content)) {
                            var fileParts = [], promptText = '';
                            m.content.forEach(function (c) {
                                if (c.type === 'image_url') { fileParts.push('[图片]'); }
                                else if (c.type === 'text') {
                                    var fm = c.text.match(/^【文件内容：(.+?)】/);
                                    if (fm) fileParts.push('[文件: ' + fm[1] + ']');
                                    else promptText = c.text.trim();
                                }
                            });
                            var parts = [];
                            if (fileParts.length) parts.push(fileParts.join(' '));
                            if (promptText) parts.push(promptText);
                            displayText = parts.join('\n\n') || '(附件)';
                        } else {
                            displayText = m.content || '';
                        }
                        validMessages.push({ id: 'h-' + i, role: 'user', content: displayText });

                    } else if (m.role === 'assistant') {
                        // 每个 assistant 消息都可能带 tool_calls，需要确保有一个 lastAssistantMsg
                        if (!lastAssistantMsg) {
                            lastAssistantMsg = {
                                id: 'h-' + i,
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
                            lastAssistantMsg.thinkingHtml = self.mdRender(lastAssistantMsg._thinkingRaw);
                        }
                        // 处理 tool_calls（OpenAI function calling 格式）
                        var toolCalls = m.tool_calls;
                        if (typeof toolCalls === 'string') {
                            try { toolCalls = JSON.parse(toolCalls); } catch (_) { toolCalls = null; }
                        }
                        if (Array.isArray(toolCalls) && toolCalls.length > 0) {
                            toolCalls.forEach(function (tc) {
                                var tcId = tc.id || ('tc-' + i + '-' + Math.random());
                                var fnName = (tc.function && tc.function.name) ? tc.function.name : (tc.name || '未知工具');
                                var paramsStr = '';
                                try {
                                    var args = tc.function ? tc.function.arguments : tc.arguments;
                                    if (typeof args === 'string') {
                                        paramsStr = JSON.stringify(JSON.parse(args), null, 2);
                                    } else if (args) {
                                        paramsStr = JSON.stringify(args, null, 2);
                                    }
                                } catch (_) { paramsStr = String(tc.function ? tc.function.arguments : ''); }
                                var blockIdx = lastAssistantMsg.blocks.length;
                                lastAssistantMsg.blocks.push({
                                    type: 'tool',
                                    id: tcId,
                                    name: fnName,
                                    paramsStr: paramsStr,
                                    status: 'done',   // 历史消息默认已完成
                                    resultStr: '',
                                    _collapsed: true
                                });
                                toolCallBlockMap[tcId] = blockIdx;
                            });
                        }
                        if (m.content) {
                            lastAssistantMsg.blocks.push({ type: 'text', content: m.content, html: self.mdRender(m.content) });
                        }

                    } else if (m.role === 'tool') {
                        // 工具结果消息：找到对应的 tool block 并填入结果
                        if (lastAssistantMsg && m.tool_call_id !== undefined) {
                            var blockIdx = toolCallBlockMap[m.tool_call_id];
                            if (blockIdx !== undefined && lastAssistantMsg.blocks[blockIdx]) {
                                lastAssistantMsg.blocks[blockIdx].resultStr = m.content || '';
                                lastAssistantMsg.blocks[blockIdx].status = 'done';
                            }
                        }

                    } else if (m.role === 'visual_log') {
                        lastAssistantMsg = null;
                        toolCallBlockMap = {};
                        validMessages.push({ id: 'h-' + i, role: 'visual_log', content: m.content, html: self.mdRender(m.content) });
                    }
                });

                this.messages = validMessages;
                if (data.estimated_tokens > 0) this.lastBackendTokens = data.estimated_tokens;
                this.notifyChatStateChanged();
            };

            obj.newSession = async function () {
                if (this.isReceiving && this.currentController) this.abortReceiving();
                this.resetDraftState();
                this.currentView = 'home';
            };

            obj.abortReceiving = function () {
                if (this.activeWorkspaceId && this.currentThreadId) {
                    fetch('/api/workspaces/' + this.activeWorkspaceId + '/sessions/' + this.currentThreadId + '/abort', {
                        method: 'POST'
                    }).catch(function () {});
                }
                if (_baseAbortReceiving) _baseAbortReceiving();
            };

            obj._pushWorkspaceAssistantPlaceholder = function (aiId, initialHtml) {
                this.messages.push({
                    id: aiId,
                    role: 'assistant',
                    content: initialHtml || '<span class="text-gray-400 text-xs italic animate-pulse">思考中...</span>',
                    thinkingHtml: '',
                    _thinkingRaw: '',
                    _thinkCollapsed: true,
                    blocks: []
                });
                this.notifyChatStateChanged();
                this.scrollToBottom();
            };

            obj._handleWorkspaceStreamEvent = function (aiId, ev) {
                var idx = this.messages.findIndex(function (m) { return m.id === aiId; });
                if (ev.type === 'status') {
                    this.pushLog('status', ev.content || '');
                    if (idx !== -1) {
                        var cur = this.messages[idx].content || '';
                        if (cur.includes('animate-pulse') || cur.includes('thinking')) {
                            this.messages[idx].content = '<span class="text-gray-500 text-xs italic">' + (ev.content || '') + '</span>';
                        }
                    }
                } else if (ev.type === 'tool_call') {
                    var paramStr = ev.params ? JSON.stringify(ev.params, null, 2) : '';
                    this.pushLog('tool_call', ev.name + '(' + paramStr + ')');
                    if (idx !== -1) {
                        var toolMessage = this.messages[idx];
                        var toolBlocks = toolMessage.blocks ? toolMessage.blocks.slice() : [];
                        toolBlocks.push({
                            type: 'tool',
                            id: ev.id,
                            name: ev.name,
                            paramsStr: paramStr,
                            status: 'running',
                            _collapsed: false
                        });
                        this.messages[idx] = Object.assign({}, toolMessage, {
                            _streaming: true,
                            _rawContent: toolMessage._rawContent || '',
                            content: toolMessage._streaming ? toolMessage.content : '',
                            _isThinking: true,
                            blocks: toolBlocks
                        });
                        this.scrollToBottom();
                    }
                } else if (ev.type === 'ask_user_interrupt') {
                    this.pushLog('tool_call', 'ask_user: ' + (ev.question || ''));
                    if (idx !== -1) {
                        var askMessage = this.messages[idx];
                        var askBlocks = (askMessage.blocks || []).slice();
                        var askOptions = (ev.options || []).map(function (opt, i) {
                            return {
                                id: typeof opt === 'object' ? (opt.id || String(i)) : String(i),
                                label: typeof opt === 'object' ? (opt.label || opt.text || String(opt)) : String(opt)
                            };
                        });
                        askBlocks.push({
                            id: ev.id || ('ask-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8)),
                            type: 'ask_user',
                            question: ev.question || '请选择：',
                            options: askOptions,
                            answered: false
                        });
                        this.messages[idx] = Object.assign({}, askMessage, {
                            _streaming: true,
                            _rawContent: askMessage._rawContent || '',
                            content: askMessage._streaming ? askMessage.content : '',
                            _isThinking: false,
                            blocks: askBlocks
                        });
                        this.scrollToBottom();
                    }
                } else if (ev.type === 'tool_result') {
                    this.pushLog('tool_result', ev.name + ' → ' + (ev.result || ''));
                    if (idx !== -1) {
                        var resultMessage = this.messages[idx];
                        var resultBlocks = (resultMessage.blocks || []).map(function (b) {
                            if (b.type === 'tool' && b.id === ev.id) {
                                return Object.assign({}, b, { status: 'done', resultStr: ev.result || '', _collapsed: true });
                            }
                            return b;
                        });
                        var stillThinking = resultBlocks.some(function (b) {
                            return b.type === 'tool' && b.status === 'running';
                        });
                        this.messages[idx] = Object.assign({}, resultMessage, {
                            blocks: resultBlocks,
                            _isThinking: stillThinking
                        });
                        this.scrollToBottom();
                    }
                } else if (ev.type === 'thinking_chunk') {
                    if (idx !== -1) {
                        var thinkingMessage = this.messages[idx];
                        var newThinkRaw = (thinkingMessage._thinkingRaw || '') + (ev.content || '');
                        this.messages[idx] = Object.assign({}, thinkingMessage, {
                            _streaming: true,
                            _rawContent: thinkingMessage._rawContent || '',
                            content: thinkingMessage._streaming ? thinkingMessage.content : '',
                            _thinkingRaw: newThinkRaw,
                            thinkingHtml: this.mdRender(newThinkRaw),
                            _thinkCollapsed: false
                        });
                        this.scrollToBottom();
                    }
                } else if (ev.type === 'message_chunk') {
                    if (idx !== -1) {
                        var chunkMessage = this.messages[idx];
                        var chunkBlocks = (chunkMessage.blocks || []).slice();
                        var needCollapseThink = chunkMessage._thinkCollapsed === false && !chunkMessage._thinkCollapseScheduled;
                        if (ev.content) {
                            var lastBlock = chunkBlocks[chunkBlocks.length - 1];
                            if (lastBlock && lastBlock.type === 'text') {
                                var newContent = lastBlock.content + ev.content;
                                chunkBlocks[chunkBlocks.length - 1] = Object.assign({}, lastBlock, {
                                    content: newContent,
                                    html: this.mdRender(newContent)
                                });
                            } else {
                                chunkBlocks.push({
                                    type: 'text',
                                    content: ev.content,
                                    html: this.mdRender(ev.content)
                                });
                            }
                        }
                        var chunkUpdated = Object.assign({}, chunkMessage, {
                            _streaming: true,
                            _rawContent: chunkMessage._rawContent || '',
                            content: chunkMessage._streaming ? chunkMessage.content : '',
                            blocks: chunkBlocks
                        });
                        if (needCollapseThink) {
                            chunkUpdated._thinkCollapseScheduled = true;
                            var self = this;
                            setTimeout(function () {
                                var ci = self.messages.findIndex(function (m) { return m.id === aiId; });
                                if (ci !== -1) {
                                    self.messages[ci] = Object.assign({}, self.messages[ci], {
                                        _thinkCollapsed: true,
                                        _thinkCollapseScheduled: false
                                    });
                                }
                            }, 1200);
                        }
                        this.messages[idx] = chunkUpdated;
                        this.scrollToBottom();
                    }
                } else if (ev.type === 'message') {
                    var logContent = (ev.content || '').trim();
                    if (!logContent && idx !== -1) {
                        var finalMessage = this.messages[idx];
                        if (finalMessage.blocks) {
                            logContent = finalMessage.blocks
                                .filter(function (block) { return block.type === 'text'; })
                                .map(function (block) { return block.content; })
                                .join('')
                                .trim();
                        }
                    }
                    if (!logContent) logContent = '响应已完成';
                    this.pushLog(
                        'message',
                        logContent.replace(/\s+/g, ' ').slice(0, 80) + (logContent.length > 80 ? '...' : '')
                    );

                    if (idx !== -1) {
                        var doneMessage = this.messages[idx];
                        var doneBlocks = (doneMessage.blocks || []).slice();
                        var hasText = doneBlocks.some(function (block) {
                            return block.type === 'text' && block.content && block.content.trim();
                        });
                        if (!hasText) {
                            doneBlocks.push({ type: 'status_done' });
                        }
                        this.messages[idx] = Object.assign({}, doneMessage, {
                            _isThinking: false,
                            _streaming: false,
                            _rawContent: undefined,
                            blocks: doneBlocks
                        });
                        this.scrollToBottom();
                    }
                } else if (ev.type === 'usage') {
                    if (ev.content && typeof ev.content === 'object') {
                        this.lastBackendTokens = ev.content.total_tokens || this.lastBackendTokens;
                        this.lastMaxTokens = ev.content.max_tokens || this.lastMaxTokens;
                    }
                } else if (ev.type === 'aborted') {
                    this.pushLog('status', '已请求停止当前对话');
                } else if (ev.type === 'error') {
                    this.pushLog('error', ev.content || '');
                    if (idx !== -1) {
                        this.messages[idx].content = '<span class="text-red-400 text-xs">❌ ' + (ev.content || '未知错误') + '</span>';
                    }
                }
            };

            obj.sendFiles = async function () {
                this.pushLog('status', '当前多工作区聊天暂未接入附件上传，请先发送纯文本消息。');
                this.messages.push({
                    id: 'ws-upload-warning-' + Date.now(),
                    role: 'assistant',
                    content: '⚠ 当前 Workspace 聊天流暂未接入附件上传，请先移除附件后发送文本消息。'
                });
                this.notifyChatStateChanged();
                this.scrollToBottom();
            };

            obj.sendMessage = async function (isProactive) {
                if (this.stagedFiles.length > 0 && !isProactive) {
                    await this.sendFiles();
                    return;
                }

                var text = (this.inputText || '').trim();
                if (!text || this.isReceiving) return;
                if (!this.activeWorkspaceId) {
                    this.pushLog('error', '请先选择工作区');
                    return;
                }

                if (!this.currentThreadId) {
                    await this.createThread(this.activeWorkspaceId);
                }
                if (!this.currentThreadId) {
                    this.pushLog('error', '无法创建新对话');
                    return;
                }

                if (!isProactive) {
                    this.messages.push({ id: 'u-' + Date.now(), role: 'user', content: text });
                    this.notifyChatStateChanged();
                }
                this.inputText = '';
                this.$nextTick(function () {
                    var ta = document.querySelector('textarea');
                    if (ta) ta.style.height = 'auto';
                });
                this.scrollToBottom();

                var aiId = 'a-' + Date.now();
                this._pushWorkspaceAssistantPlaceholder(aiId);
                this.isReceiving = true;

                try {
                    this.currentController = new AbortController();
                    var response = await fetch(
                        '/api/workspaces/' + this.activeWorkspaceId + '/sessions/' + this.currentThreadId + '/stream',
                        {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                workspace_id: this.activeWorkspaceId,
                                session_id: this.currentThreadId,
                                message: text,
                                ...(this.chatModel ? { model: this.chatModel } : {}),
                                ...(this.chatAgent ? { agent_id: this.chatAgent.id } : {})
                            }),
                            signal: this.currentController.signal
                        }
                    );
                    if (!response.ok || !response.body) {
                        throw new Error('Workspace stream request failed');
                    }

                    var reader = response.body.getReader();
                    var decoder = new TextDecoder('utf-8');
                    var buffer = '';
                    var self = this;
                    while (true) {
                        var readResult = await reader.read();
                        if (readResult.done) break;
                        buffer += decoder.decode(readResult.value, { stream: true });
                        var lines = buffer.split('\n');
                        buffer = lines.pop();
                        for (var i = 0; i < lines.length; i++) {
                            var line = lines[i];
                            if (!line.startsWith('data: ')) continue;
                            var dataStr = line.slice(6).trim();
                            if (dataStr === '[DONE]') continue;
                            try {
                                self._handleWorkspaceStreamEvent(aiId, JSON.parse(dataStr));
                            } catch (_) {}
                        }
                        // 每个网络 chunk 处理完后让出控制权，让 Alpine 刷新 DOM
                        await new Promise(function (resolve) { setTimeout(resolve, 0); });
                    }
                } catch (err) {
                    if (err.name !== 'AbortError') {
                        var idx = this.messages.findIndex(function (m) { return m.id === aiId; });
                        if (idx !== -1) {
                            this.messages[idx].content = '<span class="text-red-400 text-xs">❌ 网络异常，请稍后再试。</span>';
                        }
                    }
                } finally {
                    this.isReceiving = false;
                    this.currentController = null;
                    this.notifyChatStateChanged();
                    this.scrollToBottom();
                    this.loadTokenStats(this.tokenPeriod);
                    await this.loadWorkspaceThreads(this.activeWorkspaceId, true);
                    await this.loadHome();
                }
            };

            obj.archiveThread = async function (wsId, sessionId) {
                if (!wsId || !sessionId) return;
                try {
                    var r = await fetch('/api/workspaces/' + wsId + '/sessions/' + sessionId + '/archive', { method: 'POST' });
                    if (r.ok) {
                        if (this.currentThreadId === sessionId) {
                            this.currentThreadId = null;
                            this.messages = [];
                            this.notifyChatStateChanged();
                        }
                        await this.loadWorkspaceThreads(wsId, true);
                        await this.loadHome();
                        this.pushLog('status', '对话已归档');
                    }
                } catch (e) { console.error('[Shell] archiveThread:', e); }
            };

            obj.deleteThread = async function (wsId, sessionId) {
                if (!wsId || !sessionId) return;
                if (!confirm('删除后会从左侧历史中移除，并可在设置的归档页中恢复。继续吗？')) return;
                await this.archiveThread(wsId, sessionId);
            };

            obj.renameThread = async function (wsId, sessionId, title) {
                if (!wsId || !sessionId) return;
                var nextTitle = (title || '').trim();
                if (!nextTitle) throw new Error('请输入新的线程名称');
                try {
                    var r = await fetch('/api/workspaces/' + wsId + '/sessions/' + sessionId, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: nextTitle })
                    });
                    var data = {};
                    try {
                        data = await r.json();
                    } catch (_) {}
                    if (!r.ok) throw new Error(data.detail || '重命名线程失败');
                    await this.loadWorkspaceThreads(wsId, true);
                    await this.loadHome();
                    this.pushLog('status', '已重命名对话');
                    this.notifyShellStateChanged();
                    this.notifyChatStateChanged();
                } catch (e) {
                    console.error('[Shell] renameThread:', e);
                    throw e;
                }
            };

            obj.toggleThreadPin = async function (wsId, sessionId, pinned) {
                if (!wsId || !sessionId) return;
                var endpoint = pinned ? 'unpin' : 'pin';
                try {
                    var r = await fetch('/api/workspaces/' + wsId + '/sessions/' + sessionId + '/' + endpoint, { method: 'POST' });
                    if (r.ok) {
                        await this.loadWorkspaceThreads(wsId, true);
                        await this.loadHome();
                        this.pushLog('status', pinned ? '已取消置顶对话' : '已置顶对话');
                    }
                } catch (e) { console.error('[Shell] toggleThreadPin:', e); }
            };

            obj.deleteArchivedThread = async function (wsId, sessionId) {
                if (!wsId || !sessionId) return;
                if (!confirm('确定永久删除该对话？此操作无法撤销。')) return;
                try {
                    var r = await fetch('/api/workspaces/' + wsId + '/sessions/' + sessionId, { method: 'DELETE' });
                    if (r.ok) {
                        await this.loadWorkspaceThreads(wsId, true);
                        await this.loadHome();
                        this.pushLog('status', '对话已永久删除');
                    }
                } catch (e) { console.error('[Shell] deleteArchivedThread:', e); }
            };

            return obj;
        };
    };

    // app-logic.js 在本文件之前同步加载，必须立刻包装。
    // 否则 Alpine 会先用旧版 mainApp() 初始化，导致 shell 状态和方法缺失。
    _wrap();

})();
