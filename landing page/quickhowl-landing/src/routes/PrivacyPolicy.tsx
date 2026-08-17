import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";

const LAST_UPDATED = "17 August 2026";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="font-heading text-xl font-semibold sm:text-2xl">{title}</h2>
      <div className="space-y-3 text-sm leading-relaxed text-muted-foreground sm:text-base">{children}</div>
    </section>
  );
}

export default function PrivacyPolicy() {
  return (
    <div className="min-h-screen overflow-x-clip bg-background">
      <Nav />

      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
        <p className="eyebrow text-primary">Legal</p>
        <h1 className="mt-3 font-heading text-3xl font-semibold sm:text-4xl">Privacy Policy</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated: {LAST_UPDATED}</p>

        <div className="mt-10 space-y-10">
          <Section title="1. Introduction">
            <p>
              QuickHowl ("QuickHowl", "we", "us", "our") operates an AI voice-calling platform that lets
              businesses ("Customers", "you", "your organization") upload contact lists and run outbound and
              inbound voice campaigns using AI agents, over calls placed through our telephony and voice-AI
              infrastructure.
            </p>
            <p>
              This Privacy Policy explains what personal data we collect, how we use it, who we share it with,
              and the choices and rights you have. It applies to visitors of quickhowl.com, users of the
              QuickHowl application, and — where noted below — to individuals contacted through calls placed by
              a Customer using QuickHowl.
            </p>
            <p>
              By using our website or platform, you agree to the practices described in this policy. If you do
              not agree, please do not use QuickHowl.
            </p>
          </Section>

          <Section title="2. Two roles: Controller and Processor">
            <p>
              QuickHowl acts in two different capacities, and which one applies changes what we can do with your
              data:
            </p>
            <p>
              <strong className="text-foreground">As a Data Controller</strong> — for account, billing, and
              platform-usage data belonging to the businesses that sign up for QuickHowl (your login details,
              organization details, billing address, GSTIN, subscription and payment records, and how you use
              our dashboard). We decide how this data is used, as described in this policy.
            </p>
            <p>
              <strong className="text-foreground">As a Data Processor</strong> — for the contact lists, phone
              numbers, call recordings, and transcripts that a Customer organization uploads or generates while
              running campaigns on QuickHowl. That data belongs to, and is controlled by, the Customer
              organization — we process it only on their instructions, to deliver the calling service they've
              configured. If you were contacted by a business using QuickHowl and have questions about why you
              were called or want your number removed, please contact that business directly; we act on their
              instructions regarding their own contact lists.
            </p>
          </Section>

          <Section title="3. Information We Collect">
            <p>
              <strong className="text-foreground">Account &amp; organization data.</strong> Name, work email,
              password (stored as a salted hash, never in plain text), organization name, and role, collected
              when you sign up or when a team admin invites you.
            </p>
            <p>
              <strong className="text-foreground">Billing data.</strong> Billing address, state, and GSTIN (for
              GST-compliant invoicing), plan selection, and subscription status. Card and UPI details are
              entered directly into Razorpay's checkout and are never transmitted to or stored on QuickHowl's own
              servers.
            </p>
            <p>
              <strong className="text-foreground">Campaign contact data.</strong> Names, phone numbers, and any
              other fields a Customer includes in an uploaded contact list, for the purpose of placing calls on
              that Customer's behalf. This is Customer data — see Section 2.
            </p>
            <p>
              <strong className="text-foreground">Call data.</strong> Call recordings (audio), speech-to-text
              transcripts, call duration, timestamps, call status/outcome (e.g. answered, no-answer, interested,
              do-not-call), and AI-generated summaries produced from a call.
            </p>
            <p>
              <strong className="text-foreground">Voice cloning data.</strong> If a Customer chooses to clone a
              voice for use as an AI agent, we collect a voice audio sample and a recorded consent video in
              which the speaker confirms, on camera, that it is their own voice and that they authorize it to be
              cloned and used on QuickHowl. Every voice-cloning request is manually reviewed by our team before
              any cloned voice is created.
            </p>
            <p>
              <strong className="text-foreground">Technical &amp; usage data.</strong> IP address, browser/device
              information, login session data, and product usage such as calls placed, credits consumed, and
              pages visited within the dashboard, used to keep the platform secure and to improve it.
            </p>
            <p>
              <strong className="text-foreground">Cookies.</strong> Our marketing website does not currently use
              third-party advertising or analytics cookies. The application uses only what's strictly necessary
              to keep you signed in (session/authentication tokens).
            </p>
          </Section>

          <Section title="4. How We Use Information">
            <ul className="list-disc space-y-2 pl-5">
              <li>To provide, operate, and maintain the QuickHowl platform, including placing and receiving calls.</li>
              <li>To process payments, generate GST-compliant tax invoices, and manage subscriptions.</li>
              <li>To generate call transcripts, AI summaries, and analytics for the Customer that ran the campaign.</li>
              <li>To review and approve voice-cloning requests, and to keep the consent recording as proof of authorization for as long as that cloned voice remains in use.</li>
              <li>To maintain Do-Not-Call (DNC) records so numbers that have opted out are not called again.</li>
              <li>To detect, investigate, and prevent fraud, abuse, or security incidents.</li>
              <li>To respond to support requests and communicate service-related updates.</li>
              <li>To comply with applicable law, including tax, telecom, and data-protection regulation.</li>
            </ul>
            <p>We do not sell personal data, and we do not use Customer contact-list or call data to train models for any organization other than the Customer it belongs to.</p>
          </Section>

          <Section title="5. Who We Share Data With">
            <p>
              We share data only as needed to run the platform, with providers bound by their own confidentiality
              and security obligations:
            </p>
            <ul className="list-disc space-y-2 pl-5">
              <li><strong className="text-foreground">Telephony:</strong> our SIP/calling infrastructure provider, to place and receive calls.</li>
              <li><strong className="text-foreground">Voice AI:</strong> speech-to-text, text-to-speech, and language-model providers, to power AI conversations in real time.</li>
              <li><strong className="text-foreground">Payments:</strong> Razorpay, to process subscription payments securely (they, not us, handle your card/UPI details).</li>
              <li><strong className="text-foreground">Cloud infrastructure:</strong> database and object-storage providers, to host your account data, recordings, transcripts, and generated invoices.</li>
              <li><strong className="text-foreground">Legal &amp; safety:</strong> where required to comply with a legal obligation, enforce our terms, or protect the rights, property, or safety of QuickHowl, our Customers, or others.</li>
            </ul>
            <p>We do not share Customer contact-list, call recording, or transcript data across organizations — each Customer's data is isolated to their own account.</p>
          </Section>

          <Section title="6. Data Retention">
            <ul className="list-disc space-y-2 pl-5">
              <li>Account data is retained while your account is active, and for a reasonable period afterward to comply with legal, tax, or dispute-resolution obligations.</li>
              <li>Call recordings and transcripts are retained for as long as your account is active, unless removed earlier from the dashboard by an org admin, or applicable law requires a longer retention period.</li>
              <li>GST tax invoices and billing records are retained for the period required under Indian tax law.</li>
              <li>Voice-cloning consent recordings are retained for as long as the corresponding cloned voice is in use. If a voice-cloning request is rejected, the submitted sample and consent video are deleted.</li>
              <li>System backups are retained on a rolling basis (currently 14 days) and then automatically overwritten.</li>
              <li>DNC (do-not-call) entries are retained indefinitely once added, so a number is never called again by mistake.</li>
            </ul>
          </Section>

          <Section title="7. Security">
            <p>
              We use encryption in transit, access controls limiting who can view recordings, transcripts, and
              account data, and hashed (never plain-text) password storage. No online service can guarantee
              absolute security, but we take reasonable, industry-standard measures to protect your data and
              respond promptly to any suspected incident.
            </p>
          </Section>

          <Section title="8. TRAI / Do-Not-Call Compliance">
            <p>
              QuickHowl provides Do-Not-Call list management and lets any called party ask to be marked
              do-not-call during a call, after which that number is automatically excluded from future campaigns
              on that Customer's account. Customer organizations remain responsible for ensuring their own
              contact lists and calling practices comply with TRAI regulations and other applicable telemarketing
              and consent laws in the jurisdictions they call into.
            </p>
          </Section>

          <Section title="9. Your Rights">
            <p>
              Subject to applicable law (including India's Digital Personal Data Protection Act, 2023), you may
              have the right to:
            </p>
            <ul className="list-disc space-y-2 pl-5">
              <li>Access the personal data we hold about you.</li>
              <li>Correct inaccurate or incomplete data.</li>
              <li>Request deletion of your data, subject to our legal retention obligations.</li>
              <li>Withdraw consent previously given (for example, for a cloned voice) — though this may limit or end related features.</li>
              <li>Lodge a complaint with us, or with the relevant data protection authority.</li>
            </ul>
            <p>To exercise any of these rights, contact us using the details in Section 13.</p>
          </Section>

          <Section title="10. Children's Privacy">
            <p>QuickHowl is not directed at, and we do not knowingly collect personal data from, individuals under 18 years of age.</p>
          </Section>

          <Section title="11. International Data Transfers">
            <p>
              Some of our infrastructure and service providers may process or store data on servers located
              outside India. Where this happens, we require those providers to maintain appropriate safeguards
              for your data.
            </p>
          </Section>

          <Section title="12. Changes to This Policy">
            <p>
              We may update this Privacy Policy from time to time. Material changes will be reflected by updating
              the "Last updated" date above; continued use of QuickHowl after a change means you accept the
              revised policy.
            </p>
          </Section>

          <Section title="13. Contact Us / Grievance Officer">
            <p>
              For any questions about this policy, to exercise your data rights, or to raise a grievance, contact
              us at:
            </p>
            <p className="text-foreground">
              QuickHowl<br />
              FIRST FLOOR, Reality Warehousing Pvt Ltd, GAT NO.-1337/1, Pune Nagar Road,
              Above Reliance Smart, Wagholi, Pune, Maharashtra, India<br />
              Email: <a href="mailto:support@quickhowl.com" className="text-primary hover:underline">support@quickhowl.com</a>
            </p>
          </Section>
        </div>
      </div>

      <Footer />
    </div>
  );
}
