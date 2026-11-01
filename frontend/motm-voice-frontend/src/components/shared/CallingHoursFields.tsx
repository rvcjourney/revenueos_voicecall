import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export type CallingHours = { start: string; end: string; days: string[] };

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

// Same as the backend's CampaignCreate defaults.
export const DEFAULT_CALLING_HOURS: CallingHours = {
  start: "09:00",
  end: "19:00",
  days: ["mon", "tue", "wed", "thu", "fri", "sat"],
};

/** Returns why the hours can't be saved, or null when they're fine. */
export function callingHoursError(h: CallingHours): string | null {
  if (!h.days.length) return "Pick at least one calling day";
  if (!h.start || !h.end || h.end <= h.start) return "Calling hours must end after they start";
  return null;
}

/** Start/end time + day toggles. Times are the campaign's timezone (India time by default). */
export function CallingHoursFields({ value, onChange }: { value: CallingHours; onChange: (v: CallingHours) => void }) {
  function toggle(day: string) {
    const days = value.days.includes(day) ? value.days.filter((d) => d !== day) : [...value.days, day];
    onChange({ ...value, days: DAYS.filter((d) => days.includes(d)) });
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="calling-start">Start calling at</Label>
          <Input id="calling-start" type="time" value={value.start} onChange={(e) => onChange({ ...value, start: e.target.value })} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="calling-end">Stop calling at</Label>
          <Input id="calling-end" type="time" value={value.end} onChange={(e) => onChange({ ...value, end: e.target.value })} />
        </div>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Calling days">
        {DAYS.map((d) => {
          const on = value.days.includes(d);
          return (
            <button
              key={d}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(d)}
              className={cn(
                "h-9 min-w-12 rounded-md border px-3 text-sm font-medium capitalize transition-colors",
                on ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground hover:bg-muted"
              )}
            >
              {d}
            </button>
          );
        })}
      </div>
      {callingHoursError(value) && <p className="text-xs text-destructive">{callingHoursError(value)}</p>}
    </div>
  );
}
