"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Suspense } from "react"

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

  if (item.external) return <ItemLink item={item} active={false} className={className} />
  // The active state needs the URL (runtime data). Suspense lets the header prerender as part of
  // the static shell with an inactive link, then stream in the active state.
  return (
    <Suspense fallback={<ItemLink item={item} active={false} className={className} />}>
      <ActiveAwareLink item={item} className={className} />
    </Suspense>
  )
}

function ActiveAwareLink({ item, className }: { item: NavItem; className?: string }) {
  const pathname = usePathname()
  const active = pathname === item.href || pathname.startsWith(`${item.href}/`)
  return <ItemLink item={item} active={active} className={className} />
}

function ItemLink({ item, active, className }: { item: NavItem; active: boolean; className?: string }) {
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        base,
        active ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground",
        className,
      )}
      {...(item.external ? { target: "_blank", rel: "noreferrer" } : {})}
    >
      {item.label}
    </Link>
  )
}
