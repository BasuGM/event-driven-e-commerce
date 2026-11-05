import Link from "next/link"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import type { StaffEventFilters } from "@/lib/api/server"
import { ALL_TYPES } from "@/lib/staff-params"

/** A plain GET form: the URL is the state (shareable, back button), and it works without JS. */
export function EventFilters({ types, filters }: { types: string[]; filters: StaffEventFilters }) {
  return (
    <form method="get" action="/staff/events" className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_auto_auto_auto] lg:items-end">
      <div className="space-y-1.5">
        <Label htmlFor="filter-type">Type</Label>
        <Select name="type" defaultValue={filters.type ?? ALL_TYPES}>
          <SelectTrigger id="filter-type" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_TYPES}>All types</SelectItem>
            {types.map((type) => (
              <SelectItem key={type} value={type}>
                {type}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="filter-aggregate">Aggregate id</Label>
        <Input id="filter-aggregate" name="aggregate_id" placeholder="Order id" defaultValue={filters.aggregate_id} className="font-mono" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="filter-from">From</Label>
        <Input id="filter-from" name="date_from" type="date" defaultValue={filters.date_from} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="filter-to">To</Label>
        <Input id="filter-to" name="date_to" type="date" defaultValue={filters.date_to} />
      </div>
      <div className="flex gap-2">
        <Button type="submit">Filter</Button>
        <Button asChild variant="ghost">
          <Link href="/staff/events">Clear</Link>
        </Button>
      </div>
    </form>
  )
}
