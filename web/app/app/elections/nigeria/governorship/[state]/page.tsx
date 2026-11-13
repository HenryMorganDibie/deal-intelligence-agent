import { notFound } from "next/navigation";
import { LiveResults } from "../../../../../../components/app/LiveResults";
import { GOV_STATES, govSlug } from "../../../../../../lib/governorship";

export function generateStaticParams() {
  return GOV_STATES.map((s) => ({ state: govSlug(s) }));
}

export default function GovernorshipStatePage({ params }: { params: { state: string } }) {
  const state = GOV_STATES.find((s) => govSlug(s) === params.state);
  if (!state) notFound();
  return (
    <LiveResults election={`ng-2027-gov-${params.state}`} title={`${state}: governorship election, 6 February 2027`}
      intro={`As INEC's returning officer for ${state} declares each LGA at the state collation centre. Candidates: INEC's final list; 2023 shares: the declared result.`} />
  );
}
