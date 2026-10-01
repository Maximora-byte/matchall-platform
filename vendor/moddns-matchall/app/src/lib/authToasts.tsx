import { toast } from 'sonner';

export const AUTH_TOAST_IDS = {
    loginSuccess: 'toast-login-success',
    logoutSuccess: 'toast-logout-success',
    sessionExpired: 'toast-session-expired',
    loginInvalid: 'toast-login-invalid',
    loginUnauthorized: 'toast-login-unauthorized',
    loginTooManyAttempts: 'toast-login-rate-limit',
    loginUnexpectedError: 'toast-login-error',
    loginTOTPRequired: 'toast-login-totp-required',
    passkeyError: 'toast-passkey-error',
    passwordResetSuccess: 'toast-password-reset-success',
    accountDeletedSuccess: 'toast-account-deleted-success',
    accountCreatedSuccess: 'toast-account-created-success',
    emailVerifiedSuccess: 'toast-email-verified-success',
    emailVerifiedAlready: 'toast-email-verified-already',
    emailVerifyInvalid: 'toast-email-verify-invalid',
    emailVerifyExpired: 'toast-email-verify-expired',
    emailVerifyGenericError: 'toast-email-verify-error',
    emailVerifyRateLimit: 'toast-email-verify-rate-limit',
} as const;

type AuthToastId = keyof typeof AUTH_TOAST_IDS;

// Inline JSX factory without importing entire React namespace
const span = (id: (typeof AUTH_TOAST_IDS)[AuthToastId], message: string) => (<span data-testid={id}>{message}</span>);

export const authToasts = {
    loginSuccess: () => toast.success(span(AUTH_TOAST_IDS.loginSuccess, 'Logged in successfully.')),
    logoutSuccess: () => toast.success(span(AUTH_TOAST_IDS.logoutSuccess, 'Logged out successfully.')),
    sessionExpired: () => toast.error(span(AUTH_TOAST_IDS.sessionExpired, 'Session expired - please log in again.')),
    invalidCredentials: () => toast.error(span(AUTH_TOAST_IDS.loginInvalid, 'Invalid credentials or login failed.')),
    unauthorized: () => toast.error(span(AUTH_TOAST_IDS.loginUnauthorized, 'Unauthorized. Please check your credentials.')),
    tooManyAttempts: () => toast.error(span(AUTH_TOAST_IDS.loginTooManyAttempts, 'Too many login attempts. Please try again later.')),
    unexpectedError: (msg?: string) => toast.error(span(AUTH_TOAST_IDS.loginUnexpectedError, msg || 'An unexpected error occurred.')),
    totpRequired: () => toast.info(span(AUTH_TOAST_IDS.loginTOTPRequired, 'Two-factor authentication required. Please enter your code.')),
    passkeyError: (msg?: string) => toast.error(span(AUTH_TOAST_IDS.passkeyError, msg || 'Passkey authentication failed')),
    passwordResetSuccess: () => toast.success(span(AUTH_TOAST_IDS.passwordResetSuccess, 'Password reset successful. You can now log in.')),
    accountDeletedSuccess: () => toast.success(span(AUTH_TOAST_IDS.accountDeletedSuccess, 'Account deleted successfully.')),
    accountCreatedSuccess: () => toast.success(span(AUTH_TOAST_IDS.accountCreatedSuccess, 'Account created successfully. Please log in.')),
    emailVerifiedSuccess: () => toast.success(span(AUTH_TOAST_IDS.emailVerifiedSuccess, 'Email verified successfully. You can now log in.')),
    emailVerifiedAlready: () => toast.info(span(AUTH_TOAST_IDS.emailVerifiedAlready, 'Email already verified. You can log in.')),
    emailVerifyInvalid: () => toast.error(span(AUTH_TOAST_IDS.emailVerifyInvalid, 'Invalid or unknown verification token.')),
    emailVerifyExpired: () => toast.error(span(AUTH_TOAST_IDS.emailVerifyExpired, 'Verification link expired. Request a new one.')),
    emailVerifyGenericError: () => toast.error(span(AUTH_TOAST_IDS.emailVerifyGenericError, 'Email verification failed. Please request a new code or retry.')),
    emailVerifyRateLimit: () => toast.error(span(AUTH_TOAST_IDS.emailVerifyRateLimit, 'Too many verification attempts. Please wait and try again.')),
};

export type AuthToastHelpers = typeof authToasts;
