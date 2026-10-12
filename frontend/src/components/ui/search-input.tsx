"use client";

import { useState, type FormEvent } from "react";
import { cx } from "@/lib/cx";
import { CONTROL_CLASS } from "./control-class";

/** Search box with its own submit; Enter submits the trimmed value. */
export function SearchInput({
  id,
  label,
  defaultValue = "",
  placeholder = "Search",
  onSubmit,
}: {
  id: string;
  label: string;
  defaultValue?: string;
  placeholder?: string;
  onSubmit: (value: string) => void;
}) {
  const [value, setValue] = useState(defaultValue);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(value.trim());
  };
  return (
    <form role="search" onSubmit={submit} className="relative w-full">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <svg
        aria-hidden
        viewBox="0 0 16 16"
        className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      >
        <circle cx="7" cy="7" r="4.5" />
        <path d="m10.5 10.5 3 3" strokeLinecap="round" />
      </svg>
      <input
        id={id}
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        className={cx(CONTROL_CLASS, "h-9 pl-8")}
      />
    </form>
  );
}
