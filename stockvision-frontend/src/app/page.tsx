import { redirect } from "next/navigation";

/**
 * Root route.
 *
 * There is no landing page and no login: the application opens directly on the
 * dashboard. This is a server-side redirect rather than the v1 approach (a client
 * component that waited for auth-store hydration and then pushed), which meant
 * every visitor saw a blank white frame first.
 */
export default function RootPage() {
  redirect("/dashboard");
}
