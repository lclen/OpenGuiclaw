import type { ChatBlock } from '../bridge/openGuiclaw';

export type SessionToolCall = {
  id?: string;
  function?: {
    name?: string;
    arguments?: string;
  };
};

export type SessionApiMessage = {
  role?: string;
  content?: unknown;
  timestamp?: string;
  thinking?: string;
  tool_calls?: SessionToolCall[];
  tool_call_id?: string;
  name?: string;
};

export type ImTimelineUserMessage = {
  id: string;
  role: 'user';
  content: string;
  html: string;
  timestamp?: string;
};

export type ImTimelineAssistantMessage = {
  id: string;
  role: 'assistant';
  content?: string;
  html?: string;
  thinkingHtml?: string;
  _thinkingRaw?: string;
  _thinkCollapsed?: boolean;
  _isThinking?: boolean;
  blocks: ChatBlock[];
  timestamp?: string;
};

export type ImTimelineVisualMessage = {
  id: string;
  role: 'visual_log';
  content: string;
  html: string;
  timestamp?: string;
};

export type ImTimelineDebugMessage = {
  id: string;
  role: 'debug_log';
  content: string;
  timestamp?: string;
  debugType?: string;
};

export type ImTimelineEntry =
  | ImTimelineUserMessage
  | ImTimelineAssistantMessage
  | ImTimelineVisualMessage
  | ImTimelineDebugMessage;

export type MarkdownRenderer = (markdown: string) => string;

function truncate(value: string, limit: number) {
  return value.length > limit ? `${value.slice(0, limit)}…` : value;
}

function describeUnknownPayload(value: unknown) {
  if (typeof value === 'string') return value;
  if (value == null) return '';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function extractUserContent(content: unknown) {
  if (!Array.isArray(content)) return describeUnknownPayload(content);

  const fileParts: string[] = [];
  let promptText = '';

  content.forEach((item) => {
    if (!item || typeof item !== 'object') return;
    const record = item as { type?: string; text?: string };
    if (record.type === 'image_url') {
      fileParts.push('[图片]');
      return;
    }
    if (record.type !== 'text') return;

    const text = String(record.text || '');
    const fileMatch = text.match(/^【文件内容：(.+?)】/);
    if (fileMatch) {
      fileParts.push(`[文件: ${fileMatch[1]}]`);
      return;
    }
    promptText = text.trim();
  });

  const parts: string[] = [];
  if (fileParts.length > 0) parts.push(fileParts.join(' '));
  if (promptText) parts.push(promptText);
  return parts.join('\n\n') || '(附件)';
}

function describeDebugLog(content: unknown): { text: string; debugType?: string } {
  if (typeof content !== 'string') {
    return { text: describeUnknownPayload(content) };
  }

  try {
    const payload = JSON.parse(content) as {
      type?: string;
      name?: string;
      params?: unknown;
      result?: unknown;
      content?: unknown;
      ts?: string;
    };

    if (payload.type === 'tool_call') {
      const paramsPreview = truncate(describeUnknownPayload(payload.params), 72);
      return {
        debugType: payload.type,
        text: `调用工具 ${payload.name || 'unknown'} · ${paramsPreview}`
      };
    }

    if (payload.type === 'tool_result') {
      return {
        debugType: payload.type,
        text: `工具返回 ${payload.name || 'unknown'} · ${truncate(describeUnknownPayload(payload.result), 96)}`
      };
    }

    if (payload.type === 'usage') {
      const usage = payload.content && typeof payload.content === 'object' ? payload.content : null;
      return {
        debugType: payload.type,
        text: usage ? `Token 使用 · ${truncate(describeUnknownPayload(usage), 96)}` : 'Token 使用'
      };
    }

    if (payload.type === 'status') {
      return {
        debugType: payload.type,
        text: `状态 · ${truncate(describeUnknownPayload(payload.content), 96)}`
      };
    }

    if (payload.type === 'message') {
      return {
        debugType: payload.type,
        text: `消息 · ${truncate(describeUnknownPayload(payload.content), 96)}`
      };
    }

    return {
      debugType: payload.type,
      text: truncate(describeUnknownPayload(payload.content ?? payload), 120)
    };
  } catch {
    return { text: truncate(content, 120) };
  }
}

export function buildImTimeline(
  rawMessages: SessionApiMessage[],
  renderMarkdown: MarkdownRenderer
): ImTimelineEntry[] {
  const entries: ImTimelineEntry[] = [];
  let lastAssistant: ImTimelineAssistantMessage | null = null;

  rawMessages.forEach((message, index) => {
    const role = message.role || '';
    const messageId = `im-${index}`;
    const timestamp = message.timestamp;

    if (role === 'debug_log') {
      const debug = describeDebugLog(message.content);
      entries.push({
        id: messageId,
        role: 'debug_log',
        content: debug.text,
        debugType: debug.debugType,
        timestamp
      });
      return;
    }

    if (role === 'user') {
      lastAssistant = null;
      const content = extractUserContent(message.content);
      entries.push({
        id: messageId,
        role: 'user',
        content,
        html: renderMarkdown(content),
        timestamp
      });
      return;
    }

    if (role === 'assistant') {
      if (!lastAssistant) {
        lastAssistant = {
          id: messageId,
          role: 'assistant',
          blocks: [],
          _thinkingRaw: '',
          _thinkCollapsed: true,
          timestamp
        };
        entries.push(lastAssistant);
      }

      if (message.thinking) {
        lastAssistant._thinkingRaw = [
          lastAssistant._thinkingRaw,
          message.thinking
        ]
          .filter(Boolean)
          .join('\n\n');
        lastAssistant.thinkingHtml = renderMarkdown(lastAssistant._thinkingRaw);
      }

      const content = typeof message.content === 'string' ? message.content : '';
      if (content) {
        lastAssistant.blocks.push({
          type: 'text',
          content,
          html: renderMarkdown(content)
        });
      }

      (message.tool_calls || []).forEach((toolCall) => {
        lastAssistant?.blocks.push({
          type: 'tool',
          id: toolCall.id || toolCall.function?.name,
          name: toolCall.function?.name || 'unknown',
          paramsStr: toolCall.function?.arguments || '{}',
          status: 'done',
          _collapsed: true,
          resultStr: undefined
        });
      });
      return;
    }

    if (role === 'tool') {
      if (!lastAssistant) return;
      const block = lastAssistant.blocks.find(
        (item) => item.id === message.tool_call_id || item.name === message.name
      );
      if (block) {
        block.resultStr = describeUnknownPayload(message.content);
      }
      return;
    }

    if (role === 'visual_log') {
      lastAssistant = null;
      const content = describeUnknownPayload(message.content);
      entries.push({
        id: messageId,
        role: 'visual_log',
        content,
        html: renderMarkdown(content),
        timestamp
      });
    }
  });

  return entries;
}
