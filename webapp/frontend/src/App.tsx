import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import MyCar from './pages/MyCar'
import ReportsHub from './pages/ReportsHub'
import ReportView from './pages/ReportView'
import SignalDetail from './pages/SignalDetail'
import Brand from './pages/Brand'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/my-car" element={<MyCar />} />
        <Route path="/reports" element={<ReportsHub />} />
        <Route path="/reports/:id" element={<ReportView />} />
        <Route path="/signals/:id" element={<SignalDetail />} />
        <Route path="/brand" element={<Brand />} />
      </Route>
    </Routes>
  )
}

export default App
