import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

export default function LabChart({ timeline }) {
  try {
    if (!timeline || !Array.isArray(timeline) || timeline.length === 0) {
      return <p className="text-gray-500">No timeline data available</p>
    }

    // Transform timeline data for charting
    const chartData = timeline
      .filter(entry => entry && entry.data) // Filter out invalid entries
      .map(entry => ({
        date: entry.date === 'baseline' ? 'Baseline' : entry.date || 'Unknown',
        ALT: entry.data?.ALT ?? null,
        AST: entry.data?.AST ?? null,
        Tbil: entry.data?.Tbil ?? null,
        Alb: entry.data?.Alb ?? null,
      }))

    if (chartData.length === 0) {
      return <p className="text-gray-500">No valid timeline data available</p>
    }

    return (
      <div className="w-full h-80">
        <h4 className="text-md font-semibold mb-4">Lab Values Timeline</h4>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="ALT" stroke="#8884d8" strokeWidth={2} />
            <Line type="monotone" dataKey="AST" stroke="#82ca9d" strokeWidth={2} />
            <Line type="monotone" dataKey="Tbil" stroke="#ffc658" strokeWidth={2} />
            <Line type="monotone" dataKey="Alb" stroke="#ff7300" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    )
  } catch (error) {
    console.error('Error rendering LabChart:', error)
    return (
      <div className="text-red-600 p-4 bg-red-50 rounded">
        <p>Error rendering chart: {error.message}</p>
      </div>
    )
  }
}
