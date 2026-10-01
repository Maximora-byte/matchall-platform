import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { InputOTP, InputOTPGroup, InputOTPSeparator, InputOTPSlot } from '@/components/ui/input-otp';
import api from '@/api/api';
import { toast } from 'sonner';

interface VerifyEmailDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    email: string;
    onVerified: () => void;
}

type Phase = 'idle' | 'code-sent';

export default function VerifyEmailDialog({ open, onOpenChange, email, onVerified }: VerifyEmailDialogProps) {
    const [phase, setPhase] = useState<Phase>('idle');
    const [otp, setOtp] = useState('');
    const [sending, setSending] = useState(false);
    const [verifying, setVerifying] = useState(false);
    // Inline error text replaced by toast notifications; no persistent error state needed.
    const [cooldown, setCooldown] = useState(0);

    useEffect(() => {
        if (!open) {
            setPhase('idle');
            setOtp('');
            setSending(false);
            setVerifying(false);
            // clear previous inline state (no-op after removal)
            setCooldown(0);
        }
    }, [open]);

    // Auto-focus first OTP slot when code-sent phase becomes active
    useEffect(() => {
        if (phase === 'code-sent') {
            // Slight timeout to ensure elements rendered
            const t = setTimeout(() => {
                const firstSlot = document.querySelector<HTMLInputElement>('input[data-slot="0"]');
                firstSlot?.focus();
                firstSlot?.select();
            }, 30);
            return () => clearTimeout(t);
        }
    }, [phase]);

    useEffect(() => {
        if (cooldown <= 0) return;
        const t = setTimeout(() => setCooldown(cooldown - 1), 1000);
        return () => clearTimeout(t);
    }, [cooldown]);

    const requestCode = async () => {
        setSending(true);
        // previous inline error state removed
        try {
            await api.Client.verificationApi.apiV1VerifyEmailOtpRequestPost();
            setPhase('code-sent');
            setCooldown(30);
            toast.success('Verification code sent.');
        } catch (e: any) { // eslint-disable-line @typescript-eslint/no-explicit-any
            if (e?.response?.status === 429) toast.error('Too many requests. Please wait.');
            else toast.error('Failed to send code.');
        } finally {
            setSending(false);
        }
    };

    const resendCode = async () => {
        if (cooldown > 0) return;
        setOtp('');
        await requestCode();
    };

    const verifyCode = async () => {
        if (otp.length !== 6) { toast.error('Enter the 6-digit code.'); return; }
        setVerifying(true);
        // no inline error state
        try {
            await api.Client.verificationApi.apiV1VerifyEmailOtpConfirmPost({ otp });
            toast.success('Email verified successfully.');
            onVerified();
        } catch (e: any) { // eslint-disable-line @typescript-eslint/no-explicit-any
            const status = e?.response?.status;
            if (status === 422) toast.error('Invalid code.');
            else if (status === 410) toast.error('Code expired. Request a new one.');
            else if (status === 429) toast.error('Too many attempts. Please wait.');
            else toast.error('Verification failed. If the code is incorrect or expired, request a new one.');
        } finally {
            setVerifying(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="dialog-shell bg-[var(--shadcn-ui-app-background)] border-[var(--tailwind-colors-slate-600)] p-0 px-4 sm:px-0 max-w-sm w-full [&_[data-slot=dialog-close]_svg]:text-[var(--tailwind-colors-rdns-600)]">
                <DialogHeader className="p-6 space-y-1.5">
                    <DialogTitle className="text-lg font-semibold text-[var(--tailwind-colors-slate-50)] tracking-[-0.45px] leading-[18px] font-['Roboto_Flex-SemiBold',Helvetica] mt-[-1px]">
                        Verify email
                    </DialogTitle>
                </DialogHeader>
                <div className="flex flex-col gap-4 px-6 pb-2">
                    <p className="text-sm text-[var(--tailwind-colors-slate-50)] leading-5">
                        {phase === 'idle' ? 'Send a verification code to your email.' : `Enter the 6-digit code sent to ${email}.`}
                    </p>
                    {phase === 'code-sent' && (
                        <div className="space-y-4 w-full">
                            <div className="flex w-full justify-center">
                                <InputOTP
                                    maxLength={6}
                                    value={otp}
                                    onChange={(code: string) => setOtp(code.replace(/\D/g, '').slice(0, 6))}
                                    onEnter={() => { if (!verifying) verifyCode(); }}
                                    className="mx-auto"
                                >
                                    <InputOTPGroup>
                                        <InputOTPSlot index={0} autoFocus />
                                        <InputOTPSlot index={1} />
                                        <InputOTPSlot index={2} />
                                        <InputOTPSeparator />
                                        <InputOTPSlot index={3} />
                                        <InputOTPSlot index={4} />
                                        <InputOTPSlot index={5} />
                                    </InputOTPGroup>
                                </InputOTP>
                            </div>
                            <div className="flex items-center justify-between text-xs text-[var(--tailwind-colors-slate-400)]">
                                <span>{cooldown > 0 ? `Resend in ${cooldown}s` : 'You can resend a new code.'}</span>
                                <Button size="sm" type="button" disabled={cooldown > 0 || sending} onClick={resendCode} className="bg-[var(--tailwind-colors-slate-700)] text-[var(--tailwind-colors-slate-200)] hover:text-[var(--tailwind-colors-rdns-600)] hover:bg-[var(--tailwind-colors-slate-800)]">
                                    Resend
                                </Button>
                            </div>
                            {/* Aria-live region for countdown announcements */}
                            <div className="sr-only" aria-live="polite" aria-atomic="true">
                                {cooldown > 0 ? `Resend available in ${cooldown} seconds` : 'Resend available now'}
                            </div>
                        </div>
                    )}
                </div>
                <DialogFooter className="flex gap-2 px-6 pb-6">
                    {phase === 'idle' && (
                        <div className="flex w-full gap-3">
                            <Button
                                variant="cancel"
                                size="lg"
                                className="flex-1 min-w-32 font-medium"
                                onClick={() => onOpenChange(false)}
                                disabled={sending}
                            >
                                Cancel
                            </Button>
                            <Button
                                variant="default"
                                size="lg"
                                className="flex-1 min-w-32 bg-[var(--tailwind-colors-rdns-600)] text-[var(--tailwind-colors-slate-900)] hover:!bg-[var(--tailwind-colors-rdns-800)]"
                                onClick={requestCode}
                                disabled={sending}
                            >
                                {sending ? 'Sending…' : 'Send code'}
                            </Button>
                        </div>
                    )}
                    {phase === 'code-sent' && (
                        <form
                            className="flex w-full gap-3"
                            onSubmit={(e) => {
                                e.preventDefault();
                                if (verifying) return;
                                if (otp.length !== 6) { toast.error('Enter the 6-digit code.'); return; }
                                verifyCode();
                            }}
                        >
                            <Button
                                variant="cancel"
                                size="lg"
                                className="flex-1 min-w-32 font-medium"
                                onClick={() => onOpenChange(false)}
                                disabled={verifying}
                                type="button"
                            >
                                Cancel
                            </Button>
                            <Button
                                variant="default"
                                size="lg"
                                className="flex-1 min-w-32 bg-[var(--tailwind-colors-rdns-600)] text-[var(--tailwind-colors-slate-900)] hover:!bg-[var(--tailwind-colors-rdns-800)] flex items-center justify-center gap-2"
                                disabled={verifying}
                                type="submit"
                            >
                                {verifying && <Loader2 className="w-4 h-4 animate-spin" />}
                                {verifying ? 'Verifying…' : 'Verify'}
                            </Button>
                        </form>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
