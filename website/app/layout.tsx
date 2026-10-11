import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "NeAntik Win — локальные профили и собственное ядро",
    template: "%s · NeAntik Win",
  },
  description:
    "NeAntik Win, ранее NeVision: локальные браузерные профили для Windows. Собственное Chromium-ядро в разработке; доступный прежний выпуск не подменяет fingerprint.",
  robots: {
    index: true,
    follow: true,
  },
  openGraph: {
    title: "NeAntik Win — локальные браузерные профили",
    description:
      "Portable менеджер изолированных браузерных профилей для Windows — локально, быстро и без обязательного облака.",
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
