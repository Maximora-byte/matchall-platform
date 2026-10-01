import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { AlertTriangle } from "lucide-react";
import { type JSX } from "react";
import { DialogActions } from "@/components/dialogs/DialogLayout";

interface SessionLimitDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onConfirm: () => void;
    loading?: boolean;
}

export default function SessionLimitDialog({
    open,
    onOpenChange,
    onConfirm,
    loading = false,
}: SessionLimitDialogProps): JSX.Element {
    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent data-testid="session-limit-dialog" className="dialog-shell border-[var(--tailwind-colors-slate-600)] p-0 transition-opacity duration-200 [&_[data-slot=dialog-close]_svg]:text-[var(--tailwind-colors-rdns-600)] px-4 sm:px-0">
                <DialogHeader className="p-6 space-y-1.5">
                    <div className="flex items-center gap-3">
                        <AlertTriangle className="w-6 h-6 text-[var(--tailwind-colors-red-600)]" />
                        <DialogTitle className="text-lg font-semibold text-[var(--tailwind-colors-slate-50)] tracking-[-0.45px] leading-[18px] font-['Roboto_Flex-SemiBold',Helvetica] mt-[-1px]">
                            Session limit reached
                        </DialogTitle>
                    </div>
                    <DialogDescription className="text-sm font-normal text-[var(--tailwind-colors-slate-300)] font-['Roboto_Flex-Regular',Helvetica] leading-5">
                        You have reached the maximum number of active sessions. To continue, you can log out from all other devices and automatically log in here.
                    </DialogDescription>
                </DialogHeader>
                <DialogActions>
                    <Button
                        data-testid="session-limit-cancel"
                        variant="cancel"
                        size="lg"
                        className="flex-1 min-w-32 font-medium"
                        onClick={() => onOpenChange(false)}
                        disabled={loading}
                    >
                        Cancel
                    </Button>
                    <Button
                        data-testid="session-limit-confirm"
                        variant="default"
                        size="lg"
                        className="flex-1 min-w-32 bg-[var(--tailwind-colors-rdns-600)] text-[var(--tailwind-colors-slate-900)] hover:!bg-[var(--tailwind-colors-rdns-800)]"
                        onClick={onConfirm}
                        disabled={loading}
                    >
                        {loading ? "Logging in..." : "Log out all devices & log in"}
                    </Button>
                </DialogActions>
            </DialogContent>
        </Dialog>
    );
}
