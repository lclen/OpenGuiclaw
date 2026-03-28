import { buildImTimeline, type SessionApiMessage } from './imSessionTransform';

function renderMarkdown(value: string) {
  return `<p>${value}</p>`;
}

describe('buildImTimeline', () => {
  it('keeps debug logs visible while attaching tool results to assistant blocks', () => {
    const messages: SessionApiMessage[] = [
      { role: 'user', content: '你好', timestamp: '2026-03-29 09:00:00' },
      {
        role: 'assistant',
        content: '我来帮你查询',
        thinking: '先分析需求',
        tool_calls: [
          {
            id: 'tool-1',
            function: {
              name: 'get_weather',
              arguments: '{"city":"Nanjing"}'
            }
          }
        ],
        timestamp: '2026-03-29 09:00:02'
      },
      {
        role: 'debug_log',
        content: '{"type":"status","content":"思考中..."}',
        timestamp: '2026-03-29 09:00:03'
      },
      {
        role: 'tool',
        tool_call_id: 'tool-1',
        name: 'get_weather',
        content: '晴 24°C',
        timestamp: '2026-03-29 09:00:04'
      }
    ];

    const timeline = buildImTimeline(messages, renderMarkdown);

    expect(timeline).toHaveLength(3);
    expect(timeline[0]).toMatchObject({ role: 'user', content: '你好' });
    expect(timeline[1].role).toBe('assistant');
    expect(timeline[2]).toMatchObject({ role: 'debug_log', content: '状态 · 思考中...' });

    if (timeline[1].role !== 'assistant') {
      throw new Error('assistant entry missing');
    }

    expect(timeline[1].thinkingHtml).toContain('先分析需求');
    expect(timeline[1].blocks).toHaveLength(2);
    expect(timeline[1].blocks[0]).toMatchObject({ type: 'text', content: '我来帮你查询' });
    expect(timeline[1].blocks[1]).toMatchObject({
      type: 'tool',
      name: 'get_weather',
      paramsStr: '{"city":"Nanjing"}',
      resultStr: '晴 24°C'
    });
  });

  it('reconstructs multimodal user content into readable text', () => {
    const timeline = buildImTimeline(
      [
        {
          role: 'user',
          content: [
            { type: 'image_url', image_url: { url: 'data:image/png;base64,xxx' } },
            { type: 'text', text: '【文件内容：readme.md】\n```\nhello\n```' },
            { type: 'text', text: '请总结一下' }
          ]
        }
      ],
      renderMarkdown
    );

    expect(timeline).toHaveLength(1);
    expect(timeline[0]).toMatchObject({
      role: 'user',
      content: '[图片] [文件: readme.md]\n\n请总结一下'
    });
  });
});
