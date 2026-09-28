import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { AskDejaVu } from "@/components/ask";
import { TopBar } from "@/components/top-bar";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const jetbrainsMono = JetBrains_Mono({ variable: "--font-jetbrains-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "DejaVu · Kestrel Pay",
  description: "The on-call agent that has seen this before.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}>
      <body className="flex h-full flex-col">
        <TopBar />
        <main className="flex min-h-0 flex-1 flex-col">{children}</main>
        <AskDejaVu />
      </body>
    </html>
  );
}
