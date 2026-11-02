import { useEffect, useState } from "react";

// Pages a list already in memory for the shared <Pagination> control. `resetKey` is anything that changes the list
// (a filter); when it changes the view returns to the first page.
export function usePaged<T>(rows: T[], resetKey: unknown = null, initialLimit = 25) {
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(initialLimit);
  useEffect(() => setOffset(0), [resetKey]);
  const safeOffset = offset < rows.length ? offset : 0;
  return {
    page: rows.slice(safeOffset, safeOffset + limit),
    pager: {
      total: rows.length,
      offset: safeOffset,
      limit,
      onPageChange: setOffset,
      onPageSizeChange: (n: number) => { setLimit(n); setOffset(0); },
    },
  };
}
