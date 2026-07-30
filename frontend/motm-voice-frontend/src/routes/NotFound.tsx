import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/shared/Logo";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-4 text-center">
      <Logo />
      <div className="space-y-2">
        <p className="font-heading text-6xl font-semibold text-gradient">404</p>
        <p className="text-muted-foreground">This page doesn't exist, or you don't have access to it.</p>
      </div>
      <Button variant="gradient" asChild>
        <Link to="/">Back to home</Link>
      </Button>
    </div>
  );
}
