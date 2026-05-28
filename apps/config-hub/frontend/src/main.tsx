import { render } from 'preact';
import './styles/tokens.css';
import './styles/layout.css';
import './styles/components.css';
import './styles/forms.css';
import './styles/editors.css';
import './styles/tools.css';
import './styles/responsive.css';
import App from './App';
import { ToastProvider } from './context/ToastContext';
import { ConfirmProvider } from './components/ConfirmDialog';

render(
  <ToastProvider>
    <ConfirmProvider>
      <App />
    </ConfirmProvider>
  </ToastProvider>,
  document.getElementById('app')!,
);
