import { CircleCheck, CircleX } from "lucide-react"

import { Badge } from "@/components/ui/badge"

type ServiceStatus = "ok" | "error"

export function HealthBadges({ health }: { health: { db: ServiceStatus; redis: ServiceStatus } }) {
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
    </div>
  )
}
