import { useEffect, useEffectEvent } from "react";
import type { Status } from "./api";

export function useStatusSocket(onStatus: (s: Status) => void) {
  const onStatusEvent = useEffectEvent(onStatus);

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/status`);
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data?.type === "status") onStatusEvent(data.payload);
      } catch {
        // ignore
      }
    };
    return () => ws.close();
  }, []);
}
