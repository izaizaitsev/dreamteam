import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Обращения · AI Legal Copilot",
  description: "Рабочее пространство для обработки обращений ЖКХ",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="ru"><body>{children}</body></html>;
}
