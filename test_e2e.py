"""
端到端功能验证脚本
==================
模拟一次任务执行 → 分析 → 进化全流程，验证三大核心机制：

1. CAPTURED — 从执行轨迹中捕获新技能
2. FIX      — 分析失败技能并自动修复
3. DERIVED  — 从现有技能派生增强版本

运行方式:
    conda activate skillnexus
    cd d:\\VS\\26project\\SkillNexus
    python test_e2e.py
"""

import asyncio
import json
import shutil
from pathlib import Path

# ── 路径常量 ──
PROJECT_ROOT = Path(__file__).resolve().parent
SKILLS_DIR = PROJECT_ROOT / "skills"
RECORDING_DIR = PROJECT_ROOT / ".test_recording"
CAPTURED_DIR = SKILLS_DIR  # CAPTURED 新技能写到这里


def setup_recording_data():
    """构造一份模拟执行轨迹数据，模拟一个"用 Python 生成 CSV 报告"的任务。"""

    RECORDING_DIR.mkdir(exist_ok=True)

    # ── metadata.json ──
    metadata = {
        "task_id": "task_csv_report_001",
        "task_description": "使用 Python 读取 sales_data.json，生成一份包含月度汇总和图表的 CSV 报告",
        "skill_selection": {
            "selected": ["hello-world"],
            "available_skills": ["hello-world"],
            "method": "llm",
            "brief_plan": "读取 JSON 数据，用 pandas 做汇总，matplotlib 画图，输出 CSV"
        },
        "retrieved_tools": {
            "tools": [
                {"name": "run_shell", "backend": "shell"},
                {"name": "read_file", "backend": "shell"},
                {"name": "write_file", "backend": "shell"},
            ]
        },
        "execution_outcome": {
            "status": "success",
            "iterations": 3
        }
    }
    (RECORDING_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ── conversations.jsonl ──
    conversations = [
        {
            "type": "setup",
            "messages": [
                {
                    "role": "system",
                    "content": "# Active Skills\n\n### Skill: hello-world\n**Skill directory**: `skills/hello-world`\n\nThis is a sample skill."
                },
                {
                    "role": "user",
                    "content": "使用 Python 读取 sales_data.json，生成一份包含月度汇总和图表的 CSV 报告"
                }
            ]
        },
        {
            "type": "iteration",
            "iteration": 1,
            "messages": [
                {
                    "role": "assistant",
                    "content": "我来分步完成这个任务。首先读取 JSON 数据文件，然后用 pandas 进行月度汇总分析。"
                },
                {
                    "role": "tool_call",
                    "content": "run_shell: python -c \"import json; data=json.load(open('sales_data.json')); print(len(data))\""
                },
                {
                    "role": "tool_result",
                    "content": "156"
                }
            ]
        },
        {
            "type": "iteration",
            "iteration": 2,
            "messages": [
                {
                    "role": "assistant",
                    "content": "数据有 156 条记录。现在用 pandas 做月度汇总并生成 CSV。"
                },
                {
                    "role": "tool_call",
                    "content": "write_file: generate_report.py"
                },
                {
                    "role": "tool_result",
                    "content": "File written successfully"
                }
            ]
        },
        {
            "type": "iteration",
            "iteration": 3,
            "messages": [
                {
                    "role": "assistant",
                    "content": "脚本已写好，执行生成报告。"
                },
                {
                    "role": "tool_call",
                    "content": "run_shell: python generate_report.py"
                },
                {
                    "role": "tool_result",
                    "content": "Report generated: monthly_report.csv (312 rows)"
                }
            ]
        }
    ]
    with open(RECORDING_DIR / "conversations.jsonl", "w", encoding="utf-8") as f:
        for conv in conversations:
            f.write(json.dumps(conv, ensure_ascii=False) + "\n")

    # ── traj.jsonl ──
    traj = [
        {
            "step": 1,
            "timestamp": "2026-05-10T10:00:01",
            "backend": "shell",
            "tool": "run_shell",
            "command": "python -c \"import json; data=json.load(open('sales_data.json')); print(len(data))\"",
            "result": {"status": "success", "output": "156"}
        },
        {
            "step": 2,
            "timestamp": "2026-05-10T10:00:03",
            "backend": "shell",
            "tool": "write_file",
            "command": "generate_report.py",
            "result": {"status": "success", "output": "File written successfully"}
        },
        {
            "step": 3,
            "timestamp": "2026-05-10T10:00:05",
            "backend": "shell",
            "tool": "run_shell",
            "command": "python generate_report.py",
            "result": {"status": "success", "output": "Report generated: monthly_report.csv (312 rows)"}
        }
    ]
    with open(RECORDING_DIR / "traj.jsonl", "w", encoding="utf-8") as f:
        for entry in traj:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"[OK] 模拟执行数据已写入 {RECORDING_DIR}")


