"use client" // Error boundaries must be Client Components

import { RotateCw, ServerCrash } from "lucide-react"
import { useEffect } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"

export default function BackendError({
  error,
  retry,
}: {
  error: Error & { digest?: string }
  retry: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="flex justify-center py-12">
      <Card className="w-full max-w-md text-center">
        <CardHeader className="items-center">
          <span className="mx-auto mb-2 flex size-12 items-center justify-center rounded-full bg-destructive/10">
            <ServerCrash className="size-6 text-destructive" aria-hidden />
          </span>
          <CardTitle>Can&apos;t reach the backend</CardTitle>
          <CardDescription>
            The API didn&apos;t respond. Check that the stack is running with <code className="font-mono">make up</code>, then try again.
          </CardDescription>
        </CardHeader>
        <CardContent />
        <CardFooter className="justify-center">
          <Button onClick={() => retry()}>
            <RotateCw /> Try again
          </Button>
        </CardFooter>
      </Card>
    </div>
  )
}
