import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getSkill, getSkillContent, getAnalysesForSkill, getSkillLineage, getSkillAncestry, type SkillMeta, type AnalysisResponse } from '../api/client'

export default function SkillDetail() {
  const { skillId } = useParams<{ skillId: string }>()
  const [skill, setSkill] = useState<SkillMeta | null>(null)
  const [content, setContent] = useState('')
  const [analyses, setAnalyses] = useState<AnalysisResponse[]>([])
  const [lineage, setLineage] = useState<any>(null)
  const [ancestry, setAncestry] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'content' | 'analyses' | 'lineage'>('content')

  useEffect(() => {
    if (!skillId) return
    Promise.all([
      getSkill(skillId).catch(() => null),
      getSkillContent(skillId).catch(() => ({ content: '' })),
      getAnalysesForSkill(skillId, 10).catch(() => []),
      getSkillLineage(skillId).catch(() => null),
      getSkillAncestry(skillId).catch(() => null),
    ]).then(([s, c, a, l, an]) => {
      setSkill(s)
      setContent(c?.content ?? '')
      setAnalyses(a)
      setLineage(l)
      setAncestry(an)
      setLoading(false)
    })
  }, [skillId])

  if (loading) return <div>Loading skill details...</div>
  if (!skill) return <div>Skill not found</div>

  return (
    <div>
      <Link to="/skills" style={{ color: '#6c63ff', textDecoration: 'none', fontSize: 13 }}>
        &larr; Back to Skills
      </Link>

      <h2 style={{ marginTop: 8 }}>{skill.name}</h2>
      <p style={{ color: '#666', fontSize: 14 }}>{skill.description}</p>
      <p style={{ fontSize: 12, color: '#999' }}>ID: {skill.skill_id}</p>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '2px solid #eee', marginTop: 16 }}>
        {(['content', 'analyses', 'lineage'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: '10px 20px',
              background: tab === t ? '#6c63ff' : 'transparent',
              color: tab === t ? '#fff' : '#666',
              border: 'none',
              borderRadius: '6px 6px 0 0',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 500,
            }}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div style={{ background: '#fff', borderRadius: '0 8px 8px 8px', padding: 20, marginTop: -1, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        {tab === 'content' && (
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.6, maxHeight: 500, overflow: 'auto' }}>
            {content || '(no content)'}
          </pre>
        )}

        {tab === 'analyses' && (
          <div>
            {analyses.length === 0 ? (
              <p style={{ color: '#888' }}>No analyses recorded</p>
            ) : (
              analyses.map((a, i) => (
                <div key={i} style={{ padding: '12px 0', borderBottom: '1px solid #f0f0f0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{a.task_id}</span>
                    <span style={{
                      ...badgeStyle,
                      background: a.task_completed ? '#e8f8e8' : '#f8e8e8',
                      color: a.task_completed ? '#2ecc71' : '#e74c3c',
                    }}>
                      {a.task_completed ? 'Completed' : 'Failed'}
                    </span>
                  </div>
                  <p style={{ fontSize: 12, color: '#666', margin: '4px 0 0' }}>{a.execution_note}</p>
                  {a.evolution_suggestions.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      {a.evolution_suggestions.map((s, j) => (
                        <span key={j} style={{ ...badgeStyle, marginRight: 4, background: '#f0e8ff', color: '#6c63ff' }}>
                          {s.evolution_type}: {s.direction.slice(0, 60)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {tab === 'lineage' && (
          <div>
            {ancestry?.ancestry?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <h4 style={{ margin: '0 0 8px', fontSize: 13, color: '#888' }}>Ancestry Chain</h4>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {ancestry.ancestry.map((a: any, i: number) => (
                    <span key={i} style={{ ...badgeStyle, background: '#f0f0f8' }}>
                      {a.skill_id} (gen {a.generation})
                    </span>
                  ))}
                </div>
              </div>
            )}
            {lineage && (
              <div>
                <h4 style={{ margin: '0 0 8px', fontSize: 13, color: '#888' }}>Lineage Tree</h4>
                <pre style={{ fontSize: 12, background: '#f8f8fc', padding: 12, borderRadius: 6, overflow: 'auto' }}>
                  {JSON.stringify(lineage, null, 2)}
                </pre>
              </div>
            )}
            {!lineage && (!ancestry?.ancestry?.length) && (
              <p style={{ color: '#888' }}>No lineage data</p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

const badgeStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: 4,
  fontSize: 11,
}
