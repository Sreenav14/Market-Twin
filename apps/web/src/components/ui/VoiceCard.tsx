import type { ReactNode } from "react";
import { Avatar } from "./Avatar";

/* Tester quote / voice card — Phase 2e, ONE recipe.
   A verbatim quote renders ONE way everywhere: square persona
   avatar (2b shape rule — personas are squares), name + role,
   and the quote itself in Newsreader italic (2a type rule:
   serif = a human said this; these are simulated testers and
   the attribution always says so).
   Two lawful surfaces, never crossed (two-track separation):
   - band (default): an IMPRESSION — renders on the sunken
     impressions band surface (.voice-card-band).
   - plain: a quote attached to a CHECK — plain card surface,
     never the band treatment. */
export function VoiceCard({
  name,
  role = "Simulated tester",
  quote,
  band = true,
  tint,
  children,
}: {
  name: string;
  role?: string;
  quote: string;
  band?: boolean;
  tint?: string;
  children?: ReactNode;
}) {
  return (
    <article className={band ? "voice-card voice-card-band" : "voice-card"}>
      <div className="voice-card-head">
        <Avatar kind="persona" name={name} size="md" tint={tint} />
        <div>
          <div className="voice-card-name">{name}</div>
          <div className="voice-card-role">{role}</div>
        </div>
      </div>
      <blockquote className="voice-quote">
        <p>“{quote}”</p>
        <cite>— {name}, simulated tester</cite>
      </blockquote>
      {children}
    </article>
  );
}
