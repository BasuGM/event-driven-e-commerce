import { connection } from "next/server"

import { HealthBadges } from "@/components/dashboard/health-badges"
import { StatsCards } from "@/components/dashboard/stats-cards"
import { PageHeader } from "@/components/layout/page-header"
import { getHealth, getStats } from "@/lib/api/client"

export default async function HomePage() {
  // Always render at request time: counts change whenever the DB is re-seeded.
  await connection()
  const [stats, health] = await Promise.all([getStats(), getHealth()])

  return (
    <div className="space-y-8">
      <PageHeader
        title="Dashboard"
        description="Live counts from the Olist Brazilian E-Commerce dataset."
        actions={<HealthBadges health={health} />}
      />
      <StatsCards stats={stats} />
    </div>
  )
}
