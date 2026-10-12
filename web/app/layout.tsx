import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

/** Ticker-detail skin's UI typeface — additive only, does NOT change the app-wide
 * `font-sans` Tailwind key above. Consumed via the separate `font-td-sans` utility,
 * applied only inside the ticker-detail modal. Numeric text there keeps using the
 * existing `font-mono` (JetBrains Mono, above) — no second mono face is introduced. */
const ibmPlexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-td-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Thrive Alpha | Dashboard",
  description: "Stock signals and portfolio model from Thrive City. Decision-support for retail investors.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  userScalable: true,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`min-h-screen bg-slate-950 text-slate-100 font-sans antialiased ${jetbrainsMono.variable} ${ibmPlexSans.variable}`}>
        {children}
      </body>
    </html>
  );
}
