"""Prompts for the skill engine subsystem."""

class SkillEnginePrompts:
    """Central registry of prompts used by the skill engine."""

    EVOLUTION_COMPLETE = "<EVOLUTION_COMPLETE>"
    EVOLUTION_FAILED = "<EVOLUTION_FAILED>"

    @staticmethod
    def evolution_fix(
        *,
        current_content: str,
        direction: str,
        failure_context: str,
        tool_issue_summary: str = "",
        metric_summary: str = "",
    ) -> str:
        return _EVOLUTION_FIX_TEMPLATE.format(
            current_content=current_content,
            direction=direction,
            failure_context=failure_context,
            tool_issue_summary=tool_issue_summary or "(none)",
            metric_summary=metric_summary or "(none)",
            evolution_complete=SkillEnginePrompts.EVOLUTION_COMPLETE,
            evolution_failed=SkillEnginePrompts.EVOLUTION_FAILED,
        )

    @staticmethod
    def evolution_derived(
        *,
        parent_content: str,
        direction: str,
        execution_insights: str,
        metric_summary: str = "",
    ) -> str:
        return _EVOLUTION_DERIVED_TEMPLATE.format(
            parent_content=parent_content,
            direction=direction,
            execution_insights=execution_insights,
            metric_summary=metric_summary or "(none)",
            evolution_complete=SkillEnginePrompts.EVOLUTION_COMPLETE,
            evolution_failed=SkillEnginePrompts.EVOLUTION_FAILED,
        )

    @staticmethod
    def evolution_captured(
        *,
        direction: str,
        category: str,
        execution_highlights: str,
    ) -> str:
        return _EVOLUTION_CAPTURED_TEMPLATE.format(
            direction=direction,
            category=category,
            execution_highlights=execution_highlights,
            evolution_complete=SkillEnginePrompts.EVOLUTION_COMPLETE,
            evolution_failed=SkillEnginePrompts.EVOLUTION_FAILED,
        )

    @staticmethod
    def evolution_confirm(
        *,
        skill_id: str,
        skill_content: str,
        proposed_type: str,
        proposed_direction: str,
        trigger_context: str,
        recent_analyses: str,
    ) -> str:
        return _EVOLUTION_CONFIRM_TEMPLATE.format(
            skill_id=skill_id,
            skill_content=skill_content,
            proposed_type=proposed_type,
            proposed_direction=proposed_direction,
            trigger_context=trigger_context,
            recent_analyses=recent_analyses,
        )

    @staticmethod
    def execution_analysis(
        *,
        task_description: str,
        execution_status: str,
        iterations: int,
        tool_list: str,
        skill_section: str,
        conversation_log: str,
        traj_summary: str,
        selected_skill_ids_json: str,
        resource_info: str = "",
    ) -> str:
        return _EXECUTION_ANALYSIS_TEMPLATE.format(
            task_description=task_description,
            execution_status=execution_status,
            iterations=iterations,
            tool_list=tool_list,
            skill_section=skill_section,
            conversation_log=conversation_log,
            traj_summary=traj_summary,
            selected_skill_ids_json=selected_skill_ids_json,
            resource_info=resource_info,
        )

