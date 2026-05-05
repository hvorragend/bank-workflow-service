import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { AuthProvider } from "@/auth/AuthContext";
import { ToasterProvider } from "@/components/Toaster";
import { router } from "@/router";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Konservativ — Antragsdaten sind nicht hochfrequent, aber wir wollen
      // beim Wechsel zwischen Tabs konsistente Sicht haben.
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ToasterProvider>
          <RouterProvider router={router} />
        </ToasterProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
