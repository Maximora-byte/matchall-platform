import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React, { useState } from 'react';
import { InputOTP, InputOTPGroup, InputOTPSeparator, InputOTPSlot } from '@/components/ui/input-otp';

describe('InputOTP', () => {
    let captured = '';
    beforeEach(() => { captured = ''; });

    const Wrapper: React.FC<{ onEnter?: (code: string) => void }> = ({ onEnter }) => {
        const [value, setValue] = useState('');
        return (
            <InputOTP maxLength={6} value={value} onChange={(v) => { setValue(v); captured = v; }} onEnter={onEnter}>
                <InputOTPGroup>
                    <InputOTPSlot index={0} autoFocus />
                    <InputOTPSlot index={1} />
                    <InputOTPSlot index={2} />
                </InputOTPGroup>
                <InputOTPSeparator />
                <InputOTPGroup>
                    <InputOTPSlot index={3} />
                    <InputOTPSlot index={4} />
                    <InputOTPSlot index={5} />
                </InputOTPGroup>
            </InputOTP>
        );
    };

    const setup = (props: { onEnter?: (code: string) => void } = {}) => render(<Wrapper {...props} />);

    it('fills slots sequentially when typing', async () => {
        const user = userEvent.setup();
        setup();
        const first = screen.getByLabelText('Digit 1');
        await user.type(first, '123456');
        await waitFor(() => expect(captured).toBe('123456'));
        for (let i = 1; i <= 6; i++) {
            expect(screen.getByLabelText(`Digit ${i}`)).toHaveValue(String(i));
        }
    });

    it('allows backspace navigation', async () => {
        const user = userEvent.setup();
        setup();
        const first = screen.getByLabelText('Digit 1');
        await user.type(first, '12');
        const second = screen.getByLabelText('Digit 2');
        await user.click(second);
        await user.keyboard('{Backspace}');
        await waitFor(() => expect(captured).toBe('1'));
    });

    it('ignores non-digit characters', async () => {
        const user = userEvent.setup();
        setup();
        const first = screen.getByLabelText('Digit 1');
        await user.type(first, 'a1b2c3');
        await waitFor(() => expect(captured).toBe('123'));
    });

    it('supports paste filling all slots', async () => {
        const user = userEvent.setup();
        setup();
        const first = screen.getByLabelText('Digit 1');
        await user.click(first);
        await user.paste('987654');
        await waitFor(() => expect(captured).toBe('987654'));
        const expected = ['9', '8', '7', '6', '5', '4'];
        expected.forEach((d, i) => {
            expect(screen.getByLabelText(`Digit ${i + 1}`)).toHaveValue(d);
        });
    });

    it('fires onEnter when full code entered and Enter pressed', async () => {
        const user = userEvent.setup();
        let enterValue: string | null = null;
        setup({ onEnter: (code) => { enterValue = code; } });
        const first = screen.getByLabelText('Digit 1');
        await user.type(first, '123456');
        // Focus last slot explicitly then press Enter
        const last = screen.getByLabelText('Digit 6');
        await user.click(last);
        await user.keyboard('{Enter}');
        await waitFor(() => expect(enterValue).toBe('123456'));
    });
});
