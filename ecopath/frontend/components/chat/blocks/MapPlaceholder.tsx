import { MapPin } from 'lucide-react';
import { MapHighlightBlock, MigrationMapBlock } from '../../../types/chat';

export function MapPlaceholder({ block }: { block: MapHighlightBlock | MigrationMapBlock }) {
  const isMigration = block.type === 'migration_map';

  return (
    <div style={{
      width: '100%',
      height: '240px',
      border: '1px solid var(--border)',
      borderRadius: '12px',
      background: 'var(--surface)',
      marginTop: '16px',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '12px',
    }}>
      <MapPin size={32} color="var(--text-tertiary)" />

      <div style={{
        fontFamily: 'DM Sans',
        fontSize: '14px',
        color: 'var(--text-primary)',
        fontWeight: 500,
        textAlign: 'center'
      }}>
        {isMigration ? `Migration Map: ${block.species}` : (block as MapHighlightBlock).title}
      </div>

      <div style={{ display: 'flex', gap: '8px' }}>
        {isMigration ? (
           <span style={{
             padding: '2px 8px',
             background: 'var(--accent-muted)',
             borderRadius: '4px',
             fontSize: '11px',
             fontFamily: 'DM Sans',
             color: 'var(--text-secondary)'
           }}>
             {block.species}
           </span>
        ) : (
          (block as MapHighlightBlock).regions?.map(r => (
            <span key={r.code} style={{
              padding: '2px 8px',
              background: 'var(--accent-muted)',
              borderRadius: '4px',
              fontSize: '11px',
              fontFamily: 'DM Sans',
              color: 'var(--text-secondary)'
            }}>
              {r.name || r.code}
            </span>
          ))
        )}
      </div>

      <div style={{
        fontFamily: 'DM Sans',
        fontSize: '12px',
        color: 'var(--text-tertiary)',
      }}>
        Map visualization coming soon
      </div>
    </div>
  );
}
