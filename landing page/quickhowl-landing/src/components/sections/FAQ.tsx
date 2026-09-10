import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

const faqs = [
  {
    q: "Is this compliant with India's calling regulations?",
    a: "Yes. Every organization gets its own Do Not Call list, and all numbers are automatically checked against India's TRAI NCPR (National Customer Preference Register) before dialing.",
  },
  {
    q: "Do the AI agents actually sound natural in Hindi-English mixed conversations?",
    a: "The default agent language is Hinglish — code-mixed Hindi/English speech-to-text and text-to-speech tuned for natural, code-switching conversation. Pure Hindi and pure English are supported too.",
  },
  {
    q: "Can I use this outside India?",
    a: "Yes. Agents connect to any SIP-based number worldwide, and teams outside India use QuickHowl for English-only outbound too.",
  },
  {
    q: "Can I use my own phone number?",
    a: "Yes. Connect your own SIP trunk through a guided self-serve flow: add your credentials, run a live test call, and you're ready to dial.",
  },
  {
    q: "What happens if a call reaches voicemail or an automated phone tree?",
    a: "The agent detects voicemail greetings and IVR/phone-tree prompts and hangs up instantly, so you're not billed for dead air.",
  },
  {
    q: "Can my sales reps use this without full admin access?",
    a: "Yes. Members get a restricted view — their own campaigns only — and must request access to each AI agent before using it, which an admin approves.",
  },
  {
    q: "Can I use my own voice, or a custom voice, for the AI agent?",
    a: "Yes. Clone your own voice, a top rep's, or your founder's once using our voice cloning tool, then assign that voice to any AI agent — no re-recording needed for future campaigns.",
  },
];

export function FAQ() {
  return (
    <section id="faq" className="section-pad border-t border-border/60">
      <div className="reveal-on-scroll mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
        <h2 className="text-center font-heading text-3xl font-semibold sm:text-4xl">Frequently asked questions</h2>
        <Accordion type="single" collapsible className="mt-10">
          {faqs.map((f) => (
            <AccordionItem key={f.q} value={f.q}>
              <AccordionTrigger>{f.q}</AccordionTrigger>
              <AccordionContent>{f.a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </section>
  );
}
