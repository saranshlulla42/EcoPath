import { ComparisonTableBlock as ComparisonTableBlockType } from '../../../types/chat';

function colorCodeValue(val: string) {
  const lower = val.toLowerCase();
  if (lower.includes('critically endangered')) return { color: 'var(--danger)', text: val };
  if (lower.includes('endangered')) return { color: '#B5602A', text: val };
  if (lower.includes('vulnerable')) return { color: 'var(--warning)', text: val };
  if (lower.includes('least concern')) return { color: 'var(--success)', text: val };
  return { color: 'inherit', text: val };
}

export function ComparisonTableBlockView({ block }: { block: ComparisonTableBlockType }) {
  if (!block.rows || block.rows.length === 0) return null;

  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: '12px',
      padding: '4px',
      marginTop: '16px',
      background: 'var(--surface-raised)',
      boxShadow: 'var(--shadow-card)',
      overflowX: 'auto',
    }}>
      {block.title && (
        <div style={{
          fontFamily: 'DM Sans',
          fontSize: '13px',
          fontWeight: 600,
          color: 'var(--text-secondary)',
          padding: '12px 16px',
        }}>
          {block.title}
        </div>
      )}
      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
        <thead>
          <tr style={{ background: 'var(--surface)' }}>
            {block.headers?.map((h, i) => (
              <th key={i} style={{
                padding: '12px 16px',
                fontFamily: 'DM Sans',
                fontSize: '12px',
                fontWeight: 600,
                textTransform: i === 0 ? 'uppercase' : 'none',
                color: 'var(--text-secondary)',
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, rIndex) => (
            <tr key={rIndex} style={{
              background: rIndex % 2 === 0 ? 'transparent' : 'var(--surface)',
              borderBottom: '1px solid var(--border-subtle)'
            }}>
              {row.map((cell, cIndex) => {
                const { color, text } = colorCodeValue(cell);
                return (
                  <td key={cIndex} style={{
                    padding: '12px 16px',
                    fontFamily: 'DM Sans',
                    fontSize: '14px',
                    fontWeight: cIndex === 0 ? 500 : 400,
                    color: cIndex === 0 ? 'var(--text-primary)' : color,
                  }}>
                    {text}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
