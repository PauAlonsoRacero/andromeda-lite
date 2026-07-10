import { render } from 'solid-js/web'
import App from './App.jsx'
import './styles/index.css'

// Montar la aplicación SolidJS en el div#root del index.html
render(() => <App />, document.getElementById('root'))
