// Phase 0 placeholder. The real dashboard is built in a later phase.
// This page only confirms that the web app can reach the API.
export const dynamic = "force-dynamic";

async function apiIsReachable(): Promise<boolean> {
  const base = process.env.API_INTERNAL_URL;
  if (!base) return false;
  try {
    const res = await fetch(`${base}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export default async function Home() {
  const reachable = await apiIsReachable();

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-6">
      <div>
        <p className="font-mono text-xs uppercase tracking-widest text-muted">Phase 0</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">ModelRadar</h1>
        <p className="mt-3 text-muted">
          Official AI model announcements, collected only from official company sources. No
          announcements have been collected yet.
        </p>
      </div>
      <div className="rounded-lg border border-border bg-surface px-4 py-3 text-sm">
        <span className="text-muted">API status: </span>
        <span className={reachable ? "text-foreground" : "text-muted"}>
          {reachable ? "reachable" : "unreachable"}
        </span>
      </div>
    </main>
  );
}
