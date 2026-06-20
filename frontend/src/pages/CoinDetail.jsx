import { useParams } from 'react-router-dom'
export default function CoinDetail() {
  const { name } = useParams()
  return <div className="mx-auto max-w-6xl p-4 text-muted-foreground">Coin Detail: {name}</div>
}
