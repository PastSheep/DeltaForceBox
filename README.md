# 三角洲行动工具箱（Delta Force Box）

为三角洲玩家提供的桌面工具箱，采用侧边栏多标签页形式组织功能，支持中英文切换与明暗主题。

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

## 功能

- **侧边栏多标签页**：首页 / 设置，便于扩展新功能
- **语言切换**：中文 / English（资源文件 `resources/i18n/`，新增翻译直接编辑 JSON）
- **主题切换**：浅色 / 深色（`resources/themes/`，QSS 样式表）

## 性能设计

- Qt 事件驱动，空闲时无轮询、CPU 占用 ≈ 0，不影响游戏运行
- 未引入 Web 内核（无 QWebEngine/Electron），内存占用约几十 MB 量级

## 目录结构

```
DeltaForceBox/
├── .venv/                      # Python 虚拟环境
├── resources/
│   ├── i18n/                   # 中英文翻译 JSON
│   └── themes/                 # 明暗主题 QSS
├── src/deltaforcebox/
│   ├── core/                   # 路径 / 国际化 / 主题
│   ├── widgets/                # 主窗口与功能页面
│   │   └── pages/              # 首页 / 设置页
│   ├── games/                  # 游戏功能模块（待开发）
│   ├── app.py                  # 应用装配
│   └── main.py                 # 程序入口
├── tests/                      # 单元测试与 GUI 冒烟测试
├── config/ docs/ scripts/ data/
├── pyproject.toml
└── README.md
```
