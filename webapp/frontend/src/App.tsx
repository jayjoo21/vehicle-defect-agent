import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import MyCar from './pages/MyCar'
import ReportView from './pages/ReportView'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/my-car" element={<MyCar />} />
        <Route path="/reports/:id" element={<ReportView />} />
      </Route>
    </Routes>
  )
}

export default App
