import Link from "next/link";

export function AppNav() {
  return <nav className="flex flex-wrap gap-2" aria-label="Primary navigation">
    <Link href="/" className="rounded border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">System state</Link>
    <Link href="/strategies" className="rounded border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">Strategies</Link>
    <Link href="/trades" className="rounded border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">P&amp;L</Link>
    <Link href="/ideas" className="rounded border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800">Trade ideas</Link>
  </nav>;
}
