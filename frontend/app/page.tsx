"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/overview");
  }, [router]);
  return (
    <div className="flex h-screen items-center justify-center">
      <div className="flex items-center gap-3">
        <span className="live-dot" />
        <span className="text-muted">Loading REVEnova…</span>
      </div>
    </div>
  );
}
