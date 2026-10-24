import * as XLSX from "@stackline/xlsx";

const MAX_WORKBOOK_BYTES = 5 * 1024 * 1024;
const MAX_WORKBOOK_ROWS = 5000;
const MAX_WORKBOOK_COLUMNS = 40;

function cellToText(value: unknown): string {
  if (value == null) return "";
  if (value instanceof Date && Number.isFinite(value.getTime())) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
  return String(value);
}

export function parsePortfolioWorkbook(input: ArrayBuffer | Uint8Array): string[][] {
  const bytes = input instanceof Uint8Array ? input.byteLength : input.byteLength;
  if (bytes === 0) throw new Error("The Excel workbook is empty.");
  if (bytes > MAX_WORKBOOK_BYTES) throw new Error("Excel files must be 5 MB or smaller.");

  let workbook: XLSX.WorkBook;
  try {
    workbook = XLSX.read(input, { type: "array", cellDates: true, WTF: true });
  } catch {
    throw new Error("Could not read this Excel workbook. Use a valid .xlsx file and try again.");
  }

  const firstSheetName = workbook.SheetNames[0];
  if (!firstSheetName) throw new Error("The Excel workbook does not contain a worksheet.");
  const worksheet = workbook.Sheets[firstSheetName];
  if (!worksheet || !worksheet["!ref"]) throw new Error("The first worksheet is empty.");

  const range = XLSX.utils.decode_range(worksheet["!ref"]);
  if (range.e.r - range.s.r + 1 > MAX_WORKBOOK_ROWS + 1) {
    throw new Error(`Excel files may contain at most ${MAX_WORKBOOK_ROWS} holding rows.`);
  }
  if (range.e.c - range.s.c + 1 > MAX_WORKBOOK_COLUMNS) {
    throw new Error(`The worksheet has too many columns (maximum ${MAX_WORKBOOK_COLUMNS}).`);
  }

  // Portfolio imports are data-only. Refuse formulas instead of importing stale cached
  // results or allowing workbook formulas to be mistaken for user-entered values.
  for (let row = range.s.r; row <= range.e.r; row += 1) {
    for (let column = range.s.c; column <= range.e.c; column += 1) {
      const cell = worksheet[XLSX.utils.encode_cell({ r: row, c: column })];
      if (cell && typeof cell === "object" && "f" in cell && cell.f) {
        throw new Error("Excel formulas are not accepted. Replace formula cells with values before importing.");
      }
    }
  }

  const rawRows = XLSX.utils.sheet_to_json<unknown[]>(worksheet, {
    header: 1,
    raw: true,
    defval: "",
    blankrows: false,
  });
  const rows = rawRows.map((row) => row.map(cellToText));
  while (rows.length && rows[rows.length - 1].every((cell) => !cell.trim())) rows.pop();
  if (rows.length > MAX_WORKBOOK_ROWS + 1) {
    throw new Error(`Excel files may contain at most ${MAX_WORKBOOK_ROWS} holding rows.`);
  }
  return rows;
}

export function createPortfolioWorkbook(rows: (string | number | null | undefined)[][]): Uint8Array {
  const workbook = XLSX.utils.book_new();
  const worksheet = XLSX.utils.aoa_to_sheet(rows.map((row) => row.map((cell) => cell ?? "")));
  XLSX.utils.book_append_sheet(workbook, worksheet, "Portfolio");
  const output = XLSX.write(workbook, { bookType: "xlsx", type: "array", compression: true });
  if (output instanceof ArrayBuffer) return new Uint8Array(output);
  if (output instanceof Uint8Array) return output;
  throw new Error("Could not create the Excel workbook.");
}
