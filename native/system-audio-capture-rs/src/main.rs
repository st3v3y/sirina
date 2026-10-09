//! Captures the system audio output mix (what the user hears) on Windows and Linux and
//! streams it to stdout as raw PCM: 48 kHz, mono, signed 16-bit little-endian.
//!
//! Same contract as the macOS helper (`native/system-audio-capture/`):
//!   system-audio-capture [--exclude-pid PID]   capture until terminated
//!   system-audio-capture --probe               exit 0 if capture can run
//! Exit codes: 0 ok · 2 capture failed · 3 unavailable · 4 no output device / sound server.
//!
//! - Windows: WASAPI process loopback that leaves out `--exclude-pid`'s process tree
//!   (the desktop app), falling back to loopback of the default output device.
//! - Linux: the monitor of the default PulseAudio/PipeWire sink.
//!
//! The output never stalls (see `pacer`), and the helper exits once its stdout closes,
//! so it can't outlive a backend that died.

mod pacer;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(windows)]
mod windows;

use std::collections::VecDeque;
use std::io::Write;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

/// A capture failure, with the contract exit code it maps to.
#[derive(Debug)]
pub struct CaptureError {
    pub code: i32,
    pub message: String,
}

impl CaptureError {
    pub fn new(code: i32, message: impl Into<String>) -> Self {
        Self { code, message: message.into() }
    }
}

/// What the capture thread shares with the writer: buffered samples and when data last
/// arrived (in samples since start), or the error that ended capture.
pub struct Shared {
    pub buffer: VecDeque<i16>,
    pub last_data: u64,
    pub failed: Option<CaptureError>,
    start: Instant,
}

impl Shared {
    fn now_samples(&self) -> u64 {
        (self.start.elapsed().as_secs_f64() * pacer::SAMPLE_RATE as f64) as u64
    }

    /// Called by the capture thread with mono 48 kHz samples.
    pub fn deliver(&mut self, samples: &[i16]) {
        if samples.is_empty() {
            return;
        }
        pacer::push(&mut self.buffer, samples);
        self.last_data = self.now_samples();
    }
}

pub type SharedRef = Arc<Mutex<Shared>>;

/// Whether this platform's capture leaves the app's own audio out.
pub enum SelfExclusion {
    On,
    Off(&'static str),
}

/// Platform capture: `probe` checks that capture can start; `run` opens it, reports
/// self-exclusion, and then delivers samples until it fails.
#[cfg(windows)]
use windows as platform;
#[cfg(target_os = "linux")]
use linux as platform;

#[cfg(not(any(windows, target_os = "linux")))]
mod platform {
    use super::{CaptureError, SelfExclusion, SharedRef};

    pub fn probe(_exclude_pid: u32) -> Result<(), CaptureError> {
        Err(CaptureError::new(3, "unsupported platform (use the Swift helper on macOS)"))
    }

    pub fn run(_exclude_pid: u32, _shared: SharedRef, _ready: impl FnOnce(SelfExclusion)) -> CaptureError {
        CaptureError::new(3, "unsupported platform (use the Swift helper on macOS)")
    }
}

struct Args {
    probe: bool,
    exclude_pid: u32,
}

fn parse_args() -> Result<Args, String> {
    let mut args = Args { probe: false, exclude_pid: std::process::id() };
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--probe" => args.probe = true,
            "--exclude-pid" => {
                let v = it.next().ok_or("--exclude-pid needs a value")?;
                args.exclude_pid = v.parse().map_err(|_| format!("invalid pid: {v}"))?;
            }
            other => return Err(format!("unknown argument: {other}")),
        }
    }
    Ok(args)
}

fn fail(e: CaptureError) -> ! {
    eprintln!("{}", e.message);
    std::process::exit(e.code);
}

fn main() {
    let args = parse_args().unwrap_or_else(|e| fail(CaptureError::new(2, e)));
    if args.probe {
        match platform::probe(args.exclude_pid) {
            Ok(()) => std::process::exit(0),
            Err(e) => fail(e),
        }
    }

    let shared: SharedRef = Arc::new(Mutex::new(Shared {
        buffer: VecDeque::new(),
        last_data: 0,
        failed: None,
        start: Instant::now(),
    }));
    let capture_shared = shared.clone();
    let exclude_pid = args.exclude_pid;
    thread::Builder::new()
        .name("capture".into())
        .spawn(move || {
            let err = platform::run(exclude_pid, capture_shared.clone(), |mode| match mode {
                SelfExclusion::On => eprintln!("self-exclusion: on"),
                SelfExclusion::Off(why) => eprintln!("self-exclusion: off ({why})"),
            });
            capture_shared.lock().unwrap().failed = Some(err);
        })
        .expect("spawn capture thread");

    let mut stdout = std::io::stdout().lock();
    let mut written: u64 = 0;
    loop {
        thread::sleep(Duration::from_millis(20));
        let bytes = {
            let mut s = shared.lock().unwrap();
            if let Some(err) = s.failed.take() {
                drop(s);
                fail(err);
            }
            let now = s.now_samples();
            let starved = now.saturating_sub(s.last_data);
            let available = s.buffer.len();
            let p = pacer::plan(now, written, available, starved);
            written += (p.take + p.pad) as u64;
            pacer::render(&mut s.buffer, &p)
        };
        if bytes.is_empty() {
            continue;
        }
        if stdout.write_all(&bytes).and_then(|_| stdout.flush()).is_err() {
            // The reader (the backend) is gone: stop instead of capturing for nobody.
            std::process::exit(0);
        }
    }
}
