// SPDX-License-Identifier: MPL-2.0
export type ScreenPoint = Readonly<{ x: number; y: number }>;
export type DirectedEdgePath = Readonly<{
  start: ScreenPoint;
  end: ScreenPoint;
  control: ScreenPoint;
  opposingOffset: number;
}>;

export const directedEdgePath = (
  start: ScreenPoint,
  end: ScreenPoint,
  hasOpposingDirection: boolean,
  offsetPixels = 6,
): DirectedEdgePath => {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.max(Math.hypot(dx, dy), 1);
  const offset = hasOpposingDirection ? offsetPixels : 0;
  const normalX = -dy / length;
  const normalY = dx / length;
  return {
    start: { x: start.x + normalX * offset, y: start.y + normalY * offset },
    end: { x: end.x + normalX * offset, y: end.y + normalY * offset },
    control: { x: (start.x + end.x) / 2 + normalX * offset, y: (start.y + end.y) / 2 + normalY * offset },
    opposingOffset: offset,
  };
};

export const pointOnQuadratic = (path: DirectedEdgePath, t: number): ScreenPoint => {
  const inverse = 1 - t;
  return {
    x: inverse * inverse * path.start.x + 2 * inverse * t * path.control.x + t * t * path.end.x,
    y: inverse * inverse * path.start.y + 2 * inverse * t * path.control.y + t * t * path.end.y,
  };
};

export const distanceToEdgePath = (point: ScreenPoint, path: DirectedEdgePath): number => {
  let minimum = Number.POSITIVE_INFINITY;
  for (let index = 0; index <= 24; index += 1) {
    const candidate = pointOnQuadratic(path, index / 24);
    minimum = Math.min(minimum, Math.hypot(point.x - candidate.x, point.y - candidate.y));
  }
  return minimum;
};
