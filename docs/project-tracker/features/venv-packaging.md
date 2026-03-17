# Feature Note: venv-packaging

- feature_id: venv-packaging
- title: venv 打包方案
- updated_at: 2026-03-13T13:16:56+08:00
- status: in_progress

## 背景

将项目打包为可分发的 Windows 安装包。当前有两条路线：PyInstaller（已有 .spec 文件）和 venv + Inno Setup（installer.iss）。有独立 spec：.kiro/specs/venv-packaging/。

## 当前实现摘要

build_exe.bat 调用 PyInstaller；installer.iss 定义 Inno Setup 安装包配置；.kiro/specs/venv-packaging/ 下有完整需求和任务清单。

## 关键文件

- installer.iss
- build_exe.bat
- .kiro/specs/venv-packaging/

## 风险与已知问题

venv 方案依赖 Python 环境，PyInstaller 方案体积较大

## 后续建议

推进 venv-packaging spec 中的剩余任务

## 正式文档

-
