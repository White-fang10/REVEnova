"use client";

import "./globals.css";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800&family=Sora:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <title>REVEnova — Revenue Recovery Intelligence</title>
      </head>
      <body>{children}</body>
    </html>
  );
}
