import { useState, type ReactNode } from "react";
import { Maximize2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

interface ChartZoomButtonProps {
  title: string;
  description?: string;
  /** The enlarged chart to render inside the zoom dialog — only mounted while open. */
  children: ReactNode;
  className?: string;
}

/** Small "expand" trigger that opens the same chart at a larger size in a dialog, for closer reading. */
export function ChartZoomButton({ title, description, children, className }: ChartZoomButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        variant="outline"
        size="icon"
        className={className}
        onClick={() => setOpen(true)}
        title="Zoom chart"
        aria-label="Zoom chart"
      >
        <Maximize2 className="h-3.5 w-3.5" />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </DialogHeader>
          <div className="pt-2">{open && children}</div>
        </DialogContent>
      </Dialog>
    </>
  );
}
