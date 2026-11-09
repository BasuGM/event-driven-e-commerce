import Link from "next/link"

import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"

import { DocumentTitle } from "./document-title"

const TABS = [
  { href: "/staff/events", label: "Events" },
  { href: "/staff/health", label: "Health" },
  { href: "/staff/analytics", label: "Analytics" },
] as const

/** Rendered by each staff page *after* its data check, so non-staff never see staff chrome. */
export function StaffHeader({ active, title, description }: { active: (typeof TABS)[number]["href"] | null; title: string; description: string }) {
  return (
    <div className="space-y-4">
      <DocumentTitle title={title} />
      <nav aria-label="Staff tools" className="flex gap-1">
        {TABS.map((tab) => (
          <Button key={tab.href} asChild variant={tab.href === active ? "secondary" : "ghost"} size="sm">
            <Link href={tab.href} aria-current={tab.href === active ? "page" : undefined}>
              {tab.label}
            </Link>
          </Button>
        ))}
      </nav>
      <PageHeader title={title} description={description} />
    </div>
  )
}
