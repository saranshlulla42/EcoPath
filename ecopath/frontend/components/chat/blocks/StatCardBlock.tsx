import { useEffect, useState } from 'react';
import { StatCardBlock as StatCardBlockType } from '../../../types/chat';

function AnimatedNumber({ value }: { value: string }) {
  const [displayValue, setDisplayValue] = useState(value);

  useEffect(() => {
    const match = value.match(/([^\d-]*)([-]?\d+(?:\.\d+)?)(.*)/);
    
    // Check if it's a year heuristic
    const num = match ? parseFloat(match[2]) : null;
    const isYear = num !== null && num >= 1900 && num <= 2100;

    if (match && !isYear) {
      const prefix = match[1];
      const target = parseFloat(match[2]);
      const suffix = match[3];
      const isDecimal = match[2].includes('.');

      let start = 0;
      const duration = 1500;
      let startTime: number | null = null;

      const animate = (time: number) => {
        if (!startTime) startTime = time;
        const progress = Math.min((time - startTime) / duration, 1);
        
        // ease-out curve
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const current = start + (target - start) * easeOut;
        
        const formattedCurrent = isDecimal ? current.toFixed(1) : Math.round(current).toString();
        setDisplayValue(`${prefix}${formattedCurrent}${suffix}`);

        if (progress < 1) {
          requestAnimationFrame(animate);
        } else {
          setDisplayValue(value);
        }
      };
      
      requestAnimationFrame(animate);
    } else {
      setDisplayValue(value);
    }
  }, [value]);

  return <>{displayValue}</>;
}

export function StatCardBlockView({ block }: { block: StatCardBlockType }) {
  if (!block.stats || block.stats.length === 0) return null;

  return (
    <div style={{
      display: 'flex',
      gap: '12px',
      flexWrap: 'wrap',
      marginTop: '16px',
    }}>
      {block.stats.map((stat, i) => (
        <div key={i} style={{
          flex: '1 1 calc(50% - 12px)',
          minWidth: '140px',
          border: '1px solid var(--border)',
          borderRadius: '12px',
          padding: '16px 20px',
          background: 'var(--surface-raised)',
          boxShadow: 'var(--shadow-card)',
        }}>
          <div style={{
            fontFamily: 'DM Sans',
            fontSize: '11px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: 'var(--text-tertiary)',
            marginBottom: '8px'
          }}>
            {stat.label}
          </div>
          <div style={{
            fontFamily: 'DM Sans',
            fontSize: '28px',
            fontWeight: 700,
            color: 'var(--text-primary)',
            lineHeight: 1.2
          }}>
            <AnimatedNumber value={stat.value} />
          </div>
          {stat.detail && (
            <div style={{
              fontFamily: 'DM Sans',
              fontSize: '12px',
              color: 'var(--text-secondary)',
              marginTop: '4px'
            }}>
              {stat.detail}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
