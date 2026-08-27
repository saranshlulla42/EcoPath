import { motion } from 'framer-motion';

export function ThinkingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="thinking-indicator"
    >
      <span className="thinking-dot" />
      <span className="thinking-dot" />
      <span className="thinking-dot" />
      
      <style>{`
        .thinking-indicator {
          display: flex;
          gap: 4px;
          padding: 12px 0;
        }

        .thinking-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background-color: var(--accent-primary);
          animation: thinking-pulse 1.4s ease-in-out infinite;
        }

        .thinking-dot:nth-child(2) { animation-delay: 0.2s; }
        .thinking-dot:nth-child(3) { animation-delay: 0.4s; }

        @keyframes thinking-pulse {
          0%, 80%, 100% { opacity: 0.2; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </motion.div>
  );
}
