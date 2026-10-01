import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { describe, test, expect } from 'vitest';
import QueryLogsSection from '@/pages/settings/QueryLogsSection';
import type { LogsSetting } from '@/pages/settings/QueryLogsSection';

// Minimal shape for logsSettings passed to component
// Index mapping in component:
// 0 -> enable/disable logs
// 1,2 -> other settings (we can stub)
// 3 -> retention period
const stubSettings: LogsSetting[] = [
    { value: 'enable', options: [{ value: 'enable', label: 'Enable' }, { value: 'disable', label: 'Disable' }] },
    { title: 'Setting A', description: 'Desc A', value: 'on', options: [{ value: 'on', label: 'On' }, { value: 'off', label: 'Off' }] },
    { title: 'Setting B', description: 'Desc B', value: 'on', options: [{ value: 'on', label: 'On' }, { value: 'off', label: 'Off' }] },
    { value: '1d', options: [{ value: '1d', label: '1d' }, { value: '7d', label: '7d' }] }
];

describe('QueryLogsSection retention info tooltip', () => {
    test('shows informational tooltip content when hovering info icon', async () => {
        render(
            <QueryLogsSection
                logsSettings={stubSettings}
                activeProfile={{ profile_id: 'p1' }}
                handleLogsChange={() => { }}
            />
        );
        const trigger = screen.getByTestId('retention-info-trigger');
        expect(trigger).toBeInTheDocument();
        fireEvent.mouseEnter(trigger);
        // Tooltip uses setTimeout even with delay=0; wait for appearance
        const tooltipText = await screen.findByText(/Changing the retention period switches to a new set of query logs/i, {}, { timeout: 500 });
        expect(tooltipText).toBeVisible();
    });

    test('accessible name on trigger button', () => {
        render(
            <QueryLogsSection
                logsSettings={stubSettings}
                activeProfile={{ profile_id: 'p1' }}
                handleLogsChange={() => { }}
            />
        );
        const trigger = screen.getByRole('button', { name: /Retention period information/i });
        expect(trigger).toBeInTheDocument();
    });
});
