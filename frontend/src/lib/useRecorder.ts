import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ActiveInfo, type AudioDevice } from "./api";

const LS_MIC = "lastMicDevice";
const LS_SYSTEM = "lastSystemDevice";

function lsGet(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}
function lsSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* localStorage unavailable — ignore */
  }
}

/** Recording start + device selection + live-state polling, lifted out of the dashboard
 *  so the sidebar can offer Record from anywhere. Behavior is unchanged. */
export function useRecorder() {
  const nav = useNavigate();
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [device, setDevice] = useState("");
  const [systemDevice, setSystemDevice] = useState("");
  const [nativeAudio, setNativeAudio] = useState(false);
  const [title, setTitle] = useState("");
  const [picking, setPicking] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<ActiveInfo | null>(null);

  useEffect(() => {
    api
      .listAudioDevices()
      .then((d) => {
        setDevices(d);
        const names = new Set(d.map((x) => x.name));
        const savedMic = lsGet(LS_MIC);
        const savedSys = lsGet(LS_SYSTEM);
        const mic =
          (savedMic && names.has(savedMic) && savedMic) ||
          (d.find((x) => /microphone|mic/i.test(x.name)) ?? d[0])?.name ||
          "";
        setDevice(mic);
        setSystemDevice(savedSys && names.has(savedSys) ? savedSys : "");
      })
      .catch(() => setDevices([]));
    api.getAudioCapabilities().then((c) => setNativeAudio(c.native_system_audio)).catch(() => {});
  }, []);

  // Poll the active recording so the sidebar can show the live state from any screen.
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const a = await api.activeRecording();
        if (alive) setActive(a);
      } catch {
        /* ignore transient errors */
      }
    };
    poll();
    const t = setInterval(poll, 1000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const openPicker = useCallback(() => {
    setError(null);
    setPicking(true);
  }, []);
  const closePicker = useCallback(() => setPicking(false), []);

  const confirmStart = useCallback(async () => {
    const systemSource = nativeAudio ? "native" : systemDevice ? "device" : "none";
    if (!device && systemSource !== "native") {
      setError("Select a microphone (or, in the desktop app, system audio is automatic).");
      return;
    }
    setStarting(true);
    setError(null);
    try {
      lsSet(LS_MIC, device);
      if (!nativeAudio) lsSet(LS_SYSTEM, systemDevice);
      const { id } = await api.startRecording({
        title: title || undefined,
        device: device || undefined,
        system_device: nativeAudio ? undefined : systemDevice || undefined,
        system_source: systemSource,
      });
      setPicking(false);
      setStarting(false);
      setTitle("");
      nav(`/recordings/live/${id}`);
    } catch (e) {
      setError(String(e));
      setStarting(false);
    }
  }, [device, systemDevice, nativeAudio, title, nav]);

  return {
    devices, device, setDevice, systemDevice, setSystemDevice, nativeAudio,
    title, setTitle, picking, openPicker, closePicker, confirmStart, starting, error, active,
  };
}
