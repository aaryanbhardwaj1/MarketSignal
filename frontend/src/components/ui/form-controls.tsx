import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { cx } from "@/lib/cx";
import { CONTROL_CLASS } from "./control-class";

/** @deprecated Import `buttonClass` from `./button`. Re-exported for older components. */
export { buttonClass } from "./button";

export { CONTROL_CLASS };

/** Label + control + hint/error. `id` must match the child control's id. */
export function Field({
  id,
  label,
  hint,
  error,
  className,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string | null;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-primary">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-sm text-danger">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-hint`} className="text-sm text-muted">
            {hint}
          </p>
        )
      )}
    </div>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(CONTROL_CLASS, "h-9", className)} />;
}

/** @deprecated Use `Input`. */
export const TextInput = Input;

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(CONTROL_CLASS, "min-h-20 py-2", className)} />;
}

export interface SelectOption {
  value: string;
  label: string;
}

/** Native select. Pass `options`, or `<option>` children for older call sites. */
export function Select({
  options,
  className,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { options?: SelectOption[] }) {
  return (
    <select {...props} className={cx(CONTROL_CLASS, "h-9 pr-8", className)}>
      {options
        ? options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))
        : children}
    </select>
  );
}

export { SearchInput } from "./search-input";

export function Checkbox({
  id,
  label,
  className,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { id: string; label: ReactNode }) {
  return (
    <div className={cx("flex items-center gap-2", className)}>
      <input id={id} type="checkbox" {...props} className="h-4 w-4 rounded-sm accent-accent" />
      <label htmlFor={id} className="text-base text-primary">
        {label}
      </label>
    </div>
  );
}

export function RadioGroup({
  name,
  legend,
  options,
  value,
  onChange,
  orientation = "vertical",
}: {
  name: string;
  legend: string;
  options: Array<SelectOption & { description?: string }>;
  value: string;
  onChange: (value: string) => void;
  orientation?: "vertical" | "horizontal";
}) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-medium text-primary">{legend}</legend>
      <div className={cx("flex gap-2", orientation === "vertical" ? "flex-col" : "flex-wrap gap-x-5")}>
        {options.map((o) => {
          const id = `${name}-${o.value}`;
          return (
            <div key={o.value} className="flex items-start gap-2">
              <input
                id={id}
                type="radio"
                name={name}
                value={o.value}
                checked={value === o.value}
                onChange={() => onChange(o.value)}
                className="mt-1 h-4 w-4 accent-accent"
              />
              <label htmlFor={id} className="text-base text-primary">
                {o.label}
                {o.description && <span className="block text-sm text-muted">{o.description}</span>}
              </label>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
