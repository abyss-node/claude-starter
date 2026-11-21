// Pure helpers around browser capture: no DOM, no AudioContext.

export function magnitudesFromDb(db) {
  const n = db && Number.isFinite(db.length) ? db.length : 0;
  const out = new Array(n);
  for (let i = 0; i < n; i++) {
    const v = Number(db[i]);
    out[i] = Number.isFinite(v) ? 10 ** (v / 20) : 0;
  }
  return out;
}

// One analysis frame from an AnalyserNode's dB spectrum (getFloatFrequencyData) and the two channel levels.
export function frameFromAnalyser({ db, sampleRate, time, left = 0, right = 0 }) {
  return { time, sampleRate, magnitudes: magnitudesFromDb(db), left, right };
}

export function detectSupport(env = globalThis) {
  const devices = env?.navigator?.mediaDevices;
  return {
    mic: typeof devices?.getUserMedia === 'function',
    display: typeof devices?.getDisplayMedia === 'function',
    file: true,
    record: typeof env?.MediaRecorder === 'function',
  };
}
