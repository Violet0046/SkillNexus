import { useEffect, useState } from 'react'
import { getEvolutionCandidates, processAnalysisEvolution, type AnalysisResponse } from '../api/client'

export default function AnalysisList() {
  const [candidates, setCandidates] = useState<AnalysisResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [processing, setProcessing] = useState<string | null>(null)

  useEffect(() => {
    getEvolutionCandidates(50)
      .then(setCandidates)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleProcess = async (taskId: string) => {
    setProcessing(taskId)
    try {
      const results = await processAnalysisEvolution(taskId)
      alert(`Evolved ${results.length} skill(s): ${results.map(r => r.name).join(', ') || 'none'}`)
      // Refresh
      const updated = await getEvolutionCandidates(50)
      setCandidates(updated)
    } catch (e: any) {
      alert(`Error: ${e.message}`)
    } finally {
      setProcessing(null)
    }
  }

  if (loading) return <div>Loading analyses...</div>

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Evolution Candidates</h2>
      <p style={{ color: '#666', fontSize: 14, marginBottom: 16 }}>
        Analyses flagged as candidates for skill evolution. Click "Process" to trigger evolution.
      </p>

      {candidates.length === 0 ? (
        <div style={{ background: '#fff', borderRadius: 8, padding: 40, textAlign: 'center', color: '#888' }}>
          No evolution candidates at this time
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {candidates.map(c => (
            <div key={c.task_id} style={cardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{c.task_id}</div>
                  <div style={{ fontSize: 13, color: '#666', marginTop: 4 }}>{c.execution_note}</div>
                </div>
                <button
                  onClick={() => handleProcess(c.task_id)}
                  disabled={processing === c.task_id}
                  style={{
                    ...btnStyle,
                    opacity: processing === c.task_id ? 0.6 : 1,
                  }}
                >
                  {processing === c.task_id ? 'Processing...' : 'Process'}
                </button>
              </div>

              {/* Skills judged */}
              {c.skill_judgments.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 11, color: '#888', marginBottom: 4 }}>Skills:</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {c.skill_judgments.map((j, i) => (
                      <span key={i} style={{
                        ...badgeStyle,
                        background: j.skill_applied ? '#e8f8e8' : '#f8e8e8',
                        color: j.skill_applied ? '#2ecc71' : '#e74c3c',
                      }}>
                        {j.skill_id}: {j.skill_applied ? 'applied' : 'not applied'}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Evolution suggestions */}
              {c.evolution_suggestions.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 11, color: '#888', marginBottom: 4 }}>Suggestions:</div>
                  {c.evolution_suggestions.map((s, i) => (
                    <div key={i} style={{ fontSize: 12, padding: '4px 0' }}>
                      <span style={{ ...badgeStyle, background: '#f0e8ff', color: '#6c63ff', marginRight: 6 }}>
                        {s.evolution_type}
                      </span>
                      {s.direction}
                      {s.target_skill_ids.length > 0 && (
                        <span style={{ color: '#999', marginLeft: 6 }}>
                          ({s.target_skill_ids.join(', ')})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const cardStyle: React.CSSProperties = {
  background: '#fff',
  borderRadius: 8,
  padding: 16,
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
}

const btnStyle: React.CSSProperties = {
  background: '#6c63ff',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  padding: '8px 16px',
  cursor: 'pointer',
  fontSize: 13,
  fontWeight: 500,
  flexShrink: 0,
}

const badgeStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: 4,
  fontSize: 11,
}
