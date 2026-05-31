/** Phase B3: built-in + user-saved hunter panel filters (localStorage). */

export type HunterReason = "velocity" | "go_ready" | "almost_ready" | "warming";

export type HunterCandidate = {
  ticker: string;
  position_status: "owned" | "watching" | "universe";
  hunter_reason: HunterReason;
  readiness_tier?: string | null;
  readiness_score?: number | null;
  track?: string | null;
  velocity_triggered?: boolean;
  velocity_score?: number | null;
  gates_passed?: number | null;
  gates_total?: number | null;
  gate_cleared?: boolean | null;
  go_no_go?: string | null;
  composite_buy?: number | null;
  close?: number | null;
  signal?: string | null;
  plan_action?: string | null;
  regime?: string | null;
};

export type HunterScreenId =
  | "all_hunt"
  | "go_ready"
  | "almost_ready"
  | "tactical"
  | "not_owned"
  | `custom:${string}`;

export const HUNTER_SCREEN_STORAGE_KEY = "thrive-hunter-screen";
export const HUNTER_CUSTOM_SCREENS_KEY = "thrive-hunter-custom-screens";
export const MAX_CUSTOM_HUNTER_SCREENS = 2;

export type HunterScreenDef = {
  id: HunterScreenId;
  label: string;
  hint: string;
  builtIn?: boolean;
};

export const BUILTIN_HUNTER_SCREENS: HunterScreenDef[] = [
  { id: "all_hunt", label: "All hunt", hint: "Readiness + tactical velocity", builtIn: true },
  { id: "go_ready", label: "4/4 GO", hint: "gate_cleared / go_ready only", builtIn: true },
  { id: "almost_ready", label: "Almost ready", hint: "3/4 gates + ST supports add", builtIn: true },
  { id: "tactical", label: "Tactical", hint: "Velocity track only", builtIn: true },
  { id: "not_owned", label: "Not in book", hint: "Watching or universe — not portfolio", builtIn: true },
];

export function loadHunterScreen(): HunterScreenId {
  try {
    const raw = localStorage.getItem(HUNTER_SCREEN_STORAGE_KEY);
    if (raw) return raw as HunterScreenId;
  } catch {
    /* ignore */
  }
  return "all_hunt";
}

export function saveHunterScreen(id: HunterScreenId): void {
  try {
    localStorage.setItem(HUNTER_SCREEN_STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}

export type CustomHunterScreen = {
  id: string;
  label: string;
  reasons: HunterReason[];
};

export function loadCustomHunterScreens(): CustomHunterScreen[] {
  try {
    const raw = localStorage.getItem(HUNTER_CUSTOM_SCREENS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as CustomHunterScreen[];
    return Array.isArray(parsed) ? parsed.slice(0, MAX_CUSTOM_HUNTER_SCREENS) : [];
  } catch {
    return [];
  }
}

export function saveCustomHunterScreens(screens: CustomHunterScreen[]): void {
  try {
    localStorage.setItem(
      HUNTER_CUSTOM_SCREENS_KEY,
      JSON.stringify(screens.slice(0, MAX_CUSTOM_HUNTER_SCREENS)),
    );
  } catch {
    /* ignore */
  }
}

export function matchesHunterScreen(row: HunterCandidate, screenId: HunterScreenId): boolean {
  if (screenId === "all_hunt") return true;
  if (screenId === "go_ready") return row.hunter_reason === "go_ready";
  if (screenId === "almost_ready") return row.hunter_reason === "almost_ready";
  if (screenId === "tactical") return row.hunter_reason === "velocity";
  if (screenId === "not_owned") return row.position_status !== "owned";
  if (screenId.startsWith("custom:")) {
    const customId = screenId.slice(7);
    const custom = loadCustomHunterScreens().find((c) => c.id === customId);
    if (!custom?.reasons?.length) return true;
    return custom.reasons.includes(row.hunter_reason);
  }
  return true;
}

export function filterHunterCandidates(
  rows: HunterCandidate[],
  screenId: HunterScreenId,
): HunterCandidate[] {
  return rows.filter((r) => matchesHunterScreen(r, screenId));
}
