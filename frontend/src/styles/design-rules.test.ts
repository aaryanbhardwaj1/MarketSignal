import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Banned-class guard (plan §2.1 "Enforcement"). Scope grows wave by wave: Wave 1 covers the
 * design-system folders; Wave 2 folders join when their restyle lands.
 */
const SRC = fileURLToPath(new URL("..", import.meta.url));
const SCOPED_DIRS = ["components/ui", "components/shell", "components/evidence"];

/**
 * Legacy evidence views awaiting the W-DS evidence-drawer restyle (part 2). Remove each entry
 * as its file is restyled or deleted; do not add new entries.
 */
const PENDING_RESTYLE = new Set<string>([]);

const BANNED: Array<[string, RegExp]> = [
  ["arbitrary text size", /\btext-\[/],
  ["large radius", /\brounded-(?:[trbl]{1,2}-)?(?:xl|2xl|3xl)\b/],
  ["gradient", /\bbg-gradient/],
  ["glass blur", /\bbackdrop-blur/],
  ["heavy shadow", /\bshadow-(?:lg|xl|2xl)\b/],
  ["raw palette colour", /\b(?:indigo|amber|teal|violet|emerald|sky|slate)-\d/],
];

function tsxFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return tsxFiles(path);
    return name.endsWith(".tsx") && !name.endsWith(".test.tsx") ? [path] : [];
  });
}

function violations(source: string): string[] {
  const found: string[] = [];
  source.split("\n").forEach((line, i) => {
    for (const [rule, re] of BANNED) if (re.test(line)) found.push(`${i + 1}: ${rule}: ${line.trim()}`);
  });
  return found;
}

describe("design rules", () => {
  it("the matcher catches every banned pattern", () => {
    const sample = [
      'className="text-[11px]"',
      'className="rounded-2xl"',
      'className="rounded-t-xl"',
      'className="bg-gradient-to-r"',
      'className="backdrop-blur-sm"',
      'className="shadow-xl"',
      'className="bg-indigo-600"',
      'className="text-slate-500"',
    ];
    for (const line of sample) expect(violations(line), line).toHaveLength(1);
    expect(violations('className="rounded-md shadow-overlay text-sm bg-accent text-muted"')).toEqual([]);
  });

  const files = SCOPED_DIRS.flatMap((d) => tsxFiles(join(SRC, d))).map((p) => relative(SRC, p));

  it("scans at least the design-system primitives", () => {
    expect(files.some((f) => f.startsWith("components/ui/"))).toBe(true);
  });

  it.each(files.filter((f) => !PENDING_RESTYLE.has(f)))("%s uses only design tokens", (file) => {
    expect(violations(readFileSync(join(SRC, file), "utf8"))).toEqual([]);
  });
});
