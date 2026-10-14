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

const CHART_LIBRARIES =
  "recharts|chart\\.js|react-chartjs-2|d3(?:-[\\w-]+)?|visx|@visx\\/[\\w-]+|@nivo\\/[\\w-]+|nivo|" +
  "echarts(?:-for-react)?|victory(?:-[\\w-]+)?|plotly\\.js(?:-[\\w-]+)?|react-plotly\\.js";

/** Colour-ish tokens a Tailwind gradient stop would name (`from-accent`, `to-white`, `via-[#fff]`). */
const GRADIENT_STOP =
  /(?<=["'`\s:])(?:from|via|to)-(?:\[|transparent\b|white\b|black\b|current\b|(?:accent|surface|canvas|raised|sunken|ink|border|chart|claim|status|success|warn|danger|info|neutral|text|cite)\b|[a-z]+-\d)/;

const BANNED: Array<[string, RegExp]> = [
  ["arbitrary text size", /\btext-\[/],
  ["large radius", /\brounded-(?:[trbl]{1,2}-)?(?:xl|2xl|3xl)\b/],
  ["gradient", /\bbg-(?:gradient|linear|radial|conic)-/],
  ["gradient stop", GRADIENT_STOP],
  ["glass blur", /\bbackdrop-blur/],
  ["heavy shadow", /\bshadow-(?:lg|xl|2xl)\b/],
  ["raw palette colour", /\b(?:indigo|amber|teal|violet|emerald|sky|slate)-\d/],
  ["playful animation", /\banimate-(?:bounce|ping)\b/],
  ["arbitrary duration", /\bduration-\[/],
  ["transition-all (name the properties)", /\btransition-all\b/],
  ["emoji", /\p{Extended_Pictographic}/u],
  ["chart library import", new RegExp(`(?:\\bfrom\\s*|\\bimport\\s*\\(?\\s*|\\brequire\\s*\\(\\s*)["'](?:${CHART_LIBRARIES})["'/]`)],
];

/**
 * Inline CSS gradients in components. Only a hairline motion effect may use one (the scan line's
 * travelling highlight); larger gradients are a design-language violation.
 */
const CSS_GRADIENT: [string, RegExp] = ["inline CSS gradient", /\b(?:linear|radial|conic)-gradient\(/];
const CSS_GRADIENT_ALLOWED = new Set(["components/motion/scan-line.tsx"]);

function sourceFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return SKIP_DIRS.has(name) ? [] : sourceFiles(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && !name.endsWith(".d.ts") ? [path] : [];
  });
}

function violations(source: string, file = ""): string[] {
  const rules = CSS_GRADIENT_ALLOWED.has(file) ? BANNED : [...BANNED, CSS_GRADIENT];
  const found: string[] = [];
  source.split("\n").forEach((line, i) => {
    for (const [rule, re] of rules) if (re.test(line)) found.push(`${i + 1}: ${rule}: ${line.trim()}`);
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
      'className="bg-linear-to-r"',
      'className="from-accent"',
      'className="hover:to-white"',
      'className="via-[#fff]"',
      'className="motion-safe:animate-bounce"',
      'className="animate-ping"',
      'className="duration-[250ms]"',
      'className="transition-all"',
      'const label = "Ready \u{1F680}";',
      'const tick = "\u2705 done";',
      'import { BarChart } from "recharts";',
      'import * as d3 from "d3";',
      'import { scaleLinear } from "d3-scale";',
      'import { Group } from "@visx/group";',
      'const Plot = await import("react-plotly.js");',
      'import { ResponsiveBar } from "@nivo/bar";',
      'import "chart.js/auto";',
      'style={{ background: "linear-gradient(90deg, red, blue)" }}',
    ];
    for (const line of sample) expect(violations(line), line).toHaveLength(1);
    const clean = [
      'className="rounded-md shadow-overlay text-sm bg-accent text-muted"',
      'className="transition-colors duration-(--duration-fast) ease-standard"',
      'const copy = "Go-to-market plan from 2025 to 2026, back-to-school, opt-in";',
      'const arrows = "\u2191 \u2193 \u2192 \u00b7 \u2014 \u00d7";',
      'import { HBarChart } from "@/components/charts";',
      'import { Activity } from "lucide-react";',
    ];
    for (const line of clean) expect(violations(line), line).toEqual([]);
    expect(violations('style={{ background: "linear-gradient(90deg, red, blue)" }}', "components/motion/scan-line.tsx")).toEqual([]);
  });

  const files = sourceFiles(SRC).map((p) => relative(SRC, p));

  it("scans at least the design-system primitives, pages and .ts class helpers", () => {
    expect(files.some((f) => f.startsWith("components/ui/"))).toBe(true);
    expect(files.some((f) => f.startsWith("app/"))).toBe(true);
    expect(files).toContain("components/ui/control-class.ts");
  });

  it.each(files)("%s uses only design tokens", (file) => {
    expect(violations(readFileSync(join(SRC, file), "utf8"), file)).toEqual([]);
  });
});
