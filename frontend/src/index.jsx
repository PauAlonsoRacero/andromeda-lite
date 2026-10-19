import { render } from 'solid-js/web'
import App from './App.jsx'
// Tipografías empaquetadas en la app. Antes venían de Google Fonts: cada
// arranque enviaba la IP del usuario a Google y, sin conexión, no cargaban.
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/playfair-display/500.css'
import '@fontsource/playfair-display/600.css'
import '@fontsource/playfair-display/700.css'
import '@fontsource/inter-tight/400.css'
import '@fontsource/inter-tight/500.css'
import '@fontsource/inter-tight/600.css'
import '@fontsource/inter-tight/700.css'
import '@fontsource/inter-tight/800.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import './styles/index.css'

// Andromeda no usa Service Workers. Si una versión antigua registró alguno en
// este origen, sigue sirviendo su interfaz desde la caché del navegador: se
// eliminan al arrancar.
try {
  navigator.serviceWorker?.getRegistrations?.().then(rs => rs.forEach(r => r.unregister()))
  window.caches?.keys?.().then(ks => ks.forEach(k => caches.delete(k)))
} catch { /* navegadores sin soporte */ }

// Montar la aplicación SolidJS en el div#root del index.html
render(() => <App />, document.getElementById('root'))
