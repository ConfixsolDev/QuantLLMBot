import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuantLLM Structure",
  description: "Live XAUUSD market structure from the deterministic structure engine",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
