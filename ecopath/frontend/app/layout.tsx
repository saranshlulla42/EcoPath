import type { Metadata } from "next";
import "./globals.css";
import { Navbar } from "@/components/navbar";
import { CommandBar } from "@/components/CommandBar";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "EcoPath — Bird Biodiversity Intelligence",
  description:
    "A diagnostic ecological intelligence platform for global bird biodiversity. Identify species, explore population trends, visualize migration corridors, and understand why populations change.",
  keywords: ["birds", "biodiversity", "ecology", "ornithology", "GBIF", "conservation"],
  authors: [{ name: "EcoPath Research" }],
  openGraph: {
    title: "EcoPath — Bird Biodiversity Intelligence",
    description: "AI-powered ecological intelligence for bird populations.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500;1,600&family=DM+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased">
        <Providers>
          <div className="flex flex-col min-h-screen">
            <Navbar />
            <main className="flex-1">{children}</main>
            {/* The bar is additive for now: the tabs above stay reachable
                until it is at parity with them. */}
            <CommandBar />
          </div>
        </Providers>
      </body>
    </html>
  );
}
