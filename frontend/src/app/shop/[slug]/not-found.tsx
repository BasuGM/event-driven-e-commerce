import { PackageX } from "lucide-react"
import Link from "next/link"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

export default function ProductNotFound() {
  return (
    <div className="flex justify-center py-12">
      <Card className="w-full max-w-md text-center">
        <CardContent className="flex flex-col items-center gap-4 py-10">
          <span className="flex size-12 items-center justify-center rounded-full bg-muted">
            <PackageX className="size-6 text-muted-foreground" aria-hidden />
          </span>
          <div className="space-y-1">
            <h1 className="text-lg font-semibold">Product not found</h1>
            <p className="text-sm text-muted-foreground">
              It may have been removed, or the link is mistyped.
            </p>
          </div>
          <Button asChild>
            <Link href="/shop">Back to the shop</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
