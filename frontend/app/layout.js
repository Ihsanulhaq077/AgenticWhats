import "./globals.css";

export const metadata = {
  title: "AgenticWhats — WhatsApp AI Automation",
  description: "Multi-tenant agentic AI WhatsApp business automation platform",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
