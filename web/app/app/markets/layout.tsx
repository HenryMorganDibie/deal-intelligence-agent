import { MarketsNav } from "../../../components/app/MarketsNav";
import { Container } from "../../../components/primitives";

export default function MarketsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Container className="pt-6 lg:pt-8"><MarketsNav /></Container>
      {children}
    </>
  );
}
