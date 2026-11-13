// One steady colour per Nigerian party, so a party reads the same on every governorship page.
const PARTY: Record<string, string> = {
  APC: "#7fa8f5", PDP: "#f28b82", LP: "#9ad18b", NNPP: "#f5b955", ADC: "#c3a6ff", APGA: "#6ee7c8",
  SDP: "#f0a6ca", YPP: "#e0c37a", ADP: "#8fd3e8", PRP: "#d7a07a",
};
export const partyColour = (party: string | null | undefined) => (party && PARTY[party]) || "#a3a3a3";
