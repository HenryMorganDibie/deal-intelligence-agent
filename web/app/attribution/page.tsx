import type { Metadata } from "next";
import { Attribution } from "../../components/Attribution";
import { PublicPage } from "../../components/PublicPage";

export const metadata: Metadata = {
  title: "Attribution | Deal Intelligence",
  description: "See how the signal engine checks whether a reported event actually concerns the company it is assigned to.",
};

export default function AttributionPage() {
  return <PublicPage><Attribution /></PublicPage>;
}
