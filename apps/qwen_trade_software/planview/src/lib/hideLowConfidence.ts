"use client";

import { useCallback, useEffect, useState } from "react";

export const HIDE_LOW_CONFIDENCE_KEY = "goldflow.hideLowConfidence";
export const LOW_CONFIDENCE_FLOOR = 50;

export function useHideLowConfidence() {
  const [hideLowConfidence, setHideLowConfidence] = useState(true);

  useEffect(() => {
    try {
      if (window.localStorage.getItem(HIDE_LOW_CONFIDENCE_KEY) === "0") {
        setHideLowConfidence(false);
      }
    } catch {
      // private mode / blocked storage — keep the default hide
    }
  }, []);

  const setHide = useCallback((next: boolean) => {
    setHideLowConfidence(next);
    try {
      window.localStorage.setItem(HIDE_LOW_CONFIDENCE_KEY, next ? "1" : "0");
    } catch {
      // ignore
    }
  }, []);

  return { hideLowConfidence, setHideLowConfidence: setHide };
}
