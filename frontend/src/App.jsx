import { Routes, Route, Navigate } from 'react-router-dom'
import DashboardLayout from './layouts/DashboardLayout'
import DashboardPage from './pages/DashboardPage'
import DatasetsPage from './pages/DatasetsPage'
import DatasetProfilePage from './pages/DatasetProfilePage'
import DiscoveryPage from './pages/DiscoveryPage'
import ExplorerPage from './pages/ExplorerPage'
import EvidencePage from './pages/EvidencePage'
import TrainingPage from './pages/TrainingPage'
import SentimentPage from './pages/SentimentPage'
import BotPage from './pages/BotPage'
import MisinformationPage from './pages/MisinformationPage'
import TopicsPage from './pages/TopicsPage'
import NetworkPage from './pages/NetworkPage'
import ReportsPage from './pages/ReportsPage'
import SettingsPage from './pages/SettingsPage'
import TermsPage from './pages/TermsPage'
import PrivacyPage from './pages/PrivacyPage'

export default function App() {
  return (
    <Routes>
      <Route element={<DashboardLayout />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/datasets" element={<DatasetsPage />} />
        <Route path="/datasets/discovery" element={<DiscoveryPage />} />
        <Route path="/datasets/:id" element={<DatasetProfilePage />} />
        <Route path="/explorer" element={<ExplorerPage />} />
        <Route path="/evidence" element={<EvidencePage />} />
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/sentiment" element={<SentimentPage />} />
        <Route path="/bot-detection" element={<BotPage />} />
        <Route path="/misinformation" element={<MisinformationPage />} />
        <Route path="/topics" element={<TopicsPage />} />
        <Route path="/network" element={<NetworkPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
