/**
 * AnimatedDigits Component
 * Odometer-style rolling animation for timer digits.
 * Each digit position contains a column of 0-9 that translates vertically.
 */
import { cn } from "@/shared/lib";

const DIGITS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];

function RollingDigit({ digit }: { digit: number }) {
  return (
    <span
      className="inline-block overflow-hidden relative"
      style={{ width: "0.65em", height: "1.15em" }}
    >
      <span
        className="absolute left-0 right-0 flex flex-col transition-transform duration-300 ease-out"
        style={{ transform: `translateY(${-digit * 1.15}em)` }}
      >
        {DIGITS.map((d) => (
          <span
            key={d}
            className="flex items-center justify-center"
            style={{ height: "1.15em" }}
            aria-hidden={d !== digit}
          >
            {d}
          </span>
        ))}
      </span>
    </span>
  );
}

interface AnimatedDigitsProps {
  /** Timer string like "00:12:34" */
  value: string;
  className?: string;
  /** Extra class for the colon separators */
  colonClassName?: string;
}

export function AnimatedDigits({ value, className, colonClassName }: AnimatedDigitsProps) {
  return (
    <span className={cn("inline-flex items-baseline", className)} aria-label={value}>
      {value.split("").map((char, i) =>
        char === ":" ? (
          <span key={i} className={cn("w-[0.35em] text-center opacity-60", colonClassName)}>
            :
          </span>
        ) : (
          <RollingDigit key={i} digit={parseInt(char, 10)} />
        )
      )}
    </span>
  );
}
