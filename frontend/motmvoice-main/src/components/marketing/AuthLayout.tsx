import { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Mic } from "lucide-react";
import { SoundWave } from "./SoundWave";

export function AuthLayout({ children, title, subtitle }: { children: ReactNode; title: string; subtitle: string }) {
  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="relative hidden lg:flex flex-col justify-between p-12 overflow-hidden bg-mesh">
        <Link to="/" className="flex items-center gap-2 relative z-10">
          <div className="h-9 w-9 rounded-lg bg-gradient-primary grid place-items-center shadow-glow">
            <Mic className="h-4 w-4 text-white" />
          </div>
          <span className="font-bold text-lg">MOTMVoice</span>
        </Link>
        <div className="relative z-10">
          <h2 className="text-5xl font-bold leading-tight">
            <span className="text-gradient">Voice</span> that converts.
          </h2>
          <p className="mt-4 text-muted-foreground max-w-md">
            Join 200+ sales teams running thousands of AI voice calls every day.
          </p>
          <div className="mt-10 glass rounded-xl p-6">
            <SoundWave bars={32} />
            <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
              <span>● Live calls in progress</span>
              <span className="font-mono">1,247 today</span>
            </div>
          </div>
        </div>
        <div className="text-xs text-muted-foreground relative z-10">© 2026 MOTMVoice</div>
      </div>
      <div className="flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md fade-up">
          <div className="lg:hidden mb-8 flex items-center gap-2">
            <div className="h-9 w-9 rounded-lg bg-gradient-primary grid place-items-center"><Mic className="h-4 w-4 text-white" /></div>
            <span className="font-bold text-lg">MOTMVoice</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{subtitle}</p>
          <div className="mt-8">{children}</div>
        </div>
      </div>
    </div>
  );
}
