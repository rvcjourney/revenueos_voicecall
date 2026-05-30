export type CampaignStatus = "active" | "paused" | "completed" | "draft";
export type CallOutcome = "interested" | "completed" | "not_interested" | "no_answer" | "failed" | "in_progress";

export interface Campaign {
  id: string;
  name: string;
  description: string;
  status: CampaignStatus;
  industry: string;
  goal: string;
  total: number;
  completed: number;
  interested: number;
  notInterested: number;
  inProgress: number;
  noAnswer: number;
  failed: number;
  createdAt: string;
  startedAt?: string;
  agent: string;
  voice: string;
  language: string;
  systemPrompt: string;
  welcomeMessage: string;
}

export interface Contact {
  id: string;
  name: string;
  phone: string;
  company: string;
  email?: string;
}

export interface Call {
  id: string;
  campaignId: string;
  campaignName: string;
  contactName: string;
  phone: string;
  company: string;
  startedAt: string;
  duration: number; // seconds
  outcome: CallOutcome;
  cost: number;
  summary: string;
  sentiment: "positive" | "neutral" | "negative";
  tags: string[];
  transcript: { speaker: "agent" | "customer"; text: string; t: string }[];
}

const indianFirst = ["Rajesh","Priya","Amit","Sneha","Vikram","Ananya","Karan","Pooja","Arjun","Neha","Suresh","Divya","Manish","Kavita","Rohit","Meera","Aniket","Riya","Sandeep","Isha"];
const indianLast = ["Sharma","Verma","Patel","Iyer","Nair","Singh","Reddy","Mehta","Kapoor","Joshi","Desai","Pillai","Agarwal","Rao","Bhatt"];
const companies = ["Baba Valves","Aqua Flow Systems","Petro Industries","ChemTech Solutions","Hindustan Pumps","Reliance Polymers","Bharat Refineries","Krishna Chemicals","Indo Gulf Petro","Sai Water Treatment","Mahindra Industrial","Tata Petro Products","Adani Chemicals","Goa Petrochem","Jindal Pipes"];
const industries = ["Oil & Gas","Chemical","Petrochemical","Water Treatment","Manufacturing"];
const goals = ["Lead Generation","Product Demo","Follow-up","Cold Outreach"];

const rand = <T,>(arr: T[]) => arr[Math.floor(Math.random() * arr.length)];
const randInt = (a: number, b: number) => Math.floor(Math.random() * (b - a + 1)) + a;
const phone = () => `+91 ${randInt(70000, 99999)} ${String(randInt(10000, 99999)).padStart(5, "0")}`;
const personName = () => `${rand(indianFirst)} ${rand(indianLast)}`;

let seed = 42;
const seedRand = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };

const campaignNames = [
  "Butterfly Valve Q4 Outreach",
  "Industrial Pump Demo Drive",
  "Petrochemical Cold Outreach",
  "Water Treatment Lead Gen",
  "Chemical Plant Follow-up",
  "Oil & Gas Decision Makers",
  "Refinery Solutions Push",
  "MSME Manufacturing Survey",
  "Hindustan Pumps Reactivation",
  "ChemTech Demo Booking",
  "Q1 New Year Pitch",
  "Polymer Industries Outreach",
];

export const mockCampaigns: Campaign[] = campaignNames.map((name, i) => {
  const total = randInt(80, 1500);
  const completed = i < 8 ? randInt(Math.floor(total * 0.3), total) : (i === 11 ? 0 : Math.floor(total * 0.05));
  const interested = Math.floor(completed * (0.1 + Math.random() * 0.2));
  const notInterested = Math.floor(completed * 0.4);
  const noAnswer = Math.floor(completed * 0.15);
  const failed = Math.floor(completed * 0.05);
  const inProgress = Math.min(8, total - completed);
  const statuses: CampaignStatus[] = ["active","active","active","active","paused","completed","completed","active","paused","draft","active","draft"];
  return {
    id: `camp_${1000 + i}`,
    name,
    description: `Targeted outbound calling campaign for ${rand(industries).toLowerCase()} sector decision makers.`,
    status: statuses[i],
    industry: rand(industries),
    goal: rand(goals),
    total, completed, interested, notInterested, inProgress, noAnswer, failed,
    createdAt: new Date(Date.now() - randInt(1, 30) * 86400000).toISOString(),
    startedAt: statuses[i] !== "draft" ? new Date(Date.now() - randInt(1, 20) * 86400000).toISOString() : undefined,
    agent: i % 2 === 0 ? "Aniket — Sales Agent" : "Priya — Lead Qualifier",
    voice: i % 2 === 0 ? "Arjun (Hinglish M)" : "Priya (Hinglish F)",
    language: "Hinglish",
    welcomeMessage: "Namaste! Main Aniket bol raha hu Baba Valves se. Kya aap 2 minute baat kar sakte hain?",
    systemPrompt: `You are Aniket, a friendly and professional sales agent from Baba Valves, a leading manufacturer of industrial butterfly valves in India.\n\nYour goal is to:\n1. Greet the customer in Hinglish (mix of Hindi and English)\n2. Briefly introduce Baba Valves and our product range\n3. Qualify the lead by asking about their current valve usage\n4. Identify pain points and budget\n5. Schedule a follow-up demo if interested\n\nKeep responses short (1-2 sentences). Be polite and never pushy.\nIf the customer is not interested, thank them politely and end the call.`,
  };
});

