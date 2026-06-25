import BrokerConnectionPanel from '../components/settings/BrokerConnectionPanel.jsx'
import DataSourcePanel from '../components/settings/DataSourcePanel.jsx'
import RiskDialPanel from '../components/settings/RiskDialPanel.jsx'
import TuningJournalPanel from '../components/settings/TuningJournalPanel.jsx'
import AdvancedControls from '../components/settings/AdvancedControls.jsx'
import RebalancePanel from '../components/RebalancePanel.jsx'

export default function Settings() {
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-lg font-semibold">Settings</h1>
      <DataSourcePanel />
      <BrokerConnectionPanel />
      <RiskDialPanel />
      <RebalancePanel />
      <TuningJournalPanel />
      <AdvancedControls />
    </div>
  )
}
