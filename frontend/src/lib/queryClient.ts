import { QueryClient } from "@tanstack/react-query";

// shared singleton so non-React code (e.g. the auth store) can invalidate queries
export const queryClient = new QueryClient();
