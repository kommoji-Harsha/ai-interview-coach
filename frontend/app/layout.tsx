import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { Navbar } from "@/components/Navbar";

export const metadata: Metadata = {
  title: "AI Interview Coach",
  description:
    "Adaptive mock interviews tailored to your resume and job description with rubric scoring and progress analytics.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
        <AuthProvider>
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-indigo-600 focus:px-4 focus:py-2 focus:text-white"
          >
            Skip to main content
          </a>
          <Navbar />
          <main
            id="main-content"
            className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6"
          >
            {children}
          </main>
        </AuthProvider>
      </body>
    </html>
  );
}
