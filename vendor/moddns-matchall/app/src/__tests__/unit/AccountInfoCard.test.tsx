import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import AccountInfoCard from '@/pages/account_preferences/AccountInfoCard';

describe('AccountInfoCard', () => {
    it('renders Active until and Subscription type fields and omits Member since', () => {
        const items = [
            { label: 'modDNS ID', value: 'user@example.com' },
            { label: 'Active until', value: '2025-12-31' },
            { label: 'Subscription type', value: 'Managed' },
        ];
        render(<AccountInfoCard accountInfo={items} />);
        expect(screen.getByText('Active until')).toBeInTheDocument();
        expect(screen.getByText('Subscription type')).toBeInTheDocument();
    });
});
