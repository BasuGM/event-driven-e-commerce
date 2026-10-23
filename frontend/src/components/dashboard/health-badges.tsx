import { CircleCheck, CircleX, Inbox } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { Health } from "@/lib/api/client"

/** 45 -> "45s", 125 -> "2m", 7200 -> "2h" */
export function formatAge(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  return `${Math.floor(seconds / 3600)}h`
}

/** "Outbox: 0 pending", or "Outbox: 3 pending · oldest 2m" (a growing number = relay stuck). */
export function outboxLabel(outbox: NonNullable<Health["outbox"]>): string {
  const { unpublished, oldest_unpublished_age_seconds: age } = outbox
  return unpublished > 0 && age !== null
    ? `Outbox: ${unpublished} pending · oldest ${formatAge(age)}`
    : `Outbox: ${unpublished} pending`
}

export function HealthBadges({ health }: { health: Pick<Health, "db" | "redis" | "outbox"> }) {
  const services = [
    { name: "Database", status: health.db },
    { name: "Redis", status: health.redis },
  ]
  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Service health">
      {services.map(({ name, status }) => {
        const ok = status === "ok"
        return (
          <Badge key={name} variant={ok ? "success" : "destructive"}>
            {ok ? <CircleCheck aria-hidden /> : <CircleX aria-hidden />}
            {name}: {ok ? "healthy" : "down"}
          </Badge>
        )
      })}
      {health.outbox && (
        <Badge variant={health.outbox.unpublished === 0 ? "success" : "secondary"}>
          <Inbox aria-hidden />
          {outboxLabel(health.outbox)}
        </Badge>
      )}
    </div>
  )
}