def setup_broken_skill():
    """创建一个"有缺陷"的技能，用于测试 FIX 机制。"""
    broken_dir = SKILLS_DIR / "csv-report-broken"
    broken_dir.mkdir(exist_ok=True)
    (broken_dir / "SKILL.md").write_text(
        """---
name: csv-report-broken
description: 生成 CSV 报告（已过时，命令有误）
---

# CSV 报告生成

## 步骤

1. 使用 `pandas.read_json()` 读取数据
2. 使用 `data.groupby('month').sum()` 汇总
3. 输出到 CSV

## 注意

- 使用 `pd.to_csv('output.csv')` 导出
""", encoding="utf-8"
    )
    print(f"[OK] 缺陷技能已创建: {broken_dir}")
    return broken_dir


async def test_captured(evolver, analyzer):
    """测试 CAPTURED：从执行轨迹中捕获新技能。"""
    print("\n" + "=" * 60)
    print("测试 1: CAPTURED — 从执行中捕获新技能")
    print("=" * 60)

    # 先跑分析
    analysis = await analyzer.analyze_execution(
        task_id="task_csv_report_001",
        recording_dir=str(RECORDING_DIR),
        execution_result={"status": "success", "iterations": 3},
    )

    if analysis is None:
        print("[FAIL] 分析返回 None")
        return None

    print(f"[OK] 分析完成:")
    print(f"     任务完成: {analysis.task_completed}")
    print(f"     执行说明: {analysis.execution_note}")
    print(f"     技能判定: {len(analysis.skill_judgments)} 个")
    print(f"     进化建议: {len(analysis.evolution_suggestions)} 个")

    for i, sug in enumerate(analysis.evolution_suggestions):
        print(f"     建议 {i+1}: [{sug.evolution_type.value}] {sug.direction[:80]}")

    # 如果分析器自动产生了 CAPTURED 建议，直接处理
    captured_suggestions = [
        s for s in analysis.evolution_suggestions
        if s.evolution_type.value == "captured"
    ]

    if captured_suggestions:
        print("\n→ 分析器自动生成了 CAPTURED 建议，触发进化...")
        results = await evolver.process_analysis(analysis, capture_dir=CAPTURED_DIR)
        if results:
            for r in results:
                print(f"[OK] 新技能已创建: {r.name} (ID: {r.skill_id})")
            return results
        else:
            print("[INFO] 进化未产生结果（LLM 可能拒绝或格式不对）")

    # 如果没有自动建议，手动触发 CAPTURED
    print("\n→ 手动触发 CAPTURED 进化...")
    from skillnexus.core.types import EvolutionSuggestion, EvolutionType, SkillCategory
    from skillnexus.core.evolver import EvolutionContext, EvolutionTrigger

    ctx = EvolutionContext(
        trigger=EvolutionTrigger.ANALYSIS,
        suggestion=EvolutionSuggestion(
            evolution_type=EvolutionType.CAPTURED,
            target_skill_ids=[],
            category=SkillCategory.WORKFLOW,
            direction="捕获一个可复用的 Python CSV 报告生成工作流：读取 JSON 数据 → pandas 月度汇总 → 输出 CSV",
        ),
        source_task_id="task_csv_report_001",
        recent_analyses=[analysis],
        capture_dir=CAPTURED_DIR,
    )

    result = await evolver.evolve(ctx)
    if result:
        print(f"[OK] 新技能已创建: {result.name} (ID: {result.skill_id})")
        print(f"     路径: {result.path}")
        return result
    else:
        print("[FAIL] CAPTURED 进化失败")
        return None


