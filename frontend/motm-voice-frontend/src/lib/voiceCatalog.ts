// Sarvam's Bulbul v3 speaker catalog is a fixed, documented set (not a live
// per-account list the way ElevenLabs' is) — sourced directly from the
// installed livekit-plugins-sarvam SDK's MODEL_SPEAKER_COMPATIBILITY table
// for the "bulbul:v3" model (see agent/config.py's SARVAM_MODEL), not
// guessed. Kept here rather than round-tripping to the backend since it
// never changes without a plugin upgrade.
//
// `focus` mirrors that same SDK table's own grouping: everything under its
// "Customer Care" and "Content Creation" headings is a native Hindi/Hinglish
// voice (this platform's primary use case); only "International" (Amelia,
// Sophia) is an English-accented voice not tuned for Hindi.
export const SARVAM_VOICES: { id: string; name: string; gender: "male" | "female"; focus: "hindi" | "international" }[] = [
  { id: "shubh", name: "Shubh", gender: "male", focus: "hindi" },
  { id: "ritu", name: "Ritu", gender: "female", focus: "hindi" },
  { id: "rahul", name: "Rahul", gender: "male", focus: "hindi" },
  { id: "pooja", name: "Pooja", gender: "female", focus: "hindi" },
  { id: "simran", name: "Simran", gender: "female", focus: "hindi" },
  { id: "kavya", name: "Kavya", gender: "female", focus: "hindi" },
  { id: "amit", name: "Amit", gender: "male", focus: "hindi" },
  { id: "ratan", name: "Ratan", gender: "male", focus: "hindi" },
  { id: "rohan", name: "Rohan", gender: "male", focus: "hindi" },
  { id: "dev", name: "Dev", gender: "male", focus: "hindi" },
  { id: "ishita", name: "Ishita", gender: "female", focus: "hindi" },
  { id: "shreya", name: "Shreya", gender: "female", focus: "hindi" },
  { id: "manan", name: "Manan", gender: "male", focus: "hindi" },
  { id: "sumit", name: "Sumit", gender: "male", focus: "hindi" },
  { id: "priya", name: "Priya", gender: "female", focus: "hindi" },
  { id: "aditya", name: "Aditya", gender: "male", focus: "hindi" },
  { id: "kabir", name: "Kabir", gender: "male", focus: "hindi" },
  { id: "neha", name: "Neha", gender: "female", focus: "hindi" },
  { id: "varun", name: "Varun", gender: "male", focus: "hindi" },
  { id: "roopa", name: "Roopa", gender: "female", focus: "hindi" },
  { id: "aayan", name: "Aayan", gender: "male", focus: "hindi" },
  { id: "ashutosh", name: "Ashutosh", gender: "male", focus: "hindi" },
  { id: "advait", name: "Advait", gender: "male", focus: "hindi" },
  { id: "amelia", name: "Amelia", gender: "female", focus: "international" },
  { id: "sophia", name: "Sophia", gender: "female", focus: "international" },
];

// Curated ElevenLabs voices picked specifically for this platform's Indian
// sales/support calls (not the full account-wide catalog) — names, voice_ids,
// and language/accent came directly from the ElevenLabs voice library.
// bulbul:v4-flash speakers -- a completely different, much larger namespace
// than bulbul:v3's (hundreds of entries, encoding both the target language and
// a speaking style in the name itself, e.g. "rahul_hi_conversational"). Curated
// to one or two per platform language rather than the full catalog, and
// verified live against Sarvam's API (2026-10-21) -- its SDK's bundled list
// was already stale for Bengali (listed "bappa_bn_conversation", which the
// server rejects; "arnab_bn_conversation" is the current one).
// `language` matches languages.ts's LANGUAGES[].value ("hindi" also covers
// "hinglish", which speaks through the same hi-IN voices).
export const BULBUL_V4_FLASH_VOICES: { id: string; name: string; gender: "male" | "female"; language: string }[] = [
  { id: "rahul_hi_conversational", name: "Rahul", gender: "male", language: "hindi" },
  { id: "ritu_hi_conversation", name: "Ritu", gender: "female", language: "hindi" },
  { id: "dev_en_conversational", name: "Dev", gender: "male", language: "english" },
  { id: "simran_en_conversation", name: "Simran", gender: "female", language: "english" },
  { id: "nilesh_mr_conversation", name: "Nilesh", gender: "male", language: "marathi" },
  { id: "ishita_mr_conversational", name: "Ishita", gender: "female", language: "marathi" },
  { id: "vijay_ta_narration", name: "Vijay", gender: "male", language: "tamil" },
  { id: "kavitha_te_conversation", name: "Kavitha", gender: "female", language: "telugu" },
  { id: "tarun_te_narration", name: "Tarun", gender: "male", language: "telugu" },
  { id: "arnab_bn_conversation", name: "Arnab", gender: "male", language: "bengali" },
  { id: "roopa_bn_conversational", name: "Roopa", gender: "female", language: "bengali" },
  { id: "bhavik_gu_conversation", name: "Bhavik", gender: "male", language: "gujarati" },
  { id: "pooja_gu_conversational", name: "Pooja", gender: "female", language: "gujarati" },
  { id: "chaitra_kn_conversation", name: "Chaitra", gender: "female", language: "kannada" },
  { id: "chetan_kn_conversation", name: "Chetan", gender: "male", language: "kannada" },
  { id: "anand_pa_conversation", name: "Anand", gender: "male", language: "punjabi" },
];

export const ELEVENLABS_VOICES: {
  id: string;
  name: string;
  gender: "male" | "female";
  focus: "hindi" | "indian-english";
}[] = [
  { id: "P3JECz9WQeXyyodBL3ZD", name: "Gargi — Regional E-com Customer…", gender: "female", focus: "hindi" },
  { id: "U6U9JrUgcMgeM9W1PYFd", name: "Sujit — Regional Outbound Sales Agent", gender: "male", focus: "hindi" },
  { id: "UbB19hYD8fvYxwJAVTY5", name: "Anika — Expressive & High Energy", gender: "female", focus: "hindi" },
  { id: "7LIHJn2g4SPvZIQniujs", name: "Ramesh P — Top Indian Sales Outbound", gender: "male", focus: "indian-english" },
  { id: "Ms9OTvWb99V6DwRHZn6q", name: "Monika Sogam — Deep and Clear", gender: "female", focus: "hindi" },
  { id: "hRclHnAGI1PGQgXUYKsd", name: "Samisha — Sweet & Warm SDR Voice", gender: "female", focus: "hindi" },
  { id: "zmh5xhBvMzqR4ZlXgcgL", name: "Monika Sogam — Lead Qualification", gender: "female", focus: "hindi" },
];
