import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/store/general';

interface VerificationBannerProps {
    emailVerified: boolean | undefined;
}

export default function VerificationBanner({ emailVerified }: VerificationBannerProps) {
    const navigate = useNavigate();
    const dismissed = useAppStore(s => s.verificationBannerDismissed);
    const setDismissed = useAppStore(s => s.setVerificationBannerDismissed);

    if (emailVerified || dismissed) return null;

    return (
        <div className="w-full max-w-[630px] rounded-md border border-[var(--tailwind-colors-amber-400)] bg-[var(--tailwind-colors-amber-50)]/5 px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-3 text-[var(--tailwind-colors-amber-200)]" data-testid="verification-banner">
            <div className="flex-1 text-sm leading-5">
                <span className="font-semibold text-[var(--tailwind-colors-amber-300)]">Warning:</span> your email is not verified. Account recovery and critical notification emails are disabled.
            </div>
            <div className="flex items-center gap-2">
                <Button
                    variant="default"
                    size="sm"
                    className="bg-[var(--tailwind-colors-rdns-600)] text-[var(--tailwind-colors-slate-900)] hover:!bg-[var(--tailwind-colors-rdns-800)] animate-pulse"
                    onClick={() => { navigate('/account-preferences?highlight=verify'); }}
                >
                    Verify email
                </Button>
                <Button
                    variant="ghost"
                    size="sm"
                    className="text-[var(--tailwind-colors-amber-300)] hover:text-[var(--tailwind-colors-amber-200)]"
                    onClick={() => { setDismissed(true); }}
                >
                    Dismiss
                </Button>
            </div>
        </div>
    );
}
