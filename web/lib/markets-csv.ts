/**
 * Small strict CSV parser for user-imported portfolio files.
 * Supports UTF-8 BOMs, CRLF/LF, escaped quotes and quoted multiline cells.
 * Rejects malformed quote placement rather than silently shifting columns.
 */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  let afterQuote = false;
  let atFieldStart = true;
  const input = text.replace(/^\uFEFF/, "");

  const finishField = () => {
    row.push(field.trim());
    field = "";
    afterQuote = false;
    atFieldStart = true;
  };
  const finishRow = () => {
    finishField();
    if (row.some((cell) => cell !== "")) rows.push(row);
    row = [];
  };

  for (let i = 0; i < input.length; i += 1) {
    const char = input[i];

    if (quoted) {
      if (char === '"') {
        if (input[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
          afterQuote = true;
        }
      } else {
        field += char;
      }
      continue;
    }

    if (afterQuote) {
      if (char === "," ) {
        finishField();
      } else if (char === "\n" || char === "\r") {
        if (char === "\r" && input[i + 1] === "\n") i += 1;
        finishRow();
      } else if (char === " " || char === "\t") {
        // Whitespace outside a quoted cell is ignored.
      } else {
        throw new Error("The CSV has unexpected characters after a closing quote.");
      }
      continue;
    }

    if (char === '"') {
      if (!atFieldStart) throw new Error("The CSV has a quote inside an unquoted field.");
      quoted = true;
      atFieldStart = false;
    } else if (char === ",") {
      finishField();
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && input[i + 1] === "\n") i += 1;
      finishRow();
    } else {
      field += char;
      if (char !== " " && char !== "\t") atFieldStart = false;
    }
  }

  if (quoted) throw new Error("The CSV contains an unclosed quoted field.");
  if (field !== "" || row.length > 0 || afterQuote) finishRow();
  return rows;
}

export function csvEscape(value: string | number | null | undefined): string {
  const text = value == null ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function stringifyCsv(rows: readonly (readonly (string | number | null | undefined)[])[]): string {
  return rows.map((row) => row.map(csvEscape).join(",")).join("\r\n");
}
