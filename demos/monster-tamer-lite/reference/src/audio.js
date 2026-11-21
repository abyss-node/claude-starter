// Synthesised sound only: oscillators, no sample files.
const SCALE = [0, 3, 5, 7, 10, 12, 15];
const ROOT = 196;

export function createAudio() {
  let ctx = null;
  let on = false;
  let timer = null;
  let step = 0;

  function ensure() {
    if (!ctx && typeof AudioContext !== 'undefined') ctx = new AudioContext();
    return ctx;
  }
  function tone(freq, dur, type = 'square', gain = 0.05) {
    const c = ensure();
    if (!c || !on) return;
    const o = c.createOscillator();
    const g = c.createGain();
    o.type = type;
    o.frequency.value = freq;
    g.gain.setValueAtTime(gain, c.currentTime);
    g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + dur);
    o.connect(g).connect(c.destination);
    o.start();
    o.stop(c.currentTime + dur);
  }
  const note = (semi) => ROOT * 2 ** (semi / 12);
  return {
    get on() { return on; },
    toggle() {
      on = !on;
      if (on) {
        ensure();
        timer = setInterval(() => {
          const pattern = [0, 2, 4, 2, 1, 3, 5, 3];
          tone(note(SCALE[pattern[step % pattern.length]]), 0.22, 'triangle', 0.04);
          step++;
        }, 260);
      } else if (timer) {
        clearInterval(timer);
        timer = null;
      }
      return on;
    },
    hit() { tone(140, 0.12, 'sawtooth', 0.07); },
    heal() { tone(note(12), 0.2, 'sine', 0.06); tone(note(19), 0.3, 'sine', 0.05); },
    levelUp() { [0, 4, 7, 12].forEach((s, i) => setTimeout(() => tone(note(s + 12), 0.18, 'square', 0.05), i * 110)); },
    catchOk() { [7, 12, 16].forEach((s, i) => setTimeout(() => tone(note(s + 12), 0.15, 'square', 0.05), i * 90)); },
  };
}
