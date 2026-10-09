//! Windows: WASAPI loopback of everything the user hears.
//!
//! Preferred: process loopback (Windows 11, build 20348+) in exclude mode, which leaves
//! out the desktop app's process tree, including the WebView2 processes that play
//! recordings back. Fallback: loopback of the default render endpoint, which includes
//! everything. In both cases WASAPI converts to 48 kHz mono s16 for us (autoconvert).

use crate::{CaptureError, SelfExclusion, SharedRef};
use wasapi::{
    AudioCaptureClient, AudioClient, DeviceEnumerator, Direction, Handle, SampleType, StreamMode,
    WaveFormat, initialize_mta,
};

const SAMPLE_RATE: usize = 48_000;
/// 100 ms of buffering inside WASAPI.
const BUFFER_HNS: i64 = 1_000_000;

fn format() -> WaveFormat {
    WaveFormat::new(16, 16, &SampleType::Int, SAMPLE_RATE, 1, None)
}

fn mode() -> StreamMode {
    StreamMode::EventsShared { autoconvert: true, buffer_duration_hns: BUFFER_HNS }
}

struct Opened {
    client: AudioClient,
    capture: AudioCaptureClient,
    event: Handle,
    exclusion: SelfExclusion,
}

fn open_process_loopback(exclude_pid: u32) -> Result<Opened, String> {
    let mut client = AudioClient::new_application_loopback_client(exclude_pid, false)
        .map_err(|e| format!("process loopback unavailable: {e}"))?;
    client
        .initialize_client(&format(), &Direction::Capture, &mode())
        .map_err(|e| format!("process loopback init failed: {e}"))?;
    let event = client.set_get_eventhandle().map_err(|e| e.to_string())?;
    let capture = client.get_audiocaptureclient().map_err(|e| e.to_string())?;
    Ok(Opened { client, capture, event, exclusion: SelfExclusion::On })
}

fn open_endpoint_loopback() -> Result<Opened, CaptureError> {
    let no_device = |e: wasapi::WasapiError| CaptureError::new(4, format!("no audio output device: {e}"));
    let enumerator = DeviceEnumerator::new().map_err(|e| CaptureError::new(2, e.to_string()))?;
    let device = enumerator.get_default_device(&Direction::Render).map_err(no_device)?;
    let mut client = device.get_iaudioclient().map_err(no_device)?;
    client
        .initialize_client(&format(), &Direction::Capture, &mode())
        .map_err(|e| CaptureError::new(2, format!("loopback init failed: {e}")))?;
    let event = client.set_get_eventhandle().map_err(|e| CaptureError::new(2, e.to_string()))?;
    let capture = client.get_audiocaptureclient().map_err(|e| CaptureError::new(2, e.to_string()))?;
    Ok(Opened {
        client,
        capture,
        event,
        exclusion: SelfExclusion::Off("endpoint loopback; process loopback needs Windows 11"),
    })
}

/// WASAPI needs COM on the calling thread before any device call.
fn init_com() -> Result<(), CaptureError> {
    if initialize_mta().is_err() {
        return Err(CaptureError::new(2, "COM initialization failed"));
    }
    Ok(())
}

fn open(exclude_pid: u32) -> Result<Opened, CaptureError> {
    match open_process_loopback(exclude_pid) {
        Ok(o) => Ok(o),
        Err(why) => {
            eprintln!("{why}; using endpoint loopback");
            open_endpoint_loopback()
        }
    }
}

pub fn probe(exclude_pid: u32) -> Result<(), CaptureError> {
    init_com()?;
    // Process loopback can activate without any output device; the endpoint path tells
    // us whether there is something to capture at all.
    open_endpoint_loopback()?;
    let o = open(exclude_pid)?;
    o.client.start_stream().map_err(|e| CaptureError::new(2, e.to_string()))?;
    let _ = o.client.stop_stream();
    Ok(())
}

pub fn run(exclude_pid: u32, shared: SharedRef, ready: impl FnOnce(SelfExclusion)) -> CaptureError {
    if let Err(e) = init_com() {
        return e;
    }
    let o = match open(exclude_pid) {
        Ok(o) => o,
        Err(e) => return e,
    };
    if let Err(e) = o.client.start_stream() {
        return CaptureError::new(2, format!("could not start capture: {e}"));
    }
    ready(o.exclusion);

    let mut bytes = vec![0u8; SAMPLE_RATE * 2]; // 1 s, far more than one packet
    let mut samples: Vec<i16> = Vec::with_capacity(SAMPLE_RATE);
    loop {
        // Loopback signals no events while nothing plays; a timeout is normal here.
        let _ = o.event.wait_for_event(100);
        loop {
            let frames = match o.capture.get_next_packet_size() {
                Ok(n) => n.unwrap_or(0) as usize,
                // Typically AUDCLNT_E_DEVICE_INVALIDATED: the default device changed. Exit
                // non-zero; the backend restarts us on the new default and fills the gap.
                Err(e) => return CaptureError::new(2, format!("capture stopped: {e}")),
            };
            if frames == 0 {
                break;
            }
            let (got, info) = match o.capture.read_from_device(&mut bytes) {
                Ok(r) => r,
                Err(e) => return CaptureError::new(2, format!("capture read failed: {e}")),
            };
            let got = got as usize;
            samples.clear();
            if info.flags.silent {
                samples.resize(got, 0);
            } else {
                samples.extend(bytes[..got * 2].as_chunks::<2>().0.iter().map(|b| i16::from_le_bytes(*b)));
            }
            shared.lock().unwrap().deliver(&samples);
        }
    }
}
