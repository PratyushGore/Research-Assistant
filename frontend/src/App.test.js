import { render, screen } from '@testing-library/react';
import App from './App';

test('renders ResearchAI app', () => {
  render(<App />);
  const logoElements = screen.getAllByText(/ResearchAI/i);
  expect(logoElements.length).toBeGreaterThan(0);
});
