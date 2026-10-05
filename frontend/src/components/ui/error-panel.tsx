import { describeError } from "@/lib/api/errors";

export function ErrorPanel({ error, title = "Request failed" }: { error: unknown; title?: string }) {
  const { code, message } = describeError(error);
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <p className="font-semibold">{title}</p>
      <p className="mt-1">
        <code className="rounded bg-red-100 px-1.5 py-0.5 font-mono text-xs">{code}</code>{" "}
        <span>{message}</span>
      </p>
    </div>
  );
}

export function InlineError({ error }: { error: unknown }) {
  const { code, message } = describeError(error);
  return (
    <p role="alert" className="text-sm text-red-700">
      <code className="font-mono text-xs font-semibold">{code}</code>: {message}
    </p>
  );
}
