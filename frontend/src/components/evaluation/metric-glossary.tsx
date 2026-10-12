import { Disclosure } from "@/components/ui/disclosure";
import { METRIC_GLOSSARY, type GlossaryKey } from "@/lib/eval-view";

/** One-line "Metric glossary" disclosure for the abbreviations a Developer Tools view uses. */
export function MetricGlossary({ keys }: { keys: readonly GlossaryKey[] }) {
  return (
    <Disclosure summary="Metric glossary">
      <dl className="grid gap-x-6 gap-y-2 text-sm md:grid-cols-2">
        {keys.map((k) => (
          <div key={k} className="min-w-0">
            <dt className="font-medium text-primary">{METRIC_GLOSSARY[k].term}</dt>
            <dd className="text-secondary">{METRIC_GLOSSARY[k].meaning}</dd>
          </div>
        ))}
      </dl>
    </Disclosure>
  );
}
