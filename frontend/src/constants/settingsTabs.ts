/**
 * settingsTabs.ts — Settings tab 元数据单一来源
 *
 * workspace-logic.js 里的 settingsTabs 数组与此保持一致。
 * React 组件（SettingsNav、SettingsMainHeader）统一从这里导入，
 * 不再各自维护副本。
 */
export const SETTINGS_TABS = [
  { id: 'models',       cfgTab: 'models',     title: '模型',     description: '管理聊天、嵌入和工具调用的主模型端点' },
  { id: 'agent',        cfgTab: 'agent_sys',  title: 'Agent',    description: '调整代理行为、系统提示与运行偏好' },
  { id: 'identity',     cfgTab: 'identity',   title: '身份',     description: '维护角色设定、记忆摘要与个性化配置' },
  { id: 'integrations', cfgTab: 'channels',   title: '集成',     description: '配置 IM 通道、服务连接与外部桥接' },
  { id: 'diagnostics',  cfgTab: 'system',     title: '诊断',     description: '查看环境信息、运行状态与问题排查项' },
  { id: 'memory',       cfgTab: 'memory',     title: '记忆管理',  description: '查看、编辑和清理 AI 长期记忆条目' },
  { id: 'mcp',          cfgTab: 'mcp',        title: 'MCP 工具', description: '配置 Model Context Protocol 外部工具服务器' },
  { id: 'archived',     cfgTab: null,         title: '归档',     description: '整理已归档的工作区与线程' },
] as const;

export type SettingsTabId = typeof SETTINGS_TABS[number]['id'];

export function getTabMeta(tabId: string) {
  return SETTINGS_TABS.find((t) => t.id === tabId) ?? SETTINGS_TABS[0];
}
