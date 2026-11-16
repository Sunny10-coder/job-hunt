import * as React from "react";
import { useParams } from "react-router-dom";
import { useApi } from "@/hooks/useApi";
import { useApp } from "@/stores/app";
import type { CaseSummary } from "@/types";

/**
 * Resolves the case from the route and keeps the global store in sync so the
 * sidebar, topbar and every panel describe the same investigation.
 */
export function useCase() {
  const { caseId } = useParams<{ caseId: string }>();
  const { data, error, loading, reload } = useApi<CaseSummary>(
    caseId ? `/api/cases/${caseId}` : null,
    [caseId],
  );
  const setCurrentCase = useApp((state) => state.setCurrentCase);

  React.useEffect(() => {
    if (data) setCurrentCase(data);
  }, [data, setCurrentCase]);

  return { caseId: caseId ?? "", caseData: data, error, loading, reload };
}
