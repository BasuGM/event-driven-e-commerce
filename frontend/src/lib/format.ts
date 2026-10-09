const integerFormatter = new Intl.NumberFormat("en-US")

export function formatInteger(value: number): string {
  return integerFormatter.format(value)
}
