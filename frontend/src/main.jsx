import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.jsx'

// El proyecto no tenía TanStack Query: lo introduce el Módulo 2 en la Fase 4.
// Se monta en la raíz para que cualquier módulo futuro pueda usarlo sin duplicar el provider.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Los datos de una sesión ya procesada no cambian solos; revalidar al volver a la
      // pestaña solo gastaría peticiones. El refresco explícito lo dispara la detección.
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 60 * 1000,
    },
  },
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
