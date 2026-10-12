/** Joins class-name parts, skipping falsy values. A dependency-free `clsx` for this codebase. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
