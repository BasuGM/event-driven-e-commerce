import {
  BedDouble,
  BookOpen,
  Car,
  Coffee,
  CookingPot,
  Dumbbell,
  Headphones,
  Microwave,
  Package,
  PawPrint,
  Puzzle,
  Shirt,
  Sofa,
  Sparkles,
  Wrench,
  type LucideIcon,
} from "lucide-react"

import type { CategoryGroup, CategoryRef } from "@/lib/api/client"
import { cn } from "@/lib/utils"

const ICONS: Record<CategoryGroup, LucideIcon> = {
  textiles: BedDouble,
  furniture: Sofa,
  housewares: CookingPot,
  appliances: Microwave,
  electronics: Headphones,
  beauty: Sparkles,
  fashion: Shirt,
  sports: Dumbbell,
  toys: Puzzle,
  auto: Car,
  tools: Wrench,
  food: Coffee,
  media: BookOpen,
  pets: PawPrint,
  general: Package,
}

// Static class strings so Tailwind can see them; colours come from --category-N tokens.
const TINTS = [
  "bg-category-1/12 text-category-1",
  "bg-category-2/12 text-category-2",
  "bg-category-3/12 text-category-3",
  "bg-category-4/12 text-category-4",
  "bg-category-5/12 text-category-5",
  "bg-category-6/12 text-category-6",
  "bg-category-7/12 text-category-7",
  "bg-category-8/12 text-category-8",
]

/** Stable tint per category: a tiny string hash of the slug. */
export function tintFor(slug: string | undefined): string {
  if (!slug) return "bg-muted text-muted-foreground"
  let hash = 0
  for (const char of slug) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return TINTS[hash % TINTS.length]
}

export function CategoryPlaceholder({
  category,
  className,
  iconClassName,
}: {
  category: CategoryRef | null
  className?: string
  iconClassName?: string
}) {
  const Icon = category ? ICONS[category.group] : Package
  return (
    <div
      role="img"
      aria-label={category ? `${category.label} product image placeholder` : "Product image placeholder"}
      className={cn(
        "flex aspect-square w-full items-center justify-center rounded-lg",
        tintFor(category?.slug),
        className,
      )}
    >
      <Icon className={cn("size-12 opacity-80", iconClassName)} strokeWidth={1.5} aria-hidden />
    </div>
  )
}
