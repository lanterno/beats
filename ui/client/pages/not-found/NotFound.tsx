/**
 * Not Found Page
 * 404 error page.
 */
import { useLocation, Link } from "react-router-dom";
import { useEffect } from "react";

export default function NotFound() {
  const location = useLocation();

  useEffect(() => {
    console.error("404 Error: User attempted to access non-existent route:", location.pathname);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="text-center px-6">
        <p className="font-heading text-6xl font-light text-muted-foreground/50 tracking-tight">
          404
        </p>
        <p className="mt-4 text-muted-foreground/90 text-base">This page does not exist.</p>
        <Link
          to="/"
          className="mt-8 inline-block text-foreground/90 text-base hover:text-accent transition-colors duration-150 underline underline-offset-4"
        >
          Return home
        </Link>
      </div>
    </div>
  );
}
