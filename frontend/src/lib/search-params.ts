/** Reads the first value of a Next.js search param (which may be repeated). */
export function firstParam(value: string | string[] | undefined): string | null {
  const v = Array.isArray(value) ? value[0] : value;
  return v ? v : null;
}
