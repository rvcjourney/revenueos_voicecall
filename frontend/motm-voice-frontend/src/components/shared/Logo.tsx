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
          style={{ backgroundImage: "linear-gradient(135deg, #7dd3fc, #2563eb)" }}
        >
          Howl
        </span>
      </span>
    </span>
  );
}