_EXECUTION_ANALYSIS_TEMPLATE = """\
You are an expert analyst evaluating an autonomous agent's task execution.
Your job is to assess how the agent used its skills and tools, trace the
reasoning and outcome of each iteration, and surface actionable insights.

## Task Context

**Task**: {task_description}
**Agent self-reported status**: {execution_status}
**Iterations used**: {iterations}
**Available tools**: {tool_list}

> This is the agent's **self-reported** status, not ground truth.
> ``success`` = agent output ``<COMPLETE>`` (may be wrong/premature);
> ``incomplete`` = iteration budget exhausted; ``error`` = code exception.
> You must independently judge actual task completion below.

{skill_section}

## Tool Execution Timeline (from traj.jsonl)

This is a structured summary of every tool invocation and its outcome:

{traj_summary}

## Agent Conversation Log

This shows the agent's reasoning (ASSISTANT), tool calls (TOOL_CALL),
tool results (TOOL_RESULT / TOOL_ERROR), and the user's original instruction.

**Reading guide**:
- ``[USER INSTRUCTION]`` — the original task from the user.
- ``[Iter N] ASSISTANT:`` — the agent's reasoning and decisions at iteration N.
- ``[Iter N] TOOL_CALL:`` — what tool the agent invoked and with what arguments.
- ``[Iter N] TOOL_ERROR:`` — tool returned an error (high priority for analysis).
- ``[Iter N] TOOL_RESULT:`` — tool returned successfully.

{conversation_log}

## Available Resources

{resource_info}

## Analysis Instructions

### 1. Per-iteration trace

For each agent iteration, identify:
- **What** the agent decided to do and **why** (from ASSISTANT content).
- **Which tool** was called and what happened (success / error / timeout).
- **Cause of next iteration**: did the agent retry due to error? Switch strategy?

### 2. Task completion assessment

Did the agent **actually** accomplish the user's request?
- ``task_completed = true`` ONLY when the user's goal is genuinely fulfilled.
- Explain your reasoning in ``execution_note``.

### 3. Skill assessment

For each selected skill (IDs: {selected_skill_ids_json}), produce one
``skill_judgments`` entry:
- ``skill_id``: Use the **exact skill_id** from the list above.
- ``skill_applied``: Was the skill's information **actually used** (not just injected)?
- ``note``: Describe HOW the skill was used.

If no skills were selected, ``skill_judgments`` must be an empty list.

### 4. Tool issues

List **only tools that had actual problems** during this execution.

### 5. Evolution suggestions

You may output **0 to N** suggestions. Each suggestion is one of three types:

| Type | When to use | ``target_skills`` |
|------|------------|-------------------|
| ``fix`` | A selected skill had incorrect/outdated instructions | ``["skill_id"]`` |
| ``derived`` | A selected skill worked, but execution revealed a better approach | ``["parent_skill_id"]`` |
| ``captured`` | The agent solved the task without skill guidance and the approach is reusable | ``[]`` |

For each suggestion, specify:
- ``type``: ``"fix"`` | ``"derived"`` | ``"captured"``
- ``target_skills``: list of **exact skill_id(s)**
- ``category``: ``"tool_guide"`` | ``"workflow"`` | ``"reference"``
- ``direction``: 1-2 sentences describing **what** to fix / derive / capture

### Output format

Return **exactly one** JSON object (no markdown fences, no explanation outside JSON):

{{
  "task_completed": true,
  "execution_note": "2-3 sentence overview of execution quality and outcome.",
  "tool_issues": [],
  "skill_judgments": [
    {{
      "skill_id": "weather__imp_a1b2c3d4",
      "skill_applied": true,
      "note": "How the skill was used."
    }}
  ],
  "evolution_suggestions": [
    {{
      "type": "fix",
      "target_skills": ["weather__imp_a1b2c3d4"],
      "category": "workflow",
      "direction": "What to fix and why."
    }}
  ]
}}
"""


_EVOLUTION_FIX_TEMPLATE = """\
You are a skill editor. Your job is to **fix** an existing skill that has
been identified as broken, outdated, or incomplete.

A skill is a directory containing ``SKILL.md`` (the main instruction file)
and optionally auxiliary files.

## Current Skill Content

{current_content}

## What needs fixing

{direction}

## Execution failure context

{failure_context}

## Tool issue details

{tool_issue_summary}

## Skill health metrics

{metric_summary}

## Instructions

1. Analyze the failure context and identify the root cause.
2. Fix the affected files to address the identified issues.
3. Preserve the overall structure and YAML frontmatter format.
4. Be surgical — fix what's broken without unnecessary rewrites.

## Output format

Your output MUST have exactly two parts:

**Part 1** — A summary line on the very first line:

CHANGE_SUMMARY: <one-sentence description of what you fixed>

**Part 2** — After one blank line, the actual changes.

### Format A: Patch (PREFERRED for fixes)

*** Begin Patch
*** Update File: <relative path>
@@ <anchor line>
 <unchanged context line>
-<line to remove>
+<line to add>
 <unchanged context line>
*** End Patch

### Format B: Full rewrite (only when most of the content changes)

*** Begin Files
*** File: SKILL.md
(complete file content)
*** End Files

### Rules

- Do NOT wrap your output in markdown code fences.
- Prefer Format A (patch) for fixes.

## Self-Assessment

**If your edit is satisfactory** — include `{evolution_complete}` on the last line.

**If you cannot produce a satisfactory edit** — output ONLY:

{evolution_failed}
Reason: <brief explanation>

Do NOT output any edit content if you signal failure.
"""


