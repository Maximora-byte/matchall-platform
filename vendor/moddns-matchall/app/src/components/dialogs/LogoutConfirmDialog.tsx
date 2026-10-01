import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { DialogActions } from "@/components/dialogs/DialogLayout";
import type { JSX } from "react";

interface LogoutConfirmDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onConfirm: () => void;
    loading?: boolean;
}

export default function LogoutConfirmDialog({
    open,
    onOpenChange,
    onConfirm,
    loading = false,
}: LogoutConfirmDialogProps): JSX.Element {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="dialog-shell border-[var(--tailwind-colors-slate-600)] p-0 transition-opacity duration-200 [&_[data-slot=dialog-close]_svg]:text-[var(--tailwind-colors-rdns-600)] px-4 sm:px-0">
                <DialogHeader className="p-6 space-y-1.5">
                    <DialogTitle className="text-lg font-semibold text-[var(--tailwind-colors-slate-50)] tracking-[-0.45px] leading-[18px] font-['Roboto_Flex-SemiBold',Helvetica] mt-[-1px]">
                        Confirm Logout
                    </DialogTitle>
                    <DialogDescription className="text-sm font-normal text-[var(--tailwind-colors-slate-400)] font-['Roboto_Flex-Regular',Helvetica] leading-5">
                        Are you sure you want to logout? You will need to sign in again to access your account.
                    </DialogDescription>
                </DialogHeader>
                <DialogActions>
                    <Button
                        variant="cancel"
                        size="lg"
                        className="flex-1 min-w-32 font-medium"
                        onClick={() => onOpenChange(false)}
                        disabled={loading}
                    >
                        Cancel
                    </Button>
                    <Button
                        variant="default"
                        size="lg"
                        className="flex-1 min-w-32 bg-[var(--tailwind-colors-rdns-600)] text-[var(--tailwind-colors-slate-900)] hover:!bg-[var(--tailwind-colors-rdns-800)]"
                        onClick={onConfirm}
                        data-testid="btn-confirm-logout"
                        disabled={loading}
                    >
                        {loading ? "Logging out..." : "Logout"}
                    </Button>
                </DialogActions>
            </DialogContent>
        </Dialog>
    );
}
