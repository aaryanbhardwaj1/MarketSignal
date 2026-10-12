import { describeError } from "@/lib/api/errors";
import { errorMessage } from "@/lib/labels";
import { ErrorState } from "./states";

function plainMessage(error: unknown): { message: string; code: string } {
  const { code, message } = describeError(error);
  const known = errorMessage(code);
  return { message: known.known ? known.label : message || known.label, code };
}

/** @deprecated Use `<ErrorState>`. Shows a plain message; the code moves into "Technical details". */
export function ErrorPanel({ error, title = "Something went wrong" }: { error: unknown; title?: string }) {
  const { message, code } = plainMessage(error);
  return <ErrorState title={title} description={message} devDetail={code} />;
}

/** @deprecated Inline variant kept for older forms; no raw code in the sentence. */
export function InlineError({ error }: { error: unknown }) {
  const { message } = plainMessage(error);
  return (
    <p role="alert" className="text-sm text-danger">
      {message}
    </p>
  );
}
