import { motion } from 'framer-motion';
import React from 'react';

export function AnimatedBlockWrapper({
  children,
  index
}: {
  children: React.ReactNode;
  index: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.4,
        ease: [0.25, 0.46, 0.45, 0.94], // ease-out-quad — smooth deceleration
      }}
      style={{ marginBottom: '16px' }}
    >
      {children}
    </motion.div>
  );
}
