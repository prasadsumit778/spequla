import { redirect } from "next/navigation";

/**
 * corpus/08 section 3: the financial overview is "the landing screen." There
 * is no separate home page to land on first -- the default surface is the
 * numbers (corpus/08 section 1).
 */
export default function Home() {
  redirect("/overview");
}
