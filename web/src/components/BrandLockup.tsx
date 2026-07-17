import { Cable } from "lucide-react";

type BrandLockupProps = {
  compact?: boolean;
  inverse?: boolean;
};

export function BrandLockup({ compact = false, inverse = false }: BrandLockupProps) {
  return (
    <span className={`brand-lockup${compact ? " is-compact" : ""}${inverse ? " is-inverse" : ""}`}>
      <span className="brand-symbol" aria-hidden="true">
        <span className="brand-symbol-orbit" />
        <Cable size={compact ? 18 : 21} strokeWidth={1.9} />
      </span>
      <span className="brand-wordmark">Connector</span>
    </span>
  );
}
