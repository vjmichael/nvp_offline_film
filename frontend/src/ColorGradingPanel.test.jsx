// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ColorGradingPanel from './ColorGradingPanel.jsx';

const PID = 'a'.repeat(32);
const SOURCE = {
  id: 'exr_source_16f', frames: 16, fps: 24, width: 256, height: 144,
  source_sha256: 'b'.repeat(64), take_id: 'take_16'
};
const GRADE = {
  format: 'nvp.color.grade.global.v1', scope: 'global_all_frames',
  exposure_stops: 0, contrast: 1, saturation: 1,
  red_gain: 1, green_gain: 1, blue_gain: 1
};
function response(body) { return { ok: true, json: async () => body }; }
const PREVIEW = new Blob(['\x89PNG\r\n\x1a\n', 'z'.repeat(128)], { type: 'image/png' });

beforeEach(() => {
  let saved = [];
  global.fetch = vi.fn(async (url, options) => {
    const path = String(url);
    if (path.endsWith('/sources')) return response([SOURCE]);
    if (path.includes('/preview?')) return {
      ok: true, blob: async () => PREVIEW
    };
    if (options?.method === 'POST' && path.endsWith('/grades')) {
      const payload = JSON.parse(options.body);
      saved = [{
        id: payload.grade_id, revision: 1, recipe: payload.recipe,
        source_exr_id: payload.source_exr_id, status: 'draft_not_director_approved'
      }];
      return response({
        id: payload.grade_id, revision: 1, recipe: payload.recipe,
        source_exr_id: payload.source_exr_id, status: 'draft_not_director_approved'
      });
    }
    if (path.endsWith('/history')) return response([{revision: 1,sha256:'c'.repeat(64),recipe: GRADE}]);
    if (path.includes('/grades?')) return response(saved);
    if (path.includes('/grades/')) return response({
      id:'look_main',revision:1,recipe:GRADE,source_exr_id:SOURCE.id
    });
    throw Error('Unexpected mock request: ' + path);
  });
  let generated = 0;
  URL.createObjectURL = vi.fn(() => 'blob:graded-preview-' + ++generated);
  URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('NVP-GRADE-UI-01', () => {
  it('shows only the real source and provides accessible before/after preview controls', async () => {
    render(<ColorGradingPanel project={{ id: PID }} onHelp={() => {}} />);
    await screen.findByRole('option', { name: /exr_source_16f/ });
    expect(screen.getByRole('heading', { name: 'Color grading workspace' })).toBeTruthy();
    expect(screen.getByRole('slider', { name: 'Before and after comparison wipe' })).toBeTruthy();
    await waitFor(() => expect(global.fetch.mock.calls.some(
      ([url]) => String(url).includes('mode=before'))).toBe(true));
    await waitFor(() => expect(global.fetch.mock.calls.some(
      ([url]) => String(url).includes('mode=after'))).toBe(true), { timeout: 3500 });
    expect(screen.getByText(/not a color-calibrated grading display/i)).toBeTruthy();
  });

  it('supports real grade controls with preset, undo, redo, and neutral reset', async () => {
    render(<ColorGradingPanel project={{ id: PID }} onHelp={() => {}} />);
    await screen.findByRole('option', { name: /exr_source_16f/ });
    const exposure = screen.getByRole('slider', { name: 'Exposure' });
    const number = screen.getByRole('spinbutton', { name: 'Exposure numeric value' });
    fireEvent.change(exposure, { target: { value: '0.25' } });
    expect(number.value).toBe('0.25');
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(number.value).toBe('0');
    fireEvent.click(screen.getByRole('button', { name: 'Redo' }));
    expect(number.value).toBe('0.25');
    fireEvent.click(screen.getByRole('button', { name: 'Warm' }));
    expect(screen.getByRole('spinbutton', { name: 'Red balance numeric value' }).value).toBe('1.05');
    fireEvent.click(screen.getByRole('button', { name: 'Reset neutral' }));
    expect(screen.getByRole('spinbutton', { name: 'Red balance numeric value' }).value).toBe('1');
  });

  it('keeps Save Draft disabled until source-space consent and sends a typed immutable edit', async () => {
    render(<ColorGradingPanel project={{ id: PID }} onHelp={() => {}} />);
    await screen.findByRole('option', { name: /exr_source_16f/ });
    const save = screen.getByRole('button', { name: 'Save draft look' });
    expect(save.disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(save.disabled).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Warm' }));
    fireEvent.click(save);
    await waitFor(() => expect(global.fetch.mock.calls.some(
      ([url, options]) => String(url).endsWith('/grades') && options?.method === 'POST'
    )).toBe(true));
    const call = global.fetch.mock.calls.find(
      ([url, options]) => String(url).endsWith('/grades') && options?.method === 'POST');
    const data = JSON.parse(call[1].body);
    expect(data.grade_id).toBe('look_main');
    expect(data.expected_revision).toBe(0);
    expect(data.recipe.format).toBe('nvp.color.grade.global.v1');
    expect(data.recipe.red_gain).toBe(1.05);
    expect(data.source_primaries_declared).toBe(true);
    await screen.findByText(/Draft look saved as immutable FilmIndex revision/);
  });
});
