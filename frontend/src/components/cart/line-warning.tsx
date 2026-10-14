import { AlertTriangle } from "lucide-react"

import type { CartLine } from "@/lib/api/client"

export function lineWarningText(line: Pick<CartLine, "warning" | "available">): string | null {
  if (line.warning === "out_of_stock") return "Out of stock. Remove it to check out."
  if (line.warning === "insufficient_stock") {
    return `Only ${line.available} left. Lower the quantity to check out.`
  }
  return null
}

export function LineWarning({ line }: { line: Pick<CartLine, "warning" | "available"> }) {
  const text = lineWarningText(line)
  if (!text) return null
  return (
    <p role="alert" className="flex items-center gap-1.5 text-xs text-destructive">
      <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
      {text}
    </p>
  )
}
