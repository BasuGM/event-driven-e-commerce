export type NavItem = {
  label: string
  href: string
  /** Placeholder entries render disabled until their feature ships. */
  comingSoon?: boolean
  external?: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Shop", href: "/shop" },
  { label: "Orders", href: "/orders" },
  {
    label: "Admin",
    href: process.env.NEXT_PUBLIC_ADMIN_URL ?? "http://localhost:8000/admin/",
    external: true,
  },
]
