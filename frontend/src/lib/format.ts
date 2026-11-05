const integerFormatter = new Intl.NumberFormat("en-US")
const brlFormatter = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })
const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
})

export function formatInteger(value: number): string {
  return integerFormatter.format(value)
}

/** API money is a decimal string ("75.01"); format it as BRL ("R$ 75,01"). */
export function formatBRL(value: string | number): string {
  return brlFormatter.format(typeof value === "string" ? Number(value) : value)
}

/** API dates are ISO dates ("2018-01-21"); format without shifting the calendar day. */
export function formatDate(value: string): string {
  return dateFormatter.format(new Date(value))
}

const dateTimeFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "UTC",
  timeZoneName: "short",
})

/** Timestamps in staff tools: exact to the second, in UTC (what the logs and Redis use). */
export function formatDateTime(value: string): string {
  return dateTimeFormatter.format(new Date(value))
}
