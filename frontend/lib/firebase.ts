"use client";

import { getApp, getApps, initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "",
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "",
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "",
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET ?? "",
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID ?? "",
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ?? "",
  measurementId: process.env.NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID ?? "",
};

function assertFirebaseConfig(): void {
  const missing = Object.entries(firebaseConfig)
    .filter(([key, value]) => key !== "measurementId" && !value)
    .map(([key]) => key);
  if (missing.length > 0) {
    throw new Error(`Configuracao do Firebase incompleta no frontend: ${missing.join(", ")}`);
  }
}

assertFirebaseConfig();

export const firebaseApp = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
export const firebaseAuth = getAuth(firebaseApp);

let analyticsBootPromise: Promise<void> | null = null;

export function ensureFirebaseAnalytics(): Promise<void> {
  if (typeof window === "undefined" || !firebaseConfig.measurementId) {
    return Promise.resolve();
  }
  if (analyticsBootPromise) {
    return analyticsBootPromise;
  }
  analyticsBootPromise = import("firebase/analytics")
    .then(async ({ getAnalytics, isSupported }) => {
      if (await isSupported()) {
        getAnalytics(firebaseApp);
      }
    })
    .catch(() => undefined);
  return analyticsBootPromise;
}
