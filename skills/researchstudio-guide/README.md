# ResearchStudio 技能套件 — 安装与使用指南

> 微软研究院开源 AI 科研辅助技能套件（MIT 许可证），已适配 WorkBuddy 技能系统。
> 安装位置：`~/.workbuddy/skills/`（用户级）
> 安装日期：2026-07-20

---

## 一、技能总览

### ResearchStudio-Idea（科研第一公里：从研究方向到经得起审稿的 Idea）

| 技能 | 目录 | 触发词 | 功能 |
|------|------|--------|------|
| **idea-spark** | `idea_spark/` | "research idea", "novelty analysis", "bottleneck diagnosis" | 5 阶段构思流水线：文献奠基→瓶颈识别→选择+生成→质量审计→扩展+渲染 |
| **paper-search** | `paper_search/` | "find papers", "related work", "prior art" | 多源文献检索（arXiv/DBLP/OpenAlex/OpenReview/Semantic Scholar/Crossref） |
| **scoop-check** | `scoop_check/` | "verify novelty", "check if scooped", "prior art" | 7 步新颖性审计，4 轴评估，5 级判定 |

### ResearchStudio-Reel（科研最后一公里：从论文 PDF 到海报/视频/博客/Reel）

| 技能 | 目录 | 触发词 | 功能 |
|------|------|--------|------|
| **paper2assets** | `paper2assets/` | "extract paper", "build paper assets" | 论文 PDF → 标准化资源包（文本/图表/元数据/Logo/QR码） |
| **paper2poster** | `paper2poster/` | "render poster", "make poster from paper" | 资源包 → HTML 学术海报 → PDF/PNG + 可编辑 PPTX |
| **paper2video** | `paper2video/` | "paper to video", "narrated video" | 论文/资源包/PPT → 带旁白的 MP4 视频 |
| **paper2blog** | `paper2blog/` | "paper to blog", "bilingual editorial" | 论文 → 中英双语编辑包（公众号 + 英文博客） |
| **paper2reel** | `paper2reel/` | "interactive reel", "paper viewer" | 对齐海报+幻灯片+视频+博客 → 交互式 HTML 查看器 |

---

## 二、Python 环境

所有脚本使用 WorkBuddy 隔离 venv 执行：

```
Python: C:\Users\ZWW\.workbuddy\binaries\python\envs\default\Scripts\python.exe
版本: 3.13.12
```

### 已安装的 Python 包

| 包 | 版本 | 用途 |
|----|------|------|
| feedparser | 6.0.12 | arXiv RSS 检索 |
| openreview-py | 2.3.1 | OpenReview 检索 |
| scholarly | 1.7.11 | Google Scholar 检索 |
| pymupdf (fitz) | 1.28.0 | PDF 文本/图表提取 |
| qrcode | 8.2 | QR 码生成 |
| edge-tts | 7.2.8 | TTS 语音合成 |
| imageio-ffmpeg | 0.6.0 | 视频渲染（内置 ffmpeg 二进制） |
| playwright | 1.61.0 | 浏览器自动化 |
| pyphen | 0.17.2 | 断词处理（海报布局） |
| beautifulsoup4 | 4.15.0 | HTML 解析 |
| python-docx | 1.2.0 | Word 文档生成 |
| python-pptx | 1.0.2 | PPTX 生成 |
| lxml | 6.1.1 | XML/HTML 处理 |
| numpy | 2.5.0 | 数值计算 |
| pillow | 12.2.0 | 图像处理 |
| requests | 2.34.2 | HTTP 请求 |

### 已知限制

- **editdistance**：需 MSVC 编译，已用纯 Python 替代模块（功能正常，性能略低）
- **Playwright Chromium**：Python 包已安装，但浏览器二进制需单独安装：
  ```
  "C:\Users\ZWW\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -m playwright install chromium
  ```

---

## 三、系统依赖状态

| 依赖 | 状态 | 替代方案 |
|------|------|---------|
| ffmpeg | ✅ imageio-ffmpeg 内置 | `imageio_ffmpeg.get_ffmpeg_exe()` |
| poppler (pdftoppm/pdftotext) | ❌ 未安装 | pymupdf 可替代 PDF 文本/图表提取 |
| LibreOffice (soffice) | ❌ 未安装 | python-pptx 可生成基础 PPTX |
| Playwright Chromium | ❌ 未安装 | 需运行 `playwright install chromium` |
| LaTeX (pdflatex) | ❌ 未安装（可选） | 仅 LaTeX 海报模板需要 |

