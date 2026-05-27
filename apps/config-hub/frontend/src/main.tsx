import { render } from 'preact';
import './styles/global.css';
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
