import type { Metadata } from "next";
import "./globals.css";
import "./missing-details.css";

export const metadata: Metadata = {
  title: "DreamTeam",
  description: "Обработка обращений",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body>{children}</body></html>;
}