---

## 四、路径适配说明

原始 SKILL.md 使用 Claude Code / Codex CLI 的路径约定，已全部适配为 WorkBuddy 路径：

| 原始路径 | WorkBuddy 路径 |
|---------|---------------|
| `~/.claude/skills/<skill>/` | `~/.workbuddy/skills/<skill>/` |
| `${CLAUDE_PROJECT_DIR}/skills/<skill>/` | `~/.workbuddy/skills/<skill>/` |
| `${CLAUDE_PROJECT_DIR}/allinone.md` | `./allinone.md` |
| `${CLAUDE_PROJECT_DIR}/papers/` | `./papers/` |
| `skills/paper2video/scripts/` | `~/.workbuddy/skills/paper2video/scripts/` |

### Python 调用方式

SKILL.md 中的 `python3` 命令需替换为完整路径：
```
python3 → C:\Users\ZWW\.workbuddy\binaries\python\envs\default\Scripts\python.exe
```

---

## 五、典型工作流

### 工作流 A：从研究方向到 Research Idea

```
用户："我想研究 XXX 方向，帮我找一个有创新性的研究 idea"

1. paper-search  → 检索相关文献，建立文献基础
2. idea-spark    → 5 阶段流水线生成经得起审稿的 Idea
3. scoop-check   → 验证 Idea 的新颖性，确保未被 scoop
```

### 工作流 B：从论文 PDF 到全套传播材料

```
用户："把这篇论文 PDF 做成海报/视频/博客"

1. paper2assets  → 提取论文资源（文本/图表/元数据）
2. paper2poster  → 生成 HTML 学术海报 → PDF/PNG
3. paper2video   → 生成带旁白的 MP4 视频
4. paper2blog    → 生成中英双语编辑包
5. paper2reel    → 对齐所有产物到交互式查看器
```

### 工作流 C：单独使用文献检索

```
用户："帮我找 2023-2025 年关于 XXX 的论文"

paper-search → 多源并发检索 → 去重+排序 → 输出统一列表
```

---

## 六、技能间依赖关系

```
ResearchStudio-Idea:
  paper-search ← scoop-check (依赖)
  idea-spark (独立，但 Phase 0 使用内置检索脚本)

ResearchStudio-Reel:
  paper2assets ← paper2poster (依赖资源包)
  paper2assets ← paper2video (依赖资源包)
  paper2assets ← paper2blog  (依赖资源包)
  paper2poster ← paper2reel (依赖海报输出)
  paper2video  ← paper2reel (依赖视频输出)
  paper2blog   ← paper2reel (依赖博客输出)

跨套件:
  paper2video → ppt-master (外部依赖，WorkBuddy 已安装)
```

---

## 七、技术架构要点

### idea-spark 子 Agent 隔离
- 每阶段独立上下文，父上下文 ≤30k token
- rc=10/11 哨兵握手协议
- 磁盘输出契约：`$RUN_DIR/<phase>/<phase>_output.json`

### paper2assets 共享输出契约 (v2-assets layout)
```
<outdir>/
  manifest.json
  assets/
    meta/
      paper_spec.md     # 9-section 结构化论文摘要
      text.txt          # 全文
      captions.json     # 图表标题
      figures.json      # 图表清单
      metadata.json     # 论文元数据
      sections.json     # 分节映射
      narration.json    # 旁白脚本
    figures/*.png        # 清洗后的图表
    logos/               # 机构 Logo
    qr/                  # QR 码
    audio/*.mp3          # TTS 音频
```

### paper2video 两条路由
- **Route A**：paper.pdf → paper2assets → deck (ppt-master) → audio → render → subtitles
- **Route B**：已有 ppt-master deck → notes_to_script → audio → render → subtitles

---

## 八、注意事项

1. **Python 版本**：使用 WorkBuddy 隔离 venv（Python 3.13.12），不污染系统环境
2. **网络访问**：文献检索（arXiv/OpenReview 等）需要网络连接
3. **arXiv 限流**：arXiv 请求间隔 ≥4s（arxiv_search_throttle.lock）
4. **TTS 服务**：edge-tts 使用微软免费 TTS 服务，需网络连接
5. **PPTX 导出**：paper2poster 的 HTML→PPTX 转换依赖 html2pptx 子技能
6. **视频渲染**：imageio-ffmpeg 内置 ffmpeg 二进制，无需单独安装系统级 ffmpeg
7. **海报渲染**：paper2poster 的 HTML→PDF 渲染需要 Playwright Chromium（当前未安装）
