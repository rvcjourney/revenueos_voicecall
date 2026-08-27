import { useEffect } from "react";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { PlatformTabProvider } from "@/lib/platformTab";

const LAST_UPDATED = "25 August 2026";

function Section({ id, title, children }: { id?: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 space-y-3">
      <h2 className="font-heading text-xl font-semibold sm:text-2xl">{title}</h2>
      <div className="space-y-3 text-sm leading-relaxed text-muted-foreground sm:text-base">{children}</div>
    </section>
  );
}

export default function TermsOfService() {
  // No client-side router here (see App.tsx) -- a link like
  // /terms-of-service#trai-dnc-compliance is a full page reload, and the
  // browser's native "scroll to fragment on load" runs before React has
  // mounted this page, so the target element doesn't exist yet and the jump
  // silently does nothing. Redo it manually once mounted.
  useEffect(() => {
    if (!window.location.hash) return;
    const el = document.querySelector(window.location.hash);
    el?.scrollIntoView();
  }, []);

  return (
    <PlatformTabProvider>
      <div className="min-h-screen overflow-x-clip bg-background">
        <Nav />

        <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
          <p className="eyebrow text-primary">Legal</p>
          <h1 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">Terms of Service</h1>
          <p className="mt-2 text-sm text-muted-foreground">Last updated: {LAST_UPDATED}</p>

          <div className="mt-10 space-y-10">
            <Section title="1. Acceptance of Terms">
              <p>
                These Terms of Service ("Terms") are an agreement between QuickHowl ("QuickHowl", "we", "us", "our")
                and the organization or individual using our platform ("Customer", "you", "your"). By creating an
                account, accessing quickhowl.com, or using the QuickHowl application, you agree to be bound by these
                Terms. If you're accepting on behalf of an organization, you confirm you have the authority to do
                so, and "you" refers to that organization.
              </p>
              <p>If you do not agree to these Terms, do not use QuickHowl.</p>
            </Section>

            <Section title="2. The Service">
              <p>
                QuickHowl is an AI voice-calling platform. It lets you upload contact lists, configure AI voice
                agents, and run outbound and inbound calling campaigns over telephony infrastructure we operate or
                integrate with. Features, plans, and pricing are described on quickhowl.com and inside the
                application, and may change over time as described in Section 12.
              </p>
            </Section>

            <Section title="3. Your Account">
              <ul className="list-disc space-y-2 pl-5">
                <li>You must provide accurate information when creating an account and keep it up to date.</li>
                <li>You're responsible for activity under your account, including actions taken by team members you invite.</li>
                <li>You must keep login credentials confidential and tell us promptly if you suspect unauthorized access.</li>
                <li>You must be legally able to enter into a binding contract, and your organization must be legally permitted to conduct outbound/inbound telemarketing calls in the jurisdictions you operate in.</li>
              </ul>
            </Section>

            <Section title="4. Acceptable Use">
              <p>You agree not to use QuickHowl to:</p>
              <ul className="list-disc space-y-2 pl-5">
                <li>Call, or upload contact lists of, individuals who have not consented to be contacted, or who are registered on a do-not-call/do-not-disturb list you're not permitted to call.</li>
                <li>Impersonate a person or organization, or misrepresent who is calling or why.</li>
                <li>Run campaigns for fraud, phishing, debt-collection harassment, political robocalling, or any other unlawful or deceptive purpose.</li>
                <li>Clone a voice without the recorded, on-camera consent of the person whose voice it is (see Section 6).</li>
                <li>Attempt to circumvent rate limits, concurrency limits, or the platform's Do-Not-Call enforcement.</li>
                <li>Reverse-engineer, resell, or white-label the platform without our written agreement.</li>
              </ul>
              <p>We may suspend or terminate accounts that violate this section, as described in Section 9.</p>
            </Section>

            <Section id="trai-dnc-compliance" title="5. TRAI / Do-Not-Call (DNC) Compliance">
              <p>
                QuickHowl automatically checks every outbound call against your organization's own Do-Not-Call list
                and against India's TRAI National Customer Preference Register (NCPR) before dialing. Any called
                party can also ask to be marked do-not-call during a live call, and that number is excluded from all
                future campaigns on your account automatically — this runs on every call by default, not as an
                opt-in setting.
              </p>
              <p>
                This built-in enforcement reduces risk, but it does not transfer legal responsibility away from you.
                As the Customer, you represent and warrant that:
              </p>
              <ul className="list-disc space-y-2 pl-5">
                <li>You have a lawful basis (consent, an existing business relationship, or another valid basis under applicable law) to call every number in any contact list you upload.</li>
                <li>Your use of QuickHowl complies with TRAI's regulations on commercial communications, India's telemarketing registration requirements applicable to your business, and any other telecom or consumer-protection law that applies to your campaigns.</li>
                <li>You will not use QuickHowl to call numbers you know or reasonably should know are on a do-not-call registry, outside our automatic enforcement (for example, numbers registered after our data was last synced).</li>
              </ul>
              <p>
                Violating TRAI/DNC obligations is treated as a material breach of these Terms and may result in
                immediate suspension of your account under Section 9, in addition to any liability you hold under
                applicable law.
              </p>
            </Section>

            <Section title="6. Voice Cloning">
              <p>
                If you submit a voice sample for cloning, you must also submit a recorded, on-camera consent video
                in which the speaker confirms it is their own voice and authorizes it to be cloned and used on
                QuickHowl. Every request is manually reviewed before a cloned voice is created. You are responsible
                for ensuring you have the right to use that person's voice, and for any consequences of using a
                cloned voice in a way that misleads a called party about who — or what — they're speaking to.
              </p>
            </Section>

            <Section title="7. Fees &amp; Payment">
              <ul className="list-disc space-y-2 pl-5">
                <li>Paid plans are billed in advance on a recurring basis, processed through Razorpay; your card/UPI details are handled by Razorpay and never stored on our servers.</li>
                <li>Call usage is measured in minutes ("credits") against your plan's monthly allotment; usage beyond that allotment is billed as overage at the rate shown on your plan.</li>
                <li>GST-compliant tax invoices are generated for each billing period and available from your dashboard.</li>
                <li>Fees are non-refundable except where required by law or expressly stated otherwise.</li>
                <li>We may suspend service for accounts with a failed or overdue payment, after reasonable notice.</li>
              </ul>
            </Section>

            <Section title="8. Your Content &amp; Data">
              <p>
                Contact lists, call recordings, transcripts, and any other data you upload or generate through
                QuickHowl ("Customer Data") remain yours. You grant us a license to process Customer Data solely to
                provide the Service to you — placing calls, generating transcripts and summaries, and similar
                platform functions. We do not sell Customer Data, and we do not use one Customer's data to benefit
                or train models for another. Full detail on what we collect and how it's handled is in our{" "}
                <a href="/privacy-policy" className="text-primary hover:underline">
                  Privacy Policy
                </a>
                .
              </p>
            </Section>

            <Section title="9. Suspension &amp; Termination">
              <p>
                You may stop using QuickHowl and close your account at any time. We may suspend or terminate your
                access, with or without notice, if you materially breach these Terms (including Sections 4 or 5),
                if required by law, or if your account poses a security or compliance risk to QuickHowl or others.
                On termination, your right to use the Service ends immediately; data retention after termination is
                governed by our Privacy Policy.
              </p>
            </Section>

            <Section title="10. Disclaimers">
              <p>
                QuickHowl is provided "as is" and "as available." We don't guarantee the Service will be
                uninterrupted, error-free, or that AI-generated conversations, summaries, or classifications will
                always be accurate — AI voice and language models can make mistakes. You're responsible for
                reviewing outputs (call outcomes, extracted data, summaries) before relying on them for business
                decisions.
              </p>
            </Section>

            <Section title="11. Limitation of Liability">
              <p>
                To the maximum extent permitted by law, QuickHowl will not be liable for indirect, incidental, or
                consequential damages arising from your use of the Service, and our total liability for any claim
                relating to the Service is limited to the amount you paid us in the 3 months before the claim arose.
                Nothing in these Terms limits liability that cannot be limited under applicable law.
              </p>
            </Section>

            <Section title="12. Changes to These Terms">
              <p>
                We may update these Terms from time to time. Material changes will be reflected by updating the
                "Last updated" date above; continued use of QuickHowl after a change means you accept the revised
                Terms. If a change materially reduces your rights, we'll make reasonable efforts to notify active
                Customers in advance.
              </p>
            </Section>

            <Section title="13. Governing Law">
              <p>
                These Terms are governed by the laws of India. Any dispute arising from these Terms or your use of
                QuickHowl is subject to the exclusive jurisdiction of the courts of Pune, Maharashtra, India.
              </p>
            </Section>

            <Section title="14. Contact Us">
              <p>For any questions about these Terms, contact us at:</p>
              <p className="text-foreground">
                QuickHowl<br />
                FIRST FLOOR, Reality Warehousing Pvt Ltd, GAT NO.-1337/1, Pune Nagar Road,
                Above Reliance Smart, Wagholi, Pune, Maharashtra, India<br />
                Email: <a href="mailto:support@quickhowl.com" className="text-primary hover:underline">support@quickhowl.com</a><br />
                Phone: <a href="tel:+918308655418" className="text-primary hover:underline">+91 83086 55418</a>
              </p>
            </Section>
          </div>
        </div>

        <Footer />
      </div>
    </PlatformTabProvider>
  );
}
