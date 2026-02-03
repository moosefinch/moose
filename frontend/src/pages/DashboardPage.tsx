import { ProjectCard } from '../components/dashboard/ProjectCard'
import { PrinterStatusWidget } from '../components/dashboard/PrinterStatusWidget'
import { AgentActivityFeed } from '../components/dashboard/AgentActivityFeed'
import { QuickActions } from '../components/dashboard/QuickActions'
import type { AgentEvent, AgentState, Briefing, AgentTask } from '../types'

interface DashboardPageProps {
  agentEvents: AgentEvent[]
  agentStates: AgentState[]
  briefings: Briefing[]
  tasks: AgentTask[]
  onLaunchTask: (description: string) => void
  onNavigateViewport: () => void
}

export function DashboardPage({ agentEvents, agentStates, briefings, tasks, onLaunchTask, onNavigateViewport }: DashboardPageProps) {
  return (
    <div className="page-dashboard">
      <div className="dashboard-grid">
        <div className="dashboard-col-left">
          <QuickActions onLaunchTask={onLaunchTask} onNavigateViewport={onNavigateViewport} />
          <ProjectCard />
          <PrinterStatusWidget />
        </div>
        <div className="dashboard-col-right">
          <AgentActivityFeed
            events={agentEvents}
            agents={agentStates}
            briefings={briefings}
            tasks={tasks}
          />
        </div>
      </div>
    </div>
  )
}
