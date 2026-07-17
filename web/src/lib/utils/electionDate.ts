export interface ElectionCalendarDate {
  year: number;
  month: number;
  day: number;
}

const CALENDAR_DATE_PREFIX = /^(\d{4})-(\d{2})-(\d{2})(?:$|T)/;

/**
 * Read an election date as a calendar date, not an instant in time.
 *
 * Published race data may serialize a date as midnight UTC. Converting that
 * value directly with `new Date()` moves it to the previous day in US time
 * zones, even though Election Day itself has not changed.
 */
export function parseElectionDate(
  value: string | null | undefined,
): ElectionCalendarDate | null {
  if (!value) return null;
  const match = CALENDAR_DATE_PREFIX.exec(value.trim());
  if (!match) return null;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const validationDate = new Date(Date.UTC(year, month - 1, day));

  if (
    validationDate.getUTCFullYear() !== year ||
    validationDate.getUTCMonth() !== month - 1 ||
    validationDate.getUTCDate() !== day
  ) {
    return null;
  }

  return { year, month, day };
}

export function formatElectionDate(
  value: string | null | undefined,
  options: Intl.DateTimeFormatOptions = {
    month: "long",
    day: "numeric",
    year: "numeric",
  },
  locale: string | string[] | undefined = "en-US",
): string {
  const date = parseElectionDate(value);
  if (!date) return "Election date unavailable";

  return new Intl.DateTimeFormat(locale, {
    ...options,
    timeZone: "UTC",
  }).format(new Date(Date.UTC(date.year, date.month - 1, date.day, 12)));
}

/** Returns the difference between local calendar days, avoiding DST math. */
export function daysUntilElection(
  value: string | null | undefined,
  now = new Date(),
): number | null {
  const date = parseElectionDate(value);
  if (!date || Number.isNaN(now.getTime())) return null;

  const electionOrdinal = Date.UTC(date.year, date.month - 1, date.day);
  const todayOrdinal = Date.UTC(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  );
  return Math.round((electionOrdinal - todayOrdinal) / 86_400_000);
}
