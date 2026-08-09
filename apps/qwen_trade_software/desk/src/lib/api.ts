import type { Snapshot } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function fetchSnapshot(): Promise<Snapshot> {
  const response = await fetch(`${API_BASE}/snapshot`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`snapshot failed: ${response.status}`);
  }
  return response.json() as Promise<Snapshot>;
}

export async function requestDealSheet(): Promise<Snapshot> {
  const response = await fetch(`${API_BASE}/deal-sheet`, {
    method: "POST",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`deal-sheet failed: ${response.status}`);
  }
  return response.json() as Promise<Snapshot>;
}
