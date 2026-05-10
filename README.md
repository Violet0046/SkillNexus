# SkillNexus

**企业级 Skill 共享与自进化平台**

SkillNexus 是从 OpenSpace 多智能体框架中提取并重新设计的技能管理系统。它将技能定义为结构化知识文档（SKILL.md），支持本地执行分析、智能检索、以及三种自进化机制（修复、派生、捕获），并提供可视化 Web 界面。

---

## 目录

- [核心特性](#核心特性)
- [架构概览](#架构概览)
- [项目结构](#项目结构)
- [技能格式（SKILL.md）](#技能格式skillmd)
- [三大进化机制](#三大进化机制)
- [智能检索流程](#智能检索流程)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [API 接口](#api-接口)
- [前端页面](#前端页面)
- [数据库设计](#数据库设计)
- [与 OpenSpace 的差异](#与-openspace-的差异)
- [后续规划](#后续规划)

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **结构化技能文档** | 技能以 `SKILL.md` 格式存储，YAML frontmatter + Markdown 正文，可同时承载知识文档和可执行脚本引用 |
| **本地执行分析** | 任务执行后自动分析轨迹，评估技能质量，生成进化建议 |
| **自进化系统** | FIX（修复）、DERIVED（派生增强）、CAPTURED（捕获新模式）三种进化路径 |
| **混合检索** | BM25 词法检索 + Embedding 语义检索的两阶段排序，支持优雅降级 |
| **版本溯源** | 基于 DAG 的技能血缘关系，记录每次进化的父技能、变更摘要和内容差异 |
| **质量追踪** | 自动记录技能的选中次数、应用次数、完成次数、回退次数，计算各项成功率 |
| **Web 可视化** | React 前端提供技能浏览、分析查看、进化触发等功能 |

---

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                     前端 (React + Vite)                  │
│  Dashboard │ Skills │ Analysis │ Evolution               │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP REST
┌──────────────────────▼──────────────────────────────────┐
│                  API 层 (FastAPI)                        │
│  /api/skills │ /api/analysis │ /api/evolution            │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                    核心引擎层                             │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Registry │  │ Ranker   │  │ Analyzer │              │
│  │ 技能发现  │  │ 混合检索  │  │ 执行分析  │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       │              │              │                    │
│  ┌────▼──────────────▼──────────────▼─────┐             │
│  │            SkillStore (SQLite)          │             │
│  │  records │ analyses │ lineage │ metrics │             │
│  └────────────────────────────────────────┘             │
│                       │                                  │
│  ┌────────────────────▼─────────────────────┐           │
│  │            Evolver (进化引擎)              │           │
│  │  FIX │ DERIVED │ CAPTURED                 │           │
│  └──────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              LLM 层 (LiteLLM 多模型支持)                 │
│          OpenRouter / OpenAI / 自定义端点                 │
└─────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
SkillNexus/
├── skillnexus/                    # Python 后端包
│   ├── config/
│   │   ├── constants.py           # 项目根目录、日志级别常量
│   │   ├── settings.py            # 配置数据类（从 JSON + 环境变量加载）
│   │   └── settings.json          # 默认配置文件
│   ├── core/
│   │   ├── types.py               # 所有数据模型定义
│   │   ├── skill_utils.py         # Frontmatter 解析、安全检查
│   │   ├── fuzzy_match.py         # 6 级模糊匹配（SEARCH/REPLACE 用）
│   │   ├── patch.py               # 多文件补丁应用（FULL/DIFF/PATCH）
│   │   ├── conversation_formatter.py  # 对话日志格式化
│   │   ├── store.py               # SQLite 持久化层（WAL 模式）
│   │   ├── skill_ranker.py        # BM25 + Embedding 混合排序
│   │   ├── registry.py            # 技能发现、LLM 选择、上下文注入
│   │   ├── analyzer.py            # 执行后分析（单次 LLM 调用）
│   │   ├── evolver.py             # FIX/DERIVED/CAPTURED 进化引擎
│   │   └── retrieve_skill.py      # 执行中技能检索
│   ├── llm/
│   │   └── client.py              # LiteLLM 客户端（纯文本，无工具执行）
│   ├── prompts/
│   │   └── skill_engine_prompts.py # 所有 Prompt 模板
│   ├── api/
│   │   ├── app.py                 # FastAPI 应用（含生命周期管理）
│   │   ├── dependencies.py        # 单例依赖注入
│   │   └── routes/
│   │       ├── skills.py          # 技能 CRUD + 检索接口
│   │       ├── analysis.py        # 分析接口
│   │       └── evolution.py       # 进化接口
│   └── utils/
│       └── logging.py             # 线程安全日志（带颜色支持）
├── frontend/                      # React 前端
│   ├── src/
│   │   ├── api/client.ts          # 类型安全的 API 客户端
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx      # 仪表盘（统计、Top 技能、候选）
│   │   │   ├── SkillList.tsx      # 技能列表（可筛选、带质量指标）
│   │   │   ├── SkillDetail.tsx    # 技能详情（内容/分析/血缘）
│   │   │   ├── AnalysisList.tsx   # 进化候选列表
│   │   │   └── EvolutionPage.tsx  # 手动进化触发 + 指标检查
│   │   ├── App.tsx                # 路由 + 侧边栏导航
│   │   └── main.tsx               # 入口
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── run_server.py                  # 后端启动入口
├── requirements.txt               # Python 依赖
└── pyproject.toml                 # 项目元数据
```

---

## 技能格式（SKILL.md）

每个技能是一个目录，核心文件为 `SKILL.md`：

```markdown
---
name: pdf-report-generation
description: 生成包含图表和表格的专业 PDF 报告
---

# PDF 报告生成指南

## 前置条件
- 安装 `reportlab` 和 `matplotlib`

## 步骤

1. 准备数据源（CSV / JSON / 数据库查询）
2. 使用 matplotlib 生成图表并保存为 PNG
3. 使用 reportlab 组装 PDF：
   - 添加标题页
   - 插入图表
   - 添加数据表格
4. 输出到指定路径

## 常见问题
- 中文字体：使用 `SimHei` 或 `NotoSansCJK`
- 大文件：分页处理，避免内存溢出
```

### 技能标识

每个技能目录下有 `.skill_id` 侧面文件，存储持久化唯一标识：

- 导入技能：`{name}__imp_{uuid_hex[:8]}`
- 进化技能：`{name}__v{generation}_{uuid_hex[:8]}`

ID 首次发现时自动生成，后续从文件读取，支持目录移动和机器迁移。

---

## 三大进化机制

### 1. FIX（修复）

**触发条件**：技能被选中但未能完成任务，或回退率过高。

**行为**：原地修复同一目录下的 SKILL.md，生成新的版本记录，技能名称不变。

```
原始技能 gen0 → FIX → 修复后 gen1 → FIX → 修复后 gen2
```

**示例场景**：技能中的 API 地址过期、命令参数变更、缺少错误处理说明。

### 2. DERIVED（派生增强）

**触发条件**：技能基本可用但效果一般，存在改进空间。

**行为**：在新目录创建增强版本，原始技能保持不变。支持多父技能合并。

```
技能A gen1 ──┐
              ├── DERIVED → 技能A增强 gen2（新目录）
技能B gen0 ──┘
```

**示例场景**：在现有技能基础上增加异常处理、添加替代方案、合并两个互补技能。

### 3. CAPTURED（捕获新模式）

**触发条件**：智能体在没有技能指导的情况下成功解决了任务，且方案可复用。

**行为**：从执行轨迹中提取模式，创建全新的技能文档。

```
任务执行（无技能）→ 分析发现可复用模式 → CAPTURED → 新技能 gen0
```

### 进化流程

```
任务执行 → 执行分析 → 进化建议 → LLM 确认 → 生成编辑 → 补丁应用 → 验证 → 持久化
```

每次进化都有重试机制（最多 3 次），失败时将错误反馈给 LLM 进行修正。

---

## 智能检索流程

当技能数量超过阈值（默认 10 个）时，检索采用两阶段流水线：

```
用户任务描述
     │
     ▼
┌─────────────────────┐
│  Stage 1: BM25 粗排  │  ← 快速词法匹配，候选集 × 3
│  (rank_bm25 库)      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Stage 2: Embedding  │  ← 语义重排，返回 Top-K
│  (text-embedding-3)  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Stage 3: LLM 精选   │  ← Plan-then-Select 模式
│  (Claude / GPT)      │
└─────────────────────┘
```

**降级策略**：
- 无 `rank_bm25` 库 → 简单 token 重叠
- 无 Embedding API Key → 仅 BM25
- BM25 全部零分 → 全量 Embedding
- 全部失败 → 返回前 K 个候选

---

## 快速开始

### 环境要求

- Python >= 3.10
- Node.js >= 18
- LLM API Key（OpenRouter / OpenAI / 其他兼容端点）

### 1. 安装后端依赖

```bash
cd SkillNexus
pip install -r requirements.txt
```

### 2. 配置

编辑 `skillnexus/config/settings.json`：

```json
{
  "log_level": "INFO",
  "skills": {
    "enabled": true,
    "skill_dirs": ["./skills"],
    "max_select": 2
  },
  "llm": {
    "model": "openrouter/anthropic/claude-sonnet-4.5",
    "enable_thinking": false,
    "max_retries": 3,
    "timeout": 120.0
  }
}
```

或使用环境变量覆盖：

```bash
export SKILLNEXUS_LLM_MODEL="openai/gpt-4o"
export SKILLNEXUS_LOG_LEVEL="DEBUG"
```

### 3. 准备技能目录

```bash
mkdir -p skills/my-skill
cat > skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: 我的第一个技能
---

# 技能内容

这里是技能的指导内容...
EOF
```

### 4. 启动后端

```bash
python run_server.py
```

后端运行在 `http://localhost:8000`，API 文档在 `http://localhost:8000/docs`。

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端运行在 `http://localhost:3000`，自动代理 `/api` 请求到后端。

---

## 配置说明

### settings.json 完整字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `log_level` | string | `"INFO"` | 日志级别（DEBUG/INFO/WARNING/ERROR） |
| `skills.enabled` | bool | `true` | 是否启用技能系统 |
| `skills.skill_dirs` | list | `[]` | 技能目录列表（按优先级排序） |
| `skills.max_select` | int | `2` | 单次任务最多注入的技能数 |
| `llm.model` | string | `"openrouter/anthropic/claude-sonnet-4.5"` | LLM 模型标识 |
| `llm.enable_thinking` | bool | `false` | 是否启用推理模式 |
| `llm.rate_limit_delay` | float | `0.0` | 请求间隔（秒） |
| `llm.max_retries` | int | `3` | 最大重试次数 |
| `llm.retry_delay` | float | `1.0` | 重试间隔（秒） |
| `llm.timeout` | float | `120.0` | 请求超时（秒） |
| `embedding.model` | string | `"BAAI/bge-small-en-v1.5"` | Embedding 模型 |

### 环境变量

| 变量 | 说明 |
|------|------|
| `SKILLNEXUS_LLM_MODEL` | 覆盖 LLM 模型 |
| `SKILLNEXUS_LOG_LEVEL` | 覆盖日志级别 |
| `SKILLNEXUS_DEBUG` | 设为 `1` 启用调试日志 |
| `EMBEDDING_API_KEY` | Embedding API 密钥 |
| `EMBEDDING_API_BASE` | Embedding API 端点 |
| `OPENAI_API_KEY` | OpenAI API 密钥（Embedding 回退） |
| `OPENROUTER_API_KEY` | OpenRouter API 密钥 |

---

## API 接口

### 技能管理 `/api/skills`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 列出所有已发现的技能 |
| GET | `/records` | 列出所有技能记录（含质量指标） |
| GET | `/{skill_id}` | 获取技能元数据 |
| GET | `/{skill_id}/content` | 获取 SKILL.md 内容 |
| POST | `/select` | LLM 技能选择 |
| POST | `/discover` | 触发技能发现 |
| POST | `/register` | 注册单个技能目录 |
| GET | `/stats/summary` | 获取总体统计 |

### 执行分析 `/api/analysis`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/analyze` | 运行执行后分析 |
| GET | `/task/{task_id}` | 获取任务的分析结果 |
| GET | `/evolution-candidates` | 获取进化候选列表 |
| GET | `/skill/{skill_id}` | 获取技能的分析历史 |

### 进化管理 `/api/evolution`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/trigger` | 手动触发进化 |
| POST | `/process-analysis/{task_id}` | 处理分析中的进化建议 |
| POST | `/metric-check` | 运行指标健康检查 |
| GET | `/lineage/{skill_id}` | 获取技能进化血缘树 |
| GET | `/ancestry/{skill_id}` | 获取技能祖先链 |
| GET | `/top-skills` | 获取表现最好的技能 |

---

## 前端页面

### Dashboard（仪表盘）

- 技能总数、活跃数、分析总数等统计卡片
- Top 表现技能排行（按有效率排序）
- 进化候选概览
- 一键触发技能发现

### Skills（技能列表）

- 可筛选的技能表格（名称、分类、指标）
- 每行显示选中次数、应用率、有效率
- 点击进入技能详情页

### Skill Detail（技能详情）

- **内容标签**：查看 SKILL.md 原文
- **分析标签**：该技能的所有执行分析记录
- **血缘标签**：进化祖先链和血缘树

### Analysis（分析）

- 进化候选列表（来自执行分析的建议）
- 每个候选显示任务 ID、执行说明、技能判定、进化建议
- 一键处理进化（触发 Evolver）

### Evolution（进化）

- 手动进化触发表单（选择类型、目标技能、方向）
- 指标健康检查按钮
- Top 技能查看
- 进化结果展示

---

## 数据库设计

SQLite 数据库（WAL 模式），路径：`.skillnexus/skillnexus.db`

### 核心表

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| `skill_records` | 技能主记录 | skill_id, name, description, path, category, tags, visibility, is_active, 总选中/应用/完成/回退次数 |
| `skill_analyses` | 执行分析 | task_id, timestamp, task_completed, execution_note, tool_issues, skill_judgments, evolution_suggestions |
| `skill_lineage` | 进化血缘 | skill_id, origin, generation, parent_skill_ids, source_task_id, change_summary, content_diff, content_snapshot |
| `skill_tags` | 技能标签 | skill_id, tag |
| `skill_dependencies` | 工具依赖 | skill_id, tool_key |
| `skill_critical_tools` | 关键工具 | skill_id, tool_key |

### 质量指标计算

| 指标 | 公式 | 说明 |
|------|------|------|
| `applied_rate` | applied / selections | 被选中后实际应用的比率 |
| `completion_rate` | completions / applied | 应用后成功完成的比率 |
| `effective_rate` | completions / selections | 选中后最终完成的比率 |
| `fallback_rate` | fallbacks / applied | 应用后被回退的比率 |

---

## 与 OpenSpace 的差异

| 方面 | OpenSpace | SkillNexus |
|------|-----------|------------|
| **定位** | 多智能体执行框架 | 技能管理与进化平台 |
| **LLM 客户端** | 支持工具执行的完整 Agent 循环 | 纯文本完成（无工具执行） |
| **执行分析** | Agent 循环 + 工具调用 | 单次 LLM 调用 |
| **进化引擎** | Agent 循环 + 工具调用 + RecordingManager | 单次 LLM 调用 |
| **配置系统** | Pydantic + grounding 配置 | 纯 dataclass + JSON |
| **依赖** | grounding 框架、BaseTool、ToolQualityManager | 无外部框架依赖 |
| **API** | 无 REST API | FastAPI 完整 REST API |
| **前端** | 无 | React + Vite Web 界面 |
| **Embedding** | 通过 cloud.embedding 模块 | 直接读取环境变量 |
| **录制** | RecordingManager（视频/轨迹/动作） | 无（依赖外部系统提供 recording_dir） |

### 保留不变的核心模块

- SQLite 持久化层（6 张表，完整 CRUD + 分析查询）
- BM25 + Embedding 混合排序（优雅降级链）
- 6 级模糊匹配（SEARCH/REPLACE 补丁应用）
- 多文件补丁系统（FULL / DIFF / PATCH 三种格式）
- SKILL.md 格式（YAML frontmatter + Markdown 正文）
- `.skill_id` 侧面文件标识系统
- 版本 DAG 血缘追踪
- 对话日志优先级截断格式化

---

## 后续规划

- [ ] **执行录制模块**：记录任务执行轨迹（conversations.jsonl、traj.jsonl），供分析器使用
- [ ] **企业级功能**：部门级访问控制、云端技能池同步
- [ ] **WebSocket 实时推送**：进化进度、分析结果实时通知
- [ ] **技能市场**：技能浏览、评分、下载、版本管理
- [ ] **批量导入/导出**：从 OpenSpace 迁移技能、ZIP 打包分享
- [ ] **更多 Embedding 模型**：支持本地模型（sentence-transformers）、向量数据库
- [ ] **测试覆盖**：单元测试、集成测试、端到端测试
