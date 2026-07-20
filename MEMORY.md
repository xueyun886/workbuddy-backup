# User Memory

## ResearchStudio 技能套件

用户安装了微软研究院开源的 ResearchStudio AI 科研辅助技能套件（MIT 许可证）。
- **安装位置**：`~/.workbuddy/skills/`（用户级）
- **8 个技能**：idea-spark, paper-search, scoop-check (Idea) / paper2assets, paper2poster, paper2video, paper2blog, paper2reel (Reel)
- **Python 环境**：WorkBuddy 隔离 venv (`envs/default`, Python 3.13.12)
- **路径适配**：已从 Claude Code/Codex 路径约定适配为 WorkBuddy 路径
- **已知限制**：editdistance 纯 Python fallback；Playwright Chromium 未装浏览器二进制；poppler/LibreOffice 未安装
- **使用指南**：`~/.workbuddy/skills/researchstudio-guide/README.md`
