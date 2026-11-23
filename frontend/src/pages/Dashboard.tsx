import { Card, PageHeader } from '../components/ui'
import { useMe } from '../lib/auth'

export function DashboardPage() {
  const { data: user } = useMe()
  return (
    <>
      <PageHeader title={`Welcome, ${user?.full_name ?? ''}`} subtitle="Today's summary will appear here." />
      <Card>
        <p className="text-sm text-stone-600">
          Sales, stock, outstanding and backup status will show up here as those modules are added.
        </p>
      </Card>
    </>
  )
}
