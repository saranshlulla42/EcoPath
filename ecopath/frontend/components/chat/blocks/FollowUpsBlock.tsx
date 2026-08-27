import { motion } from 'framer-motion';
import { useState } from 'react';
import { FollowUpsBlock as FollowUpsBlockType } from '../../../types/chat';

export function FollowUpsBlockView({ block, onSelect }: { block: FollowUpsBlockType, onSelect?: (text: string) => void }) {
  const [clicked, setClicked] = useState(false);

  if (!block.suggestions || block.suggestions.length === 0) return null;

  const handleClick = (s: string) => {
    if (clicked) return;
    setClicked(true);
    if (onSelect) onSelect(s);
  };

  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: '8px',
      marginTop: '16px',
    }}>
      {block.suggestions.map((s, index) => (
        <motion.div
          key={index}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.1 }}
        >
          <button
            onClick={() => handleClick(s)}
            disabled={clicked}
            style={{
              background: clicked ? 'var(--surface)' : 'var(--accent-muted)',
              border: `1px solid ${clicked ? 'var(--border-subtle)' : 'var(--accent-secondary)'}`,
              borderRadius: '9999px',
              padding: '8px 16px',
              fontFamily: 'DM Sans',
              fontSize: '13px',
              color: clicked ? 'var(--text-tertiary)' : 'var(--accent-primary)',
              cursor: clicked ? 'default' : 'pointer',
              transition: 'all 150ms ease',
              outline: 'none',
              transform: 'scale(1)' // default
            }}
            onMouseEnter={(e) => {
              if (!clicked) {
                e.currentTarget.style.background = 'var(--accent-primary)';
                e.currentTarget.style.color = 'var(--text-on-accent)';
                e.currentTarget.style.borderColor = 'var(--accent-primary)';
              }
            }}
            onMouseLeave={(e) => {
              if (!clicked) {
                e.currentTarget.style.background = 'var(--accent-muted)';
                e.currentTarget.style.color = 'var(--accent-primary)';
                e.currentTarget.style.borderColor = 'var(--accent-secondary)';
                e.currentTarget.style.transform = 'scale(1)';
              }
            }}
            onMouseDown={(e) => {
              if (!clicked) e.currentTarget.style.transform = 'scale(0.97)';
            }}
            onMouseUp={(e) => {
              if (!clicked) e.currentTarget.style.transform = 'scale(1)';
            }}
          >
            {s}
          </button>
        </motion.div>
      ))}
    </div>
  );
}
