// Page wiring. Not graded.

import { createSynth } from './synth.js';
import { PRESETS } from './palette.js';
import { WARNING_TEXT, acknowledgeWarning, shouldShowWarning } from './safety.js';
import { detectSupport } from './capture.js';
import { createFrameReader, openDisplayAudio, openFile, openMic } from './audio.js';
import { createRenderer } from './render.js';

const $ = (id) => document.getElementById(id);
const stage = $('stage');
const status = $('status');
const support = detectSupport(globalThis);

function seedFromUrl() {
  const n = Number(new URLSearchParams(location.search).get('seed'));
  return Number.isInteger(n) && n >= 0 && n <= 4294967295 ? n : (Math.random() * 4294967296) >>> 0;
}

const synth = createSynth({ seed: seedFromUrl(), limiter: $('limiter').checked });
const draw = createRenderer(stage);
let ctx = null;
let reader = null;
let handle = null;
let recorder = null;

function fit() {
  stage.width = Math.floor(innerWidth * devicePixelRatio);
  stage.height = Math.floor(innerHeight * devicePixelRatio);
}
addEventListener('resize', fit);
fit();

for (const [name, p] of Object.entries(PRESETS)) {
  const o = document.createElement('option');
  o.value = name;
  o.textContent = p.label;
  $('preset').append(o);
}
$('preset').addEventListener('change', () => synth.setPreset($('preset').value));
$('limiter').addEventListener('change', () => {
  synth.setLimiter($('limiter').checked);
  status.textContent = $('limiter').checked ? 'Flash limiter on.' : 'Flash limiter OFF: flashes are not capped.';
});

// First run: the warning shows until it is acknowledged, and no source opens before that.
const fileInput = $('source-file');
function setSourcesEnabled(on) {
  $('source-mic').disabled = !(on && support.mic);
  $('source-tab').disabled = !(on && support.display);
  fileInput.disabled = !on;
}
let storage = null;
try {
  storage = localStorage;
} catch {
  storage = null;
}
$('warning-text').textContent = WARNING_TEXT;
if (shouldShowWarning(storage)) {
  setSourcesEnabled(false);
} else {
  $('warning').hidden = true;
  setSourcesEnabled(true);
}
$('warning-ok').addEventListener('click', () => {
  acknowledgeWarning(storage);
  $('warning').hidden = true;
  setSourcesEnabled(true);
});

// Support notes: capture varies by browser, so say what this one offers.
$('source-tab').title = 'Tab or device audio: supported in some desktop browsers only (Chromium-based ones share tab audio; others may not).';
$('support').textContent =
  `Microphone: ${support.mic ? 'yes' : 'no'}. Tab or device audio: ${support.display ? 'offered by this browser, but what it can share varies by browser and operating system' : 'not offered by this browser'}. Audio file: yes. Recording: ${support.record ? 'yes' : 'no'}.`;

async function start(open) {
  try {
    handle?.stop();
    reader?.close();
    ctx ??= new AudioContext();
    await ctx.resume();
    handle = await open(ctx);
    reader = createFrameReader(ctx, handle.node);
    status.textContent = 'Listening.';
  } catch (e) {
    status.textContent = `Could not start: ${e.message}`;
  }
}

$('source-mic').addEventListener('click', () => start(openMic));
$('source-tab').addEventListener('click', () => start(openDisplayAudio));
fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (file) start((c) => openFile(c, file));
});
document.addEventListener('dragover', (e) => e.preventDefault());
document.addEventListener('drop', (e) => {
  e.preventDefault();
  const file = e.dataTransfer?.files?.[0];
  if (file && !fileInput.disabled) start((c) => openFile(c, file));
});

$('record').disabled = !support.record;
$('record').addEventListener('click', () => {
  if (recorder) {
    recorder.stop();
    return;
  }
  const chunks = [];
  recorder = new MediaRecorder(stage.captureStream(30));
  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(chunks, { type: recorder.mimeType }));
    a.download = 'synesthesia.webm';
    a.click();
    recorder = null;
    $('record').textContent = 'Record';
  };
  recorder.start();
  $('record').textContent = 'Stop and save';
});

function loop(now) {
  const frame = reader ? reader.read(now / 1000) : { time: now / 1000, sampleRate: 44100, magnitudes: [] };
  draw(synth.push(frame));
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);
