"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, ReactElement, ReactNode, Ref } from "react";
import { cx } from "@/lib/cx";
import { Tooltip, type TooltipSide } from "./tooltip";

export type IconButtonSize = "sm" | "md";

const SIZE: Record<IconButtonSize, string> = {
  sm: "size-7 [&_svg]:size-3.5",
  md: "size-8 [&_svg]:size-4",
};

/** Class string shared by the button and link forms. */
export function iconButtonClass(size: IconButtonSize = "md", active = false): string {
  return cx(
    "inline-flex shrink-0 items-center justify-center rounded-md border border-transparent",
    "transition-[background-color,color] duration-(--duration-fast) ease-standard",
    "disabled:cursor-not-allowed disabled:opacity-50",
    SIZE[size],
    active ? "bg-accent-subtle text-accent-text" : "text-secondary hover:bg-surface-muted hover:text-primary active:bg-sunken",
  );
}

interface CommonProps {
  /** Accessible name (always required: the control has no visible text). */
  label: string;
  icon: ReactNode;
  size?: IconButtonSize;
  /** Current section or pressed state: accent tint, plus `aria-current` for links. */
  active?: boolean;
  /** Tooltip body; defaults to `label`. Pass `false` for no tooltip. */
  tooltip?: ReactNode | false;
  tooltipSide?: TooltipSide;
  className?: string;
}

export type IconButtonProps = CommonProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "aria-label" | "className"> & { ref?: Ref<HTMLButtonElement> };
export type IconLinkProps = CommonProps & { href: string; onClick?: () => void };

function withTooltip(control: ReactElement<{ "aria-describedby"?: string }>, label: string, tooltip: ReactNode | false | undefined, side: TooltipSide) {
  const tip = tooltip === undefined ? label : tooltip;
  if (tip === false) return control;
  // A tip that only repeats the accessible name is hidden from assistive technology.
  return (
    <Tooltip content={tip} side={side} decorative={tip === label}>
      {control}
    </Tooltip>
  );
}

/** Square icon-only button with a tooltip (defaults to its accessible name). */
export function IconButton({
  label,
  icon,
  size = "md",
  active = false,
  tooltip,
  tooltipSide = "bottom",
  className,
  type = "button",
  ...rest
}: IconButtonProps) {
  const control = (
    <button type={type} aria-label={label} {...rest} className={cx(iconButtonClass(size, active), className)}>
      {icon}
    </button>
  );
  return withTooltip(control, label, tooltip, tooltipSide);
}

/** Icon-only `next/link` with a tooltip; `active` marks it `aria-current="page"`. */
export function IconLink({ label, icon, size = "md", active = false, tooltip, tooltipSide = "bottom", className, href, onClick }: IconLinkProps) {
  const control = (
    <Link
      href={href}
      aria-label={label}
      aria-current={active ? "page" : undefined}
      onClick={onClick}
      className={cx(iconButtonClass(size, active), className)}
    >
      {icon}
    </Link>
  );
  return withTooltip(control, label, tooltip, tooltipSide);
}