const sampleTranscripts = [
  [
    { speaker: "agent" as const, text: "Namaste sir, main Aniket bol raha hu Baba Valves se. Kya aap 2 minute baat kar sakte hain?", t: "00:02" },
    { speaker: "customer" as const, text: "Haan boliye, kya baat hai?", t: "00:08" },
    { speaker: "agent" as const, text: "Sir, hum industrial butterfly valves manufacture karte hain. Aapki company mein currently kaunse valves use ho rahe hain?", t: "00:12" },
    { speaker: "customer" as const, text: "Hum abhi Crane company ke valves use kar rahe hain, but pricing kaafi high hai.", t: "00:22" },
    { speaker: "agent" as const, text: "Bilkul samajh gaya sir. Hum same quality 30% kam price mein de sakte hain. Kya main aapko ek demo schedule kar du?", t: "00:30" },
    { speaker: "customer" as const, text: "Theek hai, agle hafte try karte hain. Mujhe details email kar dijiye.", t: "00:42" },
  ],
  [
    { speaker: "agent" as const, text: "Hello, Priya here from Aqua Flow Systems. Am I speaking with the procurement head?", t: "00:01" },
    { speaker: "customer" as const, text: "Yes, but I'm in a meeting. Call me later.", t: "00:06" },
    { speaker: "agent" as const, text: "Of course sir, when would be a good time tomorrow?", t: "00:10" },
    { speaker: "customer" as const, text: "After 4 PM works.", t: "00:14" },
  ],
];

export const mockCalls: Call[] = Array.from({ length: 180 }).map((_, i) => {
  const camp = mockCampaigns[Math.floor(seedRand() * mockCampaigns.length)];
  const outcomes: CallOutcome[] = ["interested","completed","not_interested","no_answer","failed","in_progress"];
  const weights = [0.18, 0.3, 0.25, 0.15, 0.05, 0.07];
  let r = seedRand(); let outcome: CallOutcome = "completed";
  for (let j = 0; j < weights.length; j++) { if (r < weights[j]) { outcome = outcomes[j]; break; } r -= weights[j]; }
  const duration = outcome === "no_answer" ? randInt(5, 25) : outcome === "failed" ? 0 : randInt(45, 480);
  const summaryByOutcome: Record<CallOutcome, string> = {
    interested: "Customer showed strong interest in our butterfly valves. Mentioned current pricing concerns with existing supplier. Demo scheduled for next week.",
    completed: "Brief conversation completed. Customer requested more information via email and asked to be contacted next quarter.",
    not_interested: "Customer politely declined. Already locked in long-term contract with another supplier.",
    no_answer: "Phone rang out. No voicemail option available. Will retry tomorrow.",
    failed: "Call could not be connected. Number may be invalid or out of service.",
    in_progress: "Call currently active.",
  };
  return {
    id: `call_${20000 + i}`,
    campaignId: camp.id,
    campaignName: camp.name,
    contactName: personName(),
    phone: phone(),
    company: rand(companies),
    startedAt: new Date(Date.now() - randInt(0, 7 * 24 * 60) * 60000).toISOString(),
    duration,
    outcome,
    cost: +(duration * 0.0015).toFixed(2),
    summary: summaryByOutcome[outcome],
    sentiment: outcome === "interested" ? "positive" : outcome === "not_interested" ? "negative" : "neutral",
    tags: outcome === "interested" ? ["Butterfly Valves", `Budget: ${randInt(2,10)}L`, "Decision Maker"] : [],
    transcript: sampleTranscripts[i % 2],
  };
});

export const callsLast7Days = Array.from({ length: 7 }).map((_, i) => {
  const d = new Date(); d.setDate(d.getDate() - (6 - i));
  return {
    day: d.toLocaleDateString("en-US", { weekday: "short" }),
    calls: 800 + randInt(200, 600),
    interested: 100 + randInt(40, 180),
  };
});

export const outcomeBreakdown = [
  { name: "Completed", value: 540, color: "oklch(0.62 0.21 280)" },
  { name: "Interested", value: 184, color: "oklch(0.7 0.16 160)" },
  { name: "Not Interested", value: 320, color: "oklch(0.5 0.03 265)" },
  { name: "No Answer", value: 145, color: "oklch(0.4 0.03 265)" },
  { name: "Failed", value: 58, color: "oklch(0.62 0.23 25)" },
];

export const voices = [
  { id: "C8R8ahkE5XosZ8qPpSPy",                   provider: "elevenlabs", name: "Suyash",  lang: "Hinglish", gender: "M", desc: "Warm & professional"   },
  { id: "codoBx1vrQVwrVQylqGj",                   provider: "elevenlabs", name: "Nitesh",  lang: "Hinglish", gender: "M", desc: "Energetic & persuasive" },
  { id: "6h2Hja4LgQR8wIIv3XXW",                   provider: "elevenlabs", name: "Anandu",  lang: "Hinglish", gender: "M", desc: "Friendly & natural"     },
  { id: "910fb75e-1d20-4840-ac63-ac6b26a71bdc",   provider: "cartesia",   name: "Cartesia Sonic 3.5", lang: "English/Hindi", gender: "N", desc: "Ultra-low latency"    },
];

export const promptTemplates = [
  { id: "sales", name: "Sales Pitch", lang: "Hinglish", desc: "Cold outreach for B2B sales" },
  { id: "qual", name: "Lead Qualification", lang: "English", desc: "Qualify inbound leads" },
  { id: "appt", name: "Appointment Booking", lang: "Hinglish", desc: "Book demos & meetings" },
  { id: "survey", name: "Customer Survey", lang: "Hindi", desc: "Post-purchase feedback" },
  { id: "followup", name: "Follow-up Call", lang: "English", desc: "Re-engage warm leads" },
];

export function formatDuration(s: number) {
  if (!s) return "—";
  const m = Math.floor(s / 60); const r = s % 60;
  return `${m}m ${String(r).padStart(2, "0")}s`;
}
