import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { formatUpdatedRelative } from '@/pages/blocklists/MainContentSection';
import { formatDistanceToNow, parseISO } from 'date-fns';

vi.mock('date-fns', () => {
    return {
        formatDistanceToNow: vi.fn(),
        parseISO: vi.fn((value: string) => new Date(value)),
    };
});

const mockedFormatDistanceToNow = formatDistanceToNow as unknown as Mock;
const mockedParseISO = parseISO as unknown as Mock;

describe('formatUpdatedRelative', () => {
    beforeEach(() => {
        mockedFormatDistanceToNow.mockReset();
        mockedParseISO.mockClear();
    });

    it('returns empty string when date is missing', () => {
        expect(formatUpdatedRelative()).toBe('');
        expect(mockedFormatDistanceToNow).not.toHaveBeenCalled();
        expect(mockedParseISO).not.toHaveBeenCalled();
    });

    it('replaces leading "about" with tilde', () => {
        mockedFormatDistanceToNow.mockReturnValue('about 3 hours ago');
        const result = formatUpdatedRelative('2024-01-01T00:00:00Z');
        expect(mockedParseISO).toHaveBeenCalledWith('2024-01-01T00:00:00Z');
        expect(result).toBe('~3 hours ago');
    });

    it('returns value unchanged when no "about" prefix', () => {
        mockedFormatDistanceToNow.mockReturnValue('3 hours ago');
        expect(formatUpdatedRelative('2024-01-01T00:00:00Z')).toBe('3 hours ago');
    });
});
