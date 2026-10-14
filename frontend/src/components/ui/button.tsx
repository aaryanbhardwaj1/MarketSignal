import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
import { cx } from "@/lib/cx";

/**
 * `primary` is the one accent action per view; `secondary` is the hairline default; `ghost` is a
 * borderless toolbar action; `quiet` is an inline text action (accent text, no chrome).
 */
export type ButtonVariant = "primary" | "secondary" | "ghost" | "quiet" | "danger";
export type ButtonSize = "sm" | "md";

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "border-accent bg-accent text-white shadow-raised hover:border-accent-hover hover:bg-accent-hover active:bg-accent-hover",
  secondary:
    "border-border-strong bg-surface text-primary shadow-raised hover:border-text-disabled hover:bg-surface-muted active:bg-sunken",
  ghost: "border-transparent bg-transparent text-secondary hover:bg-surface-muted hover:text-primary active:bg-sunken",
  quiet: "border-transparent bg-transparent px-1.5 text-accent-text hover:bg-accent-subtle active:bg-accent-muted",
  danger: "border-danger bg-danger text-white shadow-raised hover:opacity-90 active:opacity-100",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-sm [&_svg]:size-3.5",
  md: "h-9 px-3.5 text-base [&_svg]:size-4",
};

/** Class string for any element that should look like a button (links, summary, label). */
export function buttonClass(variant: ButtonVariant = "primary", size: ButtonSize = "md"): string {
  return cx(
    "inline-flex select-none items-center justify-center gap-1.5 whitespace-nowrap rounded-md border font-medium",
    "transition-[background-color,border-color,color,opacity] duration-(--duration-fast) ease-standard",
    "disabled:cursor-not-allowed disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50",
    SIZES[size],
    VARIANTS[variant],
  );
}

function Spinner() {
  return (
    <span
      aria-hidden
      className="h-3.5 w-3.5 rounded-full border-2 border-current border-r-transparent motion-safe:animate-spin"
    />
  );
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  iconLeft,
  className,
  children,
  disabled,
  type = "button",
  onClick,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  iconLeft?: ReactNode;
}) {
  return (
    <button
      type={type}
      {...rest}
      // While loading the button stays focusable (aria-disabled), so keyboard and screen-reader
      // users keep their place; activation is ignored. Only `disabled` uses the native attribute.
      disabled={disabled}
      aria-disabled={loading && !disabled ? true : rest["aria-disabled"]}
      aria-busy={loading || undefined}
      onClick={(event) => {
        if (loading) {
          event.preventDefault();
          return;
        }
        onClick?.(event);
      }}
      className={cx(buttonClass(variant, size), className)}
    >
      {loading ? <Spinner /> : iconLeft}
      {children}
    </button>
  );
}

export function LinkButton({
  href,
  variant = "secondary",
  size = "md",
  iconLeft,
  className,
  children,
  ...rest
}: Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
  variant?: ButtonVariant;
  size?: ButtonSize;
  iconLeft?: ReactNode;
}) {
  return (
    <Link href={href} {...rest} className={cx(buttonClass(variant, size), className)}>
      {iconLeft}
      {children}
    </Link>
  );
}
