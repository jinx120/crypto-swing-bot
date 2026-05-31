import { marked } from 'marked'
import md from '../guide.md?raw'

// The guide is our own static markdown bundled at build time, so rendering it
// with dangerouslySetInnerHTML is safe (no user input).
const html = marked.parse(md)

export default function Guide(){
  return (
    <div className="wrap">
      <div className="panel full guide" dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  )
}
