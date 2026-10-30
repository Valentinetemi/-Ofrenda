/**
 * Ghost mode.
 *
 * The portrait is cut out once, on this machine (MediaPipe selfie segmentation,
 * or the colour-key fallback). The page receives one translucent PNG.
 *
 * The webcam never leaves the browser. Each frame we:
 *   1. Draw the camera, mirrored, like a mirror over the altar.
 *   2. Float the ancestor with the same sine as ofrenda/ghost.py `float_offset`
 *      (negative y is up; the side drift uses period * 1.7).
 *   3. Fade them in slowly, then let their light breathe a little, like a candle.
 *      The sprite already carries its low opacity (ofrenda/ghost.py); the fade
 *      and flicker here only ever dim it further, never brighten it.
 *   4. Leave a memory on a paper slip beside them.
 *
 * If there is no camera, they stand in a painted night instead. Still a visit.
 */

const FALLBACK_MOTION = {
  amplitude_px: 10,
  period_s: 3.2,
  drift: 0.28,
  opacity: 0.30,
  scale: 0.74,
  side: "right",
  fade_in_s: 2.5,
  flicker: 0.12,
  flicker_period_s: 2.6,
};

let raf = 0;
let stream = null;
let memoryIndex = 0;
let current = null;

function segmenterLabel(method) {
  if (method === "mediapipe") return "Cut out on this computer with the MediaPipe selfie segmenter.";
  if (method === "border") return "Cut out on this computer with a colour key. A real photograph against a plain wall, or any portrait, can use MediaPipe.";
  if (method === "ellipse") return "The cut-out was unsure, so the portrait fades in an oval. A clearer photograph will do better.";
  return "Cut out on this computer.";
}

function drawNight(ctx, width, height) {
  const sky = ctx.createLinearGradient(0, 0, 0, height);
  sky.addColorStop(0, "#1a0c12");
  sky.addColorStop(1, "#070406");
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "rgba(228, 162, 58, 0.35)";
  for (const [x, y, r] of [
    [width * 0.18, height * 0.72, 18],
    [width * 0.28, height * 0.8, 10],
    [width * 0.12, height * 0.84, 8],
  ]) {
    ctx.beginPath();
    ctx.ellipse(x, y, r, r * 0.55, 0, 0, Math.PI * 2);
    ctx.fill();
  }
}

function resizeCanvas(canvas) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = Math.max(1, Math.floor(width * dpr));
  canvas.height = Math.max(1, Math.floor(height * dpr));
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width, height };
}

function showMemory(person) {
  const quote = document.getElementById("memory-text");
  const who = document.getElementById("memory-who");
  const next = document.getElementById("memory-next");
  const memories = person.memories || [];
  if (!memories.length) {
    quote.textContent = "No story is written down yet. They are a face, for now.";
    who.textContent = person.name;
    next.hidden = true;
    return;
  }
  memoryIndex = memoryIndex % memories.length;
  quote.textContent = memories[memoryIndex];
  who.textContent = person.name;
  next.hidden = memories.length < 2;
}

function loop(canvas, video, sprite, motion) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const fadeMs = (motion.fade_in_s ?? 2.5) * 1000;
  const flicker = reduced ? 0 : motion.flicker ?? 0.12;
  const flickerPeriod = motion.flicker_period_s ?? 2.6;
  let started = null;
  const tick = (now) => {
    const { ctx, width, height } = resizeCanvas(canvas);
    if (video && video.readyState >= 2) {
      ctx.save();
      ctx.translate(width, 0);
      ctx.scale(-1, 1);
      ctx.drawImage(video, 0, 0, width, height);
      ctx.restore();
    } else {
      drawNight(ctx, width, height);
    }
    // Same placement as ofrenda/ghost.py float_offset.
    const t = now / 1000;
    const period = motion.period_s;
    const amplitude = motion.amplitude_px * (reduced ? 0.15 : 1);
    const y = Math.round(-amplitude * Math.sin((2 * Math.PI * t) / period));
    const x = Math.round(amplitude * motion.drift * Math.sin((2 * Math.PI * t) / (period * 1.7)));
    const targetH = height * motion.scale;
    const targetW = sprite.width * (targetH / sprite.height);
    const margin = width * 0.06;
    const left = motion.side === "left" ? margin + x : width - targetW - margin + x;
    const top = height * 0.16 + y;
    if (started === null) started = now;
    const progress = reduced ? 1 : Math.min(1, (now - started) / fadeMs);
    const fade = progress * progress * (3 - 2 * progress); // smoothstep
    // Two slow waves that never line up, so it reads as flame, not a pulse.
    const wave = 0.5 + 0.5 * (0.7 * Math.sin((2 * Math.PI * t) / flickerPeriod) + 0.3 * Math.sin((2 * Math.PI * t) / (flickerPeriod * 0.41)));
    ctx.globalAlpha = fade * (1 - flicker * wave);
    ctx.drawImage(sprite, left, top, targetW, targetH);
    ctx.globalAlpha = 1;
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
}

export async function openGhost(person) {
  closeGhost();
  current = person;
  const layer = document.getElementById("ghost");
  const canvas = document.getElementById("ghost-canvas");
  const kicker = document.getElementById("ghost-kicker");
  const note = document.getElementById("segmenter-note");
  layer.hidden = false;
  kicker.textContent = person.name;
  showMemory(person);
  note.textContent = "Bringing them forward…";

  const sprite = new Image();
  const response = await fetch(`${person.ghost_url}?v=${person.photo_mtime || 0}`);
  if (!response.ok) {
    note.textContent = "I couldn't make a ghost from that photograph.";
    return;
  }
  const method = response.headers.get("X-Segmenter") || "";
  const blob = await response.blob();
  sprite.src = URL.createObjectURL(blob);
  await sprite.decode();
  note.textContent = segmenterLabel(method);

  let motion = FALLBACK_MOTION;
  try {
    const fetched = await fetch("/api/ghost/motion");
    if (fetched.ok) motion = await fetched.json();
  } catch {
    motion = FALLBACK_MOTION;
  }

  const video = document.createElement("video");
  video.playsInline = true;
  video.muted = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
    video.srcObject = stream;
    await video.play();
  } catch {
    stream = null;
    note.textContent = `${segmenterLabel(method)} No camera, so they are standing by the altar.`;
  }
  loop(canvas, stream ? video : null, sprite, motion);
  document.getElementById("ghost-close").focus();
}

export function nextMemory() {
  if (!current || !(current.memories || []).length) return;
  memoryIndex += 1;
  showMemory(current);
}

export function closeGhost() {
  if (raf) cancelAnimationFrame(raf);
  raf = 0;
  if (stream) {
    for (const track of stream.getTracks()) track.stop();
    stream = null;
  }
  const layer = document.getElementById("ghost");
  if (layer) layer.hidden = true;
  current = null;
}
