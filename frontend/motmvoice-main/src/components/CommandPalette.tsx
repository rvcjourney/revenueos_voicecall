import { useState, useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  LayoutDashboard, Megaphone, Phone, BarChart3, Bot, Settings,
  Users, PhoneOff, ClipboardList, ArrowRight,
} from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import {
  Command, CommandInput, CommandList, CommandEmpty,
  CommandGroup, CommandItem, CommandSeparator,
} from "@/components/ui/command";
import { useCampaigns } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";

const NAV_ITEMS = [
  { label: "Dashboard",    to: "/dashboard",    icon: LayoutDashboard },
  { label: "Campaigns",    to: "/campaigns",    icon: Megaphone       },
  { label: "Call History", to: "/calls",        icon: Phone           },
  { label: "Analytics",    to: "/analytics",    icon: BarChart3       },
  { label: "AI Agents",    to: "/agents",       icon: Bot             },
  { label: "Settings",     to: "/settings",     icon: Settings        },
] as const;

const ADMIN_NAV_ITEMS = [
  { label: "Team",      to: "/admin/users", icon: Users         },
  { label: "DNC List",  to: "/admin/dnc",   icon: PhoneOff      },
  { label: "Audit Log", to: "/admin/audit", icon: ClipboardList },
] as const;

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const { isAdmin } = useAuth();
  const { data: campaignsData } = useCampaigns();

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  function go(to: string, params?: Record<string, string>) {
    navigate({ to, params } as any);
    setOpen(false);
  }

  const campaigns = campaignsData?.items ?? [];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="p-0 max-w-lg overflow-hidden gap-0 [&>button]:hidden">
        <Command>
          <CommandInput placeholder="Search pages, campaigns…" />
          <CommandList>
            <CommandEmpty>No results found.</CommandEmpty>
            <CommandGroup heading="Navigation">
              {NAV_ITEMS.map((item) => (
                <CommandItem
                  key={item.to}
                  onSelect={() => go(item.to)}
                  className="flex items-center gap-2 cursor-pointer"
                >
                  <item.icon className="h-4 w-4 text-muted-foreground" />
                  {item.label}
                </CommandItem>
              ))}
              {isAdmin &&
                ADMIN_NAV_ITEMS.map((item) => (
                  <CommandItem
                    key={item.to}
                    onSelect={() => go(item.to)}
                    className="flex items-center gap-2 cursor-pointer"
                  >
                    <item.icon className="h-4 w-4 text-muted-foreground" />
                    {item.label}
                  </CommandItem>
                ))}
            </CommandGroup>

            {campaigns.length > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup heading="Campaigns">
                  {campaigns.slice(0, 8).map((c) => (
                    <CommandItem
                      key={c.id}
                      onSelect={() => go("/campaigns/$id", { id: c.id })}
                      className="flex items-center gap-2 cursor-pointer"
                    >
                      <Megaphone className="h-4 w-4 text-muted-foreground" />
                      <span className="flex-1 truncate">{c.name}</span>
                      <ArrowRight className="h-3.5 w-3.5 text-muted-foreground/40" />
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>

          <div className="px-3 py-2 border-t border-border/50 flex items-center gap-3 text-[10px] text-muted-foreground/50">
            <span>
              <kbd className="px-1.5 py-0.5 rounded border border-border text-[10px]">↵</kbd> open
            </span>
            <span>
              <kbd className="px-1.5 py-0.5 rounded border border-border text-[10px]">ESC</kbd> close
            </span>
            <span className="ml-auto">
              <kbd className="px-1.5 py-0.5 rounded border border-border text-[10px]">⌘K</kbd>{" "}
              <span className="opacity-50">or</span>{" "}
              <kbd className="px-1.5 py-0.5 rounded border border-border text-[10px]">Ctrl+K</kbd>
            </span>
          </div>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
