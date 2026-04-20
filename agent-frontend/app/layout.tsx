import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "AuraCore Agent Hub",
  description:
    "Painel separado para operar o numero global do agente do AuraCore e rotear respostas pelo numero do observador de cada conta.",
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
