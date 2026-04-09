import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "AuraCore | Segundo Cerebro Pessoal",
  description:
    "Interface em abas para conectar o WhatsApp observador, consolidar memoria, acompanhar projetos e conversar com contexto persistido.",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
