"use client"

import { Search, X } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useDebouncedCallback } from "@/hooks/use-debounced-callback"

import { useShopNavigation } from "./shop-navigation"

export function SearchBox() {
  const { filters, apply } = useShopNavigation()
  const urlQuery = filters.q ?? ""
  const [value, setValue] = useState(urlQuery)
  const [lastUrlQuery, setLastUrlQuery] = useState(urlQuery)

  // If the URL changes from elsewhere (back button, Clear filters), show the URL's query.
  // Adjusting state during render is React's recommended alternative to a syncing effect.
  if (urlQuery !== lastUrlQuery) {
    setLastUrlQuery(urlQuery)
    setValue(urlQuery)
  }

  const push = useDebouncedCallback((q: string) => {
    if (q.trim() !== urlQuery) apply({ q: q.trim() || undefined })
  }, 300)

  return (
    <form
      role="search"
      className="relative w-full"
      onSubmit={(event) => {
        event.preventDefault()
        push.cancel()
        if (value.trim() !== urlQuery) apply({ q: value.trim() || undefined })
      }}
    >
      <label htmlFor="shop-search" className="sr-only">
        Search products
      </label>
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <Input
        id="shop-search"
        type="search"
        placeholder="Search products…"
        className="pr-9 pl-9 [&::-webkit-search-cancel-button]:hidden"
        value={value}
        maxLength={100}
        onChange={(event) => {
          setValue(event.target.value)
          push(event.target.value)
        }}
      />
      {value && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="absolute top-1/2 right-1 size-7 -translate-y-1/2"
          aria-label="Clear search"
          onClick={() => {
            push.cancel()
            setValue("")
            apply({ q: undefined })
          }}
        >
          <X />
        </Button>
      )}
    </form>
  )
}
