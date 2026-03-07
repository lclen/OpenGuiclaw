#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
桌面文件自动整理脚本
功能：按文件类型自动分类桌面文件到对应文件夹
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

# 桌面路径
DESKTOP = Path.home() / "Desktop"

# 文件类型映射（扩展名 → 文件夹名）
FILE_CATEGORIES = {
    # 文档
    '文档': ['.pdf', '.doc', '.docx', '.txt', '.md', '.rtf', '.odt', '.wps'],
    # 表格
    '表格': ['.xls', '.xlsx', '.csv', '.tsv', '.ods'],
    # 图片
    '图片': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico'],
    # 视频
    '视频': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv'],
    # 音频
    '音频': ['.mp3', '.wav', '.flac', '.aac', '.wma'],
    # 压缩包
    '压缩包': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'],
    # 安装包
    '安装包': ['.exe', '.msi', '.dmg', '.pkg', '.apk', '.jar', '.vsix'],
    # 代码
    '代码': ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.cs', '.go', '.rs', '.html', '.css'],
    # 快捷方式
    '快捷方式': ['.lnk', '.url'],
    # 字体
    '字体': ['.ttf', '.otf', '.fon'],
}

# 需要跳过的文件和文件夹
SKIP_ITEMS = [
    'Desktop.ini',
    '$RECYCLE.BIN',
    'System Volume Information',
    '快捷方式',
    '文档',
    '表格',
    '图片',
    '视频',
    '音频',
    '压缩包',
    '安装包',
    '代码',
    '字体',
]

def get_category(file_path: Path) -> str:
    """根据文件扩展名返回分类文件夹名称"""
    ext = file_path.suffix.lower()
    for category, extensions in FILE_CATEGORIES.items():
        if ext in extensions:
            return category
    return '其他'  # 未知类型

def organize_desktop(dry_run=False):
    """
    整理桌面文件
    
    Args:
        dry_run: 如果为 True，只显示将要执行的操作，不实际移动
    """
    print(f"开始整理桌面：{DESKTOP}")
    print(f"{' [预览模式]' if dry_run else ' [执行模式]'}\n")
    
    # 统计
    stats = {'moved': 0, 'skipped': 0, 'errors': 0}
    moved_files = []
    
    # 遍历桌面所有文件
    for item in DESKTOP.iterdir():
        # 跳过文件夹和特殊文件
        if item.is_dir() or item.name in SKIP_ITEMS:
            stats['skipped'] += 1
            continue
        
        try:
            # 获取分类
            category = get_category(item)
            target_folder = DESKTOP / category
            
            # 创建目标文件夹（如果不存在）
            if not dry_run and not target_folder.exists():
                target_folder.mkdir(parents=True, exist_ok=True)
            
            # 目标路径
            target_path = target_folder / item.name
            
            # 处理重名文件
            if target_path.exists():
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                target_path = target_folder / f"{item.stem}_{timestamp}{item.suffix}"
            
            # 移动文件
            if dry_run:
                print(f"  [预计移动]：{item.name} -> {category}/")
            else:
                shutil.move(str(item), str(target_path))
                print(f"  [已移动]：{item.name} -> {category}/")
                moved_files.append((item.name, category))
            
            stats['moved'] += 1
            
        except Exception as e:
            print(f"  [错误]：{item.name} - {str(e)}")
            stats['errors'] += 1
    
    # 输出统计
    print("\n" + "="*50)
    print(f"整理完成统计：")
    print(f"  成功移动：{stats['moved']} 个文件")
    print(f"  跳过：{stats['skipped']} 个（文件夹/系统文件）")
    print(f"  错误：{stats['errors']} 个")
    
    if moved_files and not dry_run:
        print(f"\n分类结果：")
        # 按文件夹分组统计
        from collections import Counter
        folder_counts = Counter([folder for _, folder in moved_files])
        for folder, count in folder_counts.most_common():
            print(f"  {folder}/: {count} 个文件")
    
    return stats

if __name__ == "__main__":
    import sys
    
    # 命令行参数：--dry-run 预览模式
    dry_run = "--dry-run" in sys.argv
    
    organize_desktop(dry_run=dry_run)
    
    if dry_run:
        print("\n提示：确认无误后，运行以下命令执行实际整理：")
        print(f"   python {sys.argv[0]}")
