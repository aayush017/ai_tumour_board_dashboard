import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import PatientList from './pages/PatientList'
import PatientCreate from './pages/PatientCreate'
import PatientEdit from './pages/PatientEdit'
import PatientView from './pages/PatientView'

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<PatientList />} />
          <Route path="/create" element={<PatientCreate />} />
          <Route path="/patient/:caseId" element={<PatientView />} />
          <Route path="/patient/:caseId/edit" element={<PatientEdit />} />
        </Routes>
      </Layout>
    </Router>
  )
}

export default App
