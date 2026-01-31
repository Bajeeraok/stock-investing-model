import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stock Investing Model | Dashboard",
  description: "Decision-support dashboard for retail investors",
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
