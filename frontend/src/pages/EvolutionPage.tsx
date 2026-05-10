import { useState } from 'react'
import { triggerEvolution, runMetricCheck, getTopSkills, type EvolutionResponse } from '../api/client'

export default function EvolutionPage() {
  const [results, setResults] = useState<EvolutionResponse[]>([])
  const [loading, setLoading] = useState(false)
  const [topSkills, setTopSkills] = useState<any[]>([])

  // Manual trigger form
  const [evoType, setEvoType] = useState('captured')
  const [direction, setDirection] = useState('')
  const [targetIds, setTargetIds] = useState('')
  const [category, setCategory] = useState('workflow')

  const handleTrigger = async () => {
    if (!direction.trim()) {
      alert('Direction is required')
      return
    }
    setLoading(true)
    try {
      const result = await triggerEvolution({
        evolution_type: evoType,
        target_skill_ids: targetIds ? targetIds.split(',').map(s => s.trim()) : [],
        direction,
        category: evoType === 'captured' ? category : undefined,
      })
      if (result) {
        setResults(prev => [result, ...prev])
        setDirection('')
      } else {
        alert('Evolution failed')
      }
    } catch (e: any) {
      alert(`Error: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleMetricCheck = async () => {
    setLoading(true)
    try {
      const result = await runMetricCheck(5)
      if (result.skills.length > 0) {
        setResults(prev => [...result.skills, ...prev])
      }
      alert(`Metric check complete: ${result.evolved} skill(s) evolved`)
    } catch (e: any) {
      alert(`Error: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleTopSkills = async () => {
    try {
      const skills = await getTopSkills(10)
      setTopSkills(skills)
    } catch (e: any) {
      alert(`Error: ${e.message}`)
    }
  }

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Evolution</h2>

      {/* Manual trigger */}
      <div style={cardStyle}>
        <h3 style={{ marginTop: 0 }}>Manual Evolution Trigger</h3>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
          <div>
            <label style={labelStyle}>Type</label>
            <select value={evoType} onChange={e => setEvoType(e.target.value)} style={inputStyle}>
              <option value="fix">Fix (repair existing)</option>
              <option value="derived">Derived (enhance)</option>
              <option value="captured">Captured (new pattern)</option>
            </select>
          </div>
          {evoType === 'captured' && (
            <div>
              <label style={labelStyle}>Category</label>
              <select value={category} onChange={e => setCategory(e.target.value)} style={inputStyle}>
                <option value="workflow">Workflow</option>
                <option value="tool_guide">Tool Guide</option>
                <option value="reference">Reference</option>
              </select>
            </div>
          )}
        </div>

        {(evoType === 'fix' || evoType === 'derived') && (
          <div style={{ marginBottom: 12 }}>
            <label style={labelStyle}>Target Skill IDs (comma-separated)</label>
            <input
              value={targetIds}
              onChange={e => setTargetIds(e.target.value)}
              placeholder="skill__imp_abc123, skill__v0_def456"
              style={inputStyle}
            />
          </div>
        )}

        <div style={{ marginBottom: 12 }}>
          <label style={labelStyle}>Direction</label>
          <textarea
            value={direction}
            onChange={e => setDirection(e.target.value)}
            placeholder="Describe what to fix / derive / capture..."
            rows={3}
            style={{ ...inputStyle, resize: 'vertical' }}
          />
        </div>

        <button onClick={handleTrigger} disabled={loading} style={btnStyle}>
          {loading ? 'Processing...' : 'Trigger Evolution'}
        </button>
      </div>

      {/* Quick actions */}
      <div style={{ display: 'flex', gap: 12, margin: '16px 0' }}>
        <button onClick={handleMetricCheck} disabled={loading} style={btnStyle}>
          Run Metric Check
        </button>
        <button onClick={handleTopSkills} style={{ ...btnStyle, background: '#3498db' }}>
          Load Top Skills
        </button>
      </div>

      {/* Top skills */}
      {topSkills.length > 0 && (
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0 }}>Top Performing Skills</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Origin</th>
                <th style={thStyle}>Selections</th>
                <th style={thStyle}>Effective</th>
              </tr>
            </thead>
            <tbody>
              {topSkills.map((s: any) => (
                <tr key={s.skill_id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                  <td style={tdStyle}>{s.name}</td>
                  <td style={tdStyle}>{s.lineage?.origin ?? 'unknown'}</td>
                  <td style={tdStyle}>{s.total_selections}</td>
                  <td style={tdStyle}>{(s.effective_rate * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Evolution results */}
      {results.length > 0 && (
        <div style={cardStyle}>
          <h3 style={{ marginTop: 0 }}>Evolution Results</h3>
          {results.map((r, i) => (
            <div key={i} style={{ padding: '12px 0', borderBottom: '1px solid #f0f0f0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 600 }}>{r.name}</span>
                <span style={{ ...badgeStyle, background: '#f0e8ff', color: '#6c63ff' }}>
                  {r.origin} gen {r.generation}
                </span>
              </div>
              <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>{r.description}</div>
              <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
                ID: {r.skill_id} | Parents: {r.parent_skill_ids.join(', ') || 'none'}
              </div>
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
  padding: 20,
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
  marginBottom: 16,
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 12,
  color: '#888',
  marginBottom: 4,
  fontWeight: 600,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 12px',
  border: '1px solid #ddd',
  borderRadius: 6,
  fontSize: 13,
  boxSizing: 'border-box',
}

const btnStyle: React.CSSProperties = {
  background: '#6c63ff',
  color: '#fff',
  border: 'none',
  borderRadius: 6,
  padding: '10px 20px',
  cursor: 'pointer',
  fontSize: 14,
  fontWeight: 500,
}

const thStyle: React.CSSProperties = { textAlign: 'left', padding: '8px 4px', fontSize: 12, color: '#888' }
const tdStyle: React.CSSProperties = { padding: '8px 4px', fontSize: 13 }

const badgeStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: 4,
  fontSize: 11,
}
