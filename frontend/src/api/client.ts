const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API error ${res.status}: ${text}`)
  }
  return res.json()
}

// Skills
export const getSkills = () => request<SkillMeta[]>('/skills/')
export const getSkillRecords = (activeOnly = true) =>
  request<SkillRecord[]>(`/skills/records?active_only=${activeOnly}`)
export const getSkill = (id: string) => request<SkillMeta>(`/skills/${id}`)
export const getSkillContent = (id: string) =>
  request<{ skill_id: string; content: string }>(`/skills/${id}/content`)
export const selectSkills = (taskDescription: string, maxSkills = 2) =>
  request<{ selected: SkillMeta[]; selection_record: any }>('/skills/select', {
    method: 'POST',
    body: JSON.stringify({ task_description: taskDescription, max_skills: maxSkills }),
  })
export const discoverSkills = () =>
  request<{ discovered: number; skills: { skill_id: string; name: string }[] }>('/skills/discover', {
    method: 'POST',
  })
export const getStats = () => request<any>('/skills/stats/summary')

// Analysis
export const getAnalysisForTask = (taskId: string) =>
  request<AnalysisResponse | null>(`/analysis/task/${taskId}`)
export const getEvolutionCandidates = (limit = 20) =>
  request<AnalysisResponse[]>(`/analysis/evolution-candidates?limit=${limit}`)
export const getAnalysesForSkill = (skillId: string, limit = 10) =>
  request<AnalysisResponse[]>(`/analysis/skill/${skillId}?limit=${limit}`)

// Evolution
export const triggerEvolution = (req: EvolutionRequest) =>
  request<EvolutionResponse | null>('/evolution/trigger', {
    method: 'POST',
    body: JSON.stringify(req),
  })
export const processAnalysisEvolution = (taskId: string) =>
  request<EvolutionResponse[]>(`/evolution/process-analysis/${taskId}`, {
    method: 'POST',
  })
export const runMetricCheck = (minSelections = 5) =>
  request<{ evolved: number; skills: EvolutionResponse[] }>(
    `/evolution/metric-check?min_selections=${minSelections}`,
    { method: 'POST' },
  )
export const getSkillLineage = (skillId: string) =>
  request<any>(`/evolution/lineage/${skillId}`)
export const getSkillAncestry = (skillId: string) =>
  request<any>(`/evolution/ancestry/${skillId}`)
export const getTopSkills = (limit = 10) =>
  request<any[]>(`/evolution/top-skills?limit=${limit}`)

// Types
export interface SkillMeta {
  skill_id: string
  name: string
  description: string
  path: string
}

export interface SkillRecord {
  skill_id: string
  name: string
  description: string
  path: string
  category: string
  tags: string[]
  visibility: string
  is_active: boolean
  total_selections: number
  total_applied: number
  total_completions: number
  total_fallbacks: number
  applied_rate: number
  completion_rate: number
  effective_rate: number
  fallback_rate: number
}

export interface AnalysisResponse {
  task_id: string
  task_completed: boolean
  execution_note: string
  tool_issues: string[]
  skill_judgments: {
    skill_id: string
    skill_applied: boolean
    note: string
  }[]
  evolution_suggestions: {
    evolution_type: string
    target_skill_ids: string[]
    category: string | null
    direction: string
  }[]
  analyzed_at: string | null
}

export interface EvolutionRequest {
  evolution_type: string
  target_skill_ids?: string[]
  direction: string
  category?: string
  source_task_id?: string
}

export interface EvolutionResponse {
  skill_id: string
  name: string
  description: string
  origin: string
  generation: number
  parent_skill_ids: string[]
}
