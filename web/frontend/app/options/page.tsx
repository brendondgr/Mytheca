import type { Metadata } from "next";
import { OptionsView } from "@/features/options/OptionsView";

export const metadata: Metadata = {
  title: "Options · Velora",
};

export default function OptionsPage() {
  return <OptionsView />;
}
