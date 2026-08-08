import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GoldFlow Plan View",
  description: "Session-hierarchy day plan with hourly validation chart",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
