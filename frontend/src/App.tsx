import React from 'react';
import Dashboard from './components/Dashboard';

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean }> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() { return { hasError: true }; }
  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#0b0e14] flex flex-col items-center justify-center p-4 text-center">
          <h1 className="text-2xl font-bold text-danger mb-2">Dashboard Crashed</h1>
          <p className="text-gray-400 mb-4">A critical error occurred in the rendering pipe.</p>
          <button
            onClick={() => window.location.reload()}
            className="bg-accent/20 text-accent px-4 py-2 rounded-lg border border-accent/40"
          >
            Reload Application
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  return (
    <div className="min-h-screen bg-hyper">
      <ErrorBoundary>
        <Dashboard />
      </ErrorBoundary>
    </div>
  );
}

export default App;
