"use client"

import { ChevronDown } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"

/** The event's payload as formatted JSON, collapsed by default. */
export function EventPayload({ payload }: { payload: unknown }) {
  return (
    <Collapsible>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="sm" className="group -ml-2">
          Payload <ChevronDown className="transition-transform group-data-[state=open]:rotate-180" aria-hidden />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre className="mt-2 max-h-96 overflow-auto rounded-md bg-muted p-3 text-xs leading-relaxed">
          {JSON.stringify(payload, null, 2)}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  )
}
