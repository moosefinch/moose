import { useState, useCallback } from 'react'
import type { CognitiveStatus, AgentState } from '../types'

interface AmbientRemark {
  id: string
  content: string
  category: string
  timestamp: number
}

export function useAmbientAI() {
  const [cognitiveStatus, setCognitiveStatus] = useState<CognitiveStatus | null>(null)
  const [remarks, setRemarks] = useState<AmbientRemark[]>([])
  const [expandedIndicator, setExpandedIndicator] = useState(false)

  const addRemark = useCallback((content: string, category = 'observation') => {
    const remark: AmbientRemark = {
      id: `remark-${Date.now()}-${Math.random().toString(36).slice(2, 5)}`,
      content,
      category,
      timestamp: Date.now(),
    }
    setRemarks(prev => [remark, ...prev].slice(0, 50))
  }, [])

  const getAIState = (cognitiveStatus: CognitiveStatus | null, agents: AgentState[]): 'idle' | 'observing' | 'thinking' | 'acting' => {
    if (!cognitiveStatus) return 'idle'
    const activeAgents = agents.filter(a => a.state === 'running')
    if (activeAgents.length > 0) return 'acting'
    if (cognitiveStatus.phase === 'observe' || cognitiveStatus.phase === 'orient') return 'observing'
    if (cognitiveStatus.phase === 'decide') return 'thinking'
    if (cognitiveStatus.phase === 'act') return 'acting'
    return 'idle'
  }

  return {
    cognitiveStatus,
    setCognitiveStatus,
    remarks,
    addRemark,
    expandedIndicator,
    setExpandedIndicator,
    getAIState,
  }
}
