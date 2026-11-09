import type { Metadata } from "next"

/**
 * Staff pages answer non-staff with the not-found UI, and (on a streamed route) still with HTTP
 * 200. So the prerendered head must not reveal them: a neutral title and noindex for every
 * /staff page; the real title is set client-side (DocumentTitle) only after the staff check.
 */
export const metadata: Metadata = {
  title: { absolute: "Olist Commerce" },
  robots: { index: false, follow: false },
}

export default function StaffLayout({ children }: { children: React.ReactNode }) {
  return children
}
