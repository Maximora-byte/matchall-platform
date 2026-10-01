import { type JSX } from "react";
import MainContentSection from "@/pages/custom_rules/MainContentSection";
import type { ModelAccount, ModelProfile } from "@/api/client/api";

interface CustomRulesProps {
    account: ModelAccount;
    profiles: ModelProfile[];
}

export default function CustomRulesMain({ profiles }: Omit<CustomRulesProps, 'account'>): JSX.Element {
    return (
        <main
            // Ensure iOS renders scrollable area (avoid 100vh quirks) using min-h-screen and overflow-auto
            className="flex w-full min-h-screen bg-[var(--shadcn-ui-app-background)] overflow-x-hidden overflow-y-auto supports-[overflow:overlay]:overflow-y-overlay"
        >
            <MainContentSection profiles={profiles} />
        </main>
    );
}
