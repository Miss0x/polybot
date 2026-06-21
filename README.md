# Polybot

Polybot 是一个面向 Polymarket 垂直事件板块的概率分析与偏离告警系统。

## 当前阶段
当前仓库已完成第一阶段基础骨架：
- 项目目录结构
- YAML + `.env` 配置加载
- SQLite 初始化脚本
- Polymarket 客户端
- 美伊冲突市场扫描器
- `run_scan.py` 手动扫描入口

## 快速开始
1. 复制环境变量模板：
   - 将 `.env.example` 复制为 `.env`
2. 安装依赖：
   - `pip install -r requirements.txt`
3. 初始化数据库：
   - `python scripts/setup_db.py`
4. 运行市场扫描：
   - `python scripts/run_scan.py`

## 目录说明
- `polybot/collect/`：市场采集与扫描
- `polybot/storage/`：数据库连接、模型与仓储
- `config/`：应用配置与板块配置
- `scripts/`：初始化、测试与手动运行脚本
