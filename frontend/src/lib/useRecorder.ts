import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ActiveInfo, type AudioCapabilities, type AudioDevice } from "./api";

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
  const [caps, setCaps] = useState<AudioCapabilities | null>(null);
  // Per-recording speech options, pre-set from Settings each time the dialog opens.
  const [liveTranscribe, setLiveTranscribe] = useState(false);
  const [liveCaptions, setLiveCaptions] = useState(false);
  const [title, setTitle] = useState("");
  const [picking, setPicking] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<ActiveInfo | null>(null);

  // Load (or reload) the device list. `refresh` asks the backend to re-enumerate PortAudio
  // so a device connected after startup (e.g. Bluetooth headphones) shows up. We always
  // update the list but only fill a default into fields the user hasn't set, so a poll
  // never clobbers an in-progress choice.
  const loadDevices = useCallback((refresh = false) => {
    api
      .listAudioDevices(refresh)
      .then((d) => {
        setDevices(d);
        const names = new Set(d.map((x) => x.name));
        setDevice((cur) => {
          if (cur && names.has(cur)) return cur;
          const savedMic = lsGet(LS_MIC);
          return (
            (savedMic && names.has(savedMic) && savedMic) ||
            (d.find((x) => /microphone|mic/i.test(x.name)) ?? d[0])?.name ||
            ""
          );
        });
        setSystemDevice((cur) => {
          if (cur && names.has(cur)) return cur;
          const savedSys = lsGet(LS_SYSTEM);
          return savedSys && names.has(savedSys) ? savedSys : "";
        });
      })
      .catch(() => setDevices([]));
  }, []);

  useEffect(() => {
    loadDevices();
    api.getAudioCapabilities().then((c) => setNativeAudio(c.native_system_audio)).catch(() => {});
  }, [loadDevices]);

  // Fresh defaults + availability whenever the dialog opens (Settings may have changed).
  useEffect(() => {
    if (!picking) return;
    api
      .getAudioCapabilities()
      .then((c) => {
        setCaps(c);
        setNativeAudio(c.native_system_audio);
        setLiveTranscribe(Boolean(c.live_transcribe_available && c.live_transcribe_default));
        setLiveCaptions(Boolean(c.captions_available && c.live_captions_default));
      })
      .catch(() => {});
  }, [picking]);

  // While the picker is open, poll for device changes (with backend re-enumeration) so a
  // just-connected mic appears without reopening the app.
  useEffect(() => {
    if (!picking) return;
    loadDevices(true);
    const t = setInterval(() => loadDevices(true), 3000);
    return () => clearInterval(t);
  }, [picking, loadDevices]);

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
    // Faster while captions are on, so they appear within about a second.
    const t = setInterval(poll, active?.live_captions ? 500 : 1000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [active?.live_captions]);

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
        live_transcribe: liveTranscribe,
        live_captions: liveCaptions,
      });
      setPicking(false);
      setStarting(false);
      setTitle("");
      nav(`/recordings/live/${id}`);
    } catch (e) {
      setError(String(e));
      setStarting(false);
    }
  }, [device, systemDevice, nativeAudio, title, nav, liveTranscribe, liveCaptions]);

  return {
    devices, device, setDevice, systemDevice, setSystemDevice, nativeAudio,
    title, setTitle, picking, openPicker, closePicker, confirmStart, starting, error, active,
    caps, liveTranscribe, setLiveTranscribe, liveCaptions, setLiveCaptions,
  };
}
