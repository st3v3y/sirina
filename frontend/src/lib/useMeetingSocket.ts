import { useEffect, useRef, useState } from "react";

export type MeetingEvent =
  | { type: "segment"; segment: import("./api").Segment }
  | { type: "aspect"; summary: import("./api").Summary }
  | { type: "qa"; message: import("./api").QAMessage }
  | { type: "full_summary"; summary: import("./api").Summary }
  | { type: "status"; status: "recording" | "ended" };

export function useMeetingSocket(meetingId: number | null, onEvent: (e: MeetingEvent) => void) {
  const [connected, setConnected] = useState(false);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (meetingId == null) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/meetings/${meetingId}`);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as MeetingEvent;
        onEventRef.current(data);
      } catch {
        // ignore
      }
    };
    return () => ws.close();
  }, [meetingId]);

  return { connected };
}

export function useStatusSocket(onStatus: (s: import("./api").Status) => void) {
  const onStatusRef = useRef(onStatus);
  onStatusRef.current = onStatus;

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/status`);
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data?.type === "status") onStatusRef.current(data.payload);
      } catch {
        // ignore
      }
    };
    return () => ws.close();
  }, []);
}