_EVOLUTION_DERIVED_TEMPLATE = """\
You are a skill editor. Your job is to **derive** an enhanced version of an
existing skill. The new skill will live in a new directory; the original
stays unchanged.

A skill is a directory containing ``SKILL.md`` and optionally auxiliary files.

## Parent Skill Content

{parent_content}

## Enhancement direction

{direction}

## Execution insights

{execution_insights}

## Skill health metrics

{metric_summary}

## Instructions

1. Create an enhanced version that addresses the improvement direction.
2. Give the new skill a **different, concise name** (in frontmatter ``name:`` field).
3. Update ``description`` to reflect the new capability.
4. The derived skill should be self-contained.

## Output format

**Part 1** — CHANGE_SUMMARY: <one-sentence description>

**Part 2** — Actual changes (Format A: patch, or Format B: full rewrite).

### Rules

- Do NOT wrap your output in markdown code fences.
- The new skill MUST have a different ``name`` from the parent.

## Self-Assessment

**If the derived skill is satisfactory** — include `{evolution_complete}` on the last line.

**If you cannot produce a worthwhile derived skill** — output ONLY:

{evolution_failed}
Reason: <brief explanation>
"""


_EVOLUTION_CAPTURED_TEMPLATE = """\
You are a skill author. Your job is to **capture** a reusable pattern that
was observed during task executions into a brand-new skill.

A skill is a directory containing ``SKILL.md`` and optionally auxiliary files.

## Pattern to capture

{direction}

## Desired category

``{category}```

Categories:
- ``tool_guide``: How to use a specific tool effectively
- ``workflow``: End-to-end multi-step procedure
- ``reference``: Reference knowledge / best practices

## Execution context

{execution_highlights}

## Instructions

1. Distill the observed pattern into a clear, reusable skill document.
2. Choose a concise, descriptive ``name`` (lowercase, hyphens for spaces).
3. Write a brief ``description`` that captures the skill's purpose.
4. Structure the body as clear, actionable instructions.
5. Make the skill **generalizable** — abstract away task-specific details.

## Output format

**Part 1** — CHANGE_SUMMARY: <one-sentence description>

**Part 2** — Complete skill content.

### Rules

- Do NOT wrap your output in markdown code fences.
- The SKILL.md MUST start with YAML frontmatter (``---`` fences) containing
  at least ``name`` and ``description``.

## Self-Assessment

**If the captured skill is satisfactory** — include `{evolution_complete}` on the last line.

**If you cannot produce a worthwhile skill** — output ONLY:

{evolution_failed}
Reason: <brief explanation>
"""


_EVOLUTION_CONFIRM_TEMPLATE = """\
You are an expert evaluating whether a skill needs evolution.

A rule-based monitoring system has flagged a skill as a candidate for
evolution. Your job is to **confirm or reject** this recommendation.

## Skill Under Review

**ID**: {skill_id}

**Content** (may be truncated):

{skill_content}

## Proposed Evolution

**Type**: ``{proposed_type}``
**Direction**: {proposed_direction}

## Trigger Context

{trigger_context}

## Recent Execution History

{recent_analyses}

## Output Format

Return **exactly one** JSON object (no markdown fences):

{{
  "proceed": true,
  "reasoning": "1-2 sentence explanation of your decision.",
  "adjusted_direction": "Optional: refined direction if you agree but want to adjust."
}}

Set ``"proceed": false`` to skip this evolution.
Set ``"proceed": true`` to confirm it should proceed.
"""
