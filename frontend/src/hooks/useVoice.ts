import { useState, useRef, useCallback } from 'react'
import { apiFetch } from '../api'

export function useVoice() {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [transcript, setTranscript] = useState('')
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm',
      })
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      mediaRecorder.start(250) // collect chunks every 250ms
      setIsRecording(true)
      setTranscript('')
    } catch (e) {
      console.error('[useVoice] Failed to start recording:', e)
    }
  }, [])

  const stopRecording = useCallback(async (): Promise<string> => {
    return new Promise((resolve) => {
      const mediaRecorder = mediaRecorderRef.current
      if (!mediaRecorder || mediaRecorder.state === 'inactive') {
        setIsRecording(false)
        resolve('')
        return
      }

      mediaRecorder.onstop = async () => {
        setIsRecording(false)
        setIsTranscribing(true)

        // Stop all tracks
        mediaRecorder.stream.getTracks().forEach(t => t.stop())

        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        const formData = new FormData()
        formData.append('file', blob, 'recording.webm')

        try {
          const r = await apiFetch('/api/voice/transcribe', {
            method: 'POST',
            body: formData,
          })
          if (r.ok) {
            const data = await r.json()
            const text = data.text || ''
            setTranscript(text)
            resolve(text)
          } else {
            console.error('[useVoice] Transcription failed:', r.status)
            resolve('')
          }
        } catch (e) {
          console.error('[useVoice] Transcription error:', e)
          resolve('')
        } finally {
          setIsTranscribing(false)
        }
      }

      mediaRecorder.stop()
    })
  }, [])

  return { isRecording, isTranscribing, transcript, startRecording, stopRecording }
}
