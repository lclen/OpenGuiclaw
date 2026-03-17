# Feature Note: im-channels

- feature_id: im-channels
- title: IM 频道接入
- updated_at: 2026-03-13T13:16:49+08:00
- status: in_progress

## 背景

支持多 IM 平台接入：DingTalk、Feishu、Telegram。通过统一的 gateway 层路由消息，各平台实现独立适配器。

## 当前实现摘要

core/channels/gateway.py 统一消息路由；core/channels/base.py 定义适配器基类；adapters/ 下有 dingtalk.py、feishu.py、telegram.py 三个适配器。Web 路由通过 core/routes/im.py 暴露 webhook 端点。

## 关键文件

- core/channels/gateway.py
- core/channels/adapters/
- core/routes/im.py

## 风险与已知问题

各平台 webhook 签名验证逻辑差异较大，需分别测试

## 后续建议

完善 Feishu、Telegram 适配器测试；补充 WeCom 适配器

## 正式文档

docs/modules/channels.md
