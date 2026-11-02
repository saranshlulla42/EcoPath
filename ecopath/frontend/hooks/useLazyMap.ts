'use client';

import { useEffect, useRef, useState, type RefObject } from 'react';

interface LazyMapState {
  /** True once the block has come near the viewport. Never goes back to false. */
  shouldRender: boolean;
  /** True while the block is actually on screen — drives animation pausing. */
  isInViewport: boolean;
}

/**
 * Defers creating a MapLibre instance until the block is close to the viewport,
 * and reports whether it is currently on screen.
 *
 * Every map is a WebGL context plus its own render loop, so a long conversation
 * with several map blocks will happily exhaust a mid-range device. Mounting late
 * and pausing off-screen animation keeps that cost proportional to what the user
 * is actually looking at.
 */
export function useLazyMap(containerRef: RefObject<HTMLElement | null>): LazyMapState {
  const [shouldRender, setShouldRender] = useState(false);
  const [isInViewport, setIsInViewport] = useState(false);
  const rendered = useRef(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // Without IntersectionObserver, render eagerly rather than never.
    if (typeof IntersectionObserver === 'undefined') {
      rendered.current = true;
      setShouldRender(true);
      setIsInViewport(true);
      return;
    }

    // Two thresholds: a 200px margin to warm the map up before it scrolls into
    // view, and a 0px margin for "is it really visible right now".
    const warmup = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !rendered.current) {
          rendered.current = true;
          setShouldRender(true);
          warmup.disconnect();
        }
      },
      { rootMargin: '200px' },
    );

    const visibility = new IntersectionObserver(
      ([entry]) => setIsInViewport(entry.isIntersecting),
      { rootMargin: '0px' },
    );

    warmup.observe(el);
    visibility.observe(el);

    return () => {
      warmup.disconnect();
      visibility.disconnect();
    };
  }, [containerRef]);

  return { shouldRender, isInViewport };
}
