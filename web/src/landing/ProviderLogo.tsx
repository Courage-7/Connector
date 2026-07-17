import type { LucideIcon } from "lucide-react";
import type { SimpleIcon } from "simple-icons";

type ProviderLogoProps = {
  icon?: SimpleIcon;
  fallback?: LucideIcon;
  color: string;
  size?: number;
};

export function ProviderLogo({ icon, fallback: Fallback, color, size = 22 }: ProviderLogoProps) {
  if (icon) {
    return (
      <svg
        aria-hidden="true"
        className="provider-logo"
        height={size}
        viewBox="0 0 24 24"
        width={size}
      >
        <path d={icon.path} fill={color} />
      </svg>
    );
  }

  return Fallback ? <Fallback aria-hidden="true" color={color} size={size} strokeWidth={1.8} /> : null;
}
