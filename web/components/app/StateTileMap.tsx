/* Nigeria's 36 states and the FCT as a tile grid: each state one square, placed by rough geography, so small states
 * (the FCT, Anambra, Ebonyi) read as clearly as large ones. No boundary data is needed. */

// [state, column, row] on a 7 x 7 grid, north at the top.
const TILES: [string, number, number][] = [
  ["Sokoto", 1, 0], ["Katsina", 2, 0], ["Kano", 3, 0], ["Jigawa", 4, 0], ["Yobe", 5, 0], ["Borno", 6, 0],
  ["Kebbi", 0, 1], ["Zamfara", 1, 1], ["Kaduna", 2, 1], ["Bauchi", 3, 1], ["Gombe", 4, 1], ["Adamawa", 5, 1],
  ["Kwara", 0, 2], ["Niger", 1, 2], ["FCT", 2, 2], ["Plateau", 3, 2], ["Taraba", 5, 2],
  ["Oyo", 0, 3], ["Osun", 1, 3], ["Ekiti", 2, 3], ["Kogi", 3, 3], ["Nasarawa", 4, 3], ["Benue", 5, 3],
  ["Ogun", 0, 4], ["Ondo", 1, 4], ["Edo", 2, 4], ["Anambra", 3, 4], ["Enugu", 4, 4], ["Ebonyi", 5, 4], ["Cross River", 6, 4],
  ["Lagos", 0, 5], ["Delta", 2, 5], ["Imo", 3, 5], ["Abia", 4, 5], ["Akwa Ibom", 5, 5],
  ["Bayelsa", 2, 6], ["Rivers", 3, 6],
];

const SHORT: Record<string, string> = { "Cross River": "C. River", "Akwa Ibom": "Akwa I.", Nasarawa: "Nasar.", Adamawa: "Adam." };

/** Each state coloured by its winner: declared results solid, the baseline year (e.g. 2023) faint where not yet in. */
export function StateTileMap({ winners, baseline, baselineYear, colour, onPick }: {
  winners: Record<string, string | null>; baseline: Record<string, string>; baselineYear: number | null;
  colour: (candidate: string) => string; onPick?: (state: string) => void;
}) {
  const size = 46, gap = 4;
  const legend = Array.from(new Set([...Object.values(winners).filter(Boolean), ...Object.values(baseline)])) as string[];
  return (
    <figure className="mt-3">
      <svg viewBox={`0 0 ${7 * (size + gap)} ${7 * (size + gap)}`} className="w-full max-w-md" role="img"
           aria-label="Map of Nigeria's states coloured by winner">
        {TILES.map(([st, c, r]) => {
          const won = winners[st];
          const prior = baseline[st];
          const fill = won ? colour(won) : prior ? colour(prior) : "transparent";
          return (
            <g key={st} transform={`translate(${c * (size + gap)} ${r * (size + gap)})`} onClick={() => onPick?.(st)}
               className={onPick ? "cursor-pointer" : undefined}>
              <title>{`${st}: ${won ? `${won} (declared)` : prior ? `${prior} won in ${baselineYear}` : "no result"}`}</title>
              <rect width={size} height={size} rx={6} fill={fill} fillOpacity={won ? 0.9 : 0.25}
                    stroke="currentColor" strokeOpacity={won ? 0 : 0.25} />
              <text x={size / 2} y={size / 2 + 4} textAnchor="middle" fontSize={9}
                    fill={won ? "#0b0f14" : "currentColor"}>{SHORT[st] ?? st}</text>
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.75rem] text-[color:var(--muted)]">
        {legend.map((n) => (
          <span key={n} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: colour(n) }} />{n}</span>
        ))}
        {baselineYear && <span className="text-[color:var(--dim)]">Faint: {baselineYear} winner, state not yet declared</span>}
      </figcaption>
    </figure>
  );
}
