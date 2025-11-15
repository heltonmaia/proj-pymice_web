import type { ROI, RectangleROI, CircleROI, PolygonROI } from '@/types'

/**
 * Draw ROI on canvas
 */
export function drawROI(
  ctx: CanvasRenderingContext2D,
  roi: ROI,
  color: string = '#00ff00',
  lineWidth: number = 2,
  fill: boolean = false,
  fillAlpha: number = 0.2
) {
  ctx.strokeStyle = color
  ctx.lineWidth = lineWidth

  if (fill) {
    ctx.fillStyle = color + Math.floor(fillAlpha * 255).toString(16).padStart(2, '0')
  }

  switch (roi.roi_type) {
    case 'Rectangle':
      drawRectangle(ctx, roi as RectangleROI, fill)
      break
    case 'Circle':
      drawCircle(ctx, roi as CircleROI, fill)
      break
    case 'Polygon':
      drawPolygon(ctx, roi as PolygonROI, fill)
      break
  }
}

function drawRectangle(ctx: CanvasRenderingContext2D, roi: RectangleROI, fill: boolean) {
  const x = roi.center_x - roi.width / 2
  const y = roi.center_y - roi.height / 2

  if (fill) {
    ctx.fillRect(x, y, roi.width, roi.height)
  }
  ctx.strokeRect(x, y, roi.width, roi.height)
}

function drawCircle(ctx: CanvasRenderingContext2D, roi: CircleROI, fill: boolean) {
  ctx.beginPath()
  ctx.arc(roi.center_x, roi.center_y, roi.radius, 0, 2 * Math.PI)
  if (fill) {
    ctx.fill()
  }
  ctx.stroke()
}

function drawPolygon(ctx: CanvasRenderingContext2D, roi: PolygonROI, fill: boolean) {
  if (roi.vertices.length < 3) return

  ctx.beginPath()
  ctx.moveTo(roi.vertices[0][0], roi.vertices[0][1])

  for (let i = 1; i < roi.vertices.length; i++) {
    ctx.lineTo(roi.vertices[i][0], roi.vertices[i][1])
  }

  ctx.closePath()

  if (fill) {
    ctx.fill()
  }
  ctx.stroke()
}

/**
 * Check if point is inside ROI
 */
export function isPointInROI(x: number, y: number, roi: ROI): boolean {
  switch (roi.roi_type) {
    case 'Rectangle':
      return isPointInRectangle(x, y, roi as RectangleROI)
    case 'Circle':
      return isPointInCircle(x, y, roi as CircleROI)
    case 'Polygon':
      return isPointInPolygon(x, y, roi as PolygonROI)
    default:
      return false
  }
}

function isPointInRectangle(x: number, y: number, roi: RectangleROI): boolean {
  const left = roi.center_x - roi.width / 2
  const right = roi.center_x + roi.width / 2
  const top = roi.center_y - roi.height / 2
  const bottom = roi.center_y + roi.height / 2

  return x >= left && x <= right && y >= top && y <= bottom
}

function isPointInCircle(x: number, y: number, roi: CircleROI): boolean {
  const dx = x - roi.center_x
  const dy = y - roi.center_y
  return Math.sqrt(dx * dx + dy * dy) <= roi.radius
}

function isPointInPolygon(x: number, y: number, roi: PolygonROI): boolean {
  const vertices = roi.vertices
  let inside = false

  for (let i = 0, j = vertices.length - 1; i < vertices.length; j = i++) {
    const xi = vertices[i][0]
    const yi = vertices[i][1]
    const xj = vertices[j][0]
    const yj = vertices[j][1]

    const intersect = ((yi > y) !== (yj > y)) &&
      (x < (xj - xi) * (y - yi) / (yj - yi) + xi)

    if (intersect) inside = !inside
  }

  return inside
}

/**
 * Draw centroid point
 */
export function drawCentroid(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  color: string = '#ff0000',
  size: number = 5
) {
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(x, y, size, 0, 2 * Math.PI)
  ctx.fill()

  // Draw crosshair
  ctx.strokeStyle = color
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(x - size * 2, y)
  ctx.lineTo(x + size * 2, y)
  ctx.moveTo(x, y - size * 2)
  ctx.lineTo(x, y + size * 2)
  ctx.stroke()
}

/**
 * Draw tracking path
 */
export function drawTrackingPath(
  ctx: CanvasRenderingContext2D,
  points: { x: number; y: number }[],
  color: string = '#00ffff',
  lineWidth: number = 2
) {
  if (points.length < 2) return

  ctx.strokeStyle = color
  ctx.lineWidth = lineWidth
  ctx.beginPath()
  ctx.moveTo(points[0].x, points[0].y)

  for (let i = 1; i < points.length; i++) {
    ctx.lineTo(points[i].x, points[i].y)
  }

  ctx.stroke()
}
