"use client";

import { useEffect, useRef, useState } from "react";

interface BirdsInFlightCounterProps {
  value: number;
  label: string;
}

export function BirdsInFlightCounter({ value, label }: BirdsInFlightCounterProps) {
  const [displayValue, setDisplayValue] = useState(value);
  const previousValueRef = useRef(value);

  useEffect(() => {
    const from = previousValueRef.current;
    const to = Number.isFinite(value) ? value : 0;
    const duration = 600;
    const startedAt = performance.now();
    let frameId = 0;

    const tick = (now: number) => {
      const elapsed = Math.min((now - startedAt) / duration, 1);
      const eased = 1 - (1 - elapsed) ** 3;
      setDisplayValue(from + (to - from) * eased);

      if (elapsed < 1) {
        frameId = requestAnimationFrame(tick);
      } else {
        previousValueRef.current = to;
      }
    };

    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [value]);

  return (
    <div className="birds-counter">
      <span className="date-label">{label}</span>
      <div className="count-box">
        <strong>{displayValue.toFixed(1)}</strong>
        <span>million birds in flight</span>
      </div>
      <div className="map-title">Live Bird Migration</div>
    </div>
  );
}
