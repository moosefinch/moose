import { useState, useEffect, useCallback, useRef } from 'react'
import MooseAvatar, { type AvatarState } from './MooseAvatar'
import type { CognitiveStatus } from '../types'

interface Props {
  cognitiveStatus: CognitiveStatus | null
  sending: boolean
  hasMessages: boolean
  onSend: (text: string) => void
  isSpeaking?: boolean
}

// Ambient idle lines Moose might "think"
const IDLE_THOUGHTS = [
  'Listening...',
  'Ready when you are.',
  'What are we working on?',
  'Just keeping watch.',
  'Systems nominal.',
  'All quiet on the network.',
  'Observing.',
  'Standing by.',
]

const THINKING_LINES = [
  'Hmm, let me think...',
  'Processing...',
  'Working on it...',
  'Analyzing...',
  'One moment...',
]

const GREETING_LINES = [
  'Hey, what can I do for you?',
  'Need anything?',
  'What are we building?',
  'Ready to work.',
]

function pickRandom(arr: string[]): string {
  return arr[Math.floor(Math.random() * arr.length)]
}

function phaseToAvatar(phase: string, sending: boolean): AvatarState {
  if (sending) return 'thinking'
  switch (phase) {
    case 'observe':
    case 'orient':
      return 'thinking'
    case 'decide':
      return 'thinking'
    case 'act':
      return 'talking'
    default:
      return 'idle'
  }
}

export function AvatarPresence({ cognitiveStatus, sending, hasMessages, onSend, isSpeaking }: Props) {
  const [avatarState, setAvatarState] = useState<AvatarState>('idle')
  const [bubble, setBubble] = useState<string | null>(null)
  const [bubbleVisible, setBubbleVisible] = useState(false)
  const bubbleTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const idleTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const prevPhase = useRef<string>('idle')

  // Derive avatar state from cognitive status + sending + speaking
  useEffect(() => {
    if (isSpeaking) {
      setAvatarState('talking')
      return
    }
    const phase = cognitiveStatus?.phase ?? 'idle'
    const state = phaseToAvatar(phase, sending)
    setAvatarState(state)

    // Show a thought bubble on phase transitions
    if (phase !== prevPhase.current) {
      prevPhase.current = phase
      if (sending || phase === 'act') {
        showBubble(pickRandom(THINKING_LINES))
      }
    }
  }, [cognitiveStatus, sending, isSpeaking])

  const showBubble = useCallback((text: string, duration = 4000) => {
    if (bubbleTimer.current) clearTimeout(bubbleTimer.current)
    setBubble(text)
    setBubbleVisible(true)
    bubbleTimer.current = setTimeout(() => {
      setBubbleVisible(false)
      setTimeout(() => setBubble(null), 300) // fade out
    }, duration)
  }, [])

  // Ambient idle thoughts — occasional speech bubbles
  useEffect(() => {
    if (hasMessages) return // only ambient when on empty state

    idleTimer.current = setInterval(() => {
      if (avatarState === 'idle' && Math.random() < 0.3) {
        showBubble(pickRandom(IDLE_THOUGHTS), 3000)
      }
    }, 15000)

    return () => {
      if (idleTimer.current) clearInterval(idleTimer.current)
    }
  }, [avatarState, hasMessages, showBubble])

  // Initial greeting
  useEffect(() => {
    if (!hasMessages) {
      const timer = setTimeout(() => {
        setAvatarState('greeting')
        showBubble(pickRandom(GREETING_LINES), 4000)
        setTimeout(() => setAvatarState('idle'), 3000)
      }, 800)
      return () => clearTimeout(timer)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleClick = useCallback(() => {
    // Click interaction — Moose reacts
    setAvatarState('greeting')
    showBubble(pickRandom(GREETING_LINES))
    setTimeout(() => {
      setAvatarState(phaseToAvatar(cognitiveStatus?.phase ?? 'idle', sending))
    }, 2000)
  }, [cognitiveStatus, sending, showBubble])

  return (
    <div className="avatar-presence">
      <div className="avatar-presence-character" onClick={handleClick}>
        <MooseAvatar state={avatarState} size={180} />
      </div>

      {bubble && (
        <div className={`avatar-speech-bubble ${bubbleVisible ? 'visible' : 'fading'}`}>
          <span>{bubble}</span>
          <div className="speech-bubble-tail" />
        </div>
      )}
    </div>
  )
}
