import Link from "next/link"

import { cn } from "@/lib/utils"

import type { NavItem } from "./nav-items"

const base =
  "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"

export function NavLink({ item, className }: { item: NavItem; className?: string }) {
  if (item.comingSoon) {
    return (
      <span
        aria-disabled="true"
        title="Coming soon"
        className={cn(base, "cursor-not-allowed text-muted-foreground/70", className)}
      >
        {item.label}
        <span className="rounded-sm bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
          Soon
        </span>
      </span>
    )
  }
  return (
    <Link
      href={item.href}
      className={cn(base, "text-muted-foreground hover:bg-accent hover:text-foreground", className)}
      {...(item.external ? { target: "_blank", rel: "noreferrer" } : {})}
    >
      {item.label}
    </Link>
  )
}
