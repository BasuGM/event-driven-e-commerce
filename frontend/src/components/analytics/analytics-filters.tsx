"use client"

import { CalendarRange } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState } from "react"
import type { DateRange } from "react-day-picker"

import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  analyticsHref,
  presets,
  SOURCE_LABELS,
  SOURCES,
  type AnalyticsFilters as Filters,
  type AnalyticsSource,
} from "@/lib/analytics-params"
import { formatDate } from "@/lib/format"

const toDate = (iso: string) => new Date(`${iso}T12:00:00`)
const toIso = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`

/** Source + date range. The URL is the state: every change is a navigation. */
export function AnalyticsFilters({
  filters,
  shown,
  lastDay,
}: {
  filters: Filters
  shown: { from: string; to: string }
  lastDay: string | null
}) {
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [range, setRange] = useState<DateRange | undefined>({ from: toDate(shown.from), to: toDate(shown.to) })
  const go = (next: Filters) => router.push(analyticsHref(next))

  return (
    <div className="flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-end">
      <div className="space-y-1.5">
        <Label htmlFor="analytics-source">Source</Label>
        <Select value={filters.source} onValueChange={(source) => go({ ...filters, source: source as AnalyticsSource })}>
          <SelectTrigger id="analytics-source" className="w-full sm:w-52">
            <SelectValue>{SOURCE_LABELS[filters.source]}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {SOURCES.map((source) => (
              <SelectItem key={source} value={source}>
                {SOURCE_LABELS[source]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="analytics-range">Purchase dates (São Paulo time)</Label>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button id="analytics-range" variant="outline" className="w-full justify-start font-normal sm:w-72">
              <CalendarRange /> {formatDate(shown.from)} – {formatDate(shown.to)}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="range"
              numberOfMonths={2}
              defaultMonth={toDate(shown.from)}
              selected={range}
              onSelect={setRange}
            />
            <div className="flex justify-end gap-2 border-t p-3">
              <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={!range?.from || !range?.to}
                onClick={() => {
                  setOpen(false)
                  if (range?.from && range.to) go({ ...filters, date_from: toIso(range.from), date_to: toIso(range.to) })
                }}
              >
                Apply
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      </div>
      <div className="flex flex-wrap gap-1" aria-label="Date presets">
        {presets(lastDay).map((preset) => (
          <Button
            key={preset.label}
            variant="ghost"
            size="sm"
            onClick={() => go({ source: filters.source, date_from: preset.from, date_to: preset.to })}
          >
            {preset.label}
          </Button>
        ))}
      </div>
    </div>
  )
}
