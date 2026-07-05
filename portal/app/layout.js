import "./globals.css";

export const metadata = {
  title: "Skill Implementation — JP Equity Partners",
  description: "Transcend AI Partners — skill implementation orchestrator",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
