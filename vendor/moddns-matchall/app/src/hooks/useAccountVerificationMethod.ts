import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ModelAccount } from '@/api/client/api';
import { useAppStore } from '@/store/general';

export type VerificationMethod = 'password' | 'passkey';

interface UseAccountVerificationMethodOptions {
    account: ModelAccount | null;
    open: boolean;
    onMethodChange?: (method: VerificationMethod) => void;
}

interface UseAccountVerificationMethodResult {
    method: VerificationMethod;
    hasPasskeys: boolean;
    passwordAvailable: boolean;
    preferredMethod: VerificationMethod;
    showOtp: boolean;
    switchMethod: (method: VerificationMethod) => void;
    resetMethod: () => void;
}

export function useAccountVerificationMethod({
    account,
    open,
    onMethodChange,
}: UseAccountVerificationMethodOptions): UseAccountVerificationMethodResult {
    const passkeys = useAppStore(s => s.passkeys);
    const hasPasskeys = useMemo(() => Array.isArray(passkeys) && passkeys.length > 0, [passkeys]);

    const passwordAvailable = useMemo(() => {
        if (!account) return true;
        const methods = account.auth_methods;
        if (!Array.isArray(methods) || methods.length === 0) {
            return true;
        }
        return methods.includes('password');
    }, [account]);

    const preferredMethod: VerificationMethod = useMemo(() => {
        if (hasPasskeys && !passwordAvailable) return 'passkey';
        if (!hasPasskeys && passwordAvailable) return 'password';
        if (hasPasskeys && passwordAvailable) return 'passkey';
        return 'password';
    }, [hasPasskeys, passwordAvailable]);

    const [method, setMethod] = useState<VerificationMethod>(preferredMethod);

    const isMethodAvailable = useCallback((candidate: VerificationMethod) =>
        candidate === 'passkey' ? hasPasskeys : passwordAvailable,
    [hasPasskeys, passwordAvailable]);

    useEffect(() => {
        if (!open) {
            setMethod(preferredMethod);
            return;
        }
        setMethod(prev => {
            if (isMethodAvailable(prev)) {
                return prev;
            }
            return preferredMethod;
        });
    }, [open, preferredMethod, isMethodAvailable]);

    useEffect(() => {
        onMethodChange?.(method);
    }, [method, onMethodChange]);

    const switchMethod = useCallback((next: VerificationMethod) => {
        if (!isMethodAvailable(next)) {
            return;
        }
        setMethod(prev => (prev === next ? prev : next));
    }, [isMethodAvailable]);

    const resetMethod = useCallback(() => {
        setMethod(preferredMethod);
    }, [preferredMethod]);

    const showOtp = Boolean(account?.mfa?.totp?.enabled) && method === 'password';

    return {
        method,
        hasPasskeys,
        passwordAvailable,
        preferredMethod,
        showOtp,
        switchMethod,
        resetMethod,
    };
}
