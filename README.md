# 鼠鼠大王工具箱

为三角洲玩家提供的 Windows 桌面工具箱，侧边栏多标签页组织功能，支持明暗主题与自动更新。

> 本项目采用 [PolyForm Noncommercial License 1.0.0](LICENSE)：允许个人及非商业组织的使用、修改与分发；**商业用途须另行获得作者书面授权**（wzylscszyzh@163.com）。

## 功能

- **首页**：版本信息、最近更新、作者信息；右上角内嵌提示条（非弹窗）承载更新等面向用户的提示
- **牢区小游戏 · 骇爪美图**：拼图游戏，含计时器、图片来源与作者窗口、最快用时记录
- **鼠鼠工具 · 每日密码**：获取三角洲行动每日密码（tmini / shushu.fan 多来源，优先级可在设置中调整），带日期/更新时间标注与缓存
- **鼠鼠工具 · 改枪码**：
  - **主播推荐**：全量同步 shushu.fan 主播改枪码，四维筛选（武器类型 / 枪械 / 作者 / 标签）、翻页、懒加载图片与磁盘/内存双层缓存
  - **我的改枪码**：保存自己的改枪码，枪械名称与武器类型由改枪码自动解析带出，支持筛选与复制
- **自动更新**：启动时检查 GitHub Releases，模式可选（自动更新 / 下载但不自动安装 / 新版本提示 / 关闭），支持断点续传与镜像降级
- **主题切换**：浅色 / 深色（`resources/themes/`，QSS 样式表）
- **设置持久化**：设置保存至 `data/settings.json`，重启后沿用（文件不入版本库）

## 环境要求

- Python >= 3.12
- Windows（GUI 基于 PySide6 / Qt）

## 快速开始

```powershell
# 1. 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 2. 安装项目（可编辑模式 + 开发依赖）
pip install -e ".[dev]"

# 3. 启动程序
双击 `start.bat`（无控制台窗口，推荐），或命令行运行：
python -m deltaforcebox.main

# 4. 运行测试 / 代码检查
pytest
ruff check .
```

## 目录结构

```
DeltaForceBox/
├── resources/
│   ├── config/                 # 隐藏配置（自动更新镜像、拼图碎片数等，可手改）
│   ├── i18n/                   # 中文文案 JSON
│   └── themes/                 # 明暗主题 QSS
├── src/deltaforcebox/
│   ├── core/                   # 路径 / 设置 / i18n / 主题 / 自动更新 / 数据核心
│   ├── widgets/                # 主窗口、提示条与功能页面
│   │   └── pages/              # 首页 / 每日密码 / 改枪码 / 我的改枪码 / 设置
│   ├── games/                  # 小游戏模块（骇爪美图拼图）
│   ├── app.py                  # 应用装配
│   └── main.py                 # 程序入口
├── tests/                      # 单元测试与 GUI 冒烟测试
├── docs/ scripts/              # 文档 / 工具脚本
├── data/                       # 运行时数据（不入版本库）
├── pyproject.toml
├── LICENSE
└── README.md
```
