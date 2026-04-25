"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/",          label: "Home" },
  { href: "/maps",      label: "Heat Map" },
  { href: "/migration", label: "Migration Corridors" },
  { href: "/chat",      label: "Chat" },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50"
      style={{
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div className="max-w-7xl mx-auto px-6 flex items-center justify-between" style={{ height: 52 }}>

        {/* Logo */}
        <Link href="/" className="flex items-center gap-3">
          <span style={{
            fontFamily: "var(--font-display)",
            fontSize: "1.05rem",
            fontWeight: 600,
            letterSpacing: "0.005em",
            color: "var(--text-primary)",
          }}>
            EcoPath
          </span>
          <span style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.6rem",
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: "var(--text-tertiary)",
            paddingTop: 1,
          }}>
            Field Intelligence
          </span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-7">
          {links.map(({ href, label }) => {
            const active = pathname === href || (href !== "/" && pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.65rem",
                  letterSpacing: "0.15em",
                  textTransform: "uppercase",
                  color: active ? "var(--accent-primary)" : "var(--text-secondary)",
                  borderBottom: active ? "2px solid var(--accent-primary)" : "2px solid transparent",
                  paddingBottom: 4,
                  transition: "color 140ms ease, border-color 140ms ease",
                  fontWeight: active ? 500 : 400,
                }}
              >
                {label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
