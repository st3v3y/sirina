import { useEffect, useRef } from "react";
import type { Status } from "./api";

export function useStatusSocket(onStatus: (s: Status) => void) {
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
