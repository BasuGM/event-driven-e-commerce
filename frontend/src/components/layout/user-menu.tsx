"use client"

import { LogOut, Package, UserRound } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useTransition } from "react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { browserApi, ensureCsrf } from "@/lib/api/browser"
import type { User } from "@/lib/api/client"

export function UserMenu({ user }: { user: User }) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()

  const logOut = () =>
    startTransition(async () => {
      await ensureCsrf()
      await browserApi.POST("/api/auth/logout/")
      router.push("/")
      router.refresh()
    })

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Account menu for ${user.name}`}>
          <UserRound className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="space-y-0.5">
          <p className="truncate text-sm font-medium">{user.name}</p>
          <p className="truncate text-xs font-normal text-muted-foreground">{user.email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/orders">
            <Package /> My orders
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={logOut} disabled={pending}>
          <LogOut /> Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
