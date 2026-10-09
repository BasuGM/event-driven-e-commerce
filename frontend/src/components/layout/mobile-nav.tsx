"use client"

import { Menu } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"

import { NAV_ITEMS } from "./nav-items"
import { NavLink } from "./nav-link"

export function MobileNav() {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
          <Menu className="size-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-72">
        <SheetHeader>
          <SheetTitle>Olist Commerce</SheetTitle>
          <SheetDescription>Event-driven e-commerce</SheetDescription>
        </SheetHeader>
        <Separator />
        <nav aria-label="Main" className="flex flex-col gap-1 px-2">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.label} item={item} className="w-full" />
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  )
}
