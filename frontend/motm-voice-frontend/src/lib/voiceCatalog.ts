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
