import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Thrive Alpha | Dashboard",
  description: "Stock signals and portfolio model from Thrive City. Decision-support for retail investors.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-slate-950 text-slate-100 font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
