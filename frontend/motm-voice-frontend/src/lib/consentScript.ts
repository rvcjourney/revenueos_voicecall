// Fixed script the org admin must read on camera when submitting a voice
// cloning request — shown identically on the submission side (VoiceCloning.tsx)
// and the superadmin review side (PlatformVoiceCloneRequests.tsx) so both
// always match exactly.
export const VOICE_CLONING_CONSENT_SCRIPT =
  "My name is [your name]. I am recording this video to confirm that this is my own voice, " +
  "and I am giving my full consent for it to be cloned and used as an AI voice agent on the " +
  "Talkryn platform. I understand how this cloned voice will be used, and I am authorized to " +
  "give this consent.";
