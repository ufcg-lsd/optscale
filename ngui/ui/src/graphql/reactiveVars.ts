import { makeVar, ReactiveVar } from "@apollo/client";

type Error = {
  id: string;
  errorCode: string;
  errorReason: string;
  url: string;
  params: Record<string, unknown>;
  apolloErrorMessage: string;
};

/**
 *  A reactive var to hold the latest error (or null if none).
 *  Components can call `useReactiveVar(errorVar)` to re-render on changes.
 */
export const errorVar: ReactiveVar<Error | null> = makeVar<Error | null>(null);
