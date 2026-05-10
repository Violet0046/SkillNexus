import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getSkillRecords, type SkillRecord } from '../api/client'

export default function SkillList() {
  const [skills, setSkills] = useState<SkillRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    getSkillRecords(true)
      .then(setSkills)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = skills.filter(s =>
    s.name.toLowerCase().includes(filter.toLowerCase()) ||
    s.description.toLowerCase().includes(filter.toLowerCase()) ||
    s.skill_id.toLowerCase().includes(filter.toLowerCase())
  )

  if (loading) return <div>Loading skills...</div>

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Skills</h2>

      <input
        type="text"
        placeholder="Filter skills..."
        value={filter}
        onChange={e => setFilter(e.target.value)}
        style={{
          width: 300,
          padding: '8px 12px',
          border: '1px solid #ddd',
          borderRadius: 6,
          fontSize: 14,
          marginBottom: 16,
        }}
      />

      <div style={{ background: '#fff', borderRadius: 8, overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f8f8fc' }}>
              <th style={thStyle}>Name</th>
              <th style={thStyle}>Category</th>
              <th style={thStyle}>Selections</th>
              <th style={thStyle}>Applied</th>
              <th style={thStyle}>Effective</th>
              <th style={thStyle}>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(skill => (
              <tr key={skill.skill_id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <td style={tdStyle}>
                  <Link to={`/skills/${skill.skill_id}`} style={{ color: '#6c63ff', textDecoration: 'none', fontWeight: 500 }}>
                    {skill.name}
                  </Link>
                  <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>{skill.skill_id}</div>
                </td>
                <td style={tdStyle}>
                  <span style={badgeStyle}>{skill.category}</span>
                </td>
                <td style={tdStyle}>{skill.total_selections}</td>
                <td style={tdStyle}>{(skill.applied_rate * 100).toFixed(0)}%</td>
                <td style={tdStyle}>
                  <span style={{
                    color: skill.effective_rate > 0.7 ? '#2ecc71' : skill.effective_rate > 0.4 ? '#e67e22' : '#e74c3c',
                    fontWeight: 600,
                  }}>
                    {(skill.effective_rate * 100).toFixed(0)}%
                  </span>
                </td>
                <td style={tdStyle}>
                  <span style={{
                    ...badgeStyle,
                    background: skill.is_active ? '#e8f8e8' : '#f8e8e8',
                    color: skill.is_active ? '#2ecc71' : '#e74c3c',
                  }}>
                    {skill.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} style={{ ...tdStyle, textAlign: 'center', color: '#888', padding: 24 }}>
                  No skills found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const thStyle: React.CSSProperties = { textAlign: 'left', padding: '12px 16px', fontSize: 12, color: '#888', fontWeight: 600 }
const tdStyle: React.CSSProperties = { padding: '12px 16px', fontSize: 13 }

const badgeStyle: React.CSSProperties = {
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: 4,
  fontSize: 11,
  background: '#f0f0f8',
  color: '#666',
}
