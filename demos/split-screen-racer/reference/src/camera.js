// Split-screen cameras as a pure function: canvas size + targets in, viewports out.

export function splitViewports(width, height, targets, { layout = 'side', scale = 1 } = {}) {
  let rects;
  if (targets.length <= 1) {
    rects = [{ x: 0, y: 0, w: width, h: height }];
  } else if (layout === 'stacked') {
    const h0 = Math.floor(height / 2);
    rects = [
      { x: 0, y: 0, w: width, h: h0 },
      { x: 0, y: h0, w: width, h: height - h0 },
    ];
  } else {
    const w0 = Math.floor(width / 2);
    rects = [
      { x: 0, y: 0, w: w0, h: height },
      { x: w0, y: 0, w: width - w0, h: height },
    ];
  }
  return rects.map((r, i) => ({ ...r, camX: targets[i]?.x ?? 0, camY: targets[i]?.y ?? 0, scale }));
}

export function worldToScreen(vp, wx, wy) {
  return {
    x: vp.x + vp.w / 2 + (wx - vp.camX) * vp.scale,
    y: vp.y + vp.h / 2 + (wy - vp.camY) * vp.scale,
  };
}
