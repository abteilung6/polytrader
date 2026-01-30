import { RouterProvider } from '@tanstack/react-router'
import { router } from './route-tree'

export default function App() {
  return <RouterProvider router={router} />
}
