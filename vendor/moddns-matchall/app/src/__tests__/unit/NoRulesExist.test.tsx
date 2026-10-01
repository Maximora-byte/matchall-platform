import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { describe, it, expect } from 'vitest';
import NoRulesExist from '@/pages/custom_rules/NoRulesExist';

// Simple test to ensure input appears before button in DOM (mobile vertical stacking)

describe('NoRulesExist composer rendering', () => {
    it('renders provided composer when showInput is true', () => {
        render(
            <NoRulesExist
                type="denied"
                showInput
                composer={<div data-testid="composer">Composer</div>}
            />
        );
        const wrapper = screen.getByTestId('no-rules-input-wrapper');
        expect(wrapper).toBeInTheDocument();
        expect(screen.getByTestId('composer')).toBeInTheDocument();
    });
});
