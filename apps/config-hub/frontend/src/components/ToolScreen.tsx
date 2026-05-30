/**
 * ToolScreen — Detail screen for tools (Jenkinsfile, Config Transfer).
 *
 * Displayed via stack navigator push from HomeScreen.
 */

import { ChevronLeft } from 'lucide-preact';
import JenkinsfilePanel from './JenkinsfilePanel';
import ConfigTransfer from './ConfigTransfer';

interface ToolScreenProps {
  onBack: () => void;
}

export default function ToolScreen({ onBack }: ToolScreenProps) {
  return (
    <div class="container">
      <header>
        <button class="back-button" onClick={onBack}>
          <ChevronLeft size={20} />
          Back
        </button>
      </header>

      <h2 class="panel-title">Tools</h2>
      <p class="panel-desc">
        Jenkins pipeline preview and configuration export/import utilities.
      </p>

      <JenkinsfilePanel />
      <div style={{ marginTop: '16px' }}>
        <ConfigTransfer />
      </div>
    </div>
  );
}
