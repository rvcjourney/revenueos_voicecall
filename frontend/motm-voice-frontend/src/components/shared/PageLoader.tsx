import { LogoMark } from "@/components/shared/Logo";

export function PageLoader() {
  return (
    <div className="flex h-screen w-full items-center justify-center bg-background">
      <LogoMark className="h-10 w-10 animate-pulse-glow" />
    </div>
  );
}
