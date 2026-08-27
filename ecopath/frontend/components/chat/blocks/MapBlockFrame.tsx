'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useLazyMap } from '../../../hooks/useLazyMap';
import { CHAT_MAP_HEIGHT, CHAT_MAP_MOBILE_HEIGHT, MOBILE_BREAKPOINT } from './map-config';

/** Chat maps shrink on narrow viewports so they don't dominate the message. */
function useMapHeight(): number {
  const [height, setHeight] = useState(CHAT_MAP_HEIGHT);

  useEffect(() => {
    const query = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`);
    const apply = () => setHeight(query.matches ? CHAT_MAP_MOBILE_HEIGHT : CHAT_MAP_HEIGHT);
    apply();
    query.addEventListener('change', apply);
    return () => query.removeEventListener('change', apply);
  }, []);

  return height;
}

export interface MapFrameContext {
  height: number;
  /** False while the map is scrolled off screen — pause animation loops. */
  isInViewport: boolean;
}

/**
 * The chrome shared by both chat map blocks: title, rounded clipping frame,
 * lazy mount, and the narrative caption.
 *
 * `children` is a render prop so the map itself is never constructed — and so
 * never creates a WebGL context — until the block nears the viewport.
 */
export function MapBlockFrame({
  title,
  narrative,
  children,
}: {
  title?: string;
  narrative?: string;
  children: (ctx: MapFrameContext) => React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { shouldRender, isInViewport } = useLazyMap(containerRef);
  const height = useMapHeight();

  return (
    <div className="map-block-container">
      {title && <p className="map-block-title">{title}</p>}
      <div className="map-block-frame">
        <div ref={containerRef} className="map-block-canvas" style={{ height }}>
          {shouldRender ? (
            children({ height, isInViewport })
          ) : (
            <div className="map-skeleton" style={{ height }} />
          )}
        </div>
        {narrative && <p className="map-block-caption">{narrative}</p>}
      </div>
    </div>
  );
}

/**
 * Guards hover handlers against a touch interaction.
 *
 * MapLibre synthesises `mousemove` → `mousedown` → `mouseup` → `click` after a
 * tap. Without this, the synthetic mousemove opens the tooltip and the click
 * that follows immediately toggles it shut, so a tap appears to do nothing.
 * Emulated mouse events arrive within a few hundred ms of the touch; genuine
 * mouse movement later on is still treated as hover, which keeps hybrid
 * touch-and-trackpad devices working.
 */
const EMULATED_MOUSE_WINDOW_MS = 700;

export function useTouchGuard() {
  const lastTouch = useRef(0);
  const markTouch = useCallback(() => {
    lastTouch.current = Date.now();
  }, []);
  const isEmulatedMouse = useCallback(
    () => Date.now() - lastTouch.current < EMULATED_MOUSE_WINDOW_MS,
    [],
  );
  return { markTouch, isEmulatedMouse };
}

/** Small dark notice rendered over a map that could not fully load. */
export function MapNotice({ children }: { children: React.ReactNode }) {
  return <div className="map-notice">{children}</div>;
}
