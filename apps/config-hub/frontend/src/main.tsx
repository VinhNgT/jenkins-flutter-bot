import { render } from 'preact';
import './styles/tokens.css';
import './styles/layout.css';
import './styles/components.css';
import './styles/forms.css';
import './styles/editors.css';
import './styles/tools.css';
import './styles/responsive.css';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import { ToastProvider } from './context/ToastContext';
import { ConfirmProvider } from './context/ConfirmDialog';

render(
  <ErrorBoundary>
    <ToastProvider>
      <ConfirmProvider>
        <App />
      </ConfirmProvider>
    </ToastProvider>
  </ErrorBoundary>,
  document.getElementById('app')!,
);
