import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { ensureToken } from './api.js'
import './theme.css'

ensureToken().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode><App /></React.StrictMode>
  )
})
