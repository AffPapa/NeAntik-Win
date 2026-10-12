import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "NeAntik Win — portable Chromium и локальные профили",
    template: "%s · NeAntik Win",
  },
  description:
    "Portable-браузер Chromium для Windows с отдельными локальными профилями, proxy vault и backup. Chromium входит в ZIP; подмены fingerprint и гарантии анонимности нет.",
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: "NeAntik Win — portable Chromium и локальные профили",
    description:
      "Chromium уже в portable ZIP для Windows: локальные профили, proxy vault и backup без обязательного облака.",
    type: "website",
  },
  icons: {
    icon: [{ url: "/assets/favicon.svg", type: "image/svg+xml" }],
  },
  manifest: "/site.webmanifest",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <head>
        <meta name="theme-color" content="#f5f5f1" media="(prefers-color-scheme: light)" />
        <meta name="theme-color" content="#0b0e15" media="(prefers-color-scheme: dark)" />
        <link rel="stylesheet" href="/assets/styles.css" />
      </head>
      <body>{children}</body>
    </html>
  );
}
