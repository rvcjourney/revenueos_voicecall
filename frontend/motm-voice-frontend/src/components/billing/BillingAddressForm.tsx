import { useState } from "react";
import { toast } from "sonner";
import { Loader2, MapPin } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useSaveBillingAddress } from "@/lib/hooks";
import { apiErrorMessage } from "@/lib/api";
import { INDIAN_STATES } from "@/lib/indianStates";
import type { BillingAddress } from "@/lib/types";

// Shown either (a) in place of the plan picker/payment button whenever the
// org's billing state isn't on file yet -- app/api/billing.py:checkout()
// rejects checkout without one, needed to decide CGST+SGST vs IGST on the GST
// tax invoice generated once payment confirms -- or (b) pre-filled, as an
// editable "Billing details" card for an org that already has one on file.
export function BillingAddressForm({
  onSaved,
  initial,
}: {
  onSaved: () => void;
  initial?: BillingAddress;
}) {
  const saveAddress = useSaveBillingAddress();
  const [state, setState] = useState(initial?.state ?? "");
  const [addressLine, setAddressLine] = useState(initial?.address_line ?? "");
  const [city, setCity] = useState(initial?.city ?? "");
  const [pincode, setPincode] = useState(initial?.pincode ?? "");
  const [gstin, setGstin] = useState(initial?.gstin ?? "");

  async function save() {
    if (!state) {
      toast.error("Select your state");
      return;
    }
    try {
      await saveAddress.mutateAsync({
        state,
        address_line: addressLine || null,
        city: city || null,
        pincode: pincode || null,
        gstin: gstin || null,
      });
      toast.success("Billing address saved");
      onSaved();
    } catch (err) {
      toast.error(apiErrorMessage(err, "Couldn't save billing address"));
    }
  }

  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardContent className="space-y-4 pt-6">
        <div className="flex items-start gap-2">
          <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <div>
            <p className="font-medium">Billing address</p>
            <p className="text-sm text-muted-foreground">
              Used to apply GST correctly on your invoices — required before checkout.
            </p>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2">
            <Label>State *</Label>
            <Select value={state} onValueChange={setState}>
              <SelectTrigger><SelectValue placeholder="Select state" /></SelectTrigger>
              <SelectContent>
                {INDIAN_STATES.map((s) => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Address line</Label>
            <Input value={addressLine} onChange={(e) => setAddressLine(e.target.value)} placeholder="Optional" />
          </div>
          <div className="space-y-1.5">
            <Label>City</Label>
            <Input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Optional" />
          </div>
          <div className="space-y-1.5">
            <Label>Pincode</Label>
            <Input value={pincode} onChange={(e) => setPincode(e.target.value)} placeholder="Optional" />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label>GSTIN</Label>
            <Input value={gstin} onChange={(e) => setGstin(e.target.value)} placeholder="Optional — for your input tax credit" />
          </div>
        </div>
        <Button variant="gradient" onClick={save} disabled={saveAddress.isPending}>
          {saveAddress.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Save
        </Button>
      </CardContent>
    </Card>
  );
}
