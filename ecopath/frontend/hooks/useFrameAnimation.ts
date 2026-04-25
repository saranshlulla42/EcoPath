"use client";

import { useCallback, useEffect, useState, useRef } from "react";

interface UseFrameAnimationOptions {
  totalFrames: number;
  intervalMs?: number;
  initialFrame?: number;
}

export function useFrameAnimation({
  totalFrames,
  intervalMs = 800,
  initialFrame = 0,
}: UseFrameAnimationOptions) {
  const [currentFrame, setCurrentFrame] = useState(initialFrame);
  const [isPlaying, setIsPlaying] = useState(false);
  const [frameProgress, setFrameProgress] = useState(0);

  const animationRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const isPlayingRef = useRef(isPlaying);
  
  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  const clampFrame = useCallback(
    (frame: number) => {
      if (totalFrames <= 0) return 0;
      return Math.min(Math.max(frame, 0), totalFrames - 1);
    },
    [totalFrames]
  );

  const setFrame = useCallback(
    (frame: number) => {
      setCurrentFrame(clampFrame(frame));
      setFrameProgress(0);
      startTimeRef.current = null;
    },
    [clampFrame]
  );

  const next = useCallback(() => {
    setCurrentFrame((frame) => {
      if (totalFrames <= 0) return 0;
      return frame >= totalFrames - 1 ? 0 : frame + 1;
    });
    setFrameProgress(0);
    startTimeRef.current = null;
  }, [totalFrames]);

  const prev = useCallback(() => {
    setCurrentFrame((frame) => {
      if (totalFrames <= 0) return 0;
      return frame <= 0 ? totalFrames - 1 : frame - 1;
    });
    setFrameProgress(0);
    startTimeRef.current = null;
  }, [totalFrames]);

  const reset = useCallback(() => {
    setCurrentFrame(0);
    setFrameProgress(0);
    startTimeRef.current = null;
  }, []);

  const play = useCallback(() => {
    if (totalFrames > 1) setIsPlaying(true);
  }, [totalFrames]);

  const pause = useCallback(() => {
    setIsPlaying(false);
  }, []);

  useEffect(() => {
    if (!isPlaying || totalFrames <= 1) {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
      return;
    }

    const tick = (timestamp: number) => {
      if (!isPlayingRef.current) return;
      if (!startTimeRef.current) startTimeRef.current = timestamp;
      
      const elapsed = timestamp - startTimeRef.current;
      if (elapsed >= intervalMs) {
        setCurrentFrame((f) => (f >= totalFrames - 1 ? 0 : f + 1));
        setFrameProgress(0);
        startTimeRef.current = timestamp;
      } else {
        setFrameProgress(elapsed / intervalMs);
      }
      animationRef.current = requestAnimationFrame(tick);
    };

    animationRef.current = requestAnimationFrame(tick);
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [intervalMs, isPlaying, totalFrames]);

  return {
    currentFrame,
    isPlaying,
    frameProgress,
    play,
    pause,
    next,
    prev,
    reset,
    setFrame,
  };
}
