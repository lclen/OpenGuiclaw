# Feature Note: memory-system

- feature_id: memory-system
- title: 记忆系统
- updated_at: 2026-03-13T13:15:24+08:00
- status: in_progress

## 背景

三层记忆架构：短期会话历史（session.py）+ 长期记忆提取（memory_extractor.py）+ 向量语义检索 RAG（vector_memory.py）+ 知识图谱（knowledge_graph.py）。每日整合由 daily_consolidator.py 负责。

## 当前实现摘要

memory.py 管理长期记忆读写；vector_memory.py 用 numpy 做内存中 cosine 相似度检索，嵌入模型 text-embedding-v4；knowledge_graph.py 维护实体关系图；memory_extractor.py 从对话中提取记忆条目。

## 关键文件

- core/memory.py
- core/vector_memory.py
- core/knowledge_graph.py
- core/memory_extractor.py
- core/daily_consolidator.py

## 风险与已知问题

向量存储全在内存，数据量大时性能下降

## 后续建议

向量检索性能优化；memory-management spec 待推进

## 正式文档

docs/modules/memory.md
