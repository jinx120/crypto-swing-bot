import BrokerConnectionPanel from '../components/settings/BrokerConnectionPanel.jsx'
import AdvancedControls from '../components/settings/AdvancedControls.jsx'
import RebalancePanel from '../components/RebalancePanel.jsx'
import TokenGate from '../components/TokenGate.jsx'

export default function Settings() {
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-lg font-semibold">Settings</h1>
      <BrokerConnectionPanel />
      <RebalancePanel />
      <AdvancedControls />
      <TokenGate />
    </div>
  )
}
