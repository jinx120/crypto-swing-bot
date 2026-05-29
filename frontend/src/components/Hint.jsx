import { useRef, useState, useCallback } from 'react'

// Small context hint: an "i" marker that reveals a tooltip on hover/focus.
// The tooltip is fixed-positioned and clamped to the viewport so it never
// clips at a screen edge, and flips above/below depending on available room.
export default function Hint({ text }){
  const ref = useRef(null)
  const [pos, setPos] = useState(null)

  const show = useCallback(() => {
    const m = ref.current?.getBoundingClientRect()
    if (!m) return
    const pad = 8, maxW = 260
    const w = Math.min(maxW, window.innerWidth - 2 * pad)
    let left = m.left + m.width / 2 - w / 2
    left = Math.max(pad, Math.min(left, window.innerWidth - w - pad))
    let arrowX = m.left + m.width / 2 - left
    arrowX = Math.max(12, Math.min(arrowX, w - 12))
    const above = m.top > 200
    setPos({ left, top: above ? m.top : m.bottom, w, arrowX, above })
  }, [])
  const hide = useCallback(() => setPos(null), [])

  return (
    <span ref={ref} className="hint" tabIndex={0} role="note" aria-label={text}
      onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      i
      {pos && (
        <span className={`hint-tip ${pos.above ? 'is-above' : 'is-below'}`}
          style={{
            left: pos.left, top: pos.top, width: pos.w,
            transform: pos.above ? 'translateY(-100%)' : 'none',
            marginTop: pos.above ? -8 : 8,
            '--arrow-x': `${pos.arrowX}px`,
          }}>
          {text}
        </span>
      )}
    </span>
  )
}
