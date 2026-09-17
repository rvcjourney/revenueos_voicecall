import { useState } from "react";
import { Check, Loader2, Upload, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ContactsUploader({
  onFile,
  uploading,
  count,
}: {
  onFile: (file: File) => void;
  uploading: boolean;
  count: number | null;
}) {
  const [dragOver, setDragOver] = useState(false);

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed p-10 text-center transition-colors",
        dragOver ? "border-primary bg-primary/10" : "border-border hover:bg-muted/30"
      )}
    >
      <input
        type="file"
        accept=".csv,.xlsx,.xls"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
        }}
      />
      {uploading ? (
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      ) : count !== null ? (
        <Check className="h-8 w-8 text-success" />
      ) : (
        <UploadCloud className="h-8 w-8 text-muted-foreground" />
      )}
      <div>
        <p className="text-sm font-medium">
          {count !== null ? `${count} contacts uploaded` : "Drag & drop a CSV or Excel file"}
        </p>
        <p className="text-xs text-muted-foreground">or click to browse — thousands of contacts supported</p>
      </div>
      <Button type="button" variant="outline" size="sm" asChild>
        <span>
          <Upload className="h-3.5 w-3.5" /> {count !== null ? "Replace file" : "Choose file"}
        </span>
      </Button>
    </label>
  );
}
