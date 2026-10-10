import { useEffect, useRef } from 'react'

import { detectorClass, FORMATS } from './camera'

export function CameraScan({ onCode }: { onCode: (code: string) => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const latest = useRef(onCode)
  useEffect(() => {
    latest.current = onCode
  }, [onCode])
  useEffect(() => {
    const Klass = detectorClass()
    if (!Klass) return
    const detector = new Klass({ formats: FORMATS })
    let stream: MediaStream | undefined
    let timer = 0
    let stopped = false
    const tick = async () => {
      if (stopped || !video.current) return
      const [hit] = await detector.detect(video.current).catch(() => [])
      if (hit?.rawValue) latest.current(hit.rawValue)
      else timer = window.setTimeout(() => void tick(), 300)
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'environment' } })
      .then(async (s) => {
        stream = s
        if (!video.current || stopped) return
        video.current.srcObject = s
        await video.current.play()
        void tick()
      })
      .catch(() => undefined)
    return () => {
      stopped = true
      window.clearTimeout(timer)
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [])
  return <video ref={video} className="w-full max-w-sm rounded-xl" muted playsInline />
}
