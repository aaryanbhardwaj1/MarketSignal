import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Banned-class guard (plan §2.1 "Enforcement"). Scans every source file under `src/`: class
 * strings live in `.ts` helpers (control-class.ts, tone.ts, labels.ts) as well as `.tsx`.
 * Tests (and fixtures) are excluded, since they spell banned patterns on purpose.
 */
const SRC = fileURLToPath(new URL("..", import.meta.url));
const SKIP_DIRS = new Set(["node_modules", "__fixtures__"]);

const BANNED: Array<[string, RegExp]> = [
  ["arbitrary text size", /\btext-\[/],
  ["large radius", /\brounded-(?:[trbl]{1,2}-)?(?:xl|2xl|3xl)\b/],
  ["gradient", /\bbg-gradient/],
  ["glass blur", /\bbackdrop-blur/],
  ["heavy shadow", /\bshadow-(?:lg|xl|2xl)\b/],
  ["raw palette colour", /\b(?:indigo|amber|teal|violet|emerald|sky|slate)-\d/],
];

function sourceFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return SKIP_DIRS.has(name) ? [] : sourceFiles(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && !name.endsWith(".d.ts") ? [path] : [];
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

  const files = sourceFiles(SRC).map((p) => relative(SRC, p));

  it("scans at least the design-system primitives, pages and .ts class helpers", () => {
    expect(files.some((f) => f.startsWith("components/ui/"))).toBe(true);
    expect(files.some((f) => f.startsWith("app/"))).toBe(true);
    expect(files).toContain("components/ui/control-class.ts");
  });

  it.each(files)("%s uses only design tokens", (file) => {
    expect(violations(readFileSync(join(SRC, file), "utf8"))).toEqual([]);
  });
});
