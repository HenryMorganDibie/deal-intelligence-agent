# Polling units

`polling_units_2025-09-27.csv.gz`: INEC's delimitation of Nigeria into 37 states (36 and the FCT), 774 LGAs,
8,809 wards (registration areas) and 176,623 polling units, one row per unit, keyed by INEC's code
`SS/LL/WW/UUU`. INEC's published total is 176,846 polling units.

**Source.** INEC's public polling-unit locator (inecnigeria.org/polling-units), as collected on 27 September 2025 by
the open-source [inec-polling-units-scraper](https://github.com/JayCodist/inec-polling-units-scraper).

**Cleaning** (`build_polling_units.py`): one blank placeholder row per ward removed; codes normalised to two-digit
state, LGA and ward and three-digit unit (a few source codes wrote the ward as `011`); where 37 units were listed
under a neighbouring ward's name, the ward takes the name most of its units carry, since the unit code is INEC's
identifier.

**Loading:** `scripts/load_polling_units.py`, run by the "Polling units" workflow.

The source data is used under the ISC licence:

> Copyright (c) 2025 Johnson Ubaezuonu
>
> Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby
> granted, provided that the above copyright notice and this permission notice appear in all copies.
>
> THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL
> IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
> INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN
> AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
> PERFORMANCE OF THIS SOFTWARE.