async def test_fix(evolver, analyzer, broken_skill_dir):
    """测试 FIX：修复有缺陷的技能。"""
    print("\n" + "=" * 60)
    print("测试 2: FIX — 修复缺陷技能")
    print("=" * 60)

    from skillnexus.core.types import (
        EvolutionSuggestion, EvolutionType, SkillRecord, SkillLineage,
        SkillOrigin, SkillCategory, SkillVisibility,
    )
    from skillnexus.core.evolver import EvolutionContext, EvolutionTrigger
    from skillnexus.core.registry import SkillMeta
    import uuid

    # 读取缺陷技能内容
    skill_content = (broken_skill_dir / "SKILL.md").read_text(encoding="utf-8")
    skill_path = str(broken_skill_dir / "SKILL.md")

    # 注册到 store
    store = evolver._store
    skill_id = "csv-report-broken__imp_test"
    record = SkillRecord(
        skill_id=skill_id,
        name="csv-report-broken",
        description="生成 CSV 报告（已过时，命令有误）",
        path=skill_path,
        category=SkillCategory.TOOL_GUIDE,
        tags=["csv", "report"],
        visibility=SkillVisibility.PRIVATE,
        creator_id="test",
        lineage=SkillLineage(
            origin=SkillOrigin.IMPORTED,
            generation=0,
            parent_skill_ids=[],
        ),
    )
    await store.save_record(record)

    # 注册到 registry
    registry = evolver._registry
    meta = SkillMeta(
        skill_id=skill_id,
        name="csv-report-broken",
        description="生成 CSV 报告（已过时，命令有误）",
        path=broken_skill_dir / "SKILL.md",
    )
    registry.add_skill(meta)

    print(f"[OK] 缺陷技能已注册: {skill_id}")

    # 构建 FIX 进化上下文
    ctx = EvolutionContext(
        trigger=EvolutionTrigger.ANALYSIS,
        suggestion=EvolutionSuggestion(
            evolution_type=EvolutionType.FIX,
            target_skill_ids=[skill_id],
            direction=(
                "技能中的 pandas 命令有误："
                "1) groupby('month').sum() 缺少 numeric_only=True 参数，新版 pandas 会报错；"
                "2) pd.to_csv() 应该是 df.to_csv()；"
                "3) 缺少编码参数 encoding='utf-8-sig'（中文 Windows Excel 兼容）。"
                "请修复这些问题。"
            ),
        ),
        skill_records=[record],
        skill_contents=[skill_content],
        skill_dirs=[broken_skill_dir],
        source_task_id="task_csv_report_001",
    )

    print("→ 触发 FIX 进化...")
    result = await evolver.evolve(ctx)

    if result:
        print(f"[OK] 技能已修复: {result.name} (新 ID: {result.skill_id})")
        print(f"     代数: gen{result.lineage.generation}")
        print(f"     父技能: {result.lineage.parent_skill_ids}")
        print(f"     变更说明: {result.lineage.change_summary}")
        return result
    else:
        print("[FAIL] FIX 进化失败")
        return None


