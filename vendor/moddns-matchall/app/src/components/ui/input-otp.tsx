import React, { useCallback, useEffect, useRef, useState, createContext, useContext } from "react";
import { cn } from "@/lib/utils";

interface InputOTPContextValue {
    value: string;
    setValue: (v: string) => void;
    maxLength: number;
    onComplete?: (code: string) => void;
    onEnter?: (code: string) => void;
}

const InputOTPContext = createContext<InputOTPContextValue | null>(null);

type DivProps = Omit<React.HTMLAttributes<HTMLDivElement>, 'onChange'>;
interface InputOTPProps extends DivProps {
    value?: string;
    defaultValue?: string;
    onChange?: (value: string) => void; // custom string onChange, not DOM event
    onComplete?: (code: string) => void;
    onEnter?: (code: string) => void; // invoked when Enter pressed and code length === maxLength
    maxLength: number;
}

export const InputOTP: React.FC<InputOTPProps> = ({
    value: controlledValue,
    defaultValue,
    onChange,
    onComplete,
    onEnter,
    maxLength,
    className,
    children,
    ...rest
}) => {
    const [uncontrolled, setUncontrolled] = useState(defaultValue || "");
    const isControlled = controlledValue !== undefined;
    const value = isControlled ? controlledValue! : uncontrolled;

    const setValue = useCallback(
        (next: string) => {
            if (next.length > maxLength) next = next.slice(0, maxLength);
            if (!isControlled) setUncontrolled(next);
            onChange?.(next);
            if (next.length === maxLength) onComplete?.(next);
        },
        [isControlled, maxLength, onChange, onComplete]
    );

    // Expose paste handling: if user pastes code while focusing any slot.
    const handlePaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
        const text = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, maxLength);
        if (text.length > 0) {
            e.preventDefault();
            setValue(text);
        }
    };

    return (
        <InputOTPContext.Provider value={{ value, setValue, maxLength, onComplete, onEnter }}>
            <div
                role="group"
                aria-label="One-time password"
                onPaste={handlePaste}
                className={cn("flex items-center gap-2", className)}
                {...rest}
            >
                {children}
            </div>
        </InputOTPContext.Provider>
    );
};

export const InputOTPGroup: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className, ...rest }) => (
    <div className={cn("flex items-center gap-2", className)} {...rest} />
);

export const InputOTPSeparator: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className, children, ...rest }) => (
    <div className={cn("text-[var(--tailwind-colors-slate-400)]", className)} {...rest}>
        {children || <span className="select-none">-</span>}
    </div>
);

interface InputOTPSlotProps extends React.InputHTMLAttributes<HTMLInputElement> {
    index: number;
}

export const InputOTPSlot: React.FC<InputOTPSlotProps> = ({ index, className, autoFocus, ...rest }) => {
    const ctx = useContext(InputOTPContext);
    if (!ctx) throw new Error("InputOTPSlot must be used within InputOTP");
    const { value, setValue, maxLength, onEnter } = ctx;
    const char = value[index] || "";
    const inputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        if (autoFocus && inputRef.current) {
            inputRef.current.focus();
            inputRef.current.select();
        }
    }, [autoFocus]);

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const raw = e.target.value;
        const digitsOnly = raw.replace(/\D/g, "");
        // If user cleared input
        if (!digitsOnly) {
            const arr = value.split("");
            arr[index] = "";
            setValue(arr.join(""));
            return;
        }
        // Distribute typed digits across current and subsequent slots (handles rapid typing or IME input)
        const arr = value.split("");
        let slot = index;
        for (const d of digitsOnly) {
            if (slot >= maxLength) break;
            arr[slot] = d;
            slot++;
        }
        setValue(arr.join(""));
        // move focus to next empty slot globally (works across separated groups)
        if (slot <= maxLength - 1) {
            const nextInput = document.querySelector<HTMLInputElement>(`input[data-slot="${slot}"]`);
            nextInput?.focus();
            nextInput?.select();
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        const globalPrev = document.querySelector<HTMLInputElement>(`input[data-slot="${index - 1}"]`);
        const globalNext = document.querySelector<HTMLInputElement>(`input[data-slot="${index + 1}"]`);
        if (e.key === "Backspace" && !char && index > 0) {
            e.preventDefault();
            globalPrev?.focus();
            globalPrev?.select();
        }
        if (e.key === "ArrowLeft" && index > 0) {
            e.preventDefault();
            globalPrev?.focus();
        }
        if (e.key === "ArrowRight" && index < maxLength - 1) {
            e.preventDefault();
            globalNext?.focus();
        }
        if (e.key === 'Enter') {
            // If full length code entered, trigger onEnter
            const code = value;
            if (code.length === maxLength) {
                e.preventDefault();
                onEnter?.(code);
            }
        }
    };

    return (
        <input
            ref={inputRef}
            data-slot={index}
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={1}
            aria-label={`Digit ${index + 1}`}
            value={char}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            className={cn(
                "w-10 h-12 rounded-md border bg-transparent text-center font-medium tracking-widest text-[var(--tailwind-colors-slate-50)] border-[var(--tailwind-colors-slate-700)] focus:outline-none focus:ring-2 focus:ring-[var(--tailwind-colors-rdns-600)]",
                char ? "border-[var(--tailwind-colors-rdns-600)]" : "",
                className
            )}
            {...rest}
        />
    );
};

export default InputOTP;
