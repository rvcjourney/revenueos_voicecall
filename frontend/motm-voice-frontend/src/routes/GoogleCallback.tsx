import { useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { PageLoader } from "@/components/shared/PageLoader";
import { GOOGLE_NONCE_KEY } from "@/components/auth/GoogleButton";
import { useAuth } from "@/lib/auth";
import { apiErrorMessage, authApi } from "@/lib/api";

/** Google redirects here with ?code&state; existing users land on the dashboard,
 *  new ones on /signup to add their company (or invite code). */
export default function GoogleCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // StrictMode runs effects twice; a code can only be used once
    started.current = true;
    const code = params.get("code");
    const state = params.get("state");
    const nonce = sessionStorage.getItem(GOOGLE_NONCE_KEY) ?? "";
    sessionStorage.removeItem(GOOGLE_NONCE_KEY);
    if (!code || !state) {
      toast.error("Google sign-in was cancelled");
      navigate("/login", { replace: true });
      return;
    }
    authApi
      .googleSignIn(code, state, nonce)
      .then(({ data }) => {
        if (data.status === "ok") {
          const user = setSession(data);
          toast.success(`Welcome back, ${user.full_name.split(" ")[0]}`);
          navigate("/dashboard", { replace: true });
        } else {
          navigate("/signup", { replace: true, state: { google: data } });
        }
      })
      .catch((err) => {
        toast.error(apiErrorMessage(err, "Google sign-in failed"));
        navigate("/login", { replace: true });
      });
  }, [params, navigate, setSession]);

  return <PageLoader />;
}
