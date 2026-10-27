import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { chatDayLabel } from "./coach-chat-format";

export function CoachChatHistory({ children, newestId, oldestId, ownLatest }: {
  children: ReactNode; newestId?: number; oldestId?: number; ownLatest: boolean;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const pointerInside = useRef(false);
  const interactionUntil = useRef(0);
  const dragging = useRef<{ pointer: number; y: number; top: number } | null>(null);
  const barTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const dateTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [barVisible, setBarVisible] = useState(false);
  const [dateVisible, setDateVisible] = useState(false);
  const [day, setDay] = useState("");
  const [bar, setBar] = useState({ height: 0, top: 0, max: 0, value: 0 });
  const previous = useRef({ newestId, oldestId, height: 0, initialized: false });

  function measure() {
    const el = viewport.current;
    if (!el) return;
    const max = Math.max(0, el.scrollHeight - el.clientHeight);
    const trackHeight = Math.max(0, el.clientHeight - 16);
    const height = Math.min(trackHeight, Math.max(28, trackHeight * el.clientHeight / el.scrollHeight));
    const value = Math.max(0, Math.min(max, el.scrollTop));
    setBar({ height, top: max ? (trackHeight - height) * value / max : 0, max, value });
    const top = el.getBoundingClientRect().top;
    const first = Array.from(el.querySelectorAll<HTMLElement>("[data-chat-day]"))
      .find((element) => element.getBoundingClientRect().bottom > top + 8);
    if (first) setDay(first.dataset.chatDay || "");
    previous.current.height = el.scrollHeight;
  }

  function showBar() {
    clearTimeout(barTimer.current);
    setBarVisible(true);
    barTimer.current = setTimeout(() => { if (!dragging.current) setBarVisible(false); }, 1100);
  }

  function markInteraction() { interactionUntil.current = Date.now() + 1500; }

  function handleScroll() {
    measure();
    if (Date.now() < interactionUntil.current || dragging.current) {
      if (pointerInside.current || dragging.current) showBar();
      clearTimeout(dateTimer.current);
      setDateVisible((viewport.current?.scrollTop || 0) > 4);
      dateTimer.current = setTimeout(() => setDateVisible(false), 1000);
    }
  }

  useLayoutEffect(() => {
    const el = viewport.current;
    if (!el) return;
    const prev = previous.current;
    if (!prev.initialized) {
      el.scrollTop = el.scrollHeight;
    } else if (oldestId !== prev.oldestId && newestId === prev.newestId) {
      // Keep the same message in view when older history is prepended.
      el.scrollTop += el.scrollHeight - prev.height;
    } else if (newestId !== prev.newestId && (ownLatest || prev.height - el.scrollTop - el.clientHeight < 64)) {
      el.scrollTop = el.scrollHeight;
    }
    previous.current = { newestId, oldestId, height: el.scrollHeight, initialized: true };
    measure();
  }, [newestId, oldestId, ownLatest]);

  useLayoutEffect(() => {
    const observer = new ResizeObserver(measure);
    if (viewport.current) observer.observe(viewport.current);
    if (content.current) observer.observe(content.current);
    return () => {
      observer.disconnect();
      clearTimeout(barTimer.current);
      clearTimeout(dateTimer.current);
    };
  }, []);

  return (
    <div className="coach-chat-history"
      onPointerEnter={() => { pointerInside.current = true; showBar(); }}
      onPointerMove={(event) => { if (event.pointerType === "mouse" && !dragging.current) showBar(); }}
      onPointerLeave={() => {
        pointerInside.current = false;
        if (!dragging.current) { clearTimeout(barTimer.current); setBarVisible(false); }
      }}>
      <div ref={viewport} id="coach-chat-history" className="coach-chat-messages" role="log"
        aria-label="Переписка" tabIndex={0} onScroll={handleScroll}
        onWheel={() => { markInteraction(); if (pointerInside.current) showBar(); }}
        onTouchStart={markInteraction} onTouchMove={markInteraction} onPointerDown={markInteraction}
        onKeyDown={markInteraction}>
        <div ref={content} className="coach-chat-content">{children}</div>
      </div>
      <div className={`coach-chat-floating-date ${dateVisible && day ? "is-visible" : ""}`} aria-hidden="true">
        {day && chatDayLabel(day)}
      </div>
      {bar.max > 0 && (
        <div ref={track} className={`coach-chat-scrollbar ${barVisible ? "is-visible" : ""}`}
          onPointerDown={(event) => {
            event.preventDefault();
            const el = viewport.current;
            if (!el || !track.current) return;
            markInteraction();
            if (event.target === event.currentTarget) {
              const y = event.clientY - track.current.getBoundingClientRect().top - bar.height / 2;
              el.scrollTop = y / Math.max(1, track.current.clientHeight - bar.height) * bar.max;
            }
            dragging.current = { pointer: event.pointerId, y: event.clientY, top: el.scrollTop };
            event.currentTarget.setPointerCapture(event.pointerId);
            showBar();
          }}
          onPointerMove={(event) => {
            const drag = dragging.current;
            if (!drag || drag.pointer !== event.pointerId || !viewport.current || !track.current) return;
            viewport.current.scrollTop = drag.top + (event.clientY - drag.y)
              * bar.max / Math.max(1, track.current.clientHeight - bar.height);
          }}
          onLostPointerCapture={() => { dragging.current = null; showBar(); }}
          onPointerUp={(event) => {
            dragging.current = null;
            event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onPointerCancel={() => { dragging.current = null; showBar(); }}>
          <div className="coach-chat-scrollbar-thumb" role="scrollbar" aria-label="Прокрутка переписки"
            aria-controls="coach-chat-history" aria-orientation="vertical" aria-valuemin={0}
            aria-valuemax={Math.round(bar.max)} aria-valuenow={Math.round(bar.value)}
            style={{ height: bar.height, transform: `translateY(${bar.top}px)` }} />
        </div>
      )}
    </div>
  );
}
