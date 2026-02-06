import { useState, useRef, useCallback, useEffect } from 'react'
import { apiFetch } from '../api'

export function useTTS() {
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [volume, setVolume] = useState(0.8)
  const [muted, setMuted] = useState(false)
  const spokenIdsRef = useRef(new Set<number>())
  const queueRef = useRef<{ text: string; index?: number }[]>([])
  const playingRef = useRef(false)

  // AudioContext approach — survives Safari autoplay restrictions
  const audioCtxRef = useRef<AudioContext | null>(null)
  const gainNodeRef = useRef<GainNode | null>(null)
  const sourceRef = useRef<AudioBufferSourceNode | null>(null)

  // Call this during a user gesture to unlock audio for the session
  const initAudio = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext()
      gainNodeRef.current = audioCtxRef.current.createGain()
      gainNodeRef.current.gain.value = volume
      gainNodeRef.current.connect(audioCtxRef.current.destination)
    }
    if (audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume()
    }
  }, [volume])

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (sourceRef.current) {
        try { sourceRef.current.stop() } catch {}
      }
      if (audioCtxRef.current) {
        audioCtxRef.current.close()
      }
    }
  }, [])

  // Keep gain node in sync with volume
  useEffect(() => {
    if (gainNodeRef.current) {
      gainNodeRef.current.gain.value = volume
    }
  }, [volume])

  const playNext = useCallback(async () => {
    if (playingRef.current || queueRef.current.length === 0) return
    if (!audioCtxRef.current || !gainNodeRef.current) return

    playingRef.current = true
    setIsSpeaking(true)

    const item = queueRef.current.shift()!

    // Strip markdown for cleaner speech
    const clean = item.text
      .replace(/```[\s\S]*?```/g, ' code block ')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/[#*_~>|-]+/g, '')
      .replace(/\n+/g, '. ')
      .replace(/\s+/g, ' ')
      .trim()

    if (!clean) {
      playingRef.current = false
      if (queueRef.current.length === 0) setIsSpeaking(false)
      else playNext()
      return
    }

    try {
      const resp = await apiFetch('/api/voice/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: clean }),
      })

      if (!resp.ok) {
        console.warn('TTS synthesis failed:', resp.status)
        playingRef.current = false
        if (queueRef.current.length === 0) setIsSpeaking(false)
        else playNext()
        return
      }

      // Resume context if suspended (Safari)
      if (audioCtxRef.current!.state === 'suspended') {
        await audioCtxRef.current!.resume()
      }

      const arrayBuffer = await resp.arrayBuffer()
      const audioBuffer = await audioCtxRef.current!.decodeAudioData(arrayBuffer)

      const source = audioCtxRef.current!.createBufferSource()
      source.buffer = audioBuffer
      source.connect(gainNodeRef.current!)
      sourceRef.current = source

      source.onended = () => {
        sourceRef.current = null
        playingRef.current = false
        if (queueRef.current.length === 0) setIsSpeaking(false)
        else playNext()
      }

      source.start()
    } catch (e) {
      console.warn('TTS error:', e)
      sourceRef.current = null
      playingRef.current = false
      if (queueRef.current.length === 0) setIsSpeaking(false)
      else playNext()
    }
  }, [volume])

  const speak = useCallback((text: string, messageIndex?: number) => {
    if (muted || !text.trim()) return

    // Deduplicate by message index if provided
    if (messageIndex !== undefined) {
      if (spokenIdsRef.current.has(messageIndex)) return
      spokenIdsRef.current.add(messageIndex)
    }

    queueRef.current.push({ text, index: messageIndex })
    playNext()
  }, [muted, playNext])

  const stop = useCallback(() => {
    queueRef.current = []
    if (sourceRef.current) {
      try { sourceRef.current.stop() } catch {}
      sourceRef.current = null
    }
    playingRef.current = false
    setIsSpeaking(false)
  }, [])

  const toggleMute = useCallback(() => {
    setMuted(prev => {
      if (!prev) stop()
      return !prev
    })
  }, [stop])

  return { isSpeaking, volume, setVolume, muted, toggleMute, speak, stop, initAudio }
}
