/** "23" plus a "+2" badge when some items have no estimate yet. */
export function Points({ points, unestimated }: { points: number; unestimated: number }) {
  return (
    <span className="ml-auto shrink-0 tabular-nums text-neutral-500">
      {points}
      {unestimated > 0 && (
        <span
          className="ml-1 text-xs text-amber-600 dark:text-amber-400"
          title={`${unestimated} unestimated`}
        >
          +{unestimated}
        </span>
      )}
    </span>
  );
}