async def test_derived(evolver, fixed_record=None):
    """测试 DERIVED：从现有技能派生增强版本。"""
    print("\n" + "=" * 60)
    print("测试 3: DERIVED — 派生增强技能")
    print("=" * 60)

    from skillnexus.core.types import (
        EvolutionSuggestion, EvolutionType, SkillRecord, SkillLineage,
        SkillOrigin, SkillCategory, SkillVisibility,
    )
    from skillnexus.core.evolver import EvolutionContext, EvolutionTrigger
    from skillnexus.core.registry import SkillMeta
    import uuid

    # 如果没有 FIX 结果，用 hello-world 作为父技能
    if fixed_record is None:
        parent_id = "hello-world__imp_test"
        parent_dir = SKILLS_DIR / "hello-world"
        parent_content = (parent_dir / "SKILL.md").read_text(encoding="utf-8")
        parent_desc = "示例技能"
    else:
        parent_id = fixed_record.skill_id
        parent_dir = Path(fixed_record.path).parent
        parent_content = (parent_dir / "SKILL.md").read_text(encoding="utf-8")
        parent_desc = fixed_record.description

    # 确保父技能在 store 和 registry 中
    store = evolver._store
    existing = store.load_record(parent_id)
    if existing is None:
        record = SkillRecord(
            skill_id=parent_id,
            name="hello-world",
            description=parent_desc,
            path=str(parent_dir / "SKILL.md"),
            category=SkillCategory.WORKFLOW,
            visibility=SkillVisibility.PRIVATE,
            creator_id="test",
            lineage=SkillLineage(
                origin=SkillOrigin.IMPORTED,
                generation=0,
                parent_skill_ids=[],
            ),
        )
        await store.save_record(record)

    registry = evolver._registry
    if registry.get_skill(parent_id) is None:
        meta = SkillMeta(
            skill_id=parent_id,
            name="hello-world",
            description=parent_desc,
            path=parent_dir / "SKILL.md",
        )
        registry.add_skill(meta)

    print(f"[OK] 父技能: {parent_id}")

    ctx = EvolutionContext(
        trigger=EvolutionTrigger.ANALYSIS,
        suggestion=EvolutionSuggestion(
            evolution_type=EvolutionType.DERIVED,
            target_skill_ids=[parent_id],
            direction=(
                "基于现有技能创建一个增强版本，专注于 Python 数据分析报告生成的完整工作流，"
                "包含：数据读取（JSON/CSV/Excel）、pandas 数据清洗、统计汇总、matplotlib 可视化、"
                "输出格式化报告。添加常见错误处理和性能优化建议。"
            ),
        ),
        skill_records=[existing or record],
        skill_contents=[parent_content],
        skill_dirs=[parent_dir],
        source_task_id="task_csv_report_001",
    )

    print("→ 触发 DERIVED 进化...")
    result = await evolver.evolve(ctx)

    if result:
        print(f"[OK] 增强技能已创建: {result.name} (ID: {result.skill_id})")
        print(f"     路径: {result.path}")
        print(f"     代数: gen{result.lineage.generation}")
        print(f"     父技能: {result.lineage.parent_skill_ids}")
        return result
    else:
        print("[FAIL] DERIVED 进化失败")
        return None


async def main():
    print("=" * 60)
    print("SkillNexus 端到端功能验证")
    print("=" * 60)

    # 1. 准备数据
    print("\n[准备] 构造测试数据...")
    setup_recording_data()
    broken_skill_dir = setup_broken_skill()

    # 2. 初始化组件
    print("\n[准备] 初始化组件...")
    from skillnexus.config.settings import Settings
    from skillnexus.core.store import SkillStore
    from skillnexus.core.registry import SkillRegistry
    from skillnexus.llm.client import LLMClient
    from skillnexus.core.analyzer import ExecutionAnalyzer
    from skillnexus.core.evolver import SkillEvolver

    settings = Settings.load()
    store = SkillStore()
    registry = SkillRegistry(skill_dirs=[SKILLS_DIR])
    registry.discover()

    llm_client = LLMClient(
        model=settings.llm.model,
        timeout=settings.llm.timeout,
        max_retries=settings.llm.max_retries,
    )

    analyzer = ExecutionAnalyzer(
        store=store,
        llm_client=llm_client,
        skill_registry=registry,
    )

    evolver = SkillEvolver(
        store=store,
        registry=registry,
        llm_client=llm_client,
    )

    print(f"[OK] 模型: {settings.llm.model}")
    print(f"[OK] 已发现 {len(registry.list_skills())} 个技能")

    # 3. 运行测试
    try:
        # 测试 CAPTURED
        captured = await test_captured(evolver, analyzer)

        # 测试 FIX
        fixed = await test_fix(evolver, analyzer, broken_skill_dir)

        # 测试 DERIVED
        derived = await test_derived(evolver, fixed)

    except Exception as e:
        print(f"\n[ERROR] 测试异常: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 清理
        if RECORDING_DIR.exists():
            shutil.rmtree(RECORDING_DIR, ignore_errors=True)
        store.close()

    # 4. 汇总
    print("\n" + "=" * 60)
    print("验证完成！查看 skills/ 目录下的新技能文件。")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
