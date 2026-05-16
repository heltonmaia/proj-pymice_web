import { useEffect, useRef, useState } from 'react'
import type { ROI } from '@/types'
import { drawROI } from '@/utils/canvas'

export type ROIToolType =
  | 'Rectangle'
  | 'Circle'
  | 'Polygon'
  | 'OpenFieldRectangle'
  | 'OpenFieldCircle'

export type ROICanvasMode = 'edit' | 'view-only' | 'live-overlay'

interface ROICanvasProps {
  width: number
  height: number
  rois: ROI[]
  onRoisChange?: (rois: ROI[]) => void
  mode: ROICanvasMode
  activeRoiIndex?: number | null
  /** Background image to render under the ROIs. Pass null for a black canvas. */
  backgroundFrame?: HTMLImageElement | HTMLCanvasElement | null
  /** Optional tool selection — only used in edit mode. */
  tool?: ROIToolType
  onToolChange?: (tool: ROIToolType) => void
  colors?: string[]
}

const DEFAULT_COLORS = ['#ef4444', '#22c55e', '#3b82f6', '#f59e0b', '#a855f7', '#06b6d4']

export default function ROICanvas({
  width,
  height,
  rois,
  onRoisChange,
  mode,
  activeRoiIndex = null,
  backgroundFrame = null,
  tool = 'Rectangle',
  colors = DEFAULT_COLORS,
}: ROICanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [isDrawing, setIsDrawing] = useState(false)
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null)
  const [polygonPoints, setPolygonPoints] = useState<{ x: number; y: number }[]>([])
  const [hoverPoint, setHoverPoint] = useState<{ x: number; y: number } | null>(null)

  const editable = mode === 'edit'

  const repaint = () => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    canvas.width = width
    canvas.height = height
    ctx.clearRect(0, 0, width, height)

    if (backgroundFrame) {
      ctx.drawImage(backgroundFrame, 0, 0, width, height)
    } else {
      ctx.fillStyle = '#000'
      ctx.fillRect(0, 0, width, height)
    }

    rois.forEach((roi, idx) => {
      const color = colors[idx % colors.length]
      const highlight = mode === 'live-overlay' && idx === activeRoiIndex
      drawROI(ctx, roi, color, highlight ? 4 : 2, true, highlight ? 0.3 : 0.1)
    })

    if (editable && isDrawing && drawStart && hoverPoint) {
      ctx.strokeStyle = '#fbbf24'
      ctx.lineWidth = 2
      if (tool === 'Rectangle' || tool === 'OpenFieldRectangle') {
        ctx.strokeRect(
          drawStart.x,
          drawStart.y,
          hoverPoint.x - drawStart.x,
          hoverPoint.y - drawStart.y,
        )
      } else if (tool === 'Circle' || tool === 'OpenFieldCircle') {
        const r = Math.hypot(hoverPoint.x - drawStart.x, hoverPoint.y - drawStart.y)
        ctx.beginPath()
        ctx.arc(drawStart.x, drawStart.y, r, 0, Math.PI * 2)
        ctx.stroke()
      }
    }
    if (editable && tool === 'Polygon' && polygonPoints.length > 0) {
      ctx.strokeStyle = '#fbbf24'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(polygonPoints[0].x, polygonPoints[0].y)
      polygonPoints.slice(1).forEach((p) => ctx.lineTo(p.x, p.y))
      if (hoverPoint) ctx.lineTo(hoverPoint.x, hoverPoint.y)
      ctx.stroke()
      polygonPoints.forEach((p) => {
        ctx.fillStyle = '#fbbf24'
        ctx.beginPath()
        ctx.arc(p.x, p.y, 3, 0, Math.PI * 2)
        ctx.fill()
      })
    }
  }

  useEffect(() => {
    repaint()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rois, activeRoiIndex, backgroundFrame, isDrawing, drawStart, hoverPoint, polygonPoints, tool])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!editable) return
      if (e.key === 'Escape' && tool === 'Polygon' && polygonPoints.length > 0) {
        setPolygonPoints([])
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [editable, tool, polygonPoints])

  const toCanvas = (e: React.MouseEvent) => {
    const canvas = canvasRef.current!
    const rect = canvas.getBoundingClientRect()
    return {
      x: ((e.clientX - rect.left) / rect.width) * width,
      y: ((e.clientY - rect.top) / rect.height) * height,
    }
  }

  const onMouseDown = (e: React.MouseEvent) => {
    if (!editable) return
    const p = toCanvas(e)
    if (tool === 'Polygon') {
      if (polygonPoints.length >= 3) {
        const first = polygonPoints[0]
        if (Math.hypot(first.x - p.x, first.y - p.y) < 10) {
          const cx = polygonPoints.reduce((s, pt) => s + pt.x, 0) / polygonPoints.length
          const cy = polygonPoints.reduce((s, pt) => s + pt.y, 0) / polygonPoints.length
          const newRoi: ROI = {
            roi_type: 'Polygon',
            center_x: cx,
            center_y: cy,
            vertices: polygonPoints.map((pt) => [pt.x, pt.y] as [number, number]),
          }
          onRoisChange?.([...rois, newRoi])
          setPolygonPoints([])
          return
        }
      }
      setPolygonPoints([...polygonPoints, p])
      return
    }
    setIsDrawing(true)
    setDrawStart(p)
  }

  const onMouseMove = (e: React.MouseEvent) => {
    if (!editable) return
    setHoverPoint(toCanvas(e))
  }

  const onMouseUp = (e: React.MouseEvent) => {
    if (!editable || !isDrawing || !drawStart) return
    setIsDrawing(false)
    const p = toCanvas(e)
    let newRoi: ROI | null = null
    if (tool === 'Rectangle' || tool === 'OpenFieldRectangle') {
      const w = Math.abs(p.x - drawStart.x)
      const h = Math.abs(p.y - drawStart.y)
      if (w < 5 || h < 5) {
        setDrawStart(null)
        return
      }
      newRoi = {
        roi_type: 'Rectangle',
        center_x: (drawStart.x + p.x) / 2,
        center_y: (drawStart.y + p.y) / 2,
        width: w,
        height: h,
      }
    } else if (tool === 'Circle' || tool === 'OpenFieldCircle') {
      const r = Math.hypot(p.x - drawStart.x, p.y - drawStart.y)
      if (r < 5) {
        setDrawStart(null)
        return
      }
      newRoi = {
        roi_type: 'Circle',
        center_x: drawStart.x,
        center_y: drawStart.y,
        radius: r,
      }
    }
    if (newRoi) onRoisChange?.([...rois, newRoi])
    setDrawStart(null)
  }

  return (
    <canvas
      ref={canvasRef}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      style={{ width: '100%', maxWidth: width, cursor: editable ? 'crosshair' : 'default' }}
      className="bg-black rounded-lg border border-gray-300 dark:border-gray-700"
    />
  )
}
