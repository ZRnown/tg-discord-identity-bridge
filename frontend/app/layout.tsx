import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "TG→Discord Identity Bridge",
  description: "Telegram-to-Discord message forwarding + identity mirroring via selfbots",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#0e0e0e", color: "#eee" }}>
        {children}
      </body>
    </html>
  );
}
