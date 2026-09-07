"use client";

import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

export default function AppShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-ink">
      <Sidebar />
      <div className="md:pl-64">
        <TopBar />
        <main className="relative min-h-screen px-4 py-8 md:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
