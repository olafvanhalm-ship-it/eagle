import "./globals.css";

export const metadata = {
  title: "Eagle — Report Viewer",
  description: "AIFMD Annex IV report viewer and validator",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
