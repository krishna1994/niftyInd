import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('App crashed:', error, info);
    this.setState({ info });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '30px',
          color: '#ff4757',
          background: '#0a0e1a',
          minHeight: '100vh',
          fontFamily: 'monospace'
        }}>
          <h2 style={{ color: '#ffa502' }}>⚠️ App Error — Check Console</h2>
          <pre style={{ color: '#e8eaf6', whiteSpace: 'pre-wrap', fontSize: '13px' }}>
            {this.state.error?.toString()}
          </pre>
          <pre style={{ color: '#546e7a', whiteSpace: 'pre-wrap', fontSize: '12px' }}>
            {this.state.error?.stack}
          </pre>
          {this.state.info && (
            <pre style={{ color: '#546e7a', whiteSpace: 'pre-wrap', fontSize: '12px' }}>
              {this.state.info.componentStack}
            </pre>
          )}
        </div>
      );
    }
    return this.props.children;
  }
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
