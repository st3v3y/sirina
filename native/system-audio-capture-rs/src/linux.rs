//! Linux: the monitor of the default sink, through the PulseAudio API (served natively by
//! PulseAudio, and by PipeWire through pipewire-pulse). The server converts to 48 kHz
//! mono s16 for us. The app's own audio can't be left out here.

use crate::{CaptureError, SelfExclusion, SharedRef};
use libpulse_binding::def::BufferAttr;
use libpulse_binding::sample::{Format, Spec};
use libpulse_binding::stream::Direction;
use libpulse_simple_binding::Simple;

const SAMPLE_RATE: u32 = 48_000;
/// 20 ms per read, matching the backend's block size.
const FRAGMENT_BYTES: u32 = SAMPLE_RATE / 50 * 2;

fn open() -> Result<Simple, CaptureError> {
    let spec = Spec { format: Format::S16le, rate: SAMPLE_RATE, channels: 1 };
    // Without an explicit fragment size the server may hand out seconds-long reads.
    let attr = BufferAttr {
        maxlength: u32::MAX,
        tlength: u32::MAX,
        prebuf: u32::MAX,
        minreq: u32::MAX,
        fragsize: FRAGMENT_BYTES,
    };
    Simple::new(
        None,
        "Sirina",
        Direction::Record,
        Some("@DEFAULT_MONITOR@"),
        "System audio",
        &spec,
        None,
        Some(&attr),
    )
    .map_err(|e| {
        let msg = e.to_string().unwrap_or_else(|| format!("error {}", e.0));
        CaptureError::new(4, format!("no PulseAudio/PipeWire server ({msg})"))
    })
}

pub fn probe(_exclude_pid: u32) -> Result<(), CaptureError> {
    open().map(|_| ())
}

pub fn run(_exclude_pid: u32, shared: SharedRef, ready: impl FnOnce(SelfExclusion)) -> CaptureError {
    let stream = match open() {
        Ok(s) => s,
        Err(e) => return e,
    };
    ready(SelfExclusion::Off("not supported on Linux"));
    let mut bytes = vec![0u8; FRAGMENT_BYTES as usize];
    let mut samples: Vec<i16> = Vec::with_capacity(bytes.len() / 2);
    loop {
        if let Err(e) = stream.read(&mut bytes) {
            let msg = e.to_string().unwrap_or_else(|| format!("error {}", e.0));
            return CaptureError::new(2, format!("capture read failed: {msg}"));
        }
        samples.clear();
        samples.extend(bytes.as_chunks::<2>().0.iter().map(|b| i16::from_le_bytes(*b)));
        shared.lock().unwrap().deliver(&samples);
    }
}
