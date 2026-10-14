import { ShoppingBag } from "lucide-react"
import Link from "next/link"

import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { getMe } from "@/lib/api/server"

import { UserMenu } from "./user-menu"

/** Cart badge + account menu. Reads the session cookie, so it renders under <Suspense>. */
export async function HeaderAccount() {
  let me
  try {
    me = await getMe()
  } catch {
    me = { user: null, cart_count: 0 } // a header must never take the page down
  }

  if (!me.user) {
    return (
      <Button asChild variant="outline" size="sm">
        <Link href="/login">Log in</Link>
      </Button>
    )
  }
  const count = me.cart_count
  return (
    <>
      <Button asChild variant="ghost" size="icon" className="relative">
        <Link href="/cart" aria-label={count ? `Cart, ${count} item${count === 1 ? "" : "s"}` : "Cart"}>
          <ShoppingBag className="size-4" />
          {count > 0 && (
            <span
              aria-hidden
              className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground tabular-nums"
            >
              {count > 99 ? "99+" : count}
            </span>
          )}
        </Link>
      </Button>
      <UserMenu user={me.user} />
    </>
  )
}

export function HeaderAccountSkeleton() {
  return (
    <>
      <Skeleton className="size-9 rounded-md" />
      <Skeleton className="size-9 rounded-md" />
    </>
  )
}
