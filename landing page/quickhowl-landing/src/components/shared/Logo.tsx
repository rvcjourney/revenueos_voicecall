import { cn } from "@/lib/utils";
import logoIcon from "@/assets/logo-icon.png";

export function LogoMark({ className }: { className?: string }) {
  return <img src={logoIcon} alt="" className={cn("h-8 w-auto object-contain", className)} aria-hidden />;
}

export function Logo({ className, iconClassName }: { className?: string; iconClassName?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-heading text-lg font-semibold tracking-tight", className)}>
      <LogoMark className={iconClassName} />
      <span>
        Quick
        <span
          className="bg-clip-text text-transparent"
          style={{ backgroundImage: "var(--gradient-primary)" }}
        >
          Howl
        </span>
      </span>
    </span>
  );
}
