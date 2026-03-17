#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OpenGuiclaw 初始化测试脚本
检查核心模块是否可以正常导入和初始化
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_imports():
    """测试核心模块导入"""
    print("=" * 60)
    print("OpenGuiclaw 初始化测试")
    print("=" * 60)
    print()
    
    tests = [
        ("配置模块", "from core import bootstrap"),
        ("Agent 核心", "from core.agent import Agent"),
        ("Web 服务器", "from core.server import app"),
        ("会话管理", "from core.session import SessionManager"),
        ("记忆系统", "from core.memory import MemoryManager"),
        ("向量存储", "from core.vector_memory import VectorStore"),
        ("知识图谱", "from core.knowledge_graph import KnowledgeGraph"),
        ("技能管理", "from core.skills import SkillManager"),
        ("插件管理", "from core.plugin_manager import PluginManager"),
        ("人设管理", "from core.identity_manager import IdentityManager"),
        ("视觉感知", "from core.context import ContextManager"),
        ("自我进化", "from core.self_evolution import SelfEvolution"),
    ]
    
    passed = 0
    failed = 0
    
    for name, import_stmt in tests:
        try:
            exec(import_stmt)
            print(f"✓ {name:20s} ... OK")
            passed += 1
        except Exception as e:
            print(f"✗ {name:20s} ... FAILED: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    return failed == 0

def test_config():
    """测试配置文件"""
    print()
    print("检查配置文件...")
    
    config_path = project_root / "config.json"
    if not config_path.exists():
        print("✗ config.json 不存在，请从 config.json.example 复制")
        return False
    
    try:
        import json
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 检查必要的配置项
        required_keys = ['api', 'chat_endpoints', 'active_chat_endpoint_id']
        missing = [key for key in required_keys if key not in config]
        
        if missing:
            print(f"✗ 配置文件缺少必要项: {', '.join(missing)}")
            return False
        
        print("✓ 配置文件检查通过")
        return True
    except Exception as e:
        print(f"✗ 配置文件读取失败: {e}")
        return False

def test_data_dirs():
    """测试数据目录"""
    print()
    print("检查数据目录...")
    
    data_root = project_root / "data"
    required_dirs = [
        "sessions",
        "memory",
        "diary",
        "journals",
        "identities",
        "plans",
        "scheduler",
        "screenshots"
    ]
    
    all_exist = True
    for dir_name in required_dirs:
        dir_path = data_root / dir_name
        if dir_path.exists():
            print(f"✓ data/{dir_name}")
        else:
            print(f"✗ data/{dir_name} 不存在")
            all_exist = False
    
    return all_exist

if __name__ == "__main__":
    print()
    
    # 运行测试
    imports_ok = test_imports()
    config_ok = test_config()
    dirs_ok = test_data_dirs()
    
    print()
    if imports_ok and config_ok and dirs_ok:
        print("🎉 所有测试通过！OpenGuiclaw 已准备就绪。")
        print()
        print("启动方式:")
        print("  - Web UI:  python -m uvicorn core.server:app --host 127.0.0.1 --port 8010")
        print("  - CLI:     python main.py")
        print("  - GUI:     python run_gui.py")
        print()
        sys.exit(0)
    else:
        print("❌ 部分测试失败，请检查上述错误信息。")
        sys.exit(1)
