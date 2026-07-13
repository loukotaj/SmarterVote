import { Tooltip } from "../Tooltip";

export type Grade = "A" | "B" | "C" | "D" | "F";

export interface ValidationGradeInfo {
  grade: Grade;
  score: number;
  summary: string;
}

export interface ValidationGradeBadgeProps {
  grade: ValidationGradeInfo;
  /** Called when the user clicks "View Full Review" inside the popover. */
  onViewReview?: () => void;
}

const gradeColors: Record<Grade, string> = {
  A: "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200 border-green-300 dark:border-green-700",
  B: "bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 border-blue-300 dark:border-blue-700",
  C: "bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-200 border-yellow-300 dark:border-yellow-700",
  D: "bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-200 border-orange-300 dark:border-orange-700",
  F: "bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200 border-red-300 dark:border-red-700",
};

/**
 * Circular A–F AI-validation grade pill. Clicking it opens a popover with
 * the score, a summary, and a "View Full Review" link.
 */
export function ValidationGradeBadge({ grade, onViewReview }: ValidationGradeBadgeProps) {
  const colorClass = gradeColors[grade.grade];

  return (
    <Tooltip
      trigger={
        <span
          aria-label={`Validation Grade: ${grade.grade}`}
          className={`grade-badge inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm font-semibold cursor-pointer transition-all duration-150 hover:shadow-md active:scale-95 ${colorClass}`}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span className="text-base font-bold leading-none">{grade.grade}</span>
          <span className="text-xs font-medium opacity-75">Validation</span>
        </span>
      }
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold text-content">AI Validation Grade</span>
        <span className={`px-2 py-0.5 rounded text-sm font-bold border ${colorClass}`}>{grade.grade}</span>
      </div>
      <p className="text-sm font-medium text-content-muted mb-1">Score: {grade.score}/100</p>
      <p className="text-sm text-content-muted mb-3">{grade.summary}</p>
      <p className="text-xs text-content-subtle mb-3 leading-relaxed">
        Multiple AI models independently review each race profile for factual accuracy, source quality,
        completeness, and neutrality. The grade reflects the average score across all reviewers.
      </p>
      <button
        type="button"
        onClick={onViewReview}
        className="inline-flex items-center gap-1 text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 cursor-pointer transition-colors duration-150"
      >
        View Full Review
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
        </svg>
      </button>
    </Tooltip>
  );
}
