import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

export default function LabChart({ timeline }) {
  try {
    if (!timeline || !Array.isArray(timeline) || timeline.length === 0) {
      return <p className="text-gray-500">No timeline data available</p>
    }

    // Transform timeline data for charting
    const chartData = timeline
      .filter(entry => entry && entry.data)
      .map(entry => ({
        date: entry.date === 'baseline' ? 'Baseline' : entry.date || 'Unknown',
        ALT_U_L: entry.data?.ALT_U_L ?? null,
        AST_U_L: entry.data?.AST_U_L ?? null,
        total_bilirubin_mg_dl: entry.data?.total_bilirubin_mg_dl ?? null,
        AFP_ng_ml: entry.data?.AFP_ng_ml ?? null,
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
            <Line type="monotone" dataKey="ALT_U_L" stroke="#8884d8" strokeWidth={2} name="ALT (U/L)" />
            <Line type="monotone" dataKey="AST_U_L" stroke="#82ca9d" strokeWidth={2} name="AST (U/L)" />
            <Line
              type="monotone"
              dataKey="total_bilirubin_mg_dl"
              stroke="#ffc658"
              strokeWidth={2}
              name="Total Bilirubin (mg/dL)"
            />
            <Line
              type="monotone"
              dataKey="AFP_ng_ml"
              stroke="#ff7300"
              strokeWidth={2}
              name="AFP (ng/mL)"
            />
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
