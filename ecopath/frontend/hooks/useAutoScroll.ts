import { useEffect, useRef } from 'react';

export function useAutoScroll<T extends HTMLElement>(dependencies: any[]) {
  const containerRef = useRef<T>(null);
  const isUserScrolledUp = useRef(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handleScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      isUserScrolledUp.current = distanceFromBottom > 100;
    };

    el.addEventListener('scroll', handleScroll);
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    if (!isUserScrolledUp.current && containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, dependencies);

  return containerRef;
}
