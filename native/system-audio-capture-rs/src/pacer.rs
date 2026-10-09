//! Turns an irregular capture source into a continuous, real-time PCM stream.
//!
//! WASAPI loopback delivers no packets at all while nothing is playing. The backend
//! treats a track that stops growing as stalled and restarts the helper, so the output
//! must keep flowing at the real-time rate: captured samples go out as they arrive, and
//! once the source has been quiet for longer than a grace period the gap up to "now" is
//! filled with silence. The written sample count therefore follows wall-clock time.

use std::collections::VecDeque;

pub const SAMPLE_RATE: u64 = 48_000;
/// 20 ms, the block size the backend reads.
pub const BLOCK: usize = (SAMPLE_RATE / 50) as usize;
/// How long the source may deliver nothing before the gap is padded with silence.
/// Longer than any normal packet jitter, short enough that the watchdog never fires.
pub const GRACE: u64 = SAMPLE_RATE / 5; // 200 ms
/// Captured audio buffered beyond this is dropped (the source clock runs fast).
pub const MAX_BUFFER: usize = SAMPLE_RATE as usize; // 1 s

/// What to write next: `take` samples from the capture buffer, then `pad` zeros.
#[derive(Debug, PartialEq, Eq)]
pub struct Plan {
    pub take: usize,
    pub pad: usize,
}

/// Decide the next write. `expected` is how many samples real time says should have
/// been written since the start, `written` how many were, `available` how many are
/// buffered, and `starved` how many samples of time have passed since data last arrived.
pub fn plan(expected: u64, written: u64, available: usize, starved: u64) -> Plan {
    let take = available - available % BLOCK; // whole 20 ms blocks only
    let after = written + take as u64;
    let pad = if starved >= GRACE && after < expected {
        (expected - after) as usize
    } else {
        0
    };
    Plan { take, pad }
}

/// Append captured samples, dropping the oldest ones beyond `MAX_BUFFER`.
pub fn push(buffer: &mut VecDeque<i16>, samples: &[i16]) {
    buffer.extend(samples.iter().copied());
    let excess = buffer.len().saturating_sub(MAX_BUFFER);
    if excess > 0 {
        buffer.drain(..excess);
    }
}

/// Little-endian bytes for `take` samples from the buffer followed by `pad` zeros.
pub fn render(buffer: &mut VecDeque<i16>, p: &Plan) -> Vec<u8> {
    let mut out = Vec::with_capacity((p.take + p.pad) * 2);
    for s in buffer.drain(..p.take) {
        out.extend_from_slice(&s.to_le_bytes());
    }
    out.resize(out.len() + p.pad * 2, 0);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn steady_source_is_passed_through_in_blocks() {
        let p = plan(BLOCK as u64 * 3, 0, BLOCK * 2 + 100, 0);
        assert_eq!(p, Plan { take: BLOCK * 2, pad: 0 });
    }

    #[test]
    fn short_jitter_is_not_padded() {
        // 100 ms behind but data arrived 100 ms ago: wait for it, don't insert silence.
        let p = plan(SAMPLE_RATE, SAMPLE_RATE - 4_800, 0, 4_800);
        assert_eq!(p, Plan { take: 0, pad: 0 });
    }

    #[test]
    fn silent_source_is_padded_up_to_real_time() {
        // Nothing played for a minute: the stream must still be a minute long.
        let p = plan(SAMPLE_RATE * 60, SAMPLE_RATE * 59, 0, SAMPLE_RATE);
        assert_eq!(p, Plan { take: 0, pad: SAMPLE_RATE as usize });
    }

    #[test]
    fn padding_never_runs_ahead_of_real_time() {
        let p = plan(SAMPLE_RATE, SAMPLE_RATE, 0, GRACE * 10);
        assert_eq!(p.pad, 0);
    }

    #[test]
    fn buffered_data_goes_out_before_padding() {
        let p = plan(SAMPLE_RATE, 0, BLOCK, GRACE);
        assert_eq!(p, Plan { take: BLOCK, pad: SAMPLE_RATE as usize - BLOCK });
    }

    #[test]
    fn buffer_is_bounded() {
        let mut b = VecDeque::new();
        push(&mut b, &vec![1i16; MAX_BUFFER]);
        push(&mut b, &[2i16; 10]);
        assert_eq!(b.len(), MAX_BUFFER);
        assert_eq!(b.back(), Some(&2));
        assert_eq!(b.front(), Some(&1));
    }

    #[test]
    fn render_writes_samples_then_zeros() {
        let mut b: VecDeque<i16> = VecDeque::from(vec![1, -1, 7]);
        let bytes = render(&mut b, &Plan { take: 2, pad: 2 });
        assert_eq!(bytes, vec![1, 0, 0xff, 0xff, 0, 0, 0, 0]);
        assert_eq!(b, VecDeque::from(vec![7]));
    }
}
