// Browser capture: mic, tab or device audio, or a dropped file, read as analysis frames. Not graded.

import { frameFromAnalyser } from './capture.js';

function rms(buffer) {
  let sum = 0;
  for (let i = 0; i < buffer.length; i++) sum += buffer[i] * buffer[i];
  return Math.sqrt(sum / buffer.length);
}

// Reads frames from an audio node. `read(time)` returns a frame; `close()` disconnects.
export function createFrameReader(ctx, node) {
  const spectrum = ctx.createAnalyser();
  spectrum.fftSize = 4096;
  spectrum.smoothingTimeConstant = 0;
  node.connect(spectrum);

  const splitter = ctx.createChannelSplitter(2);
  const leftTap = ctx.createAnalyser();
  const rightTap = ctx.createAnalyser();
  leftTap.fftSize = rightTap.fftSize = 1024;
  node.connect(splitter);
  splitter.connect(leftTap, 0);
  splitter.connect(rightTap, 1);

  const db = new Float32Array(spectrum.frequencyBinCount);
  const lBuf = new Float32Array(leftTap.fftSize);
  const rBuf = new Float32Array(rightTap.fftSize);

  return {
    read(time) {
      spectrum.getFloatFrequencyData(db);
      leftTap.getFloatTimeDomainData(lBuf);
      rightTap.getFloatTimeDomainData(rBuf);
      const left = rms(lBuf);
      const right = node.channelCount < 2 ? left : rms(rBuf);
      return frameFromAnalyser({ db, sampleRate: ctx.sampleRate, time, left, right });
    },
    close() {
      for (const n of [spectrum, splitter, leftTap, rightTap]) n.disconnect();
      try {
        node.disconnect(spectrum);
        node.disconnect(splitter);
      } catch {
        // already disconnected
      }
    },
  };
}

export async function openMic(ctx) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
  });
  return { node: ctx.createMediaStreamSource(stream), stop: () => stream.getTracks().forEach((t) => t.stop()) };
}

// Tab or device audio. Browsers insist on a video track in the request; it is dropped at once.
export async function openDisplayAudio(ctx) {
  const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true });
  stream.getVideoTracks().forEach((t) => t.stop());
  if (stream.getAudioTracks().length === 0) {
    stream.getTracks().forEach((t) => t.stop());
    throw new Error('No audio was shared. Choose a tab (or the whole screen on Windows) and tick "share audio".');
  }
  return { node: ctx.createMediaStreamSource(stream), stop: () => stream.getTracks().forEach((t) => t.stop()) };
}

export async function openFile(ctx, file) {
  const buffer = await ctx.decodeAudioData(await file.arrayBuffer());
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);
  source.start();
  return { node: source, stop: () => source.stop() };
}
