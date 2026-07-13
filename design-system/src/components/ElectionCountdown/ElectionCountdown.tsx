import * as React from "react";
import { StatTile } from "../StatTile";

export interface ElectionCountdownProps {
  electionDate: string;
}

type Status = "upcoming" | "today" | "past";

function diffParts(electionDate: string) {
  const target = new Date(electionDate).getTime();
  const now = Date.now();
  const difference = target - now;

  if (difference <= 0) {
    const isToday = new Date(electionDate).toDateString() === new Date().toDateString();
    return { status: (isToday ? "today" : "past") as Status, days: 0, hours: 0, minutes: 0, seconds: 0 };
  }

  return {
    status: "upcoming" as Status,
    days: Math.floor(difference / (1000 * 60 * 60 * 24)),
    hours: Math.floor((difference % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)),
    minutes: Math.floor((difference % (1000 * 60 * 60)) / (1000 * 60)),
    seconds: Math.floor((difference % (1000 * 60)) / 1000),
  };
}

/**
 * Election-day countdown banner — a live Days/Hrs/Mins/Secs tile row while
 * upcoming, or a status pill ("Polls Open" / "Voting Closed") once the date
 * has passed.
 */
export function ElectionCountdown({ electionDate }: ElectionCountdownProps) {
  const [parts, setParts] = React.useState(() => diffParts(electionDate));

  React.useEffect(() => {
    const id = setInterval(() => setParts(diffParts(electionDate)), 1000);
    return () => clearInterval(id);
  }, [electionDate]);

  const { status, days, hours, minutes, seconds } = parts;

  return (
    <div className="bg-gradient-to-r from-blue-500/10 to-red-500/10 border border-stroke rounded-2xl p-4 sm:p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
          </span>
          <h3 className="text-xs font-black uppercase text-content-subtle tracking-wider">Countdown to Election Day</h3>
        </div>
        <p className="text-sm font-semibold text-content">
          {status === "upcoming"
            ? `The general election will be held on ${new Date(electionDate).toLocaleDateString(undefined, { dateStyle: "long" })}.`
            : `Election status: ${status === "today" ? "Polls are open today!" : "Completed"}`}
        </p>
      </div>

      {status === "upcoming" ? (
        <div className="flex gap-2 sm:gap-3 justify-center">
          <StatTile size="sm" value={days} label="Days" className="min-w-[56px] px-2.5 py-1.5" />
          <StatTile size="sm" value={hours} label="Hrs" className="min-w-[56px] px-2.5 py-1.5" />
          <StatTile size="sm" value={minutes} label="Mins" className="min-w-[56px] px-2.5 py-1.5" />
          <StatTile size="sm" value={seconds} label="Secs" className="min-w-[56px] px-2.5 py-1.5" />
        </div>
      ) : (
        <div
          className={`px-4 py-2 rounded-xl text-sm font-black border uppercase tracking-wider shadow-sm ${
            status === "today"
              ? "bg-emerald-500/10 text-emerald-700 border-emerald-500/20 dark:text-emerald-400"
              : "bg-slate-500/10 text-slate-700 border-slate-500/20 dark:text-slate-400"
          }`}
        >
          {status === "today" ? "Polls Open" : "Voting Closed"}
        </div>
      )}
    </div>
  );
}
